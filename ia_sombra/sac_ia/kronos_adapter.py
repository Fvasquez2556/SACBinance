"""
Kronos en un proceso hijo: se le puede matar si tarda, y SAC ni se entera.

Decisiones que vienen del diseño y del codigo de Kronos:

- **Entrada exacta de Binance, no de la base de SAC.** SAC guarda en `klines.v`
  el volumen en USDT (`k[7]`); Kronos se entreno con volumen en moneda base
  (`k[5]`) Y con el importe en USDT (`k[7]`). Dividir por el precio para
  inventar el primero no es un dato, es una suposicion. Se piden las velas
  cerradas a la API publica (una peticion por aviso, peso 2) y, si falla,
  Kronos se abstiene en ese caso: no se mezclan dos tipos de entrada en un
  mismo brazo.
- **Cada trayectoria por separado.** `predict()` promedia las muestras; aqui se
  usa `predict_batch()` con la misma serie repetida y `sample_count=1`, que da
  N caminos independientes. Se guardan todos, con su huella.
- **Un proceso hijo con plazo.** Si una inferencia pasa de su plazo, se mata
  el proceso y se relanza al siguiente aviso. Un hilo no se puede matar; un
  proceso si, y ademas su memoria no es la del servicio.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import multiprocessing as mp
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from sac_ia import barreras, registro

PASOS_MS = {"15m": 900_000, "1h": 3_600_000}
PASO_MS = PASOS_MS[registro.KRONOS["tf"]]


# --- Velas de Binance -------------------------------------------------------------

def velas_binance(base_url: str, symbol: str, as_of_ms: int, n: int,
                  tf: str = registro.KRONOS["tf"], timeout_s: float = 10.0) -> list[dict]:
    """Las ultimas `n` velas CERRADAS antes de `as_of_ms`, con volumen base e importe."""
    paso = PASOS_MS[tf]
    q = urllib.parse.urlencode({"symbol": symbol, "interval": tf,
                                "endTime": as_of_ms - 1, "limit": min(n + 2, 1000)})
    with urllib.request.urlopen(f"{base_url}/api/v3/klines?{q}", timeout=timeout_s) as r:
        crudas = json.loads(r.read().decode("utf-8"))
    velas = [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
              "c": float(k[4]), "volumen": float(k[5]), "importe": float(k[7])}
             for k in crudas if int(k[0]) + paso <= as_of_ms]
    return velas[-n:]


def serie_util(velas: list[dict], n: int, paso_ms: int = PASO_MS) -> Optional[str]:
    """Motivo para no usar la serie, o None si sirve."""
    if len(velas) < n:
        return f"solo {len(velas)} de {n} velas"
    if any(b["t"] - a["t"] != paso_ms for a, b in zip(velas, velas[1:])):
        return "huecos en la serie"
    if not all(barreras.vela_valida(v["o"], v["h"], v["l"], v["c"]) for v in velas):
        return "velas imposibles en la serie"
    return None


# --- El trabajador ----------------------------------------------------------------

def cargar_predictor(ajustes: dict):
    """Carga Kronos desde el codigo vendorizado y los pesos fijados. Solo en el hijo."""
    import sys

    import torch

    sys.path.insert(0, ajustes["codigo"])
    from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402

    torch.set_num_threads(max(1, int(ajustes["hilos"])))
    tok = KronosTokenizer.from_pretrained(ajustes["tokenizador"],
                                          revision=ajustes["revision_tokenizador"] or None)
    modelo = Kronos.from_pretrained(ajustes["modelo"],
                                    revision=ajustes["revision_modelo"] or None)
    modelo.eval()
    return KronosPredictor(modelo, tok, device="cpu", max_context=ajustes["max_contexto"])


def trayectorias_reales(predictor, velas: list[dict], pasos: int, n: int, semilla: int,
                        temperatura: float, top_p: float) -> list[list[tuple]]:
    import numpy as np
    import pandas as pd
    import torch

    df = pd.DataFrame({"open": [v["o"] for v in velas], "high": [v["h"] for v in velas],
                       "low": [v["l"] for v in velas], "close": [v["c"] for v in velas],
                       "volume": [v["volumen"] for v in velas],
                       "amount": [v["importe"] for v in velas]})
    x_ts = pd.Series(pd.to_datetime([v["t"] for v in velas], unit="ms"))
    y_ts = pd.Series(pd.to_datetime([velas[-1]["t"] + (i + 1) * PASO_MS
                                     for i in range(pasos)], unit="ms"))
    torch.manual_seed(semilla)
    np.random.seed(semilla % (2 ** 32))
    with torch.no_grad():
        salidas = predictor.predict_batch([df] * n, [x_ts] * n, [y_ts] * n, pred_len=pasos,
                                          T=temperatura, top_p=top_p, sample_count=1,
                                          verbose=False)
    return [[(float(r.open), float(r.high), float(r.low), float(r.close))
             for r in s.itertuples()] for s in salidas]


def _bucle(conn, ajustes: dict, fabrica: Callable, simulador: Callable) -> None:
    try:
        predictor = fabrica(ajustes)
        conn.send({"listo": True})
    except Exception as exc:                           # noqa: BLE001
        conn.send({"error": f"carga: {type(exc).__name__}: {exc}"})
        return
    while True:
        try:
            peticion = conn.recv()
        except EOFError:
            return
        if peticion is None:
            return
        try:
            t0 = time.monotonic()
            salida = {}
            for caso in peticion["casos"]:
                salida[caso["caso_id"]] = simulador(
                    predictor, caso["velas"], peticion["pasos"], peticion["n"],
                    caso["semilla"], peticion["temperatura"], peticion["top_p"])
            conn.send({"trayectorias": salida,
                       "latencia_ms": int((time.monotonic() - t0) * 1000)})
        except Exception as exc:                       # noqa: BLE001
            conn.send({"error": f"{type(exc).__name__}: {exc}"})


class MotorKronos:
    """Fachada del proceso hijo. `fabrica` y `simulador` se sustituyen en las pruebas."""

    def __init__(self, ajustes: dict, fabrica: Callable = cargar_predictor,
                 simulador: Callable = trayectorias_reales, timeout_carga_s: float = 180) -> None:
        self.ajustes = ajustes
        self.fabrica, self.simulador = fabrica, simulador
        self.timeout_carga_s = timeout_carga_s
        self.proc = None
        self.conn = None

    @classmethod
    def desde_config(cls, cfg, **kw) -> "MotorKronos":
        k = registro.KRONOS
        return cls({"codigo": str(cfg.kronos_codigo), "hilos": cfg.kronos_hilos,
                    "modelo": k["modelo"], "tokenizador": k["tokenizador"],
                    "revision_modelo": k["revision_modelo"],
                    "revision_tokenizador": k["revision_tokenizador"],
                    "max_contexto": k["max_contexto"]}, **kw)

    def instalado(self) -> bool:
        return (Path(self.ajustes["codigo"]) / "model").is_dir()

    def vivo(self) -> bool:
        return self.proc is not None and self.proc.is_alive()

    def arrancar(self) -> None:
        ctx = mp.get_context("spawn")
        padre, hijo = ctx.Pipe()
        self.proc = ctx.Process(target=_bucle, args=(hijo, self.ajustes, self.fabrica,
                                                     self.simulador), daemon=True)
        self.proc.start()
        self.conn = padre
        # Se vigila al hijo mientras carga: si muere al arrancar, se sabe al
        # momento y no al agotar el plazo de carga entero.
        limite = time.monotonic() + self.timeout_carga_s
        while not padre.poll(1.0):
            if not self.proc.is_alive():
                codigo = self.proc.exitcode
                self.parar()
                raise RuntimeError(f"el proceso de Kronos murio al arrancar (codigo {codigo})")
            if time.monotonic() > limite:
                self.parar()
                raise TimeoutError("Kronos no cargo a tiempo")
        msg = padre.recv()
        if "error" in msg:
            self.parar()
            raise RuntimeError(msg["error"])

    def parar(self) -> None:
        if self.proc is not None:
            try:
                if self.conn is not None:
                    self.conn.send(None)
            except (OSError, BrokenPipeError):
                pass
            self.proc.join(timeout=2)
            if self.proc.is_alive():
                self.proc.kill()
                self.proc.join(timeout=5)
        self.proc, self.conn = None, None

    def simular(self, casos: list[dict], timeout_s: float) -> dict:
        """casos: [{caso_id, velas, semilla}] -> {caso_id: [trayectorias]}, latencia_ms."""
        if not self.vivo():
            self.arrancar()
        k = registro.KRONOS
        self.conn.send({"casos": casos, "pasos": k["pasos"], "n": k["trayectorias"],
                        "temperatura": k["temperatura"], "top_p": k["top_p"]})
        if not self.conn.poll(timeout_s):
            self.parar()                    # se mata: el siguiente aviso lo relanza
            raise TimeoutError(f"Kronos paso de {timeout_s:.0f} s")
        msg = self.conn.recv()
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg


# --- De trayectorias a resumen --------------------------------------------------------

def futuras(trayectoria: list, primera_apertura_ms: int, as_of_ms: int, pasos_futuros: int):
    """Quita la vela que empezo antes del aviso y se queda con las del horizonte."""
    inicio = 1 if primera_apertura_ms < as_of_ms else 0
    return trayectoria[inicio:inicio + pasos_futuros]


def guardar_artefacto(directorio: Path, caso_id: int, contenido: dict) -> tuple[str, str]:
    directorio.mkdir(parents=True, exist_ok=True)
    datos = json.dumps(contenido, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(datos).hexdigest()
    ruta = directorio / f"kronos_{caso_id}.json.gz"
    tmp = ruta.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(datos))
    tmp.replace(ruta)
    return str(ruta), sha
