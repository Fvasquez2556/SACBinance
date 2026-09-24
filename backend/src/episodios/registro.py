"""
A que movimiento pertenece cada aviso, y que plan concreto se propuso.

Fase 1 del plan de evolucion (`audit/2026-09-22/plan-evolucion-motores/`). No
decide nada: se ejecuta despues de que la alerta ya esta emitida y registrada,
y su unico efecto es dejar dos identidades persistentes donde antes no habia
ninguna.

Por que hace falta
------------------
Hoy la unica identidad de un aviso es `signals.id`, y `abrir_senal()` se niega
a abrir una segunda señal OPEN del mismo par: 137 de 258 avisos enviados a
Telegram no tienen fila en `signals`. Sus niveles concretos no tienen nada que
los evalue. Aqui todo aviso con niveles coherentes obtiene `plan_id`, exista o
no `signal_id`.

La regla del episodio, congelada el 21-sep-2026
-----------------------------------------------
Un episodio de compra se cierra por LO PRIMERO que ocurra:

1. `DESENLACE`   — el plan vigente toco su objetivo o su stop (lo anota quien
                   evalue el recorrido; aqui solo se registra el cierre).
2. `ANCLA`       — el nuevo candidato se apoya en otro nivel estructural.
3. `SILENCIO`    — 12 h sin candidato nuevo del mismo simbolo y direccion.
4. `CADUCIDAD`   — 12 h desde la apertura sin resolucion.

Las 12 h no son un numero redondo elegido a ojo: es el horizonte que ya usa el
sistema (`signal_expiry_hours`), el reloj del plan notificado, y el punto donde
el 82 % de las repeticiones de Telegram todavia no ha llegado — la mediana
entre dos avisos del mismo par es de 21 h. Con 4 o 6 h se partirian en dos
episodios que hoy son uno solo sin ganar nada; con 24 h se fundirian
movimientos distintos: por encima de ese hueco la segunda entrada ya difiere un
7,7 % de la primera.

La tolerancia del ancla (2,5 % por defecto) sale de la misma medicion: entre
avisos consecutivos separados por menos de 12 h, el stop se mueve 0,20 % de
mediana y el 90 % se queda por debajo del 2,62 %; pasadas 24 h la mediana ya es
del 4,01 %. Es decir, dentro del episodio el nivel estructural apenas respira.

Lo que este modulo NO hace
--------------------------
No evalua recorridos, no decide emision, no reordena candidatos y no toca
`signals`, `alertas_emitidas` (mas alla de anotar los dos identificadores) ni
la politica de Telegram. El evaluador comun y el diario de operaciones son las
fases 2 y 3.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

# Version de la regla de asociacion. Va en cada fila: si la regla cambia, las
# filas viejas siguen diciendo con cual se agruparon.
REGLA_EPISODIO = "episodio-v1"

# Motores. Hoy solo existe el de continuacion alcista; el de caida y
# recuperacion en spot es la fase 4 y se registra con su propio nombre.
MOTOR_CONTINUACION = "CONTINUACION"

EPISODIOS_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodios (
    episode_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    direccion        TEXT    NOT NULL DEFAULT 'ALCISTA',
    motor            TEXT    NOT NULL,
    ancla_tf         TEXT,
    ancla_tipo       TEXT,
    ancla_precio     REAL,
    ts_apertura      INTEGER NOT NULL,
    ts_ultimo_plan   INTEGER NOT NULL,
    ts_cierre        INTEGER,
    motivo_cierre    TEXT,
    fase             TEXT    NOT NULL DEFAULT 'ABIERTO',
    n_planes         INTEGER NOT NULL DEFAULT 0,
    primer_plan_id   INTEGER,
    ultimo_plan_id   INTEGER,
    episodio_padre   INTEGER,
    regla_version    TEXT    NOT NULL,
    strategy_version TEXT,
    config_hash      TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodios_abiertos
    ON episodios (symbol, direccion, fase, ts_ultimo_plan DESC);
CREATE INDEX IF NOT EXISTS idx_episodios_reloj ON episodios (fase, ts_ultimo_plan);

CREATE TABLE IF NOT EXISTS planes (
    plan_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id       INTEGER NOT NULL,
    plan_padre       INTEGER,
    revision         INTEGER NOT NULL DEFAULT 1,
    ordinal_episodio INTEGER NOT NULL,
    symbol           TEXT    NOT NULL,
    direccion        TEXT    NOT NULL DEFAULT 'ALCISTA',
    motor            TEXT    NOT NULL,
    ts_creado        INTEGER NOT NULL,
    entry            REAL    NOT NULL,
    take_profit      REAL    NOT NULL,
    stop_loss        REAL    NOT NULL,
    tp_pct           REAL,
    sl_pct           REAL,
    reward_neto_pct  REAL,
    r_multiplo       REAL,
    objetivo_tipo    TEXT    NOT NULL DEFAULT 'TP_VARIABLE',
    coste_pct        REAL,
    horizonte_ms     INTEGER NOT NULL,
    trigger_tf       TEXT,
    escenario        TEXT,
    tier             TEXT,
    score            INTEGER,
    snapshot         TEXT    NOT NULL DEFAULT '{}',
    desenlace        TEXT,
    ts_desenlace     INTEGER,
    legacy_alerta_id INTEGER UNIQUE,
    legacy_signal_id INTEGER,
    regla_version    TEXT    NOT NULL,
    strategy_version TEXT,
    config_hash      TEXT
);
CREATE INDEX IF NOT EXISTS idx_planes_episodio ON planes (episode_id, ts_creado);
CREATE INDEX IF NOT EXISTS idx_planes_symbol ON planes (symbol, ts_creado DESC);
CREATE INDEX IF NOT EXISTS idx_planes_signal ON planes (legacy_signal_id);
"""

# Lo que se guarda del contexto: escalares y textos. Fuera quedan listas y
# diccionarios (velas, niveles, subestructuras), que no caben en una fila y ya
# viven en sus propias tablas.
_SNAPSHOT_FUERA = frozenset({"candles", "klines", "historial", "niveles_sr"})


def _snapshot_plano(snap: Optional[dict]) -> str:
    if not snap:
        return "{}"
    plano = {k: v for k, v in snap.items()
             if k not in _SNAPSHOT_FUERA
             and isinstance(v, (int, float, str, bool, type(None)))}
    return json.dumps(plano, ensure_ascii=False, sort_keys=True)


class RegistroEpisodios:
    """
    Agrupa avisos en episodios y guarda cada plan como version inmutable.

    Vive sobre la misma conexion que el resto de la persistencia. El estado del
    episodio esta en la tabla, no en memoria: un reinicio no puede reabrir un
    episodio cerrado ni renumerar el primer plan.
    """

    def __init__(self, conn: sqlite3.Connection, *,
                 silencio_ms: int = 12 * 3600_000,
                 caducidad_ms: int = 12 * 3600_000,
                 ancla_tolerancia_pct: float = 2.5) -> None:
        self.db = conn
        self.silencio_ms = silencio_ms
        self.caducidad_ms = caducidad_ms
        self.ancla_tolerancia_pct = ancla_tolerancia_pct

    # --- Lectura -----------------------------------------------------------

    def filas(self, sql: str, args=()) -> list[dict]:
        cur = self.db.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def vigente(self, symbol: str, direccion: str = "ALCISTA") -> Optional[dict]:
        filas = self.filas(
            """SELECT * FROM episodios
               WHERE symbol = ? AND direccion = ? AND fase = 'ABIERTO'
               ORDER BY ts_apertura DESC LIMIT 1""", (symbol, direccion))
        return filas[0] if filas else None

    def plan(self, plan_id: int) -> Optional[dict]:
        filas = self.filas("SELECT * FROM planes WHERE plan_id = ?", (plan_id,))
        return filas[0] if filas else None

    def planes_de(self, episode_id: int) -> list[dict]:
        return self.filas(
            "SELECT * FROM planes WHERE episode_id = ? ORDER BY ordinal_episodio",
            (episode_id,))

    # --- Cierre ------------------------------------------------------------

    def cerrar(self, episode_id: int, ts_ms: int, motivo: str) -> None:
        """Cierra un episodio abierto. Cerrar dos veces no cambia el primero."""
        self.db.execute(
            """UPDATE episodios SET fase = 'CERRADO', ts_cierre = ?, motivo_cierre = ?
               WHERE episode_id = ? AND fase = 'ABIERTO'""",
            (ts_ms, motivo, episode_id))

    def cerrar_por_desenlace(self, plan_id: int, ts_ms: int,
                             desenlace: str) -> None:
        """
        El plan toco su objetivo o su stop: el episodio termina ahi.

        Un plan posterior sobre el mismo simbolo abre episodio nuevo, enlazado
        al anterior. Que el precio suba un 8 % despues del stop no convierte
        aquella parada en una victoria: son dos tesis distintas.
        """
        fila = self.plan(plan_id)
        if fila is None or fila["desenlace"]:
            return
        self.db.execute(
            "UPDATE planes SET desenlace = ?, ts_desenlace = ? WHERE plan_id = ?",
            (desenlace, ts_ms, plan_id))
        self.cerrar(fila["episode_id"], ts_ms, f"DESENLACE:{desenlace}")

    def barrer(self, ts_ms: int) -> int:
        """
        Cierra por reloj los episodios que nadie volvio a tocar.

        Sin esto, un episodio sin candidatos nuevos se quedaria abierto para
        siempre y el proximo aviso del par —dias despues— entraria como si
        fuera el mismo movimiento.
        """
        n = 0
        for e in self.filas("SELECT * FROM episodios WHERE fase = 'ABIERTO'"):
            motivo = self._motivo_reloj(e, ts_ms)
            if motivo:
                self.cerrar(e["episode_id"], ts_ms, motivo)
                n += 1
        if n:
            # El alta cuelga del commit diferido de la persistencia, pero el
            # barrido puede ser lo unico que pase en horas: si no se confirma
            # aqui, un corte lo pierde.
            self.db.commit()
        return n

    def _motivo_reloj(self, episodio: dict, ts_ms: int) -> str:
        if ts_ms - episodio["ts_ultimo_plan"] >= self.silencio_ms:
            return "SILENCIO"
        if ts_ms - episodio["ts_apertura"] >= self.caducidad_ms:
            return "CADUCIDAD"
        return ""

    def _ancla_cambio(self, episodio: dict, ancla: Optional[float]) -> bool:
        previa = episodio.get("ancla_precio")
        if not previa or not ancla:
            return False
        return abs(ancla / previa - 1.0) * 100.0 > self.ancla_tolerancia_pct

    # --- Alta --------------------------------------------------------------

    def registrar(self, *, symbol: str, ts_ms: int, tl: dict,
                  snap: Optional[dict] = None,
                  alerta_id: Optional[int] = None,
                  signal_id: Optional[int] = None,
                  direccion: str = "ALCISTA",
                  motor: str = MOTOR_CONTINUACION,
                  horizonte_ms: int = 12 * 3600_000,
                  coste_pct: Optional[float] = None,
                  strategy_version: Optional[str] = None,
                  config_hash: Optional[str] = None) -> Optional[dict]:
        """
        Da identidad a un aviso ya emitido. Devuelve None si no hay plan medible.

        Es idempotente por `alerta_id`: repetir la llamada —un reintento, un
        reinicio a media vela— devuelve el plan que ya existia en vez de crear
        otro y adelantar el ordinal.
        """
        entry = tl.get("entry") or tl.get("entrada_ref")
        tp, sl = tl.get("take_profit"), tl.get("stop_loss")
        if not all(isinstance(x, (int, float)) for x in (entry, tp, sl)):
            return None
        if not 0 < sl < entry < tp:
            return None

        if alerta_id is not None:
            ya = self.filas("SELECT * FROM planes WHERE legacy_alerta_id = ?",
                            (alerta_id,))
            if ya:
                p = ya[0]
                return {"episode_id": p["episode_id"], "plan_id": p["plan_id"],
                        "ordinal": p["ordinal_episodio"], "episodio_nuevo": False,
                        "motivo_cierre": "", "repetido": True}

        ancla = float(sl)
        episodio = self.vigente(symbol, direccion)
        motivo_cierre = ""
        if episodio is not None:
            motivo_cierre = (self._motivo_reloj(episodio, ts_ms)
                             or ("ANCLA" if self._ancla_cambio(episodio, ancla) else ""))
            if motivo_cierre:
                self.cerrar(episodio["episode_id"], ts_ms, motivo_cierre)
                episodio = None

        nuevo = episodio is None
        if nuevo:
            padre = None
            previos = self.filas(
                """SELECT episode_id FROM episodios
                   WHERE symbol = ? AND direccion = ? ORDER BY episode_id DESC LIMIT 1""",
                (symbol, direccion))
            if previos:
                padre = previos[0]["episode_id"]
            cur = self.db.execute(
                """INSERT INTO episodios
                   (symbol, direccion, motor, ancla_tf, ancla_tipo, ancla_precio,
                    ts_apertura, ts_ultimo_plan, episodio_padre, regla_version,
                    strategy_version, config_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (symbol, direccion, motor, tl.get("tf"), tl.get("sl_basis"), ancla,
                 ts_ms, ts_ms, padre, REGLA_EPISODIO, strategy_version, config_hash))
            episode_id = int(cur.lastrowid)
            ordinal = 1
        else:
            episode_id = episodio["episode_id"]
            ordinal = int(episodio["n_planes"]) + 1

        risk = entry - sl
        cur = self.db.execute(
            """INSERT INTO planes
               (episode_id, ordinal_episodio, symbol, direccion, motor, ts_creado,
                entry, take_profit, stop_loss, tp_pct, sl_pct, reward_neto_pct,
                r_multiplo, coste_pct, horizonte_ms, trigger_tf, escenario, tier,
                score, snapshot, legacy_alerta_id, legacy_signal_id, regla_version,
                strategy_version, config_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (episode_id, ordinal, symbol, direccion, motor, ts_ms,
             entry, tp, sl, tl.get("reward_pct"), tl.get("risk_pct"),
             tl.get("reward_neto_pct"),
             round((tp - entry) / risk, 3) if risk > 0 else None,
             coste_pct, horizonte_ms, tl.get("tf"),
             (snap or {}).get("display_state"), (snap or {}).get("tier"),
             (snap or {}).get("score"), _snapshot_plano(snap),
             alerta_id, signal_id, REGLA_EPISODIO, strategy_version, config_hash))
        plan_id = int(cur.lastrowid)

        self.db.execute(
            """UPDATE episodios
               SET n_planes = n_planes + 1, ts_ultimo_plan = ?, ultimo_plan_id = ?,
                   primer_plan_id = COALESCE(primer_plan_id, ?)
               WHERE episode_id = ?""",
            (ts_ms, plan_id, plan_id, episode_id))

        return {"episode_id": episode_id, "plan_id": plan_id, "ordinal": ordinal,
                "episodio_nuevo": nuevo, "motivo_cierre": motivo_cierre,
                "repetido": False}

    def sincronizar_desenlaces(self, ts_ms: int) -> int:
        """
        Cierra los episodios cuyo plan ya termino, leyendo lo que otros midieron.

        En la fase 1 el evaluador comun todavia no existe, asi que el desenlace
        se toma de quien hoy lo mide: el plan notificado si el aviso llego a
        Telegram, y `signals` en el resto. Es una lectura, no una segunda
        opinion: si mañana el evaluador de la fase 2 dice otra cosa, esta linea
        desaparece en vez de competir con el.
        """
        n = 0
        mapa = {"TP": "TP", "SL": "SL"}
        for fila in self.filas(
                """SELECT p.plan_id, n.estado FROM planes p
                   JOIN notificacion_planes n ON n.alerta_id = p.legacy_alerta_id
                   WHERE p.desenlace IS NULL AND n.estado IN ('TP','SL','VENCIDO')"""):
            estado = fila["estado"]
            if estado in mapa:
                self.cerrar_por_desenlace(fila["plan_id"], ts_ms, mapa[estado])
            else:
                self._caducar(fila["plan_id"], ts_ms)
            n += 1
        for fila in self.filas(
                """SELECT p.plan_id, s.status FROM planes p
                   JOIN signals s ON s.id = p.legacy_signal_id
                   WHERE p.desenlace IS NULL AND s.status IN ('TP','SL','EXPIRED','STALE')"""):
            estado = fila["status"]
            if estado in mapa:
                self.cerrar_por_desenlace(fila["plan_id"], ts_ms, mapa[estado])
            else:
                self._caducar(fila["plan_id"], ts_ms)
            n += 1
        if n:
            self.db.commit()
        return n

    def _caducar(self, plan_id: int, ts_ms: int) -> None:
        """Vencer sin tocar nada no es un desenlace, pero cierra el episodio."""
        fila = self.plan(plan_id)
        if fila is None or fila["desenlace"]:
            return
        self.db.execute(
            "UPDATE planes SET desenlace = 'VENCIDO', ts_desenlace = ? WHERE plan_id = ?",
            (ts_ms, plan_id))
        self.cerrar(fila["episode_id"], ts_ms, "CADUCIDAD")

    # --- Resumen para el tablero y las pruebas -----------------------------

    def resumen(self) -> dict:
        ep = self.filas(
            """SELECT fase, COUNT(*) n, SUM(n_planes) planes
               FROM episodios GROUP BY fase""")
        cierres = self.filas(
            """SELECT motivo_cierre, COUNT(*) n FROM episodios
               WHERE motivo_cierre IS NOT NULL GROUP BY motivo_cierre""")
        planes = self.filas(
            """SELECT COUNT(*) n,
                      SUM(legacy_signal_id IS NULL) sin_signal,
                      SUM(ordinal_episodio = 1) primeros
               FROM planes""")
        return {"episodios": ep, "cierres": cierres,
                "planes": planes[0] if planes else {},
                "regla": REGLA_EPISODIO,
                "silencio_h": round(self.silencio_ms / 3600_000, 2),
                "ancla_tolerancia_pct": self.ancla_tolerancia_pct}
