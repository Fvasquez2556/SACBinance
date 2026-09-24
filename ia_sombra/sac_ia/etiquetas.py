"""
Que paso de verdad, medido con EL MISMO evaluador que usa SAC.

No hay un segundo evaluador: se importa `backend/src/evaluacion/recorrido.py`,
que es puro (sin reloj, sin base, sin estado global). Asi la IA se juzga con la
misma regla que el resto del proyecto: la vela cuenta solo si su minuto entero
cae en la ventana, el hueco bajo el stop se ejecuta en la apertura y, si una
vela toca meta y stop, gana el stop.

Dos planes sobre las mismas velas:
- **meta**: entrada -> meta del operador (+3,2 % neto) o stop. Es la etiqueta
  principal.
- **tp**: entrada -> TP del plan o stop. Secundaria, para comparar con SAC.

La etiqueta se recalcula mientras la cobertura no llegue a 0,99 (SAC repara
huecos por REST) y se congela al llegar, o a las 24 h de cerrar la ventana con
la que haya. Una etiqueta con menos cobertura existe, pero no entra en el
analisis principal.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from sac_ia import registro
from sac_ia.fuente import FuenteSAC


def importar_recorrido(sac_backend: Path):
    ruta = str(Path(sac_backend).resolve())
    if ruta not in sys.path:
        sys.path.insert(0, ruta)
    from src.evaluacion import recorrido   # noqa: E402
    return recorrido


def etiquetar(caso: dict, fuente: FuenteSAC, recorrido, ahora_ms: int) -> Optional[dict]:
    fin = caso["as_of_ms"] + registro.HORIZONTE_MS
    if ahora_ms < fin + registro.ESPERA_ETIQUETA_MS:
        return None
    velas = [recorrido.Vela(t, o, h, l, c) for t, o, h, l, c, _ in
             fuente.velas(caso["symbol"], "1m", caso["as_of_ms"], fin)]

    def plan(objetivo: float):
        return recorrido.Plan(entrada=caso["entrada"], objetivo=objetivo, stop=caso["stop"],
                              inicio_ms=caso["as_of_ms"], horizonte_ms=registro.HORIZONTE_MS)

    p_meta, p_tp = plan(caso["meta_precio"]), plan(caso["objetivo"])
    e_meta = recorrido.evaluar(p_meta, velas, ahora_ms=ahora_ms)
    cobertura = recorrido.cobertura(p_meta, e_meta, ahora_ms)
    tp_valido = p_tp.valido()
    e_tp = recorrido.evaluar(p_tp, velas, ahora_ms=ahora_ms) if tp_valido else None
    final = (cobertura >= registro.COBERTURA_MINIMA
             or ahora_ms >= fin + registro.ABANDONO_ETIQUETA_MS)
    return {
        "caso_id": caso["caso_id"],
        "evaluador": recorrido.EVALUADOR_VERSION,
        "cobertura": cobertura,
        "n_velas": e_meta.n_velas,
        "meta_primero": int(e_meta.desenlace == "OBJETIVO"),
        "desenlace_meta": e_meta.desenlace,
        "resultado_meta_pct": recorrido.resultado_politica(p_meta, e_meta, registro.COSTE_PCT),
        "desenlace_tp": e_tp.desenlace if e_tp else None,
        "resultado_tp_pct": (recorrido.resultado_politica(p_tp, e_tp, registro.COSTE_PCT)
                             if e_tp else None),
        "ambiguo": int(e_meta.ambiguo),
        "salto": int(e_meta.salto),
        "mfe_pct": round(e_meta.mfe_pct, 4),
        "mae_pct": round(e_meta.mae_pct, 4),
        "final": int(final),
        "evaluado_ms": ahora_ms,
    }
