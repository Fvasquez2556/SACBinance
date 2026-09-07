# -*- coding: utf-8 -*-
"""
Por que no ha sonado el telefono.

El silencio de una notificacion es ambiguo: puede que no se haya generado
ninguna alerta, que se generaran y el filtro las descartara, o que algo este
roto. Sin poder distinguirlos, la unica reaccion posible es desconfiar del
sistema entero.

Este script coge las senales de las ultimas N horas y dice, una por una, que
filtro las dejo fuera. Reconstruye el patron con las velas 1m del instante en
que se emitio cada una, igual que lo hizo el engine.

Uso
---
    cd ~/sacbinance/backend
    ./venv/bin/python ../deploy/por_que_no_aviso.py        # ultima hora
    ./venv/bin/python ../deploy/por_que_no_aviso.py 6      # ultimas 6 horas
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

TZ = -6
ZONA = 8            # velas 1m donde se busca el suelo
LOOKBACK = 40       # velas previas donde se busca el pico


def leer_env(ruta: Path) -> dict:
    datos = {}
    if not ruta.exists():
        return datos
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        datos[k.strip().upper()] = v.strip().strip('"').strip("'")
    return datos


def gt(ts: int) -> str:
    return (dt.datetime.utcfromtimestamp(ts / 1000)
            + dt.timedelta(hours=TZ)).strftime("%H:%M")


def main() -> int:
    horas = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    raiz = Path(__file__).resolve().parent.parent
    env = leer_env(raiz / "backend" / ".env")

    activo = (env.get("TELEGRAM_ENABLED", "false").lower() == "true"
              and env.get("TELEGRAM_TOKEN") and env.get("TELEGRAM_CHAT_ID"))
    solo_conf = env.get("AVISO_SOLO_CONFIRMADO", "true").lower() == "true"
    score_min = int(env.get("AVISO_SCORE_MIN", 75))
    vol_min = float(env.get("AVISO_VOL24H_MIN", 2_000_000))

    print(f"Telegram: {'ACTIVO' if activo else 'APAGADO'}")
    print(f"Criterio: {'rebote confirmado' if solo_conf else 'solo caida previa'}"
          f" + score >= {score_min} + vol24h >= {vol_min/1e6:.0f}M\n")

    con = sqlite3.connect(str(raiz / "backend" / "data" / "sacbinance.db"))
    con.row_factory = sqlite3.Row
    desde = int(time.time() * 1000) - int(horas * 3600_000)

    kl = defaultdict(list)
    for s, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "AND open_time >= ? ORDER BY symbol, open_time",
            (desde - 3600_000,)):
        kl[s].append((t, h, l, c))
    kl = {s: np.array(v, dtype=float) for s, v in kl.items()}

    filas = list(con.execute(
        "SELECT s.*, m.vol_24h FROM signals s "
        "LEFT JOIN pair_metadata m ON m.symbol = s.symbol "
        "WHERE s.ts_open >= ? ORDER BY s.ts_open", (desde,)))

    print(f"Ultimas {horas:g}h: {len(filas)} senales emitidas")
    if not filas:
        print("\nNo se emitio ninguna senal. El silencio no es un fallo:")
        print("es que no hubo nada que avisar.")
        return 0

    print("=" * 92)
    print(f"{'hora':>6} {'par':>10} {'score':>5} {'vol24h':>8} {'caida':>7} "
          f"{'rebote':>7}   por que no sono")
    motivos = Counter()
    avisadas = 0
    for r in filas:
        sym = r["symbol"]
        sc = r["score"] or 0
        v = r["vol_24h"] or 0
        a = kl.get(sym)
        if a is None or len(a) < ZONA + LOOKBACK:
            motivos["sin velas suficientes"] += 1
            continue
        i = int(np.searchsorted(a[:, 0], r["ts_open"], side="right")) - 1
        if i < ZONA + LOOKBACK:
            motivos["sin velas suficientes"] += 1
            continue
        seg = a[i - ZONA + 1:i + 1]
        prev = a[i - ZONA - LOOKBACK + 1:i - ZONA + 1]
        pico, suelo = prev[:, 1].max(), seg[:, 2].min()
        if pico <= 0 or suelo <= 0:
            continue
        caida = (suelo - pico) / pico * 100.0
        rebote = (a[i, 3] - suelo) / suelo * 100.0
        det = caida <= -2.0
        conf = det and rebote >= 1.0

        if not det:
            m = "no viene de una caida"
        elif solo_conf and not conf:
            m = "cayo pero aun no rebota"
        elif sc < score_min:
            m = f"score {sc} < {score_min}"
        elif v and v < vol_min:
            m = f"volumen {v/1e6:.1f}M bajo"
        else:
            m = "SI AVISO"
            avisadas += 1
        motivos[m] += 1
        print(f"{gt(r['ts_open']):>6} {sym.replace('USDT','')[:10]:>10} {sc:>5} "
              f"{v/1e6:>7.1f}M {caida:>6.2f}% {rebote:>6.2f}%   {m}")

    print("\n" + "=" * 92)
    print("RESUMEN")
    for m, n in motivos.most_common():
        print(f"  {n:>4}  {m}")
    print(f"\n  {avisadas} de {len(filas)} habrian sonado.")
    if avisadas == 0 and motivos.get("no viene de una caida", 0) > len(filas) * 0.7:
        print("\n  Casi todas fallan el mismo filtro. El patron exige una caida")
        print("  previa del 2%, y en un mercado que sube nada viene de caer.")
        print("  El sistema no esta roto: esta callado a proposito.")
        print("\n  Para aflojarlo, en backend/.env:")
        print("      AVISO_SOLO_CONFIRMADO=false   (no exige el rebote)")
        print("      AVISO_SCORE_MIN=85            (avisa sin exigir patron")
        print("                                     solo si subes el score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
