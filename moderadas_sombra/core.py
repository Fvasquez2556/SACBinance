"""Reglas congeladas de moderadas-sombra-v1. Sin E/S.

Definición registrada en audit/2026-10-02/moderadas/REGLAS.md, escrita antes de
mirar resultados. Todo usa velas de 1 minuto cerradas y alineadas desde el primer
minuto entero tras la señal, sin huecos (el llamador lo comprueba).
"""
import hashlib
import json
import random

VERSION = "moderadas-sombra-v2"
MIN = 60_000
NIVELES = ("MODERADA", "FUERTE")
VENTANAS = (60, 180, 360, 720)                    # minutos
SPAN = max(VENTANAS)
ESCALERA = (0.5, 1.0, 1.5, 2.0, 2.5, 2.67, 3.0, 3.5, 4.0, 5.0)   # % brutos sobre R
OBJETIVOS = (2.5, 2.67, 3.0)                      # % brutos sobre el precio de compra
ENTRADAS = (0.0, 0.3, 0.5, 0.7, 1.0)              # % bajo R
STOPS = ("SISTEMA", "SIN_STOP", "FIJO_1.8")    # v2: stop fijo bajo el precio de compra
STOP_FIJO_PCT = 1.8
COSTE = 0.5
RETOQUE_ARMA = 0.5                                # % sobre R que arma un retoque
GRUPO = {"meta": 2.67, "baja": 1.0, "corta": 1.0, "cae": 2.0}
PREVIAS = 60
CONTROL_MIN = (12 * 60, 36 * 60)                  # el control empieza entre 12 h y 36 h antes
EPS = 1e-12
VARIANTES = tuple((e, m, s) for e in ENTRADAS for m in OBJETIVOS for s in STOPS)
CONFIG = {"version": VERSION, "niveles": NIVELES, "ventanas_min": VENTANAS, "escalera_pct": ESCALERA,
          "objetivos_pct": OBJETIVOS, "entradas_bajo_R_pct": ENTRADAS, "stops": STOPS, "stop_fijo_pct": STOP_FIJO_PCT,
          "coste_pct": COSTE,
          "retoque_arma_pct": RETOQUE_ARMA, "grupo": GRUPO, "previas": PREVIAS, "control_min": CONTROL_MIN,
          "misma_vela_tp_sl": "SL", "entradas": "todas limite, tambien R", "limite_tp_desde": "vela siguiente",
          "salto_bajo_stop": "apertura"}
CONFIG_HASH = hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()


# --- Búsqueda rápida del primer toque ----------------------------------------------

def sparse(values, fn):
    """Tabla dispersa: table[i][p] = fn(values[p:p + 2**i])."""
    table, half = [list(values)], 1
    while 2 * half <= len(values):
        prev = table[-1]
        table.append(list(map(fn, prev[:len(prev) - half], prev[half:])))
        half *= 2
    return table


def first_reach(table, start, end, reached):
    """Primer índice en [start, end] cuyo valor cumple reached."""
    if start is None or start > end:
        return None
    pos = start
    for i in range(len(table) - 1, -1, -1):
        span = 1 << i
        if pos + span - 1 <= end and not reached(table[i][pos]):
            pos += span
    return pos if pos <= end and reached(table[0][pos]) else None


def _pct(x, R):
    return round((x / R - 1) * 100, 4)


# --- Antes de la señal -----------------------------------------------------------------

def velas_15m(O, H, L, C, i):
    """Las cuatro velas de 15 min que forman las 60 de 1 min que terminan en i."""
    out = []
    for k in range(4):
        a, b = i - 59 + 15 * k, i - 45 + 15 * k
        out.append((O[a], max(H[a:b + 1]), min(L[a:b + 1]), C[b]))
    return out


def patrones(v15):
    """Patrones clásicos sobre la última vela de 15 min (y la anterior)."""
    o2, h2, l2, c2 = v15[-2]
    o, h, l, c = v15[-1]
    rng, cuerpo = h - l, abs(c - o)
    if rng <= 0:
        return ["SIN_RANGO"]
    arriba, abajo = h - max(o, c), min(o, c) - l
    p = []
    if abajo >= 2 * cuerpo and arriba <= max(cuerpo, 0.1 * rng):
        p.append("MARTILLO")
    if arriba >= 2 * cuerpo and abajo <= max(cuerpo, 0.1 * rng):
        p.append("ESTRELLA_FUGAZ")
    if cuerpo <= 0.1 * rng:
        p.append("DOJI")
    if c > o and cuerpo >= 0.7 * rng:
        p.append("FUERTE_ALCISTA")
    if c < o and cuerpo >= 0.7 * rng:
        p.append("FUERTE_BAJISTA")
    if c2 < o2 and c > o and o <= c2 and c >= o2:
        p.append("ENVOLVENTE_ALCISTA")
    if c2 > o2 and c < o and o >= c2 and c <= o2:
        p.append("ENVOLVENTE_BAJISTA")
    if all(x[3] > x[0] for x in v15[-3:]):
        p.append("TRES_VERDES")
    return p or ["NINGUNO"]


def features(T, O, H, L, C, V, ts, buscar):
    """Con las 60 velas cerradas antes de ts. None si faltan o no son continuas.

    buscar(t) -> índice de la vela que abre en t, o None.
    """
    last = (ts - MIN) // MIN * MIN
    i = buscar(last)
    if i is None or i < PREVIAS - 1 or T[i - PREVIAS + 1] != last - (PREVIAS - 1) * MIN:
        return None
    lo, hi = min(L[i - 59:i + 1]), max(H[i - 59:i + 1])
    if lo <= 0:
        return None
    base = sum(V[i - 59:i - 4]) / 55
    return {"ret5": round((C[i] / C[i - 5] - 1) * 100, 4),
            "ret15": round((C[i] / O[i - 14] - 1) * 100, 4),
            "ret60": round((C[i] / O[i - 59] - 1) * 100, 4),
            "rango60": round((hi / lo - 1) * 100, 4),
            "pos60": round((C[i] - lo) / (hi - lo), 4) if hi > lo else 0.5,
            "vol5_vs_55": round(sum(V[i - 4:i + 1]) / 5 / base, 4) if base > 0 else None,
            "patrones": patrones(velas_15m(O, H, L, C, i))}


# --- Después de la señal ------------------------------------------------------------------

def medir(o, h, l, c, R):
    """Máximo, mínimo, escalera, mínimo antes de la meta, retoques y grupo por ventana."""
    n = min(len(h), SPAN)
    out = {"bars": n, "ventanas": {}}
    if n == 0:
        return out
    TH, TL = sparse(h[:n], max), sparse(l[:n], min)
    esc = [first_reach(TH, 0, n - 1, lambda v, p=R * (1 + x / 100): v >= p * (1 - EPS)) for x in ESCALERA]
    caida = first_reach(TL, 0, n - 1, lambda v, p=R * (1 - GRUPO["baja"] / 100): v <= p * (1 + EPS))
    arma, toque = R * (1 + RETOQUE_ARMA / 100) * (1 - EPS), R * (1 + EPS)
    pmin, pmax, retoques = [], [], []
    lo, hi, armado, n_ret = float("inf"), float("-inf"), False, 0
    for j in range(n):
        lo, hi = min(lo, l[j]), max(hi, h[j])
        pmin.append(lo)
        pmax.append(hi)
        if armado and l[j] <= toque:
            n_ret, armado = n_ret + 1, False
        if h[j] >= arma:
            armado = True
        retoques.append(n_ret)
    i_meta = esc[ESCALERA.index(GRUPO["meta"])]
    for W in VENTANAS:
        if n < W:
            out["ventanas"][str(W)] = None
            continue
        dentro = [x if x is not None and x < W else None for x in esc]
        antes = []
        for meta in OBJETIVOS:
            m = dentro[ESCALERA.index(meta)]
            antes.append(_pct(pmin[m] if m is not None else pmin[W - 1], R))
        mx, mn = _pct(pmax[W - 1], R), _pct(pmin[W - 1], R)
        if i_meta is not None and i_meta < W:
            grupo = "BAJA_Y_SUBE" if caida is not None and caida <= i_meta else "SUBE_DIRECTO"
        elif mx >= GRUPO["corta"]:
            grupo = "SE_QUEDA_CORTA"
        elif mn <= -GRUPO["cae"]:
            grupo = "CAE"
        else:
            grupo = "LATERAL"
        out["ventanas"][str(W)] = {"max": mx, "min": mn, "cierre": _pct(c[W - 1], R), "esc": dentro,
                                   "min_antes": antes, "retoques": retoques[W - 1], "grupo": grupo}
    return out


def _resultado(W, n, f, precio, meta, t, s, stop, o, c, roto):
    if n < W:
        return ["AB", None, None]
    if f is None or f >= W:
        return ["NE", None, 0.0]
    if roto:
        return ["PR", None, 0.0]
    tt = t if t is not None and t < W else None
    ss = s if s is not None and s < W else None
    if ss is not None and (tt is None or ss <= tt):
        salida = min(stop, o[ss]) if ss > f else stop      # una vela que abre bajo el stop sale peor
        return ["SL", ss - f, round((salida / precio - 1) * 100 - COSTE, 4)]
    if tt is not None:
        return ["TP", tt - f, round(meta - COSTE, 4)]
    return ["TI", W - 1 - f, round((c[W - 1] / precio - 1) * 100 - COSTE, 4)]


def simular(o, h, l, c, R, stop):
    """Las 45 variantes (entrada x meta x stop) en cada ventana, en el orden de VARIANTES."""
    n = min(len(h), SPAN)
    res = {str(W): [] for W in VENTANAS}
    TH, TL = (sparse(h[:n], max), sparse(l[:n], min)) if n else (None, None)
    valido = isinstance(stop, (int, float)) and 0 < stop < R
    for off, meta, st in VARIANTES:
        precio = R * (1 - off / 100)
        # Todas las entradas son órdenes límite, también la de R: si el precio ya
        # está por encima al empezar, comprar "en R" no habría sido posible.
        f = first_reach(TL, 0, n - 1, lambda v: v <= precio * (1 + EPS)) if n else None
        t = s = None
        roto = False
        nivel_stop = stop if st == "SISTEMA" else precio * (1 - STOP_FIJO_PCT / 100)
        if f is not None:
            # La compra ocurre dentro de su vela: no puede cobrar la meta en ella.
            tp_from = f + 1
            if tp_from <= n - 1:
                tp = precio * (1 + meta / 100)
                t = first_reach(TH, tp_from, n - 1, lambda v: v >= tp * (1 - EPS))
            if st == "SISTEMA" and (not valido or stop >= precio * (1 - EPS)):
                roto = True
            elif st != "SIN_STOP":
                s = first_reach(TL, f, n - 1, lambda v: v <= nivel_stop * (1 + EPS))
        for W in VENTANAS:
            res[str(W)].append(_resultado(W, n, f, precio, meta, t, s, nivel_stop, o, c, roto))
    return res


def evaluar(o, h, l, c, R, stop):
    out = medir(o, h, l, c, R)
    out["ops"] = simular(o, h, l, c, R, stop)
    return out


def inicio_control(alerta_id, ts):
    """Minuto al azar de la misma moneda entre 36 h y 12 h antes; semilla = id de la señal."""
    minutos = random.Random(f"{VERSION}:{alerta_id}").randint(*CONTROL_MIN)
    return (ts - minutos * MIN) // MIN * MIN
