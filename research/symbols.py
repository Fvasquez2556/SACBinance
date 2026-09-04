"""
Genera la lista de simbolos para la ingesta.

Advertencia sobre sesgo de supervivencia
----------------------------------------
`--top-n` toma los pares con mas volumen HOY. Si backtesteas 6 meses con esa
lista, estas eligiendo monedas que sobrevivieron y prosperaron: los resultados
saldran optimistas. Sirve para una primera pasada rapida, no para conclusiones.

`--all` toma todos los pares USDT que cotizan actualmente (exchangeInfo), que
sigue excluyendo los deslistados pero es bastante mas ancho.

Para eliminar el sesgo del todo hay que listar los directorios de Data Vision
mes a mes, que incluye pares ya deslistados. Es el paso correcto si las
conclusiones van a decidir dinero real.

Uso:
    python -m research.symbols --top-n 150 --min-vol 5000000 > pares.txt
    python -m research.symbols --all > pares.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.request import Request, urlopen

API = "https://api.binance.com/api/v3"
UA = {"User-Agent": "sacbinance-research/1.0"}
EXCLUIR = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")  # tokens apalancados


def _get(url: str):
    with urlopen(Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read())


def pares_activos() -> list:
    info = _get(f"{API}/exchangeInfo")
    return sorted(
        s["symbol"] for s in info["symbols"]
        if s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
        and s.get("isSpotTradingAllowed")
        and not s["symbol"].endswith(EXCLUIR)
    )


def top_por_volumen(n: int, min_vol: float) -> list:
    activos = set(pares_activos())
    tickers = _get(f"{API}/ticker/24hr")
    filas = [
        (t["symbol"], float(t.get("quoteVolume", 0)))
        for t in tickers if t["symbol"] in activos
    ]
    filas = [f for f in filas if f[1] >= min_vol]
    filas.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in filas[:n]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, help="top N por volumen 24h (sesgado)")
    ap.add_argument("--min-vol", type=float, default=1_000_000)
    ap.add_argument("--all", action="store_true", help="todos los USDT en TRADING")
    a = ap.parse_args()

    if a.all:
        syms = pares_activos()
        print("# todos los pares USDT en TRADING", file=sys.stderr)
    elif a.top_n:
        syms = top_por_volumen(a.top_n, a.min_vol)
        print(f"# top {a.top_n} por volumen 24h — OJO: sesgo de supervivencia",
              file=sys.stderr)
    else:
        ap.error("usa --all o --top-n N")

    print(f"# {len(syms)} pares", file=sys.stderr)
    for s in syms:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
