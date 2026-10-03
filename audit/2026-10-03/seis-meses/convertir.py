"""Convierte los .zip de Binance (CSV de velas de 1 m) en un .npz por moneda.

Columnas de Binance: open_time, open, high, low, close, volume, close_time, quote_volume, trades,
taker_buy_base, taker_buy_quote, ignore. Desde 2025 open_time viene en microsegundos.
Salida: data/binance_vision/npz/<SYMBOL>.npz con t (minuto UTC, int32), o, h, l, c, qv (USDT), tbq
(USDT comprados por agresores) y n (operaciones).
"""
from __future__ import annotations

import io
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
ORIGEN = AQUI.parents[2] / "data" / "binance_vision" / "spot_1m"
DESTINO = AQUI.parents[2] / "data" / "binance_vision" / "npz"


def leer_zip(ruta: Path) -> pd.DataFrame:
    with zipfile.ZipFile(ruta) as z:
        nombre = z.namelist()[0]
        crudo = z.read(nombre)
    primera = crudo.split(b"\n", 1)[0]
    cabecera = 0 if not primera[:1].isdigit() else None
    df = pd.read_csv(io.BytesIO(crudo), header=cabecera, usecols=[0, 1, 2, 3, 4, 7, 8, 10])
    df.columns = ["t", "o", "h", "l", "c", "qv", "n", "tbq"]
    t = df["t"].astype("int64")
    df["t"] = np.where(t > 10 ** 14, t // 60_000_000, t // 60_000)     # µs o ms -> minuto
    return df


def convertir(symbol: str) -> tuple[str, int, int]:
    archivos = sorted((ORIGEN / symbol).glob("*.zip"))
    if not archivos:
        return symbol, 0, 0
    df = pd.concat([leer_zip(a) for a in archivos], ignore_index=True)
    df = df.drop_duplicates("t").sort_values("t")
    DESTINO.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(DESTINO / f"{symbol}.npz", t=df["t"].to_numpy(np.int32),
                        o=df["o"].to_numpy(np.float64), h=df["h"].to_numpy(np.float64),
                        l=df["l"].to_numpy(np.float64), c=df["c"].to_numpy(np.float64),
                        qv=df["qv"].to_numpy(np.float32), tbq=df["tbq"].to_numpy(np.float32),
                        n=df["n"].to_numpy(np.int32))
    return symbol, len(df), len(archivos)


if __name__ == "__main__":
    simbolos = sys.argv[1:] or sorted(p.name for p in ORIGEN.iterdir() if p.is_dir())
    with Pool(6) as pool:
        for sym, filas, archivos in pool.imap_unordered(convertir, simbolos):
            print(f"{sym}: {archivos} archivos, {filas} velas", flush=True)
