"""Informe diario: lo que pasa con las señales nuevas, al lado de la referencia histórica.

Mismo código (resumen.py) para las dos columnas. Solo cuentan las señales registradas al
emitirse (PROSPECTIVO) y solo las ventanas ya cerradas.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from . import core as K
from . import observador as OB
from . import resumen as S

GT = timezone(timedelta(hours=-6))           # Felix lee en hora de Guatemala
MODO = "PRIMERA_DEL_MOVIMIENTO"


def _f(x, pct=True):
    if x is None:
        return "—"
    return f"{x:+.2f} %" if pct else f"{x:g}"


def _fecha(ms):
    return datetime.fromtimestamp(ms / 1000, GT).strftime("%d-%m %H:%M")


def _fila_recorrido(tier, W, ref, rs):
    a = ref["niveles"][tier][MODO][str(W)]["recorrido"]
    b = S.recorrido(rs, W) if rs else None

    def g(d, *ruta):
        for k in ruta:
            if d is None:
                return None
            d = d.get(k)
        return d
    celdas = [f"{W // 60} h", f"{a['n']} / {b['n'] if b else 0}"]
    for ruta in (("llegan_2_67", "pct"), ("escalera", "2.67", "minutos_mediana"), ("maximo_pct", "mediana"),
                 ("minimo_pct", "mediana"), ("minimo_antes_de_la_meta_pct", "2.67", "mediana"), ("retoques", "media")):
        va, vb = g(a, *ruta), g(b, *ruta)
        es_pct = ruta[-1] in ("mediana",) and ruta[0] != "escalera"
        fmt = (lambda x: _f(x)) if es_pct else (lambda x: "—" if x is None else f"{x:g}")
        celdas.append(f"{fmt(va)} → {fmt(vb)}")
    return "| " + " | ".join(celdas) + " |"


def generar(ruta_db, ruta_ref, ahora_ms=None):
    ahora_ms = ahora_ms or OB.ahora_ms()
    ref = json.loads(Path(ruta_ref).read_text(encoding="utf-8"))
    regs, meta, ciclos = OB.registros(ruta_db)
    S.marcar_repeticiones(regs)
    instal = int(meta.get("instalacion_ms", ahora_ms))
    ultimo = int(meta.get("ultimo_ciclo_ms", 0))
    L = [f"# Sombra de las moderadas · {K.VERSION}", "",
         f"Instalada el {_fecha(instal)} (hora de Guatemala) · último ciclo {_fecha(ultimo) if ultimo else '—'} · "
         f"último sin errores {_fecha(int(meta['ultimo_exito_ms'])) if meta.get('ultimo_exito_ms') else '—'}", "",
         "Cada celda dice **histórico → nuevo**. El histórico es la referencia del 11-sep al 2-oct; lo nuevo, "
         "las señales registradas al emitirse. Se cuenta la **primera de cada movimiento** (12 h sin señales de "
         "esa moneda y nivel).", ""]
    cuenta = defaultdict(int)
    for r in regs:
        cuenta[(r["tier"], r["estado"])] += 1
    L.append("Señales nuevas registradas: " + ", ".join(f"{t} {e.lower()}: {n}" for (t, e), n in sorted(cuenta.items()))
             if cuenta else "Señales nuevas registradas: todavía ninguna.")
    for tier in K.NIVELES:
        L += ["", f"## {tier}", "",
              "| ventana | señales | llegan a +2,67 % | minutos hasta +2,67 % (mediana) | máximo (mediana) | "
              "mínimo (mediana) | mínimo antes de +2,67 % | retoques (media) |",
              "|---|---|---|---|---|---|---|---|"]
        for W in K.VENTANAS:
            L.append(_fila_recorrido(tier, W, ref, S.elegir(regs, tier, MODO, W)))
        L += ["", "Grupos a 12 h y señal frente a un minuto al azar de la misma moneda (llegar a +2,67 %):", ""]
        a = ref["niveles"][tier][MODO]["720"]["recorrido"]
        rs = S.elegir(regs, tier, MODO, 720)
        b = S.recorrido(rs, 720) if rs else None
        for g in ("SUBE_DIRECTO", "BAJA_Y_SUBE", "SE_QUEDA_CORTA", "LATERAL", "CAE"):
            L.append(f"- {g}: {_f(a['grupos_pct'][g], False)} % → {_f(b['grupos_pct'][g], False) if b else '—'} %")
        ca = a.get("control", {})
        cb = (b or {}).get("control", {})
        L.append(f"- Señal frente a azar: {ca.get('escalera_senal_pct', {}).get('2.67', '—')} % vs "
                 f"{ca.get('escalera_azar_pct', {}).get('2.67', '—')} % en el histórico → "
                 f"{cb.get('escalera_senal_pct', {}).get('2.67', '—')} % vs {cb.get('escalera_azar_pct', {}).get('2.67', '—')} % ahora")

    p = ref["principal"]
    W, v = p["ventana_min"], tuple(p["variante"])
    rs = S.elegir(regs, "MODERADA", MODO, W)
    o = S.operaciones(rs, W, v) if rs else None
    L += ["", "## Simulación de operaciones (MODERADA)", "",
          f"**Variante principal** (elegida en el histórico antes de ver datos nuevos): {p['nombre']}, ventana "
          f"{W // 60} h. Neto por señal en el histórico {_f(p['neto_por_senal'])} (IC 95 % por moneda "
          f"{p['ic95_por_moneda']}); mitades {p['mitades']}." +
          ("" if p.get("cumple_reglas") else " **Ninguna variante fue positiva en las dos mitades del histórico**; "
           "se sigue la mejor como referencia, no como recomendación."),
          f"Ahora: {o['entradas'] if o else 0} entradas de {o['n'] if o else 0} señales, TP {_f(o['tp_pct'], False) if o else '—'} %, "
          f"neto por señal {_f(o['neto_por_senal']) if o else '—'}.", "",
          "¿Qué entrada conviene? Meta +2,67 %, neto por señal (las que no entran = 0), histórico → nuevo:", "",
          "| entrada | 3 h, stop fijo 1,8 % | 3 h, stop del sistema | 12 h, stop fijo 1,8 % | 12 h, stop del sistema |",
          "|---|---|---|---|---|"]
    for e in K.ENTRADAS:
        celdas = [f"R − {e:g} %" if e else "R"]
        for Wx in (180, 720):
            for st in ("FIJO_1.8", "SISTEMA"):
                v2 = (e, 2.67, st)
                a = ref["niveles"]["MODERADA"][MODO][str(Wx)]["operaciones"][S.nombre(v2)]
                rs2 = S.elegir(regs, "MODERADA", MODO, Wx)
                b = S.operaciones(rs2, Wx, v2) if rs2 else None
                celdas.append(f"{_f(a['neto_por_senal'])} → {_f(b['neto_por_senal']) if b else '—'}")
        L.append("| " + " | ".join(celdas) + " |")

    dias = defaultdict(list)
    for r in S.elegir(regs, "MODERADA", MODO, W):
        dias[datetime.fromtimestamp(r["ts"] / 1000, GT).strftime("%d-%m")].append(r)
    if dias:
        L += ["", "Día a día (hora de Guatemala), variante principal:", ""]
        for d in sorted(dias, key=lambda d: (d[3:], d[:2])):
            od = S.operaciones(dias[d], W, v)
            L.append(f"- {d}: {od['n']} señales, {od['entradas']} entradas, neto por señal {_f(od['neto_por_senal'])}")
    L += ["", "Notas: medición en sombra, no es consejo de inversión. TP y SL en la misma vela cuentan como SL. "
          "Coste supuesto 0,5 puntos. Un patrón o una variante que gana en el histórico solo vale si repite aquí."]
    return "\n".join(L)
