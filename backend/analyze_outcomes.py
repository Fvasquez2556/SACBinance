"""
Informe de outcomes: ¿las señales llegan a donde el sistema dice?

Uso:
    python analyze_outcomes.py                 # solo señales con ventana cumplida
    python analyze_outcomes.py --incluir-vivas # incluye las aun en seguimiento
    python analyze_outcomes.py --dias 7        # ultimos N dias
    python analyze_outcomes.py --por tier      # desglose por tier/estado/taxonomia/macro

Lee la tabla `outcomes`, que sigue el camino de cada señal durante
outcome_window_hours SIN cerrarla al tocar TP/SL. Por eso puede responder
que hizo el precio DESPUES del stop, cosa que el win rate no ve.

Disciplina anti-autoengaño: con menos de MIN_MUESTRAS casos no se reportan
porcentajes por categoria, solo el recuento. Un 100% sobre 3 señales no es
un resultado, es ruido.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.analysis.outcome_tracker import ESCALERA, OBJETIVO, _SUFIJO  # noqa: E402
from src.persistence.db import Database  # noqa: E402

MIN_MUESTRAS = 15


def _dur(ms) -> str:
    if ms is None:
        return "—"
    m = ms / 60000.0
    if m < 60:
        return f"{m:.0f}min"
    if m < 1440:
        return f"{m/60:.1f}h"
    return f"{m/1440:.1f}d"


def _mediana(vals: list):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _pct(n: int, total: int) -> str:
    return f"{n/total*100:5.1f}%" if total else "    —"


def _linea(titulo: str) -> None:
    print(f"\n{titulo}")
    print("─" * 74)


def informe(rows: list, incluir_vivas: bool) -> None:
    total = len(rows)
    if not total:
        print("\nSin outcomes registrados todavia.")
        print("El sistema los va acumulando: cada señal necesita completar su")
        print("ventana de seguimiento antes de contar como cerrada.")
        return

    cerrados = [r for r in rows if r["cerrado"]]
    vivos = total - len(cerrados)
    print(f"\n{'=' * 74}")
    print(f"  INFORME DE OUTCOMES — {total} señales"
          + (f" ({len(cerrados)} con ventana cumplida, {vivos} en curso)" if vivos else ""))
    print(f"{'=' * 74}")

    if total < MIN_MUESTRAS:
        print(f"\n  ⚠  Solo {total} muestras. Por debajo de {MIN_MUESTRAS} los porcentajes")
        print("     no significan nada — se muestran los datos crudos igualmente,")
        print("     pero no conviene sacar conclusiones todavia.")

    # --- 1. ¿Llega al objetivo de +3.2%? ---
    suf_obj = _SUFIJO[OBJETIVO]
    llegaron = [r for r in rows if r.get(f"ms_up_{suf_obj}") is not None]
    _linea(f"1. ¿ALCANZA +{OBJETIVO}% DESDE LA ENTRADA SUGERIDA?")
    print(f"  Si  {len(llegaron):4d} / {total}   {_pct(len(llegaron), total)}")
    print(f"  No  {total-len(llegaron):4d} / {total}   {_pct(total-len(llegaron), total)}")
    if llegaron:
        tiempos = [r[f"ms_up_{suf_obj}"] for r in llegaron]
        print(f"\n  Tiempo hasta +{OBJETIVO}%:")
        print(f"    mediana {_dur(_mediana(tiempos))}   "
              f"mas rapida {_dur(min(tiempos))}   mas lenta {_dur(max(tiempos))}")
        bandas = [("< 15 min", 0, 15), ("15-60 min", 15, 60),
                  ("1-4 h", 60, 240), ("4-12 h", 240, 720), ("> 12 h", 720, 1e9)]
        print("\n  Reparto:")
        for nombre, lo, hi in bandas:
            n = sum(1 for t in tiempos if lo <= t / 60000.0 < hi)
            if n:
                print(f"    {nombre:11s} {n:4d}   {_pct(n, len(llegaron))}")

    # --- 2. Forma del camino ---
    _linea("2. ¿QUE PASO ANTES DE LLEGAR? (forma del camino)")
    formas = {}
    for r in rows:
        formas.setdefault(r.get("forma") or "EN_CURSO", []).append(r)
    etiquetas = {
        "DIRECTO": "Subio directo (sin retroceso relevante)",
        "DIP_Y_SUBE": f"Bajo primero y despues llego a +{OBJETIVO}%",
        "SOLO_BAJO": "Nunca llego, y cayo de forma relevante",
        "LATERAL": "Nunca llego, se quedo lateral",
        "EN_CURSO": "Aun en seguimiento",
    }
    for k in ("DIRECTO", "DIP_Y_SUBE", "SOLO_BAJO", "LATERAL", "EN_CURSO"):
        grupo = formas.get(k)
        if not grupo:
            continue
        print(f"  {etiquetas[k]:44s} {len(grupo):4d}   {_pct(len(grupo), total)}")
        if k == "DIP_Y_SUBE":
            dips = [r["dip_antes_obj"] for r in grupo if r.get("dip_antes_obj") is not None]
            if dips:
                print(f"      caida previa: mediana {_mediana(dips):+.2f}%   "
                      f"peor {min(dips):+.2f}%")
            recup = [r[f"ms_up_{suf_obj}"] for r in grupo if r.get(f"ms_up_{suf_obj}")]
            if recup:
                print(f"      tardo en llegar: mediana {_dur(_mediana(recup))}")

    # --- 3. Promesa del sistema: TP y SL ofrecidos ---
    _linea("3. ¿CUMPLE EL TP/SL QUE OFRECE?")
    con_tp = [r for r in rows if r.get("tp_pct")]
    if con_tp:
        toco_tp = [r for r in con_tp if r.get("ms_tp") is not None]
        toco_sl = [r for r in con_tp if r.get("ms_sl") is not None]
        tp_primero = [r for r in toco_tp
                      if r.get("ms_sl") is None or r["ms_tp"] < r["ms_sl"]]
        print(f"  TP ofrecido: mediana {_mediana([r['tp_pct'] for r in con_tp]):+.2f}%   "
              f"rango {min(r['tp_pct'] for r in con_tp):+.2f}% a "
              f"{max(r['tp_pct'] for r in con_tp):+.2f}%")
        print(f"\n  Toco el TP        {len(toco_tp):4d} / {len(con_tp)}   "
              f"{_pct(len(toco_tp), len(con_tp))}")
        print(f"  Toco el SL        {len(toco_sl):4d} / {len(con_tp)}   "
              f"{_pct(len(toco_sl), len(con_tp))}")
        print(f"  TP antes que SL   {len(tp_primero):4d} / {len(con_tp)}   "
              f"{_pct(len(tp_primero), len(con_tp))}")
        if toco_tp:
            print(f"\n  Tiempo hasta el TP: mediana "
                  f"{_dur(_mediana([r['ms_tp'] for r in toco_tp]))}")
        # Lo que el win rate NO ve
        rebotes = [r for r in toco_sl if r.get(f"ms_up_{suf_obj}") is not None
                   and r[f"ms_up_{suf_obj}"] > r["ms_sl"]]
        if toco_sl:
            print(f"\n  De las que tocaron SL, luego subieron a +{OBJETIVO}%: "
                  f"{len(rebotes)} / {len(toco_sl)}   {_pct(len(rebotes), len(toco_sl))}")
            print("    (esto es lo que el win rate por si solo no puede ver)")

    # --- 4. Escalera fija ---
    _linea("4. ESCALERA: ¿HASTA DONDE LLEGAN?")
    print(f"  {'umbral':>8s}  {'alcanzado':>19s}   {'mediana tiempo':>15s}")
    for u in ESCALERA:
        suf = _SUFIJO[u]
        alc = [r for r in rows if r.get(f"ms_up_{suf}") is not None]
        med = _mediana([r[f"ms_up_{suf}"] for r in alc])
        marca = "  ← objetivo" if u == OBJETIVO else ""
        print(f"  {'+' + str(u) + '%':>8s}  {len(alc):5d} / {total}  "
              f"{_pct(len(alc), total)}   {_dur(med):>15s}{marca}")
    print()
    for u in ESCALERA:
        suf = _SUFIJO[u]
        alc = [r for r in rows if r.get(f"ms_dn_{suf}") is not None]
        print(f"  {'-' + str(u) + '%':>8s}  {len(alc):5d} / {total}  {_pct(len(alc), total)}")

    # --- 5. Excursiones ---
    _linea("5. EXCURSIONES (lo maximo que se movio cada señal)")
    mfes = [r["mfe_pct"] for r in rows if r.get("mfe_pct") is not None]
    maes = [r["mae_pct"] for r in rows if r.get("mae_pct") is not None]
    if mfes:
        print(f"  Subida maxima (MFE):  mediana {_mediana(mfes):+6.2f}%   "
              f"mejor {max(mfes):+6.2f}%")
    if maes:
        print(f"  Bajada maxima (MAE):  mediana {_mediana(maes):+6.2f}%   "
              f"peor  {min(maes):+6.2f}%")


def desglose(rows: list, campo: str) -> None:
    suf_obj = _SUFIJO[OBJETIVO]
    grupos: dict = {}
    for r in rows:
        grupos.setdefault(r.get(campo) or "—", []).append(r)

    _linea(f"DESGLOSE POR {campo.upper()}")
    print(f"  {campo:16s} {'n':>5s}  {'llega a +' + str(OBJETIVO) + '%':>16s}  "
          f"{'mediana':>10s}  {'MFE med':>8s}")
    for k, g in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
        alc = [r for r in g if r.get(f"ms_up_{suf_obj}") is not None]
        med = _mediana([r[f"ms_up_{suf_obj}"] for r in alc])
        mfe = _mediana([r["mfe_pct"] for r in g if r.get("mfe_pct") is not None])
        ratio = _pct(len(alc), len(g)) if len(g) >= MIN_MUESTRAS else "  (pocas)"
        print(f"  {str(k):16s} {len(g):5d}  {ratio:>16s}  {_dur(med):>10s}  "
              f"{(f'{mfe:+.2f}%' if mfe is not None else '—'):>8s}")
    if any(len(g) < MIN_MUESTRAS for g in grupos.values()):
        print(f"\n  «(pocas)» = menos de {MIN_MUESTRAS} muestras; el porcentaje seria ruido.")



def desglose_liquidez(rows: list) -> None:
    """
    Liquidez contra resultado.

    Las metricas de impulso son todas ratios, y un ratio no tiene escala:
    "volumen 1.77x" sobre 1.195 USDT/min no es el mismo suceso que 1.59x
    sobre 40.048. Esta tabla existe para comprobar si esa intuicion se
    sostiene con muestras, en vez de con el caso NILUSDT del 4-sep.
    """
    con = [r for r in rows if r.get("vol_24h")]
    if not con:
        _linea("DESGLOSE POR LIQUIDEZ")
        print("  Sin datos de liquidez todavia (se registran desde la v5 del esquema).")
        return

    suf = _SUFIJO[OBJETIVO]
    bandas = [("< 2M", 0, 2e6), ("2M - 5M", 2e6, 5e6), ("5M - 20M", 5e6, 2e7),
              ("> 20M", 2e7, float("inf"))]
    _linea("DESGLOSE POR LIQUIDEZ (volumen 24h del par)")
    print(f"  {'vol 24h':>10s} {'n':>5s}  {'llega a +' + str(OBJETIVO) + '%':>16s}  "
          f"{'MFE med':>9s}  {'MAE med':>9s}")
    for nombre, lo, hi in bandas:
        g = [r for r in con if lo <= r["vol_24h"] < hi]
        if not g:
            continue
        alc = [r for r in g if r.get(f"ms_up_{suf}") is not None]
        ratio = _pct(len(alc), len(g)) if len(g) >= MIN_MUESTRAS else "  (pocas)"
        mfe = _mediana([r["mfe_pct"] for r in g if r.get("mfe_pct") is not None])
        mae = _mediana([r["mae_pct"] for r in g if r.get("mae_pct") is not None])
        print(f"  {nombre:>10s} {len(g):5d}  {ratio:>16s}  "
              f"{(f'{mfe:+.2f}%' if mfe is not None else '—'):>9s}  "
              f"{(f'{mae:+.2f}%' if mae is not None else '—'):>9s}")

    v1m = [r for r in rows if r.get("vol_1m_medio")]
    if v1m:
        print("\n  Volumen por minuto en la señal (USDT):")
        for nombre, lo, hi in (("< 2.000", 0, 2000), ("2.000-10.000", 2000, 10000),
                               ("10.000-50.000", 10000, 50000),
                               ("> 50.000", 50000, float("inf"))):
            g = [r for r in v1m if lo <= r["vol_1m_medio"] < hi]
            if not g:
                continue
            alc = [r for r in g if r.get(f"ms_up_{suf}") is not None]
            ratio = _pct(len(alc), len(g)) if len(g) >= MIN_MUESTRAS else "  (pocas)"
            mfe = _mediana([r["mfe_pct"] for r in g if r.get("mfe_pct") is not None])
            print(f"  {nombre:>14s} {len(g):5d}  {ratio:>16s}  "
                  f"{(f'{mfe:+.2f}%' if mfe is not None else '—'):>9s}")



def linea_csv(rows: list) -> str:
    """
    Una linea CSV con el estado actual. Pensada para acumular una serie
    horaria: leyendo el fichero de golpe se ve la evolucion sin tener que
    abrir treinta informes.
    """
    suf = _SUFIJO[OBJETIVO]
    total = len(rows)
    cerrados = sum(1 for r in rows if r["cerrado"])
    llegaron = sum(1 for r in rows if r.get(f"ms_up_{suf}") is not None)
    tp = sum(1 for r in rows if r.get("ms_tp") is not None)
    sl = sum(1 for r in rows if r.get("ms_sl") is not None)
    sombra = sum(1 for r in rows if r.get("sombra"))
    mfe = _mediana([r["mfe_pct"] for r in rows if r.get("mfe_pct") is not None])
    mae = _mediana([r["mae_pct"] for r in rows if r.get("mae_pct") is not None])
    return (f"{time.strftime('%Y-%m-%d %H:%M')},{total},{cerrados},{sombra},"
            f"{llegaron},{tp},{sl},"
            f"{mfe if mfe is not None else ''},{mae if mae is not None else ''}")


CSV_CABECERA = "fecha,total,cerrados,sombra,llegaron_32,toco_tp,toco_sl,mfe_mediana,mae_mediana"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incluir-vivas", action="store_true",
                    help="incluye señales que aun no cumplieron la ventana")
    ap.add_argument("--dias", type=float, default=None, help="solo los ultimos N dias")
    ap.add_argument("--csv", action="store_true",
                    help="imprime una sola linea CSV con el estado actual")
    ap.add_argument("--cabecera-csv", action="store_true",
                    help="imprime la cabecera del CSV y sale")
    ap.add_argument("--por", choices=["tier", "display_state", "taxonomia", "macro", "symbol"],
                    help="desglose por categoria")
    args = ap.parse_args()

    if args.cabecera_csv:
        print(CSV_CABECERA)
        return

    db = Database()
    rows = db.get_outcomes(solo_cerrados=not args.incluir_vivas)
    if args.dias:
        corte = int((time.time() - args.dias * 86400) * 1000)
        rows = [r for r in rows if r["ts_open"] >= corte]

    if args.csv:
        print(linea_csv(rows))
        db.close()
        return

    informe(rows, args.incluir_vivas)
    desglose_liquidez(rows)
    if args.por:
        desglose(rows, args.por)
    print()
    db.close()


if __name__ == "__main__":
    main()
