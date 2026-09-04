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

SCHEMA_LABELS = """
CREATE TABLE IF NOT EXISTS labels (
    symbol        TEXT    NOT NULL,
    interval      TEXT    NOT NULL,
    t0            INTEGER NOT NULL,     -- ms del evento (entrada)
    t1            INTEGER,              -- ms de salida
    precio_e      REAL    NOT NULL,     -- precio de entrada
    precio_s      REAL,                 -- precio de salida
    tp_pct        REAL,                 -- barrera superior usada (%)
    sl_pct        REAL,                 -- barrera inferior usada (%)
    horizonte     INTEGER,              -- velas de la barrera temporal
    etiqueta      INTEGER,              -- 1=TP  -1=SL  0=expiro
    ret_pct       REAL,                 -- retorno realizado
    mfe_pct       REAL,                 -- maximo favorable
    mae_pct       REAL,                 -- maximo adverso
    velas_a_tp    INTEGER,              -- velas hasta tocar TP (NULL si no)
    ambiguo       INTEGER DEFAULT 0,    -- TP y SL en la misma vela
    concurrencia  INTEGER,              -- etiquetas vivas simultaneas
    -- features del estado en t0
    f_pct_dia     REAL,
    f_pos_dia     REAL,
    f_atr_rel     REAL,
    f_vol_rel     REAL,
    f_ret_1h      REAL,
    f_dist_max20  REAL,
    f_btc_reg     REAL,
    PRIMARY KEY (symbol, interval, t0)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_lab_t0 ON labels (t0);
CREATE INDEX IF NOT EXISTS idx_lab_sym ON labels (symbol, t0);
"""


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


def cargar(conn: sqlite3.Connection, symbol: str, interval: str) -> Optional[Serie]:
    cur = conn.execute(
        """SELECT open_time, open, high, low, close, quote_volume
           FROM klines WHERE symbol=? AND interval=? ORDER BY open_time""",
        (symbol, interval),
    )
    filas = cur.fetchall()
    if len(filas) < 500:
        return None
    a = np.array(filas, dtype=float)
    return Serie(t=a[:, 0].astype(np.int64), o=a[:, 1], h=a[:, 2],
                 l=a[:, 3], c=a[:, 4], v=a[:, 5], n=len(filas))


# =============================================================================
#  Indicadores auxiliares
# =============================================================================

def atr_pct(s: Serie, period: int = 14) -> np.ndarray:
    """ATR como % del precio. atr[i] usa datos hasta i inclusive."""
    tr = np.empty(s.n)
    tr[0] = s.h[0] - s.l[0]
    tr[1:] = np.maximum(
        s.h[1:] - s.l[1:],
        np.maximum(np.abs(s.h[1:] - s.c[:-1]), np.abs(s.l[1:] - s.c[:-1])),
    )
    k = np.ones(period) / period
    suave = np.convolve(tr, k, mode="full")[:s.n]
    suave[:period] = tr[:period].mean() if period <= s.n else tr.mean()
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
    ch = cl = -np.inf, np.inf
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
    win = min(500, max(50, n // 10))
    k = np.ones(win) / win
    atr_med = np.convolve(atr, k, mode="full")[:n]
    atr_med[:win] = atr[:win].mean() if win <= n else atr.mean()
    atr_rel = np.where(atr_med > 0, atr / np.maximum(atr_med, 1e-12), 1.0)

    # Volumen relativo
    wv = min(200, max(30, n // 20))
    kv = np.ones(wv) / wv
    vol_med = np.convolve(s.v, kv, mode="full")[:n]
    vol_med[:wv] = s.v[:wv].mean() if wv <= n else s.v.mean()
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
    horizonte: int,
) -> Dict[str, np.ndarray]:
    """
    Para cada evento devuelve que barrera se toco primero, mas MFE/MAE.
    tp_pct / sl_pct son arrays por evento (positivos, en %).
    """
    m = eventos.size
    etiqueta = np.zeros(m, dtype=np.int8)
    t1_idx = np.zeros(m, dtype=np.int64)
    ret = np.zeros(m); mfe = np.zeros(m); mae = np.zeros(m)
    velas_tp = np.full(m, -1, dtype=np.int64)
    ambiguo = np.zeros(m, dtype=np.int8)

    for j in range(m):
        i = int(eventos[j])
        fin = min(i + horizonte, s.n - 1)
        if fin <= i:
            t1_idx[j] = i
            continue
        pe = s.c[i]
        hs = s.h[i + 1:fin + 1]
        ls = s.l[i + 1:fin + 1]
        if hs.size == 0:
            t1_idx[j] = i
            continue

        up = pe * (1.0 + tp_pct[j] / 100.0)
        dn = pe * (1.0 - sl_pct[j] / 100.0)

        toco_up = hs >= up
        toco_dn = ls <= dn
        i_up = int(np.argmax(toco_up)) if toco_up.any() else -1
        i_dn = int(np.argmax(toco_dn)) if toco_dn.any() else -1

        if i_up >= 0:
            velas_tp[j] = i_up + 1

        if i_up < 0 and i_dn < 0:
            k = hs.size - 1
            etiqueta[j] = 0
            precio_sal = s.c[i + 1 + k]
        elif i_dn < 0 or (i_up >= 0 and i_up < i_dn):
            k = i_up
            etiqueta[j] = 1
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
        mfe[j] = (hs[:k + 1].max() - pe) / pe * 100.0
        mae[j] = (ls[:k + 1].min() - pe) / pe * 100.0

    # Concurrencia: cuantas etiquetas estan vivas en cada evento
    conc = np.zeros(m, dtype=np.int64)
    for j in range(m):
        conc[j] = int(np.sum((eventos <= eventos[j]) & (t1_idx > eventos[j])))

    return {"etiqueta": etiqueta, "t1_idx": t1_idx, "ret": ret, "mfe": mfe,
            "mae": mae, "velas_tp": velas_tp, "ambiguo": ambiguo, "conc": conc}


# =============================================================================
#  Orquestacion
# =============================================================================

_VELAS_HORA = {"1m": 60, "3m": 20, "5m": 12, "15m": 4, "1h": 1}


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
    horizonte = int(horizonte_h * vph)
    velas_dia = vph * 24

    stats = {"simbolos": 0, "eventos": 0, "tp": 0, "sl": 0, "exp": 0, "amb": 0}
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
        ev = ev[(ev > velas_dia // 24) & (ev < s.n - horizonte - 1)]
        if ev.size == 0:
            continue

        if modo == "atr":
            tp = np.maximum(atr[ev] * k_tp, 0.2)
            sl = np.maximum(atr[ev] * k_sl, 0.15)
        else:
            tp = np.full(ev.size, tp_fijo)
            sl = np.full(ev.size, sl_fijo)

        r = triple_barrera(s, ev, tp, sl, horizonte)

        filas = [
            (sym, interval, int(s.t[ev[j]]), int(s.t[r["t1_idx"][j]]),
             float(s.c[ev[j]]),
             float(s.c[ev[j]] * (1 + r["ret"][j] / 100.0)),
             float(tp[j]), float(sl[j]), horizonte,
             int(r["etiqueta"][j]), float(r["ret"][j]),
             float(r["mfe"][j]), float(r["mae"][j]),
             int(r["velas_tp"][j]), int(r["ambiguo"][j]), int(r["conc"][j]),
             float(feats["f_pct_dia"][ev[j]]), float(feats["f_pos_dia"][ev[j]]),
             float(feats["f_atr_rel"][ev[j]]), float(feats["f_vol_rel"][ev[j]]),
             float(feats["f_ret_1h"][ev[j]]), float(feats["f_dist_max20"][ev[j]]),
             float(feats["f_btc_reg"][ev[j]]))
            for j in range(ev.size)
        ]
        conn.executemany(
            f"INSERT OR REPLACE INTO labels VALUES ({','.join('?' * 23)})", filas
        )
        conn.commit()

        stats["simbolos"] += 1
        stats["eventos"] += ev.size
        stats["tp"] += int((r["etiqueta"] == 1).sum())
        stats["sl"] += int((r["etiqueta"] == -1).sum())
        stats["exp"] += int((r["etiqueta"] == 0).sum())
        stats["amb"] += int(r["ambiguo"].sum())

        if si % 10 == 0 or si == len(symbols):
            print(f"  {si}/{len(symbols)} | {stats['eventos']:,} eventos | "
                  f"{time.monotonic() - t0:.0f}s")

    n = max(stats["eventos"], 1)
    print(f"\n{stats['simbolos']} simbolos, {stats['eventos']:,} eventos")
    print(f"  TP  {stats['tp']:>8,} ({stats['tp']/n:6.1%})")
    print(f"  SL  {stats['sl']:>8,} ({stats['sl']/n:6.1%})")
    print(f"  EXP {stats['exp']:>8,} ({stats['exp']/n:6.1%})")
    print(f"  ambiguos intra-vela: {stats['amb']:,} ({stats['amb']/n:.1%})")
    if stats["amb"] / n > 0.05:
        print("  ⚠ ambiguedad >5%: las etiquetas estan sesgadas hacia SL.")
        print("    Para conclusiones firmes hace falta 1s klines o aggTrades.")
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
    if a.symbols:
        syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    else:
        syms = [r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval=? ORDER BY symbol",
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
