"""
CAPA 2 (a) — Motor de etiquetado: triple barrera + MFE/MAE.

Que responde
------------
Para cada punto historico: desde aca, ¿que pasa PRIMERO? ¿toca +X%, toca
-Y%, o expira? Las tres opciones particionan el espacio y suman 1.0 por
construccion. Ademas registra MFE (cuanto llego a subir) y MAE (cuanto
llego a bajar), que son los que responden "¿cuanto drawdown hay que aguantar
para capturar el objetivo?" y "¿cuanto se dejo sobre la mesa?".

Por que las barreras se escalan por ATR y no son % fijos
--------------------------------------------------------
Barreras demasiado ajustadas respecto al ruido producen etiquetas casi
aleatorias; demasiado anchas y casi todo expira. Un stop del 2% en una
moneda cuyas velas horarias tienen 2% de rango no mide una tesis: mide
ruido. Por eso el modo por defecto es `atr`: tp = k_tp * ATR%, sl = k_sl *
ATR%, con lo que cada moneda recibe barreras proporcionales a SU propia
volatilidad.

El modo `fijo` existe para la pregunta concreta "¿cuantos pares llegan a
+3.2%?", que necesita un umbral absoluto. Los dos modos sobre los mismos
eventos permiten comparar politicas de salida.

Ambiguedad intra-vela
---------------------
Con OHLC de 1m no se sabe si dentro de la vela se toco primero el maximo o
el minimo. Cuando ambas barreras caen en la misma vela se asigna SL
(conservador) y se marca `ambiguo=1`. El reporte cuenta cuantos son: si el
porcentaje es alto, las conclusiones estan sesgadas y hace falta bajar a
klines de 1s o aggTrades.

Muestreo de eventos
-------------------
Muestrear cada vela genera etiquetas masivamente superpuestas y redundantes.
El filtro CUSUM simetrico dispara un evento solo cuando el retorno acumulado
supera un umbral desde el ultimo evento, lo que concentra el muestreo en
momentos con movimiento real. Se registra ademas la concurrencia para poder
aplicar despues la ponderacion por unicidad promedio.

-----------------------------------------------------------------------------
CORRECCIONES DE LA REVISION DEL 11-SEP (path-engine-review)
-----------------------------------------------------------------------------
La revision encontro cuatro defectos que invalidaban el dataset producido.
Todos estan corregidos aqui, y `verificar_labeling.py` lo comprueba:

1. FILTRACION DE FUTURO. Las medias de calentamiento se rellenaban con la
   media de las PRIMERAS 500 observaciones (`atr_med[:win] = atr[:win].mean()`),
   asi que la feature del indice 100 dependia de las velas 101..499. Cambiando
   solo el futuro, `f_atr_rel[100]` pasaba de 1.0 a 0.294. Peor aun: el ancho
   de ventana era `min(500, max(50, n//10))`, o sea funcion del largo TOTAL de
   la serie — la misma vela daba features distintas segun cuantos datos se
   hubieran cargado, y el filtro de eventos (idx > 60) no cubria ni de lejos
   la zona contaminada (0..500). Ahora las ventanas son constantes y las
   medias son causales por construccion: el valor en i depende solo de
   0..i. Se comprueba con una prueba de invariancia de prefijo.

2. IDENTIDAD. La PK era `(symbol, interval, t0)` con `INSERT OR REPLACE`, asi
   que etiquetar a 4h y despues a 8h dejaba solo lo ultimo, y un SL fijo
   pisaba al SL por ATR sobre la misma entrada. La PK incluye ahora horizonte,
   politica y version del evaluador: cada combinacion es una fila propia.

3. TIEMPO. El horizonte se contaba en VELAS. Con huecos —y el historico de 1m
   los tiene— dos velas pueden abarcar 60 minutos y quedar etiquetadas como un
   horizonte de 2 minutos. Ahora el horizonte es tiempo real en milisegundos y
   cada fila guarda su cobertura: que fraccion de las velas esperadas existia
   de verdad.

4. SEMANTICA DE MFE/MAE. El tracker en vivo mide el recorrido completo de la
   ventana; aqui se medía hasta la vela de salida. Las dos son utiles y no son
   la misma: tras un SL en -2% con subida posterior a +5%, una dice +1% y la
   otra +5%. Ahora se guardan las DOS, con nombres distintos.

Ademas, `velas_a_tp` se rellenaba aunque el SL hubiera ido primero: la fila
decia "SL" y a la vez "llego al TP en 3 velas". Se conserva —es informacion
real sobre el recorrido— pero acompañada de `tp_primero`, para que nadie lo
lea como un acierto.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_DAY_MS = 86_400_000

# Version del evaluador. Sube cuando cambia la SEMANTICA de una etiqueta, para
# que dos filas con el mismo t0 y distinta version no se confundan ni se pisen.
#   1 -> 2: features causales, horizonte en tiempo real, MFE de ventana
#           completa ademas del de salida, identidad por politica.
EVALUADOR_VERSION = 2

# Anchos de ventana FIJOS. Antes salian de `n//10`, o sea del largo total de la
# serie: la misma vela daba features distintas segun el rango cargado, y dos
# corridas del etiquetador no eran comparables entre si.
VENTANA_ATR_REL = 500
VENTANA_VOL_REL = 200

# Estados de completitud de una etiqueta.
COMPLETO = "COMPLETO"       # el horizonte entero existe y sin huecos relevantes
INCOMPLETO = "INCOMPLETO"   # el horizonte existe pero le faltan velas
PENDIENTE = "PENDIENTE"     # la serie se acaba antes del horizonte

SCHEMA_LABELS = """
CREATE TABLE IF NOT EXISTS labels (
    symbol        TEXT    NOT NULL,
    interval      TEXT    NOT NULL,
    t0            INTEGER NOT NULL,     -- ms del evento (entrada)
    -- Identidad de la EVALUACION, no solo del instante. Sin esto, etiquetar a
    -- 4h y luego a 8h dejaba una sola fila, y un SL fijo pisaba al de ATR.
    horizonte_min INTEGER NOT NULL,     -- horizonte en MINUTOS reales
    politica      TEXT    NOT NULL,     -- p.ej. "atr:2.0/1.5" o "fijo:3.2/2.0"
    evaluador     INTEGER NOT NULL,     -- EVALUADOR_VERSION
    t1            INTEGER,              -- ms de salida
    precio_e      REAL    NOT NULL,     -- precio de entrada
    precio_s      REAL,                 -- precio de salida
    tp_pct        REAL,                 -- barrera superior usada (%)
    sl_pct        REAL,                 -- barrera inferior usada (%)
    etiqueta      INTEGER,              -- 1=TP  -1=SL  0=expiro
    ret_pct       REAL,                 -- retorno realizado
    -- Las DOS definiciones de excursion, que no son la misma cosa:
    mfe_salida    REAL,                 -- maximo favorable HASTA LA SALIDA
    mae_salida    REAL,                 -- maximo adverso  HASTA LA SALIDA
    mfe_ventana   REAL,                 -- maximo favorable en TODO el horizonte
    mae_ventana   REAL,                 -- maximo adverso  en TODO el horizonte
    ms_a_tp       INTEGER,              -- ms hasta tocar TP (NULL si nunca)
    tp_primero    INTEGER,              -- 1 si el TP se toco ANTES que el SL
    ambiguo       INTEGER DEFAULT 0,    -- TP y SL en la misma vela
    concurrencia  INTEGER,              -- etiquetas vivas simultaneas
    -- Calidad del dato: sin esto una etiqueta con huecos parece una completa
    estado        TEXT,                 -- COMPLETO / INCOMPLETO / PENDIENTE
    cobertura     REAL,                 -- velas presentes / velas esperadas
    -- features del estado en t0 (todas causales: solo usan datos <= t0)
    f_pct_dia     REAL,
    f_pos_dia     REAL,
    f_atr_rel     REAL,
    f_vol_rel     REAL,
    f_ret_1h      REAL,
    f_dist_max20  REAL,
    f_btc_reg     REAL,
    PRIMARY KEY (symbol, interval, t0, horizonte_min, politica, evaluador)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_lab_t0 ON labels (t0);
CREATE INDEX IF NOT EXISTS idx_lab_sym ON labels (symbol, t0);
CREATE INDEX IF NOT EXISTS idx_lab_pol ON labels (politica, horizonte_min);
"""

# Orden canonico de las columnas al insertar. Se nombran a proposito: un INSERT
# posicional contra `VALUES (?,?,...)` se descuadra en silencio en cuanto
# alguien añade una columna al esquema.
COLUMNAS_LABELS = (
    "symbol", "interval", "t0", "horizonte_min", "politica", "evaluador",
    "t1", "precio_e", "precio_s", "tp_pct", "sl_pct", "etiqueta", "ret_pct",
    "mfe_salida", "mae_salida", "mfe_ventana", "mae_ventana",
    "ms_a_tp", "tp_primero", "ambiguo", "concurrencia", "estado", "cobertura",
    "f_pct_dia", "f_pos_dia", "f_atr_rel", "f_vol_rel", "f_ret_1h",
    "f_dist_max20", "f_btc_reg",
)

_INSERT_LABELS = (
    f"INSERT OR REPLACE INTO labels ({', '.join(COLUMNAS_LABELS)}) "
    f"VALUES ({', '.join('?' * len(COLUMNAS_LABELS))})"
)


# =============================================================================
#  Carga
# =============================================================================

@dataclass
class Serie:
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray          # quote volume
    n: int


# Los dos esquemas de klines que existen en el proyecto. Produccion guarda
# `tf/o/h/l/c/v`; la base de investigacion, `interval/open/high/low/close/
# quote_volume`. Apuntar el etiquetador a produccion fallaba con "no such
# column: open" — no daba un resultado malo, no daba ninguno.
#
# En los dos casos `v` es volumen COTIZADO: el WS guarda k["q"], y mezclarlo
# con volumen base romperia vol_rel, que es un ratio entre ambos.
_ESQUEMAS = (
    ("tf", "SELECT open_time, o, h, l, c, v FROM klines "
           "WHERE symbol=? AND tf=? ORDER BY open_time"),
    ("interval", "SELECT open_time, open, high, low, close, quote_volume "
                 "FROM klines WHERE symbol=? AND interval=? ORDER BY open_time"),
)


def _columnas_klines(conn: sqlite3.Connection) -> set:
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(klines)")}
    except sqlite3.Error:
        return set()


def cargar(conn: sqlite3.Connection, symbol: str, interval: str,
           minimo: int = 500) -> Optional[Serie]:
    """
    Lee una serie de klines, sea cual sea el esquema de la base.

    `minimo` es configurable para poder probar el motor con series cortas sin
    tener que fabricar 500 velas; en produccion el valor por defecto sigue
    siendo el que evita entrenar sobre nada.
    """
    cols = _columnas_klines(conn)
    filas = None
    for marca, sql in _ESQUEMAS:
        if marca not in cols:
            continue
        filas = conn.execute(sql, (symbol, interval)).fetchall()
        break
    if filas is None:
        raise ValueError(
            "La tabla klines no tiene ni la columna 'tf' (esquema de "
            "produccion) ni 'interval' (esquema de investigacion)"
        )
    if len(filas) < minimo:
        return None
    a = np.array(filas, dtype=float)
    return Serie(t=a[:, 0].astype(np.int64), o=a[:, 1], h=a[:, 2],
                 l=a[:, 3], c=a[:, 4], v=a[:, 5], n=len(filas))


# =============================================================================
#  Indicadores auxiliares
# =============================================================================

def _media_causal(x: np.ndarray, win: int) -> np.ndarray:
    """
    Media movil de `win` que en el arranque se expande en vez de rellenarse.

    Es la pieza que elimina la filtracion: el valor en i sale de x[0..i] y de
    nada mas. Antes las primeras `win` posiciones se rellenaban con la media de
    las primeras `win` observaciones — que para i=100 y win=500 significa mirar
    400 velas del futuro.

    Propiedad que garantiza: si dos series comparten el prefijo 0..i, el
    resultado en i es identico aunque el resto difiera. `verificar_labeling.py`
    lo comprueba.
    """
    n = x.size
    if n == 0:
        return x.astype(float)
    cs = np.concatenate(([0.0], np.cumsum(x, dtype=float)))
    i = np.arange(n)
    lo = np.maximum(0, i - win + 1)
    return (cs[i + 1] - cs[lo]) / (i - lo + 1)


def atr_pct(s: Serie, period: int = 14) -> np.ndarray:
    """ATR como % del precio. atr[i] usa datos hasta i inclusive."""
    tr = np.empty(s.n)
    tr[0] = s.h[0] - s.l[0]
    tr[1:] = np.maximum(
        s.h[1:] - s.l[1:],
        np.maximum(np.abs(s.h[1:] - s.c[:-1]), np.abs(s.l[1:] - s.c[:-1])),
    )
    suave = _media_causal(tr, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.nan_to_num(suave / s.c * 100.0, nan=0.0, posinf=0.0)


def eventos_cusum(closes: np.ndarray, umbral: np.ndarray) -> np.ndarray:
    """
    Filtro CUSUM simetrico. Dispara cuando el retorno acumulado desde el
    ultimo evento supera +umbral o -umbral, y resetea.
    `umbral` puede variar por barra (ej. proporcional al ATR).
    """
    idx: List[int] = []
    sp = sn = 0.0
    r = np.zeros_like(closes)
    r[1:] = np.diff(np.log(np.maximum(closes, 1e-12)))
    for i in range(1, closes.size):
        u = umbral[i]
        sp = max(0.0, sp + r[i])
        sn = min(0.0, sn + r[i])
        if sp > u:
            sp = 0.0
            idx.append(i)
        elif sn < -u:
            sn = 0.0
            idx.append(i)
    return np.array(idx, dtype=np.int64)


# =============================================================================
#  Features en t0
# =============================================================================

def calcular_features(s: Serie, atr: np.ndarray, velas_por_hora: int,
                      btc_reg: Optional[np.ndarray]) -> Dict[str, np.ndarray]:
    """
    Estado del mercado en cada vela. TODAS las features son causales: el valor
    en i sale de las velas 0..i y de ninguna posterior.
    """
    n = s.n

    # Ancla diaria fija: open de la primera vela de cada dia UTC
    dia = s.t // _DAY_MS
    cambio = np.empty(n, dtype=bool)
    cambio[0] = True
    cambio[1:] = dia[1:] != dia[:-1]
    idx_dia = np.maximum.accumulate(np.where(cambio, np.arange(n), 0))
    open_dia = s.o[idx_dia]
    with np.errstate(divide="ignore", invalid="ignore"):
        pct_dia = np.nan_to_num((s.c - open_dia) / open_dia * 100.0)

    # Posicion en el rango del dia (max/min acumulados DENTRO del dia)
    hi = np.empty(n); lo = np.empty(n)
    ch, cl = -np.inf, np.inf
    for i in range(n):
        if cambio[i]:
            ch, cl = s.h[i], s.l[i]
        else:
            ch = max(ch, s.h[i]); cl = min(cl, s.l[i])
        hi[i] = ch; lo[i] = cl
    rng = hi - lo
    pos_dia = np.where(rng > 0, (s.c - lo) / np.maximum(rng, 1e-12), 0.5)

    # ATR relativo a su propia media larga (¿comprimida o expandida?)
    # Ventana FIJA y media causal: ver `_media_causal`.
    atr_med = _media_causal(atr, VENTANA_ATR_REL)
    atr_rel = np.where(atr_med > 0, atr / np.maximum(atr_med, 1e-12), 1.0)

    # Volumen relativo
    vol_med = _media_causal(s.v, VENTANA_VOL_REL)
    vol_rel = np.where(vol_med > 0, s.v / np.maximum(vol_med, 1e-12), 1.0)

    # Retorno de la ultima hora
    lag = max(1, velas_por_hora)
    ret_1h = np.zeros(n)
    ret_1h[lag:] = (s.c[lag:] - s.c[:-lag]) / np.maximum(s.c[:-lag], 1e-12) * 100.0

    # Distancia al maximo de las ultimas 20 velas
    max20 = np.copy(s.h)
    for i in range(1, n):
        j = max(0, i - 19)
        max20[i] = s.h[j:i + 1].max()
    dist_max20 = (s.c - max20) / np.maximum(max20, 1e-12) * 100.0

    return {
        "f_pct_dia": pct_dia, "f_pos_dia": pos_dia, "f_atr_rel": atr_rel,
        "f_vol_rel": vol_rel, "f_ret_1h": ret_1h, "f_dist_max20": dist_max20,
        "f_btc_reg": btc_reg if btc_reg is not None else np.zeros(n),
    }


def regimen_btc(conn: sqlite3.Connection, interval: str,
                t_ref: np.ndarray, velas_dia: int) -> Optional[np.ndarray]:
    """Retorno % de BTC en las ultimas 24h, alineado por timestamp."""
    b = cargar(conn, "BTCUSDT", interval)
    if b is None:
        return None
    lag = max(1, velas_dia)
    reg = np.zeros(b.n)
    reg[lag:] = (b.c[lag:] - b.c[:-lag]) / np.maximum(b.c[:-lag], 1e-12) * 100.0
    pos = np.searchsorted(b.t, t_ref, side="right") - 1
    pos = np.clip(pos, 0, b.n - 1)
    return reg[pos]


# =============================================================================
#  Triple barrera
# =============================================================================

def triple_barrera(
    s: Serie, eventos: np.ndarray, tp_pct: np.ndarray, sl_pct: np.ndarray,
    horizonte_ms: int, intervalo_ms: int, cobertura_min: float = 0.98,
) -> Dict[str, np.ndarray]:
    """
    Para cada evento devuelve que barrera se toco primero, mas MFE/MAE.

    El horizonte es TIEMPO REAL en milisegundos, no un numero de velas. Con
    huecos en el historico —y los hay— contar velas hacia que dos velas
    separadas por una hora pasaran por un horizonte de dos minutos.

    Devuelve las dos definiciones de excursion, que no son intercambiables:
      - `mfe_salida` / `mae_salida`: hasta la vela en que se sale. Es lo que
        habrias vivido operando con esas barreras.
      - `mfe_ventana` / `mae_ventana`: en todo el horizonte, pase lo que pase
        con las barreras. Es lo que mide el tracker en vivo, y lo que responde
        "¿el movimiento llego a estar ahi?".

    `estado` y `cobertura` dicen si la fila se puede creer: una etiqueta
    calculada sobre la mitad de las velas no es una etiqueta incompleta, es una
    etiqueta distinta.
    """
    m = eventos.size
    etiqueta = np.zeros(m, dtype=np.int8)
    t1_idx = np.zeros(m, dtype=np.int64)
    ret = np.zeros(m)
    mfe_sal = np.zeros(m); mae_sal = np.zeros(m)
    mfe_ven = np.zeros(m); mae_ven = np.zeros(m)
    ms_tp = np.full(m, -1, dtype=np.int64)
    tp_primero = np.zeros(m, dtype=np.int8)
    ambiguo = np.zeros(m, dtype=np.int8)
    estado = np.full(m, PENDIENTE, dtype=object)
    cobertura = np.zeros(m)

    esperadas = max(1, horizonte_ms // max(1, intervalo_ms))

    for j in range(m):
        i = int(eventos[j])
        limite = s.t[i] + horizonte_ms
        # Ultima vela cuya APERTURA cae dentro del horizonte.
        fin = int(np.searchsorted(s.t, limite, side="right")) - 1
        fin = min(fin, s.n - 1)
        if fin <= i:
            t1_idx[j] = i
            cobertura[j] = 0.0
            continue

        pe = s.c[i]
        hs = s.h[i + 1:fin + 1]
        ls = s.l[i + 1:fin + 1]
        ts = s.t[i + 1:fin + 1]

        # Calidad: velas presentes frente a las que deberia haber, y si la
        # serie llega siquiera al final del horizonte.
        cobertura[j] = min(1.0, hs.size / esperadas)
        if s.t[s.n - 1] < limite:
            estado[j] = PENDIENTE
        elif cobertura[j] >= cobertura_min:
            estado[j] = COMPLETO
        else:
            estado[j] = INCOMPLETO

        up = pe * (1.0 + tp_pct[j] / 100.0)
        dn = pe * (1.0 - sl_pct[j] / 100.0)

        toco_up = hs >= up
        toco_dn = ls <= dn
        i_up = int(np.argmax(toco_up)) if toco_up.any() else -1
        i_dn = int(np.argmax(toco_dn)) if toco_dn.any() else -1

        # Momento del primer toque del TP, ocurra antes o despues del SL. Se
        # conserva porque es informacion real del recorrido, pero `tp_primero`
        # es lo unico que autoriza a contarlo como acierto.
        if i_up >= 0:
            ms_tp[j] = int(ts[i_up] - s.t[i])

        if i_up < 0 and i_dn < 0:
            k = hs.size - 1
            etiqueta[j] = 0
            precio_sal = s.c[i + 1 + k]
        elif i_dn < 0 or (i_up >= 0 and i_up < i_dn):
            k = i_up
            etiqueta[j] = 1
            tp_primero[j] = 1
            precio_sal = up
        elif i_up < 0 or i_dn < i_up:
            k = i_dn
            etiqueta[j] = -1
            precio_sal = dn
        else:
            # Misma vela: no se puede saber el orden con OHLC.
            # Conservador: se asume SL. Se marca para poder cuantificar el sesgo.
            k = i_up
            etiqueta[j] = -1
            precio_sal = dn
            ambiguo[j] = 1

        t1_idx[j] = i + 1 + k
        ret[j] = (precio_sal - pe) / pe * 100.0
        mfe_sal[j] = (hs[:k + 1].max() - pe) / pe * 100.0
        mae_sal[j] = (ls[:k + 1].min() - pe) / pe * 100.0
        mfe_ven[j] = (hs.max() - pe) / pe * 100.0
        mae_ven[j] = (ls.min() - pe) / pe * 100.0

    # Concurrencia: cuantas etiquetas estan vivas en cada evento
    conc = np.zeros(m, dtype=np.int64)
    for j in range(m):
        conc[j] = int(np.sum((eventos <= eventos[j]) & (t1_idx > eventos[j])))

    return {"etiqueta": etiqueta, "t1_idx": t1_idx, "ret": ret,
            "mfe_salida": mfe_sal, "mae_salida": mae_sal,
            "mfe_ventana": mfe_ven, "mae_ventana": mae_ven,
            "ms_a_tp": ms_tp, "tp_primero": tp_primero,
            "ambiguo": ambiguo, "conc": conc,
            "estado": estado, "cobertura": cobertura}


# =============================================================================
#  Orquestacion
# =============================================================================

_VELAS_HORA = {"1m": 60, "3m": 20, "5m": 12, "15m": 4, "1h": 1}
_MS_INTERVALO = {"1m": 60_000, "3m": 180_000, "5m": 300_000,
                 "15m": 900_000, "1h": 3_600_000}


def nombre_politica(modo: str, k_tp: float, k_sl: float,
                    tp_fijo: float, sl_fijo: float) -> str:
    """Identidad legible de la politica de salida. Entra en la PK."""
    if modo == "atr":
        return f"atr:{k_tp:g}/{k_sl:g}"
    return f"fijo:{tp_fijo:g}/{sl_fijo:g}"


def etiquetar(
    db_path: str, symbols: List[str], interval: str,
    modo: str = "atr", k_tp: float = 2.0, k_sl: float = 1.5,
    tp_fijo: float = 3.2, sl_fijo: float = 2.0,
    horizonte_h: float = 8.0, cusum_k: float = 1.0,
) -> dict:
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_LABELS)

    vph = _VELAS_HORA.get(interval, 60)
    intervalo_ms = _MS_INTERVALO.get(interval, 60_000)
    horizonte_ms = int(horizonte_h * 3_600_000)
    horizonte_min = int(round(horizonte_h * 60))
    horizonte_velas = int(horizonte_h * vph)      # solo para filtrar eventos
    velas_dia = vph * 24
    politica = nombre_politica(modo, k_tp, k_sl, tp_fijo, sl_fijo)

    # Los eventos no pueden salir de la zona en la que las medias todavia se
    # estan expandiendo: ahi la feature es causal pero tiene poca muestra. Se
    # exige el mayor de los dos calentamientos, no `velas_dia // 24`, que eran
    # 60 velas contra una zona de 500.
    calentamiento = max(VENTANA_ATR_REL, VENTANA_VOL_REL, velas_dia)

    stats = {"simbolos": 0, "eventos": 0, "tp": 0, "sl": 0, "exp": 0, "amb": 0,
             "completos": 0, "incompletos": 0, "pendientes": 0}
    t0 = time.monotonic()

    for si, sym in enumerate(symbols, 1):
        s = cargar(conn, sym, interval)
        if s is None:
            continue
        atr = atr_pct(s)
        btc = regimen_btc(conn, interval, s.t, velas_dia) if sym != "BTCUSDT" else None
        feats = calcular_features(s, atr, vph, btc)

        # Umbral CUSUM proporcional a la volatilidad de cada momento
        umbral = np.maximum(atr / 100.0 * cusum_k, 1e-4)
        ev = eventos_cusum(s.c, umbral)
        ev = ev[(ev > calentamiento) & (ev < s.n - horizonte_velas - 1)]
        if ev.size == 0:
            continue

        if modo == "atr":
            tp = np.maximum(atr[ev] * k_tp, 0.2)
            sl = np.maximum(atr[ev] * k_sl, 0.15)
        else:
            tp = np.full(ev.size, tp_fijo)
            sl = np.full(ev.size, sl_fijo)

        r = triple_barrera(s, ev, tp, sl, horizonte_ms, intervalo_ms)

        filas = [
            (sym, interval, int(s.t[ev[j]]), horizonte_min, politica,
             EVALUADOR_VERSION,
             int(s.t[r["t1_idx"][j]]),
             float(s.c[ev[j]]),
             float(s.c[ev[j]] * (1 + r["ret"][j] / 100.0)),
             float(tp[j]), float(sl[j]),
             int(r["etiqueta"][j]), float(r["ret"][j]),
             float(r["mfe_salida"][j]), float(r["mae_salida"][j]),
             float(r["mfe_ventana"][j]), float(r["mae_ventana"][j]),
             (int(r["ms_a_tp"][j]) if r["ms_a_tp"][j] >= 0 else None),
             int(r["tp_primero"][j]), int(r["ambiguo"][j]), int(r["conc"][j]),
             str(r["estado"][j]), float(r["cobertura"][j]),
             float(feats["f_pct_dia"][ev[j]]), float(feats["f_pos_dia"][ev[j]]),
             float(feats["f_atr_rel"][ev[j]]), float(feats["f_vol_rel"][ev[j]]),
             float(feats["f_ret_1h"][ev[j]]), float(feats["f_dist_max20"][ev[j]]),
             float(feats["f_btc_reg"][ev[j]]))
            for j in range(ev.size)
        ]
        if filas and len(filas[0]) != len(COLUMNAS_LABELS):
            raise ValueError(
                f"la fila tiene {len(filas[0])} valores y COLUMNAS_LABELS "
                f"declara {len(COLUMNAS_LABELS)}"
            )
        conn.executemany(_INSERT_LABELS, filas)
        conn.commit()

        stats["simbolos"] += 1
        stats["eventos"] += ev.size
        stats["tp"] += int((r["etiqueta"] == 1).sum())
        stats["sl"] += int((r["etiqueta"] == -1).sum())
        stats["exp"] += int((r["etiqueta"] == 0).sum())
        stats["amb"] += int(r["ambiguo"].sum())
        stats["completos"] += int((r["estado"] == COMPLETO).sum())
        stats["incompletos"] += int((r["estado"] == INCOMPLETO).sum())
        stats["pendientes"] += int((r["estado"] == PENDIENTE).sum())

        if si % 10 == 0 or si == len(symbols):
            print(f"  {si}/{len(symbols)} | {stats['eventos']:,} eventos | "
                  f"{time.monotonic() - t0:.0f}s")

    n = max(stats["eventos"], 1)
    print(f"\n{stats['simbolos']} simbolos, {stats['eventos']:,} eventos")
    print(f"  politica {politica} | horizonte {horizonte_min} min | "
          f"evaluador v{EVALUADOR_VERSION}")
    print(f"  TP  {stats['tp']:>8,} ({stats['tp']/n:6.1%})")
    print(f"  SL  {stats['sl']:>8,} ({stats['sl']/n:6.1%})")
    print(f"  EXP {stats['exp']:>8,} ({stats['exp']/n:6.1%})")
    print(f"  ambiguos intra-vela: {stats['amb']:,} ({stats['amb']/n:.1%})")
    print(f"  calidad: {stats['completos']:,} completos, "
          f"{stats['incompletos']:,} con huecos, {stats['pendientes']:,} sin "
          f"horizonte entero")
    if stats["amb"] / n > 0.05:
        print("  ⚠ ambiguedad >5%: las etiquetas estan sesgadas hacia SL.")
        print("    Para conclusiones firmes hace falta 1s klines o aggTrades.")
    if stats["incompletos"] / n > 0.05:
        print("  ⚠ mas del 5% de las etiquetas tiene huecos en su horizonte.")
        print("    Filtra por estado='COMPLETO' antes de sacar conclusiones.")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Etiquetado triple barrera + MFE/MAE")
    ap.add_argument("--db", default="research/data/history.db")
    ap.add_argument("--symbols", help="coma-separado; vacio = todos los de la DB")
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--modo", choices=["atr", "fijo"], default="atr")
    ap.add_argument("--k-tp", type=float, default=2.0, help="TP = k * ATR%%")
    ap.add_argument("--k-sl", type=float, default=1.5, help="SL = k * ATR%%")
    ap.add_argument("--tp-fijo", type=float, default=3.2)
    ap.add_argument("--sl-fijo", type=float, default=2.0)
    ap.add_argument("--horizonte-h", type=float, default=8.0)
    ap.add_argument("--cusum-k", type=float, default=1.0)
    a = ap.parse_args(argv)

    conn = sqlite3.connect(a.db)
    cols = _columnas_klines(conn)
    campo_tf = "tf" if "tf" in cols else "interval"
    if a.symbols:
        syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    else:
        syms = [r[0] for r in conn.execute(
            f"SELECT DISTINCT symbol FROM klines WHERE {campo_tf}=? ORDER BY symbol",
            (a.interval,))]
    conn.close()
    if not syms:
        print("No hay simbolos en la DB para ese intervalo.")
        return 1

    print(f"Etiquetando {len(syms)} simbolos | modo={a.modo} | "
          f"horizonte={a.horizonte_h}h")
    etiquetar(a.db, syms, a.interval, a.modo, a.k_tp, a.k_sl,
              a.tp_fijo, a.sl_fijo, a.horizonte_h, a.cusum_k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
