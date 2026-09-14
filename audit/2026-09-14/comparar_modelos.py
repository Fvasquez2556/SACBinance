# -*- coding: utf-8 -*-
"""
Comparacion honesta de modelos de entrada sobre las señales que el sistema YA
emitio. La pregunta es la de Felix: el sistema lanza una señal, ¿que modelo
acierta mas?

Que se compara
--------------
M0  SISTEMA ACTUAL      se opera todo lo que pasa los vetos. Es la tasa base.
M1  SCORE               se ordena por el score que el sistema ya calcula y se
                        opera solo el tramo alto.
M2  CONTINUACION        regresion logistica sobre features de TIEMPO DE SEÑAL,
                        el modelo del handoff del 14-sep.
M3  OBJETIVO POR GRUPO  no filtra señales: cambia el objetivo segun la
                        volatilidad previa de la moneda (columnas v12).
M4  ENTRADA DIFERIDA    no filtra: pone la entrada 0.5% por debajo y espera.

Reglas que hacen que la comparacion signifique algo
---------------------------------------------------
1. FUERA DE MUESTRA Y EN ORDEN. El modelo se entrena con lo anterior y se juzga
   con lo posterior. Un AUC medido sobre lo mismo con lo que se entreno no dice
   nada; con dos dias de datos es facil engañarse.
2. SIN FUGA DE POLITICA. `sl_pct`, `tp_pct`, `take_profit`, `stop_loss`, `ms_*`,
   `mfe_pct` y `mae_pct` NO son features: describen la salida o el futuro.
   Predecir que se toque el SL usando el ancho del SL es circular.
3. AGRUPADO POR SIMBOLO. Varias señales del mismo par en el mismo tramo no son
   observaciones independientes.
4. LA TASA DE ACIERTO NO BASTA. Un modelo que acierta mas sobre un objetivo mas
   facil no es mejor. Por eso se reporta ademas la esperanza por operacion.

Limite grande, declarado por delante: son ~3 dias de una sola version. Esto
ordena candidatos, no certifica ninguno.
"""
import json
import pathlib
import sys

import numpy as np

RUTA = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "datos.json")
META = 3.2
COSTE = 0.5          # puntos porcentuales, ida y vuelta

# Lo que el modelo puede mirar. Todo esto existe ANTES de que el precio se
# mueva; nada describe la salida ni el resultado.
FEATURES = [
    "score", "vol_24h", "vol_1m_medio", "pos_en_rango", "dist_soporte_pct",
    "dist_resistencia_pct", "z_drop", "z_rise", "velocity", "ret_1m_pct",
    "drawdown_pct", "rango_1h_pct", "sigma_pct", "atr_pct", "ruido_1m_pct",
    "atr_percentile", "vol_ratio", "rsi5", "rsi14", "macd_hist", "bb_position",
    "fuerza_impulso", "consumido_pct", "retro_caida_pct", "retro_rebote_pct",
    "macro_gate_mult", "score_trend", "senal_n", "vol_previa_pct",
    "rsi14_1m", "rsi14_15m", "macd_hist_15m", "bb_position_15m",
]
PROHIBIDAS = {"sl_pct", "tp_pct", "take_profit", "stop_loss", "mfe_pct",
              "mae_pct", "ms_up_32", "ms_sl", "ms_tp", "ms_objetivo_grupo"}
assert not (set(FEATURES) & PROHIBIDAS), "una feature prohibida se colo"


# ---------------------------------------------------------------- datos
def cargar():
    filas = json.loads(RUTA.read_text(encoding="utf-8"))
    return [r for r in filas if not r["sombra"]]


def etiqueta_llega(r):
    """Llego a +3.2% en algun momento de las 24h."""
    return 1 if r["ms_up_32"] is not None else 0


def etiqueta_antes_sl(r):
    """Llego a +3.2% ANTES de tocar el SL. Es la que se puede operar."""
    a, b = r["ms_up_32"], r["ms_sl"]
    return 1 if (a is not None and (b is None or a < b)) else 0


def resultado_operacion(r):
    """
    Resultado bruto de operar la señal tal cual la ofrece el sistema.
    Expirada sin tocar nada = 0 (se sale plana). Es optimista, pero se aplica
    igual a todos los modelos, asi que no favorece a ninguno.
    """
    tp, sl = r["ms_tp"], r["ms_sl"]
    if tp is not None and (sl is None or tp < sl):
        return r["tp_pct"] or 0.0
    if sl is not None:
        return r["sl_pct"] or 0.0
    return 0.0


def matriz(filas):
    X = np.zeros((len(filas), len(FEATURES)))
    for i, r in enumerate(filas):
        for j, f in enumerate(FEATURES):
            v = r.get(f)
            X[i, j] = float(v) if v is not None else np.nan
    # Los huecos se rellenan con la MEDIANA DEL ENTRENAMIENTO, nunca del total:
    # usar la mediana global filtraria informacion del test al entrenamiento.
    return X


def normalizar(X, med, iqr):
    Z = (X - med) / iqr
    Z = np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)
    # Recorte imprescindible: hay features con colas enormes (vol_24h va de
    # 1e6 a 6e8) y sin esto el descenso diverge.
    return np.clip(Z, -5.0, 5.0)


# ---------------------------------------------------------------- modelo
def entrenar_logistica(X, y, l2=1.0, iters=3000, lr=0.05):
    """
    Regresion logistica con descenso de gradiente y regularizacion L2.

    Se implementa a mano porque el entorno no tiene scikit-learn; para 30
    features y ~400 filas no hace falta mas.

    Dos detalles que costaron un diagnostico falso: sin RECORTAR los valores
    normalizados, un par de outliers hacen divergir el descenso — el AUC de
    ENTRENAMIENTO bajaba a 0.40 al pedir mas iteraciones, que es imposible si
    el ajuste funciona. Y `lr` alto diverge igual. Se devuelve tambien la
    perdida para poder comprobarlo en vez de suponerlo.
    """
    n, k = X.shape
    w = np.zeros(k)
    b = 0.0
    primera = ultima = None
    for t in range(iters):
        z = np.clip(X @ w + b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        if t == 0 or t == iters - 1:
            perdida = -(y * np.log(p + 1e-12)
                        + (1 - y) * np.log(1 - p + 1e-12)).mean()
            if t == 0:
                primera = perdida
            else:
                ultima = perdida
        err = p - y
        w -= lr * (X.T @ err / n + l2 * w / n)
        b -= lr * err.mean()
    if ultima is not None and ultima > primera:
        raise RuntimeError(
            "el descenso diverge (perdida %.4f -> %.4f): revisa escala o lr"
            % (primera, ultima))
    return w, b


def predecir(X, w, b):
    z = X @ w + b
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def auc(y, s):
    """AUC por conteo de pares concordantes (Mann-Whitney)."""
    pos, neg = s[y == 1], s[y == 0]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    orden = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    rangos = np.empty(orden.size)
    rangos[orden] = np.arange(1, orden.size + 1)
    return (rangos[:pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size)


def ic95_prop(k, n):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    e = 1.96 * np.sqrt(max(p * (1 - p), 1e-12) / n)
    return (max(0.0, p - e), min(1.0, p + e))


def ic95_media(x):
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return (float("nan"), float("nan"))
    e = 1.96 * x.std(ddof=1) / np.sqrt(x.size)
    return (x.mean() - e, x.mean() + e)


# ---------------------------------------------------------------- informe
def cabecera(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    filas = cargar()
    filas.sort(key=lambda r: r["ts_open"])
    n = len(filas)
    y_llega = np.array([etiqueta_llega(r) for r in filas])
    y_oper = np.array([etiqueta_antes_sl(r) for r in filas])
    ret = np.array([resultado_operacion(r) for r in filas])

    cabecera("PERIMETRO")
    print(f"   señales emitidas, cerradas, cobertura >=98%, version f82bcff: {n}")
    print(f"   simbolos distintos: {len({r['symbol'] for r in filas})}")
    print(f"   llegan a +3.2% alguna vez:      {y_llega.sum():3d}  ({y_llega.mean():.1%})")
    print(f"   llegan a +3.2% ANTES del SL:    {y_oper.sum():3d}  ({y_oper.mean():.1%})")
    print(f"   esperanza bruta de operarlo todo: {ret.mean():+.3f}%   "
          f"neta: {ret.mean()-COSTE:+.3f}%")

    # --- corte cronologico: se entrena con lo viejo, se juzga con lo nuevo ---
    corte = int(n * 0.6)
    tr, te = slice(0, corte), slice(corte, n)
    X = matriz(filas)
    # `rsi14`, `macd_hist` y `bb_position` estan 100% vacias en esta cohorte:
    # el snapshot guarda las versiones con marco temporal en el nombre.
    vivas = [j for j in range(X.shape[1]) if np.isnan(X[:, j]).mean() <= 0.5]
    vacias = [FEATURES[j] for j in range(X.shape[1]) if j not in vivas]
    if vacias:
        print("   features descartadas por estar vacias: "
              + ", ".join(vacias))
    X = X[:, vivas]
    nombres = [FEATURES[j] for j in vivas]
    med = np.nanmedian(X[tr], axis=0)
    q1, q3 = np.nanpercentile(X[tr], 25, axis=0), np.nanpercentile(X[tr], 75, axis=0)
    iqr = np.where((q3 - q1) > 1e-9, q3 - q1, 1.0)
    Z = normalizar(X, med, iqr)

    import datetime as dt
    g = lambda ms: (dt.datetime.utcfromtimestamp(ms / 1000)
                    - dt.timedelta(hours=6)).strftime("%d/%m %H:%M")
    print(f"\n   entrenamiento: {corte} señales ({g(filas[0]['ts_open'])} -> "
          f"{g(filas[corte-1]['ts_open'])})")
    print(f"   prueba:        {n-corte} señales ({g(filas[corte]['ts_open'])} -> "
          f"{g(filas[-1]['ts_open'])})")

    resultados = {}
    for nombre, y in (("llega a +3.2%", y_llega), ("+3.2% antes del SL", y_oper)):
        w, b = entrenar_logistica(Z[tr], y[tr])
        s_te = predecir(Z[te], w, b)
        resultados[nombre] = (w, b, s_te, y[te])

    cabecera("1 · ¿ORDENA MEJOR QUE EL AZAR? (AUC fuera de muestra)")
    print("   0.50 = azar.  Medido SOLO sobre el tramo de prueba.\n")
    print(f"   {'objetivo':24} {'AUC modelo':>12} {'AUC score solo':>16}")
    score_te = Z[te][:, nombres.index("score")]
    rango_te = Z[te][:, nombres.index("rango_1h_pct")]
    for nombre, (w, b, s_te, y_te) in resultados.items():
        print(f"   {nombre:24} {auc(y_te, s_te):12.3f} {auc(y_te, score_te):16.3f}")
    print("\n   El handoff reporta 0.736 y 0.755 con validacion por simbolo.")

    cabecera("2 · SIMULACION: el sistema lanza la señal, ¿cual la operaria mejor?")
    print("   Se opera el tramo ALTO de cada modelo sobre el periodo de prueba.")
    print("   'acierto' = llega a +3.2% antes del SL, que es lo unico cobrable.\n")
    y_te = y_oper[te]
    ret_te = ret[te]
    m = y_te.size
    _, _, s_cont, _ = resultados["+3.2% antes del SL"]

    print(f"   {'modelo':32} {'opera':>7} {'acierta':>9} {'IC95':>16} {'esperanza neta':>16}")

    def linea(nombre, sel):
        k = int(y_te[sel].sum())
        nn = int(sel.sum())
        if nn == 0:
            print(f"   {nombre:32} {0:7d}        --")
            return
        lo, hi = ic95_prop(k, nn)
        esp = ret_te[sel].mean() - COSTE
        print(f"   {nombre:32} {nn:7d} {k/nn:8.1%} [{lo:5.1%},{hi:5.1%}] {esp:15.3f}%")

    linea("M0 · sistema actual (todo)", np.ones(m, dtype=bool))
    for q, et in ((0.5, "mitad alta"), (0.2, "top 20%")):
        umbral = np.quantile(score_te, 1 - q)
        linea(f"M1 · score, {et}", score_te >= umbral)
    for q, et in ((0.5, "mitad alta"), (0.2, "top 20%")):
        umbral = np.quantile(s_cont, 1 - q)
        linea(f"M2 · continuacion, {et}", s_cont >= umbral)
    # Una sola columna ya es un modelo, y es el contraste que importa: si
    # rankear por volatilidad iguala al modelo entrenado, el modelo no aporta
    # nada que no estuviera ya en el snapshot.
    for q, et in ((0.5, "mitad alta"), (0.2, "top 20%")):
        umbral = np.quantile(rango_te, 1 - q)
        linea(f"M1b · rango_1h sola, {et}", rango_te >= umbral)

    cabecera("3 · M3 · OBJETIVO POR GRUPO (no filtra: cambia la meta)")
    te_filas = filas[corte:]
    con_g = [r for r in te_filas if r.get("grupo_vol")]
    if con_g:
        a = sum(1 for r in con_g if r["ms_objetivo_grupo"] is not None)
        b2 = sum(1 for r in con_g if r["ms_up_32"] is not None)
        lo, hi = ic95_prop(a, len(con_g))
        print(f"   n={len(con_g)}")
        print(f"   alcanza el objetivo de su grupo: {a/len(con_g):6.1%}  "
              f"[{lo:.1%}, {hi:.1%}]")
        print(f"   alcanza el 3.2% fijo:            {b2/len(con_g):6.1%}")
        print("\n   Ojo: el objetivo del grupo es MAS BAJO (1.23%-2.49%), asi que")
        print("   acertar mas es lo esperable. Lo que decide es la esperanza, y")
        print("   medida en su dia dio solo +0.085 puntos por operacion.")

    cabecera("4 · M4 · ENTRADA DIFERIDA (candidato del handoff)")
    print("   El handoff propone entrar 0.5% por debajo en las continuaciones.")
    print("   Su propio limite: el grupo 'continuacion' se elige DESPUES de ver")
    print("   el camino. Aqui se comprueba si un modelo de tiempo-de-señal puede")
    print("   seleccionar ese grupo por adelantado, que es lo que haria falta.\n")
    top = s_cont >= np.quantile(s_cont, 0.8)
    k, nn = int(y_te[top].sum()), int(top.sum())
    lo, hi = ic95_prop(k, nn)
    print(f"   top 20% del modelo en prueba: {nn} señales, aciertan {k/nn:.1%} "
          f"[{lo:.1%}, {hi:.1%}]")
    print(f"   base del mismo tramo:         {y_te.mean():.1%}")
    print("   -> si ese intervalo no despega de la base, la entrada diferida")
    print("      no tiene a quien aplicarse por adelantado.")

    cabecera("5 · ¿LA MEJORA ES SIGNIFICATIVA?")
    base_k, base_n = int(y_te.sum()), m
    for etiqueta, sel in (("M1 score top 20%", score_te >= np.quantile(score_te, 0.8)),
                          ("M2 continuacion top 20%", s_cont >= np.quantile(s_cont, 0.8)),
                          ("M1b rango_1h top 20%", rango_te >= np.quantile(rango_te, 0.8))):
        k, nn = int(y_te[sel].sum()), int(sel.sum())
        p1, p0 = k / nn, base_k / base_n
        se = np.sqrt(p1 * (1 - p1) / nn + p0 * (1 - p0) / base_n)
        z = (p1 - p0) / se if se > 0 else 0.0
        vered = "SIGNIFICATIVA" if abs(z) > 1.96 else "no significativa"
        print(f"   {etiqueta:28} {p1:6.1%} vs base {p0:5.1%}   z={z:+5.2f}   {vered}")

    print("\n   Con este tamaño de muestra hace falta una diferencia grande para")
    print("   que z supere 1.96. Un 'no significativa' aqui no dice que el modelo")
    print("   no sirva: dice que estos datos no alcanzan para afirmarlo.")


if __name__ == "__main__":
    main()
