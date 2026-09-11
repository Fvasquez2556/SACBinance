"""
CAPA 2 (b) — Probabilidades por conteo empirico de analogos.

No hay modelo entrenado. El vector de estado se discretiza en celdas, y la
probabilidad de una consulta es la frecuencia observada en su celda. Eso lo
hace auditable: siempre se puede pedir "mostrame los casos".

Las tres cosas que este modulo se niega a ocultar
-------------------------------------------------
1. EL n. Una celda con 12 casos no produce un "83%": produce "no se". El
   umbral `n_min` es duro y las consultas por debajo devuelven SIN_DATOS.

2. LA TASA BASE. Si el 40% de los eventos llegan a TP sin condicionar por
   nada, un modelo que acierta 45% aporta casi cero. Todo se reporta como
   lift sobre la tasa base, no en absoluto.

3. LA DESCOMPOSICION DEL BRIER. El Brier mezcla calibracion y discriminacion:
   un modelo que predice la tasa base para todo sale perfectamente calibrado
   y es inutil. Por eso se reporta reliability (calibracion, menor mejor) y
   resolution (discriminacion, mayor mejor) por separado. Un sistema con
   resolution ~0 no sirve aunque su Brier se vea bien.

Validacion
----------
Se usa split temporal con PURGA: se eliminan del entrenamiento las etiquetas
cuyo intervalo [t0, t1] se solapa con el periodo de prueba. Sin eso, la
superposicion de etiquetas filtra el futuro al pasado y todo sale hermoso y
falso. Se anade un embargo posterior por la autocorrelacion.

Nota: la literatura reciente encuentra que Combinatorial Purged CV supera a
walk-forward en prevencion de falsos descubrimientos. Esto implementa la
version simple (purga + embargo sobre un split temporal). Para el paso
siguiente existe `purgedcv` en PyPI, compatible con scikit-learn.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

FEATURES = ["f_pct_dia", "f_pos_dia", "f_atr_rel", "f_vol_rel",
            "f_ret_1h", "f_dist_max20", "f_btc_reg"]

# Cortes por defecto. Menos features y menos cortes = celdas mas pobladas.
CORTES_DEFAULT: Dict[str, List[float]] = {
    "f_pct_dia":    [-3.0, 0.0, 5.0, 12.0],
    "f_pos_dia":    [0.25, 0.60, 0.90],
    "f_atr_rel":    [0.7, 1.0, 1.5],
    "f_vol_rel":    [0.8, 1.5, 3.0],
    "f_ret_1h":     [-1.0, 0.0, 1.0],
    "f_dist_max20": [-3.0, -1.0, -0.2],
    "f_btc_reg":    [-2.0, 0.0, 2.0],
}


@dataclass
class Consulta:
    n: int = 0
    # Filas frente a observaciones INDEPENDIENTES. Con etiquetas superpuestas
    # las dos cifras se separan mucho, y la que decide es la segunda.
    n_efectivo: float = 0.0
    p_tp: Optional[float] = None
    p_sl: Optional[float] = None
    p_exp: Optional[float] = None
    ret_medio: Optional[float] = None
    mfe_medio: Optional[float] = None
    mae_medio: Optional[float] = None
    mae_p90: Optional[float] = None       # drawdown a tolerar en el 90% de casos
    esperanza: Optional[float] = None
    lift: Optional[float] = None          # p_tp / tasa_base
    suficiente: bool = False
    celda: str = ""

    def __str__(self) -> str:
        if not self.suficiente:
            return f"SIN_DATOS (n={self.n}) celda={self.celda}"
        return (f"n={self.n} | TP {self.p_tp:.1%} SL {self.p_sl:.1%} "
                f"EXP {self.p_exp:.1%} | lift {self.lift:.2f}x | "
                f"E[ret]={self.esperanza:+.2f}% | "
                f"MFE {self.mfe_medio:+.2f}% MAE {self.mae_medio:+.2f}% "
                f"(p90 {self.mae_p90:+.2f}%)")


# =============================================================================
#  Carga y discretizacion
# =============================================================================

def cargar_labels(db: str, features: Sequence[str],
                  horizonte_min: Optional[int] = None,
                  politica: Optional[str] = None,
                  evaluador: Optional[int] = None,
                  solo_completos: bool = True) -> dict:
    """
    Lee las etiquetas de UNA evaluacion concreta.

    Desde que `labels` distingue horizonte, politica y version del evaluador,
    la tabla contiene varias evaluaciones a la vez. Leerla entera mezclaria
    horizontes de 4h con los de 8h y stops por ATR con stops fijos en la misma
    frecuencia — que es exactamente el error que la identidad nueva vino a
    evitar. Si no se especifica cual, se exige que solo haya una.

    `solo_completos` descarta las etiquetas cuyo horizonte tiene huecos o
    todavia no ha terminado: una frecuencia calculada sobre ventanas a medias
    no es una frecuencia mas ruidosa, es otra cosa.
    """
    conn = sqlite3.connect(db)
    combos = conn.execute(
        "SELECT DISTINCT horizonte_min, politica, evaluador FROM labels"
    ).fetchall()
    if not combos:
        conn.close()
        raise SystemExit("No hay etiquetas. Corre research/labeling.py primero.")

    sel = [c for c in combos
           if (horizonte_min is None or c[0] == horizonte_min)
           and (politica is None or c[1] == politica)
           and (evaluador is None or c[2] == evaluador)]
    if not sel:
        conn.close()
        raise SystemExit(
            f"Ninguna evaluacion coincide. Disponibles: {combos}")
    if len(sel) > 1:
        conn.close()
        raise SystemExit(
            "La base tiene varias evaluaciones y mezclarlas daria una "
            "frecuencia sin sentido. Elige una con --horizonte-min / "
            f"--politica / --evaluador. Disponibles: {sel}")
    h, pol, ev = sel[0]

    cols = ", ".join(features)
    filtro = "WHERE horizonte_min=? AND politica=? AND evaluador=?"
    params = [h, pol, ev]
    if solo_completos:
        filtro += " AND estado='COMPLETO'"
    cur = conn.execute(
        f"""SELECT t0, t1, etiqueta, ret_pct, mfe_salida, mae_salida, ambiguo,
                   concurrencia, mfe_ventana, {cols}
            FROM labels {filtro} ORDER BY t0""", params
    )
    filas = cur.fetchall()
    conn.close()
    if not filas:
        raise SystemExit(
            f"La evaluacion {pol} a {h} min no tiene etiquetas"
            + (" con estado COMPLETO." if solo_completos else "."))
    a = np.array(filas, dtype=float)
    return {
        "t0": a[:, 0].astype(np.int64), "t1": a[:, 1].astype(np.int64),
        "y": a[:, 2].astype(np.int8), "ret": a[:, 3], "mfe": a[:, 4],
        "mae": a[:, 5], "amb": a[:, 6].astype(np.int8),
        "conc": np.maximum(a[:, 7], 1.0), "mfe_ventana": a[:, 8],
        "X": a[:, 9:],
        "evaluacion": {"horizonte_min": int(h), "politica": pol,
                       "evaluador": int(ev), "solo_completos": solo_completos},
    }


def discretizar(X: np.ndarray, features: Sequence[str],
                cortes: Dict[str, List[float]]) -> np.ndarray:
    """Devuelve un id de celda entero por fila."""
    ids = np.zeros(X.shape[0], dtype=np.int64)
    mult = 1
    for k, f in enumerate(features):
        b = np.array(cortes[f], dtype=float)
        idx = np.searchsorted(b, X[:, k], side="right")
        ids += idx * mult
        mult *= (b.size + 1)
    return ids


def etiqueta_celda(x: Sequence[float], features: Sequence[str],
                   cortes: Dict[str, List[float]]) -> str:
    partes = []
    for k, f in enumerate(features):
        b = cortes[f]
        i = int(np.searchsorted(np.array(b), x[k], side="right"))
        lo = "-inf" if i == 0 else f"{b[i-1]}"
        hi = "+inf" if i == len(b) else f"{b[i]}"
        partes.append(f"{f}[{lo},{hi})")
    return " ".join(partes)


# =============================================================================
#  Tabla de frecuencias
# =============================================================================

class TablaFrecuencias:
    def __init__(self, features: Sequence[str], cortes: Dict[str, List[float]],
                 n_min: int = 200, ponderar_unicidad: bool = True):
        self.features = list(features)
        self.cortes = cortes
        self.n_min = n_min
        self.ponderar = ponderar_unicidad
        self.tabla: Dict[int, dict] = {}
        self.tasa_base: float = 0.0
        self.n_total: int = 0

    def entrenar(self, d: dict, mask: Optional[np.ndarray] = None) -> None:
        m = np.ones(d["y"].size, dtype=bool) if mask is None else mask
        y, ret, mfe, mae = d["y"][m], d["ret"][m], d["mfe"][m], d["mae"][m]
        # Ponderacion por unicidad: etiquetas superpuestas no son
        # observaciones independientes; se pondera 1/concurrencia.
        w = (1.0 / d["conc"][m]) if self.ponderar else np.ones(y.size)
        ids = discretizar(d["X"][m], self.features, self.cortes)

        self.n_total = int(y.size)
        self.tasa_base = float(np.average(y == 1, weights=w)) if y.size else 0.0

        self.tabla = {}
        for cid in np.unique(ids):
            sel = ids == cid
            ws = w[sel]
            sw = float(ws.sum())
            if sw <= 0:
                continue
            # Tamaño efectivo de muestra (Kish): (sum w)^2 / sum w^2. Con
            # etiquetas superpuestas, mil filas que se solapan casi del todo
            # valen como unas pocas observaciones independientes. Contar filas
            # dejaba pasar celdas que parecian robustas y no lo eran.
            n_ef = float(sw * sw / max(float((ws * ws).sum()), 1e-12))
            self.tabla[int(cid)] = {
                "n": int(sel.sum()),
                "n_efectivo": n_ef,
                "p_tp": float(np.average(y[sel] == 1, weights=ws)),
                "p_sl": float(np.average(y[sel] == -1, weights=ws)),
                "p_exp": float(np.average(y[sel] == 0, weights=ws)),
                "ret": float(np.average(ret[sel], weights=ws)),
                "mfe": float(np.average(mfe[sel], weights=ws)),
                "mae": float(np.average(mae[sel], weights=ws)),
                "mae_p90": float(np.percentile(mae[sel], 10)),  # cola adversa
            }

    def consultar(self, x: Sequence[float]) -> Consulta:
        cid = int(discretizar(np.array([x], dtype=float), self.features, self.cortes)[0])
        c = Consulta(celda=etiqueta_celda(x, self.features, self.cortes))
        e = self.tabla.get(cid)
        if e is None:
            return c
        c.n = e["n"]
        c.n_efectivo = e["n_efectivo"]
        if e["n_efectivo"] < self.n_min:
            return c            # suficiente = False -> SIN_DATOS
        c.suficiente = True
        c.p_tp, c.p_sl, c.p_exp = e["p_tp"], e["p_sl"], e["p_exp"]
        c.ret_medio, c.mfe_medio = e["ret"], e["mfe"]
        c.mae_medio, c.mae_p90 = e["mae"], e["mae_p90"]
        c.esperanza = e["ret"]
        c.lift = e["p_tp"] / self.tasa_base if self.tasa_base > 0 else None
        return c

    def p_tp_array(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """(probabilidades, mascara de celdas con n suficiente)."""
        ids = discretizar(X, self.features, self.cortes)
        p = np.full(ids.size, self.tasa_base)
        ok = np.zeros(ids.size, dtype=bool)
        for i, cid in enumerate(ids):
            e = self.tabla.get(int(cid))
            if e is not None and e["n_efectivo"] >= self.n_min:
                p[i] = e["p_tp"]
                ok[i] = True
        return p, ok


# =============================================================================
#  Calibracion
# =============================================================================

def brier_descompuesto(p: np.ndarray, y: np.ndarray, bins: int = 10) -> dict:
    """
    Brier = Reliability - Resolution + Uncertainty.
    reliability bajo = bien calibrado. resolution alto = discrimina.
    resolution ~ 0 significa que el modelo solo repite la tasa base.
    """
    n = p.size
    if n == 0:
        return {}
    base = float(y.mean())
    bs = float(np.mean((p - y) ** 2))
    bordes = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, bordes[1:-1]), 0, bins - 1)
    rel = res = 0.0
    filas = []
    for k in range(bins):
        sel = idx == k
        nk = int(sel.sum())
        if nk == 0:
            continue
        pk, ok_ = float(p[sel].mean()), float(y[sel].mean())
        rel += nk * (pk - ok_) ** 2
        res += nk * (ok_ - base) ** 2
        filas.append((k, nk, pk, ok_))
    return {"brier": bs, "reliability": rel / n, "resolution": res / n,
            "uncertainty": base * (1 - base), "base": base, "bins": filas}


def split_purgado(d: dict, frac_train: float = 0.7,
                  embargo_frac: float = 0.01) -> Tuple[np.ndarray, np.ndarray]:
    """
    Split temporal con purga y embargo.
    - Test = ultimo (1-frac_train) del tiempo.
    - Purga: se quitan del train las etiquetas cuyo t1 entra en el test.
    - Embargo: margen extra antes del test.
    """
    t0, t1 = d["t0"], d["t1"]
    orden = np.argsort(t0)
    corte = t0[orden[int(len(orden) * frac_train)]]
    span = int(t0.max() - t0.min())
    emb = int(span * embargo_frac)

    test = t0 >= corte
    train = (t0 < corte - emb) & (t1 < corte - emb)   # purga + embargo
    return train, test


# =============================================================================
#  Reportes
# =============================================================================

def reporte(db: str, features: Sequence[str], n_min: int,
            frac_train: float, horizonte_min: Optional[int] = None,
            politica: Optional[str] = None, evaluador: Optional[int] = None,
            solo_completos: bool = True) -> None:
    d = cargar_labels(db, features, horizonte_min, politica, evaluador,
                      solo_completos)
    n = d["y"].size
    ev = d["evaluacion"]

    print("=" * 68)
    print(f"TASA BASE  —  {n:,} eventos etiquetados")
    # Sin esto, dos reportes con numeros distintos parecen un cambio de
    # mercado cuando en realidad son horizontes o politicas distintas.
    print(f"evaluacion: politica {ev['politica']} | horizonte "
          f"{ev['horizonte_min']} min | evaluador v{ev['evaluador']}"
          + ("" if ev["solo_completos"] else " | INCLUYE ventanas incompletas"))
    print("=" * 68)
    for lab, val in (("TP", 1), ("SL", -1), ("EXPIRO", 0)):
        m = d["y"] == val
        print(f"  {lab:<7} {m.sum():>9,}  {m.mean():>6.1%}")
    print(f"  ambiguos intra-vela: {d['amb'].mean():.1%}")
    print(f"\n  MFE medio {d['mfe'].mean():+.2f}%   MAE medio {d['mae'].mean():+.2f}%")
    print(f"  MAE p10 (cola adversa) {np.percentile(d['mae'], 10):+.2f}%")
    print(f"  MFE p90 (cola favorable) {np.percentile(d['mfe'], 90):+.2f}%")
    print("\n  → Cualquier modelo debe superar la tasa base de TP para aportar algo.")

    print("\n" + "=" * 68)
    print("DISTRIBUCION DE MFE  (¿cuanto se deja sobre la mesa?)")
    print("=" * 68)
    for u in (1.0, 2.0, 3.2, 5.0, 8.0, 12.0):
        print(f"  MFE >= {u:>5.1f}% : {(d['mfe'] >= u).mean():>6.1%}")

    print("\n" + "=" * 68)
    print("VALIDACION CON PURGA Y EMBARGO")
    print("=" * 68)
    tr, te = split_purgado(d, frac_train)
    print(f"  train {tr.sum():,}  |  test {te.sum():,}  |  "
          f"purgados {n - tr.sum() - te.sum():,}")

    t = TablaFrecuencias(features, CORTES_DEFAULT, n_min=n_min)
    t.entrenar(d, tr)
    print(f"  celdas: {len(t.tabla):,} | con muestra efectiva >={n_min}: "
          f"{sum(1 for v in t.tabla.values() if v['n_efectivo'] >= n_min):,}")

    p, ok = t.p_tp_array(d["X"][te])
    y = (d["y"][te] == 1).astype(float)
    print(f"  cobertura (consultas con n suficiente): {ok.mean():.1%}")

    if ok.sum() > 50:
        r = brier_descompuesto(p[ok], y[ok])
        print(f"\n  Brier        {r['brier']:.4f}")
        print(f"  reliability  {r['reliability']:.4f}  (calibracion — menor mejor)")
        print(f"  resolution   {r['resolution']:.4f}  (discriminacion — mayor mejor)")
        print(f"  uncertainty  {r['uncertainty']:.4f}")
        if r["resolution"] < 0.002:
            print("\n  ⚠ resolution ~0: el modelo esta repitiendo la tasa base.")
            print("    Sale bien calibrado pero NO discrimina. No aporta nada.")
        print("\n  Diagrama de fiabilidad (predicho vs observado):")
        for k, nk, pk, okk in r["bins"]:
            barra = "█" * int(okk * 40)
            print(f"    {pk:5.1%} → {okk:5.1%}  n={nk:>6,}  {barra}")

    print("\n" + "=" * 68)
    print("MEJORES CELDAS POR ESPERANZA  (solo n suficiente)")
    print("=" * 68)
    filas = [(cid, e) for cid, e in t.tabla.items()
             if e["n_efectivo"] >= n_min]
    filas.sort(key=lambda x: x[1]["ret"], reverse=True)
    print(f"  {'n':>8} {'TP':>7} {'lift':>6} {'E[ret]':>8} {'MAE p10':>9}")
    for cid, e in filas[:10]:
        lift = e["p_tp"] / t.tasa_base if t.tasa_base > 0 else 0
        print(f"  {e['n']:>8,} {e['p_tp']:>6.1%} {lift:>5.2f}x "
              f"{e['ret']:>+7.2f}% {e['mae_p90']:>+8.2f}%")
    if not filas:
        print("  Ninguna celda alcanza el n minimo. Reduce features o cortes.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Probabilidades por conteo de analogos")
    ap.add_argument("--db", default="research/data/history.db")
    ap.add_argument("--features", default=",".join(FEATURES[:4]),
                    help="menos features = celdas mas pobladas")
    ap.add_argument("--n-min", type=int, default=200,
                    help="muestra EFECTIVA minima por celda (Kish), no filas")
    ap.add_argument("--horizonte-min", type=int,
                    help="horizonte de la evaluacion a leer, en minutos")
    ap.add_argument("--politica", help='p.ej. "fijo:3.2/2" o "atr:2/1.5"')
    ap.add_argument("--evaluador", type=int, help="version del evaluador")
    ap.add_argument("--incluir-incompletas", action="store_true",
                    help="no filtrar por estado=COMPLETO (no recomendado)")
    ap.add_argument("--frac-train", type=float, default=0.7)
    a = ap.parse_args(argv)

    feats = [f.strip() for f in a.features.split(",") if f.strip()]
    for f in feats:
        if f not in FEATURES:
            ap.error(f"feature desconocida: {f}. Validas: {FEATURES}")
    reporte(a.db, feats, a.n_min, a.frac_train, a.horizonte_min,
            a.politica, a.evaluador, not a.incluir_incompletas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
