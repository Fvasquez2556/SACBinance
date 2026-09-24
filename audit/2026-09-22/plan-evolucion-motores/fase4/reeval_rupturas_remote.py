"""
Reevaluacion de las rupturas por marco con barreras HOMOGENEAS EN R.

Por que
-------
`rupturas_tf` guarda el desenlace contra el plan que se habria publicado, y ese
plan tiene un stop que cambia de una fila a otra (risk_pct va de 0,5 % a 2,5 %).
Comparar "5m acierta mas que 1h" con esas barreras compara anchos de stop, no
detectores. El analisis del 21-sep ya mostro que las columnas que parecian
predecir eran medidas de amplitud: al normalizar por el riesgo del propio plan
no quedaba nada.

Aqui la barrera es la misma para todos en unidades de ruido del par:

    R = atr_pct(%) del marco en el momento de detectar, sobre price_open

y se miden dos geometrias:

    simetrica   +1R antes que -1R    (azar ~ 50 %)
    plan        +2R antes que -1R    (azar ~ 33 %, la geometria real del plan)

En direccion BAJISTA las barreras se reflejan: "a favor" es hacia abajo. No es
un corto — es la pregunta del motor B, "¿la caida sigue activa?".

Control
-------
Por cada ruptura se evalua una entrada aleatoria del MISMO par, dentro del mismo
periodo, con la MISMA R. Es la unica forma de separar "el detector elige el
momento" de "el par se movia asi de todos modos".

Reglas de evaluacion, las mismas de la fase 2
---------------------------------------------
- Solo cuentan las velas cuyo minuto entero cae dentro de la ventana de 12 h.
- Primer toque manda; si una vela toca las dos barreras, gana la adversa y la
  fila queda marcada ambigua.
- Si la vela abre ya pasada la barrera, se ejecuta en la apertura.
- Sin cobertura no hay medicion: se reporta aparte.

Solo lectura. Escribe JSON comprimido a stdout.
"""
import bisect
import gzip
import json
import sqlite3
import sys
import time

import numpy as np

DB = 'file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
HORIZONTE_MS = 12 * 3600 * 1000
MINUTO = 60_000
SEMILLA = 20260922

db = sqlite3.connect(DB, uri=True)
db.row_factory = sqlite3.Row
db.execute('PRAGMA query_only=ON')
db.execute('BEGIN')
ahora = int(time.time() * 1000)

COLS = ('id,symbol,tf,direction,ts_open,price_open,confirmada,nivel_roto,toques_nivel,'
        'velas_desde_ruptura,tendencia,atr_pct,rsi14,vol_ratio,conf_dominante,'
        'conf_tf_dominante,conf_alcistas,conf_bajistas,conf_confirmadas,conf_en_conflicto,'
        'plan_valid,entrada_ref,stop_loss,take_profit,risk_pct,reward_pct,tp_bloqueado')
filas = [dict(r) for r in db.execute(f'SELECT {COLS} FROM rupturas_tf')]
print(f'{len(filas)} rupturas', file=sys.stderr)

por_symbol = {}
for f in filas:
    por_symbol.setdefault(f['symbol'], []).append(f)


def evaluar(T, O, H, L, C, i0, entrada, r_abs, alcista):
    """
    Devuelve el desenlace de las dos geometrias desde el indice i0.
    `i0` es la primera vela cuyo minuto entero cae dentro de la ventana.
    """
    ts = T[i0] if i0 < len(T) else None
    if ts is None or entrada <= 0 or r_abs <= 0:
        return None
    fin = ts + HORIZONTE_MS
    i1 = bisect.bisect_right(T, fin - MINUTO, i0)
    n = i1 - i0
    horizonte_real = min(fin, ahora)
    esperadas = max(0, (horizonte_real - ts) // MINUTO)
    res = {'n': int(n), 'esperadas': int(esperadas),
           'madura': int(fin <= ahora)}
    if n <= 0:
        return res

    h = H[i0:i1]
    l = L[i0:i1]
    o = O[i0:i1]

    if alcista:
        favor1, favor2, contra = entrada + r_abs, entrada + 2 * r_abs, entrada - r_abs
        toca_f1 = h >= favor1
        toca_f2 = h >= favor2
        toca_c = l <= contra
        mfe = (float(h.max()) / entrada - 1.0)
        mae = (float(l.min()) / entrada - 1.0)
    else:
        favor1, favor2, contra = entrada - r_abs, entrada - 2 * r_abs, entrada + r_abs
        toca_f1 = l <= favor1
        toca_f2 = l <= favor2
        toca_c = h >= contra
        mfe = -(float(l.min()) / entrada - 1.0)
        mae = -(float(h.max()) / entrada - 1.0)

    def primero(mask):
        if not mask.any():
            return None
        return int(mask.argmax())

    i_f1, i_f2, i_c = primero(toca_f1), primero(toca_f2), primero(toca_c)

    def desenlace(i_fav):
        """OBJETIVO / STOP / VENCIDO + ambiguedad, con la regla del hueco."""
        if i_fav is None and i_c is None:
            return 'VENCIDO', None, 0, 0
        if i_fav is not None and (i_c is None or i_fav < i_c):
            return 'OBJETIVO', int(i_fav), 0, 0
        if i_c is not None and (i_fav is None or i_c < i_fav):
            salto = int((o[i_c] <= contra) if alcista else (o[i_c] >= contra))
            return 'STOP', int(i_c), 0, salto
        # misma vela: gana la adversa
        salto = int((o[i_c] <= contra) if alcista else (o[i_c] >= contra))
        return 'STOP', int(i_c), 1, salto

    for nombre, i_fav in (('sim', i_f1), ('plan', i_f2)):
        d, idx, amb, salto = desenlace(i_fav)
        res[f'{nombre}_desenlace'] = d
        res[f'{nombre}_min'] = None if idx is None else idx
        res[f'{nombre}_ambiguo'] = amb
        res[f'{nombre}_salto'] = salto

    res['mfe_r'] = round(mfe * entrada / r_abs, 4)
    res['mae_r'] = round(mae * entrada / r_abs, 4)
    res['cierre_r'] = round(
        ((float(C[i1 - 1]) / entrada - 1.0) * (1 if alcista else -1)) * entrada / r_abs, 4)
    return res


rng = np.random.default_rng(SEMILLA)
salida = {}
control = {}
simbolos = sorted(por_symbol)
for k, sym in enumerate(simbolos):
    grupo = por_symbol[sym]
    lo = min(g['ts_open'] for g in grupo)
    hi = min(ahora, max(g['ts_open'] for g in grupo) + HORIZONTE_MS)
    T, O, H, L, C = [], [], [], [], []
    for t, o_, h_, l_, c_ in db.execute(
            "SELECT open_time,o,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
            "AND open_time>=? AND open_time<=? ORDER BY open_time",
            (sym, lo - MINUTO, hi)):
        T.append(t); O.append(o_); H.append(h_); L.append(l_); C.append(c_)
    if len(T) < 60:
        print(f'{k+1}/{len(simbolos)} {sym} SIN VELAS ({len(T)})', file=sys.stderr)
        continue
    O = np.asarray(O, dtype=float); H = np.asarray(H, dtype=float)
    L = np.asarray(L, dtype=float); C = np.asarray(C, dtype=float)

    # Indices validos para el control: los que dejan ventana por delante.
    tope = bisect.bisect_right(T, ahora - HORIZONTE_MS)
    for f in grupo:
        atr = f['atr_pct']
        entrada = f['price_open']
        if not atr or atr <= 0 or not entrada or entrada <= 0:
            continue
        r_abs = entrada * atr / 100.0
        alcista = f['direction'] == 'RUPTURA_ALCISTA'
        i0 = bisect.bisect_left(T, f['ts_open'])
        r = evaluar(T, O, H, L, C, i0, entrada, r_abs, alcista)
        if r is not None:
            salida[f['id']] = r
        if tope > 1:
            j = int(rng.integers(0, tope))
            ent_c = float(C[j])
            rc = evaluar(T, O, H, L, C, j + 1, ent_c, ent_c * atr / 100.0, alcista)
            if rc is not None:
                control[f['id']] = rc
    print(f'{k+1}/{len(simbolos)} {sym} velas={len(T)} filas={len(grupo)}', file=sys.stderr)

db.rollback()
db.close()
out = {'ahora': ahora, 'horizonte_ms': HORIZONTE_MS, 'semilla': SEMILLA,
       'filas': filas, 'eval': salida, 'control': control}
sys.stdout.buffer.write(gzip.compress(json.dumps(out, ensure_ascii=False).encode('utf-8')))
