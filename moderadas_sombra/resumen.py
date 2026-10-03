"""Resúmenes de moderadas-sombra-v1. Puro: el mismo código hace la referencia
histórica y el informe diario, para que las dos se midan con la misma vara.

Cada registro es un dict con: id, symbol, ts, tier, telegram, R, stop, alerta (campos
de la señal), feat (patrones previos o None), eval (core.evaluar) y ctrl (core.evaluar
del control, o None).
"""
import random
from collections import defaultdict

from . import core as K

MOVIMIENTO_MIN = 12 * 60          # 12 h de silencio = movimiento nuevo (regla del proyecto)
MODOS = ("TODAS", "PRIMERA_DEL_MOVIMIENTO", "UNA_POR_VENTANA")
CODIGOS = {"TP": "TP", "SL": "SL", "TI": "TIEMPO", "NE": "SIN_ENTRADA", "PR": "PLAN_ROTO", "AB": "ABIERTO"}


def marcar_repeticiones(registros):
    """Añade r['primera'] y r['una_por'][W] según las dos reglas de repetición."""
    por = defaultdict(list)
    for r in registros:
        por[(r["symbol"], r["tier"])].append(r)
    for lista in por.values():
        lista.sort(key=lambda r: (r["ts"], r["id"]))
        previo = None
        ultimo = {W: None for W in K.VENTANAS}
        for r in lista:
            r["primera"] = previo is None or r["ts"] - previo >= MOVIMIENTO_MIN * K.MIN
            previo = r["ts"]
            r["una_por"] = {}
            for W in K.VENTANAS:
                ok = ultimo[W] is None or r["ts"] - ultimo[W] >= W * K.MIN
                r["una_por"][W] = ok
                if ok:
                    ultimo[W] = r["ts"]
    return registros


def elegir(registros, tier, modo, W):
    """Registros del nivel, con la ventana W completa, según la regla de conteo."""
    clave = str(W)
    out = []
    for r in registros:
        if r["tier"] != tier or not r.get("eval") or not r["eval"]["ventanas"].get(clave):
            continue
        if modo == "PRIMERA_DEL_MOVIMIENTO" and not r["primera"]:
            continue
        if modo == "UNA_POR_VENTANA" and not r["una_por"][W]:
            continue
        out.append(r)
    return out


def cuantil(xs, q):
    if not xs:
        return None
    v = sorted(xs)
    pos = (len(v) - 1) * q
    a = int(pos)
    b = min(a + 1, len(v) - 1)
    return round(v[a] + (v[b] - v[a]) * (pos - a), 4)


def describir(xs):
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "media": round(sum(xs) / len(xs), 4), "mediana": cuantil(xs, 0.5),
            "p10": cuantil(xs, 0.1), "p90": cuantil(xs, 0.9), "minimo": round(min(xs), 4),
            "maximo": round(max(xs), 4)}


def _tasa(k, n):
    return round(100 * k / n, 2) if n else None


def escalera(evs):
    """% que toca cada nivel y minutos medianos hasta tocarlo."""
    out = {}
    for i, x in enumerate(K.ESCALERA):
        mins = [e["esc"][i] for e in evs if e["esc"][i] is not None]
        out[f"{x:g}"] = {"pct": _tasa(len(mins), len(evs)), "minutos_mediana": cuantil(mins, 0.5)}
    return out


def recorrido(rs, W):
    """Lo que hizo el precio desde R en la ventana: lo que pidió Felix."""
    clave = str(W)
    evs = [r["eval"]["ventanas"][clave] for r in rs]
    n = len(evs)
    i_meta = K.ESCALERA.index(2.67)
    llegan = [e for e in evs if e["esc"][i_meta] is not None]
    cortas = [e for e in evs if e["esc"][i_meta] is None]
    grupos = defaultdict(int)
    for e in evs:
        grupos[e["grupo"]] += 1
    ret = [e["retoques"] for e in evs]
    out = {
        "n": n,
        "maximo_pct": describir([e["max"] for e in evs]),
        "minimo_pct": describir([e["min"] for e in evs]),
        "cierre_pct": describir([e["cierre"] for e in evs]),
        "escalera": escalera(evs),
        "llegan_2_67": {"n": len(llegan), "pct": _tasa(len(llegan), n),
                        "subida_maxima_pct": describir([e["max"] for e in llegan]),
                        "minimo_antes_de_llegar_pct": describir([e["min_antes"][1] for e in llegan])},
        "se_quedan_cortas": {"n": len(cortas), "pct": _tasa(len(cortas), n),
                             "hasta_donde_subieron_pct": describir([e["max"] for e in cortas]),
                             "minimo_pct": describir([e["min"] for e in cortas])},
        "minimo_antes_de_la_meta_pct": {f"{m:g}": describir([e["min_antes"][i] for e in evs])
                                        for i, m in enumerate(K.OBJETIVOS)},
        "retoques": {"media": round(sum(ret) / n, 3) if n else None,
                     "al_menos_uno_pct": _tasa(sum(1 for x in ret if x), n),
                     "reparto": {k: sum(1 for x in ret if (x if x < 3 else 3) == k) for k in (0, 1, 2, 3)}},
        "grupos_pct": {g: _tasa(grupos[g], n) for g in
                       ("SUBE_DIRECTO", "BAJA_Y_SUBE", "SE_QUEDA_CORTA", "LATERAL", "CAE")},
    }
    pares = [(r["eval"]["ventanas"][clave], r["ctrl"]["ventanas"][clave]) for r in rs
             if r.get("ctrl") and r["ctrl"]["ventanas"].get(clave)]
    if pares:
        out["control"] = {"n_pares": len(pares), "escalera_senal_pct": {}, "escalera_azar_pct": {}}
        for i, x in enumerate(K.ESCALERA):
            out["control"]["escalera_senal_pct"][f"{x:g}"] = _tasa(sum(a["esc"][i] is not None for a, _ in pares), len(pares))
            out["control"]["escalera_azar_pct"][f"{x:g}"] = _tasa(sum(b["esc"][i] is not None for _, b in pares), len(pares))
    return out


def operaciones(rs, W, variante):
    """Una variante en una ventana: llenado, desenlaces, neto por operación y por señal."""
    j = K.VARIANTES.index(variante)
    filas = [(r, r["eval"]["ops"][str(W)][j]) for r in rs]
    cuenta = defaultdict(int)
    netos, por_senal, mins_tp = [], [], []
    for _, (cod, mins, neto) in filas:
        cuenta[CODIGOS[cod]] += 1
        if cod in ("TP", "SL", "TI"):
            netos.append(neto)
        if cod != "AB":
            por_senal.append(neto or 0.0)
        if cod == "TP":
            mins_tp.append(mins)
    e = len(netos)
    return {"n": len(filas), "entradas": e, "llenado_pct": _tasa(e, len(por_senal)),
            "tp_pct": _tasa(cuenta["TP"], e), "sl_pct": _tasa(cuenta["SL"], e), "tiempo_pct": _tasa(cuenta["TIEMPO"], e),
            "neto_por_operacion": round(sum(netos) / e, 4) if e else None,
            "neto_por_senal": round(sum(por_senal) / len(por_senal), 4) if por_senal else None,
            "minutos_hasta_tp_mediana": cuantil(mins_tp, 0.5), "desenlaces": dict(cuenta)}


def nombre(variante):
    e, m, s = variante
    return f"entrada-{e:g}%|meta+{m:g}%|{s}"


def mitades(rs, fn):
    """La misma métrica en la primera y la segunda mitad del periodo (por fecha)."""
    rs = sorted(rs, key=lambda r: r["ts"])
    k = len(rs) // 2
    return fn(rs[:k]), fn(rs[k:])


def bootstrap_por_moneda(rs, fn, b=1000, semilla=20261002):
    """IC 95 % remuestreando monedas enteras: las señales de una moneda no son independientes."""
    por = defaultdict(list)
    for r in rs:
        por[r["symbol"]].append(r)
    claves = sorted(por)
    if len(claves) < 5:
        return None
    rng = random.Random(semilla)
    vals = []
    for _ in range(b):
        muestra = []
        for _ in claves:
            muestra.extend(por[claves[rng.randrange(len(claves))]])
        v = fn(muestra)
        if v is not None:
            vals.append(v)
    return [cuantil(vals, 0.025), cuantil(vals, 0.975)] if vals else None


def neto_por_senal(rs, W, variante):
    return operaciones(rs, W, variante)["neto_por_senal"] if rs else None


def auc(puntos, etiquetas):
    pares = sorted(zip(puntos, etiquetas))
    pos = sum(etiquetas)
    neg = len(etiquetas) - pos
    if not pos or not neg:
        return None
    rango, i = 0.0, 0
    while i < len(pares):
        j = i
        while j < len(pares) and pares[j][0] == pares[i][0]:
            j += 1
        rango += (i + j + 1) / 2 * sum(e for _, e in pares[i:j])
        i = j
    return round((rango - pos * (pos + 1) / 2) / (pos * neg), 4)


CAMPOS_NUMERICOS = ("ret5", "ret15", "ret60", "rango60", "pos60", "vol5_vs_55")
CAMPOS_SENAL = ("score", "senal_n", "tp_pct", "sl_pct")


def patrones(rs, W, meta=2.67):
    """Exploratorio: qué rasgos previos acompañan a llegar a la meta en la ventana."""
    clave, i = str(W), K.ESCALERA.index(meta)
    ok = [r for r in rs if r.get("feat")]
    if not ok:
        return {}
    y = [int(r["eval"]["ventanas"][clave]["esc"][i] is not None) for r in ok]
    base = _tasa(sum(y), len(y))
    out = {"n": len(ok), "tasa_base_pct": base, "velas_15m": {}, "numericos": {}, "senal": {}, "categoricos": {}}
    conteo = defaultdict(lambda: [0, 0])
    for r, yy in zip(ok, y):
        for p in r["feat"]["patrones"]:
            conteo[p][0] += 1
            conteo[p][1] += yy
    for p, (n, k) in sorted(conteo.items()):
        out["velas_15m"][p] = {"n": n, "tasa_pct": _tasa(k, n), "diferencia_pp": round(_tasa(k, n) - base, 2)}

    def cuantiles(valores):
        pares = [(v, yy) for v, yy in zip(valores, y) if v is not None]
        if len(pares) < 50:
            return None
        # Solo por valor: ordenar el par entero pondría, entre empates, los que llegan al
        # final y fabricaría un quintil "bueno" en variables discretas como el score.
        pares.sort(key=lambda p: p[0])
        q = len(pares) // 5
        tramos = []
        for k in range(5):
            tramo = pares[k * q:(k + 1) * q if k < 4 else len(pares)]
            tramos.append({"desde": round(tramo[0][0], 4), "hasta": round(tramo[-1][0], 4), "n": len(tramo),
                           "tasa_pct": _tasa(sum(t[1] for t in tramo), len(tramo))})
        return {"auc": auc([p[0] for p in pares], [p[1] for p in pares]), "quintiles": tramos}

    for campo in CAMPOS_NUMERICOS:
        out["numericos"][campo] = cuantiles([r["feat"].get(campo) for r in ok])
    for campo in CAMPOS_SENAL:
        out["senal"][campo] = cuantiles([r["alerta"].get(campo) for r in ok])
    for campo in ("display_state", "telegram", "hora_utc"):
        conteo = defaultdict(lambda: [0, 0])
        for r, yy in zip(ok, y):
            v = (r["ts"] // 3_600_000) % 24 if campo == "hora_utc" else r["alerta"].get(campo)
            conteo[v][0] += 1
            conteo[v][1] += yy
        out["categoricos"][campo] = {str(v): {"n": n, "tasa_pct": _tasa(k, n)}
                                     for v, (n, k) in sorted(conteo.items(), key=lambda kv: str(kv[0])) if n >= 30}
    return out


# --- La referencia historica y la variante principal (REGLAS.md) ---------------------------

MIN_ENTRADAS = 100


def referencia(regs, sha):
    marcar_repeticiones(regs)
    completos = [r for r in regs if r.get("estado") == "COMPLETO"]
    ref = {"version": K.VERSION, "config_hash": K.CONFIG_HASH, "fuente_sha256": sha,
           "periodo": {"desde_ms": min(r["ts"] for r in completos), "hasta_ms": max(r["ts"] for r in completos)},
           "senales": {t: {"total": sum(r["tier"] == t for r in regs),
                           "completas": sum(r["tier"] == t for r in completos),
                           "con_huecos": sum(r["tier"] == t and r.get("estado") == "HUECOS" for r in regs)}
                       for t in K.NIVELES},
           "apertura_vs_R_pct": describir([r["o0_pct"] for r in completos if r.get("o0_pct") is not None]),
           "niveles": {}, "patrones": {}}
    for tier in K.NIVELES:
        ref["niveles"][tier] = {}
        for modo in MODOS:
            ref["niveles"][tier][modo] = {}
            for W in K.VENTANAS:
                rs = elegir(completos, tier, modo, W)
                ops = {}
                for v in K.VARIANTES:
                    o = operaciones(rs, W, v)
                    o["neto_por_senal_mitades"] = list(mitades(rs, lambda m, v=v: neto_por_senal(m, W, v)))
                    ops[nombre(v)] = o
                ref["niveles"][tier][modo][str(W)] = {"recorrido": recorrido(rs, W), "operaciones": ops}
        ref["patrones"][tier] = {}
        for modo in ("PRIMERA_DEL_MOVIMIENTO", "TODAS"):
            ref["patrones"][tier][modo] = {}
            for W in (180, 720):
                rs = sorted(elegir(completos, tier, modo, W), key=lambda r: r["ts"])
                k = len(rs) // 2
                ref["patrones"][tier][modo][str(W)] = {"todo": patrones(rs, W), "primera_mitad": patrones(rs[:k], W),
                                                      "segunda_mitad": patrones(rs[k:], W)}
    return ref, completos


def elegir_principal(ref, completos):
    """REGLAS.md: mayor neto por señal en MODERADA, PRIMERA_DEL_MOVIMIENTO, >= 100 entradas y
    positiva en las dos mitades. Si ninguna cumple, se registra igual la mejor, marcada."""
    candidatas = []
    for W in K.VENTANAS:
        for v in K.VARIANTES:
            o = ref["niveles"]["MODERADA"]["PRIMERA_DEL_MOVIMIENTO"][str(W)]["operaciones"][nombre(v)]
            if o["entradas"] < MIN_ENTRADAS or o["neto_por_senal"] is None:
                continue
            m1, m2 = o["neto_por_senal_mitades"]
            candidatas.append({"ventana_min": W, "variante": list(v), "nombre": nombre(v),
                               "neto_por_senal": o["neto_por_senal"], "mitades": [m1, m2],
                               "positiva_en_ambas": bool(m1 and m2 and m1 > 0 and m2 > 0), "resumen": o})
    candidatas.sort(key=lambda c: -c["neto_por_senal"])
    validas = [c for c in candidatas if c["positiva_en_ambas"]]
    elegida = (validas or candidatas)[0]
    elegida = dict(elegida, cumple_reglas=bool(validas))
    rs = elegir(completos, "MODERADA", "PRIMERA_DEL_MOVIMIENTO", elegida["ventana_min"])
    elegida["ic95_por_moneda"] = bootstrap_por_moneda(
        rs, lambda m: neto_por_senal(m, elegida["ventana_min"], tuple(elegida["variante"])))
    top = []
    for c in candidatas[:8]:
        rs = elegir(completos, "MODERADA", "PRIMERA_DEL_MOVIMIENTO", c["ventana_min"])
        ic = bootstrap_por_moneda(rs, lambda m, c=c: neto_por_senal(m, c["ventana_min"], tuple(c["variante"])))
        top.append({k: c[k] for k in ("ventana_min", "nombre", "neto_por_senal", "mitades", "positiva_en_ambas")}
                   | {"ic95_por_moneda": ic, "entradas": c["resumen"]["entradas"], "tp_pct": c["resumen"]["tp_pct"],
                      "llenado_pct": c["resumen"]["llenado_pct"]})
    return elegida, top
