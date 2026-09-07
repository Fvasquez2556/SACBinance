# -*- coding: utf-8 -*-
"""
Avisar por Telegram cuando el mercado se ponga BAJISTA.

Por que existe
--------------
Todo lo que el sistema ha medido sale de dias alcistas y planos. El examen que
falta —el unico que dice si hay filo de verdad o solo hubo marea— es un dia
rojo. Y ese dia puede caer un miercoles cualquiera sin que nadie abra el
informe.

Esto lo vigila: calcula el regimen de las ultimas horas y, cuando pasa a
BAJISTA, manda un aviso con el veredicto contra las dos referencias.

Solo avisa en el CAMBIO de regimen, no en cada corrida. El estado anterior se
guarda en un fichero: sin eso, con la corrida horaria mandaria el mismo aviso
24 veces al dia y dejaria de leerse.

Uso
---
    ./venv/bin/python ../deploy/aviso_regimen.py            # 6h hacia atras
    ./venv/bin/python ../deploy/aviso_regimen.py --horas 24
    ./venv/bin/python ../deploy/aviso_regimen.py --forzar   # avisa igual
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "informes" / ".regimen"
UMBRAL = 0.5        # % de mediana para llamarlo alcista o bajista


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


def regimen(horas: float) -> tuple:
    """(nombre, mediana, % de pares que suben, n_pares) en las ultimas horas."""
    con = sqlite3.connect(str(RAIZ / "backend" / "data" / "sacbinance.db"))
    desde = int(time.time() * 1000) - int(horas * 3600_000)
    d = defaultdict(list)
    for s, t, c in con.execute(
            "SELECT symbol, open_time, c FROM klines WHERE tf='1m' "
            "AND open_time >= ? ORDER BY symbol, open_time", (desde,)):
        d[s].append(c)
    subs = [(v[-1] / v[0] - 1) * 100.0
            for v in d.values() if len(v) > 60 and v[0] > 0]
    if len(subs) < 20:
        return "SIN_DATOS", 0.0, 0.0, len(subs)
    a = np.array(subs)
    med = float(np.median(a))
    nombre = ("ALCISTA" if med > UMBRAL
              else "BAJISTA" if med < -UMBRAL else "PLANO")
    return nombre, med, float((a > 0).mean() * 100), len(a)


def enviar(token: str, chat: str, texto: str) -> bool:
    datos = json.dumps({"chat_id": chat, "text": texto,
                        "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=datos, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")).get("ok", False)
    except Exception as e:
        print(f"No se pudo enviar: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=6.0)
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    nombre, med, pct_suben, n = regimen(args.horas)
    print(f"regimen ultimas {args.horas:g}h: {nombre} "
          f"(mediana {med:+.2f}%, suben {pct_suben:.0f}% de {n} pares)")

    if nombre == "SIN_DATOS":
        return 1

    previo = ESTADO.read_text().strip() if ESTADO.exists() else ""
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(nombre)

    if nombre != "BAJISTA":
        print(f"(sin aviso: solo se avisa al pasar a BAJISTA; antes: {previo or '—'})")
        return 0
    if previo == "BAJISTA" and not args.forzar:
        print("(sin aviso: ya estaba en BAJISTA, solo se avisa en el cambio)")
        return 0

    env = leer_env(RAIZ / "backend" / ".env")
    token = (env.get("TELEGRAM_TOKEN") or "").strip()
    chat = (env.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("Telegram no configurado: no se envia")
        return 1

    texto = "\n".join([
        "🔻 <b>MERCADO BAJISTA</b>",
        "",
        f"Últimas {args.horas:g}h: mediana <b>{med:+.2f}%</b>, "
        f"suben {pct_suben:.0f}% de {n} pares.",
        "",
        "Es el examen que faltaba. Todo lo que el sistema midió hasta ahora",
        "salía de días alcistas y planos — este es el primer dato que dice",
        "si hay filo de verdad o solo hubo marea.",
        "",
        "El informe de hoy trae el veredicto contra las dos referencias",
        "(azar y comprar-y-aguantar) en su sección 0.",
    ])
    if enviar(token, chat, texto):
        print("Aviso de régimen bajista enviado.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
