"""
Rutas y una base de SAC de verdad para las pruebas.

La base se crea con la clase `Database` del backend, asi que tiene el esquema
real (el mismo que produccion). Si SAC cambia una tabla que la IA lee, estas
pruebas lo notan, en vez de pasar contra un esquema inventado.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

IA = Path(__file__).resolve().parent.parent
BACKEND = IA.parent / "backend"
for ruta in (str(IA), str(BACKEND)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from sac_ia import config, registro  # noqa: E402

M = 60_000
T0 = 1_789_999_200_000            # frontera exacta de 15 min (sep-2026)


class BaseSAC:
    """Una base de SAC en un fichero temporal, con su propia conexion de escritura."""

    def __init__(self) -> None:
        from src.config.settings import get_settings
        from src.persistence.db import Database

        self.dir = tempfile.TemporaryDirectory()
        self.ruta = Path(self.dir.name) / "sacbinance.db"
        ajustes = get_settings().model_copy(update={"db_path": str(self.ruta)})
        with patch("src.persistence.db.get_settings", return_value=ajustes):
            self.db = Database()
        self.conn = self.db._conn

    def cerrar(self) -> None:
        self.conn.close()
        self.dir.cleanup()

    def alerta(self, symbol="POLUSDT", ts=T0, entry=100.0, tp=110.0, sl=95.0,
               telegram="pendiente", score=80) -> int:
        cur = self.conn.execute(
            "INSERT INTO alertas_emitidas (ts_ms, symbol, entry, take_profit, stop_loss, "
            "tp_pct, sl_pct, tier, score, display_state, senal_n, telegram) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'FUERTE', ?, 'SUBIENDO', 3, ?)",
            (ts, symbol, entry, tp, sl, (tp / entry - 1) * 100, (1 - sl / entry) * 100,
             score, telegram))
        self.conn.commit()
        return cur.lastrowid

    def notificar(self, alerta_id: int, symbol="POLUSDT", activado=T0 + 30_000,
                  entry=100.0, tp=110.0, sl=95.0) -> None:
        ctx = {"macro_trends": {"1h": "ALCISTA"}, "coste_pct": 0.5, "score": 80,
               "perfil": "SUBIENDO", "plan_id": 7, "episode_id": 3, "ordinal_episodio": 1,
               "trigger_tf": "1h"}
        self.conn.execute(
            "INSERT INTO notificacion_planes (alerta_id, symbol, ts_open, ts_activado, entry, "
            "take_profit, stop_loss, contexto, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ABIERTO')",
            (alerta_id, symbol, activado - 30_000, activado, entry, tp, sl, json.dumps(ctx)))
        self.conn.commit()

    def telegram(self, alerta_id: int, estado: str) -> None:
        self.conn.execute("UPDATE alertas_emitidas SET telegram = ? WHERE id = ?",
                          (estado, alerta_id))
        self.conn.commit()

    def velas(self, symbol: str, tf: str, desde: int, filas) -> None:
        """filas: (o, h, l, c, v) consecutivas desde `desde`."""
        paso = {"1m": M, "15m": 15 * M, "1h": 60 * M, "4h": 240 * M}[tf]
        self.conn.executemany(
            "INSERT OR REPLACE INTO klines (symbol, tf, open_time, o, h, l, c, v) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(symbol, tf, desde + i * paso, *f) for i, f in enumerate(filas)])
        self.conn.commit()


def cfg(sac: BaseSAC, ia_dir: Path, **extra) -> config.Config:
    return config.cargar({"IA_SAC_DB": str(sac.ruta), "IA_DB": str(ia_dir / "ia.db"),
                          "IA_ARTEFACTOS": str(ia_dir / "art"),
                          "IA_CLAVE_OPENAI": str(ia_dir / "no-existe.key"),
                          "IA_SAC_BACKEND": str(BACKEND), **extra})


def velas_kronos_sinteticas(symbol, as_of_ms, n):
    """n velas cerradas del marco de Kronos, suaves, terminando justo antes de as_of."""
    paso = {"15m": 15 * M, "1h": 60 * M}[registro.KRONOS["tf"]]
    ultima = (as_of_ms // paso) * paso - paso
    salida = []
    for i in range(n):
        t = ultima - (n - 1 - i) * paso
        p = 100 + (i % 7) * 0.1
        salida.append({"t": t, "o": p, "h": p + 0.3, "l": p - 0.3, "c": p + 0.05,
                       "volumen": 10.0, "importe": 1000.0})
    return salida


# --- Un cliente de OpenAI de mentira -----------------------------------------------


def respuesta(texto: str = None, status="completed", entrada=1000, salida=300, rechazo=None,
              razonamiento=100, incompleta=None):
    if texto is None:
        texto = json.dumps({"accion": "ENTRAR", "p_meta": 0.62, "confianza": "MEDIA",
                            "codigos": ["TENDENCIA_A_FAVOR"], "razon": "rsi14 1h 58"})
    contenido = [SimpleNamespace(type="refusal", refusal=rechazo)] if rechazo else \
        [SimpleNamespace(type="output_text", text=texto)]
    return SimpleNamespace(
        id="resp_1", status=status, output_text="" if rechazo else texto,
        incomplete_details=SimpleNamespace(reason=incompleta) if incompleta else None,
        output=[SimpleNamespace(type="message", content=contenido)],
        usage=SimpleNamespace(input_tokens=entrada, output_tokens=salida,
                              input_tokens_details=SimpleNamespace(cached_tokens=0),
                              output_tokens_details=SimpleNamespace(reasoning_tokens=razonamiento)))


class ClienteFalso:
    def __init__(self, respuestas=None, excepcion=None):
        self.llamadas = []
        self.respuestas = list(respuestas or [])
        self.excepcion = excepcion
        self.responses = self

    def create(self, **kw):
        self.llamadas.append(kw)
        if self.excepcion:
            raise self.excepcion
        return self.respuestas.pop(0) if self.respuestas else respuesta()


class MotorFalso:
    """Kronos sin torch: trayectorias fijas que suben hasta la meta."""

    def __init__(self, instalado=True, error=None, meta=100 * (1 + registro.META_BRUTA_PCT / 100)):
        self._instalado, self.error, self.meta = instalado, error, meta
        self.peticiones = []
        self.arrancado = False

    def instalado(self):
        return self._instalado

    def vivo(self):
        return self.arrancado

    def arrancar(self):
        self.arrancado = True

    def simular(self, casos, timeout_s):
        self.peticiones.append((casos, timeout_s))
        if self.error:
            raise self.error
        k = registro.KRONOS
        sube = [(100.0, 100.5, 99.8, 100.4)] + [(100.4, self.meta + 0.1, 100.2, self.meta)] \
            + [(self.meta, self.meta + 0.1, self.meta - 0.1, self.meta)] * (k["pasos"] - 2)
        baja = [(100.0, 100.2, 99.0, 99.2)] + [(99.2, 99.3, 90.0, 91.0)] * (k["pasos"] - 1)
        tray = [sube if i % 4 else baja for i in range(k["trayectorias"])]
        return {"trayectorias": {c["caso_id"]: tray for c in casos}, "latencia_ms": 1234}

    def parar(self):
        pass
