"""
El veredicto del dia 15, y lo unico que se puede ver antes.

Antes de que cierre la ventana, el informe solo enseña salud operativa: cuantos
casos, cuantos a tiempo, cuanto gasto, cuanto tarda, si SAC va mas lento. Nada
de lo que decidieron Luna y Sol ni de como les fue: mirar a mitad de camino y
seguir o parar segun lo que se ve es elegir el resultado. `--desvelar` existe,
pero queda anotado en la base.

El veredicto aplica `registro.CRITERIOS` tal cual; este modulo no decide umbrales.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from sac_ia import registro
from sac_ia.almacen import Almacen

# --- Estadistica pura -----------------------------------------------------------


def auc(puntos: Sequence[float], etiquetas: Sequence[int]) -> Optional[float]:
    """Probabilidad de que un positivo puntue mas que un negativo; empates cuentan 1/2."""
    pares = sorted(zip(puntos, etiquetas))
    n_pos = sum(etiquetas)
    n_neg = len(etiquetas) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rango_pos, i = 0.0, 0
    while i < len(pares):
        j = i
        while j < len(pares) and pares[j][0] == pares[i][0]:
            j += 1
        rango_medio = (i + j + 1) / 2              # rangos 1-based, medio del empate
        rango_pos += rango_medio * sum(e for _, e in pares[i:j])
        i = j
    return (rango_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def media(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def cuantil(xs: Sequence[float], q: float) -> Optional[float]:
    if not xs:
        return None
    v = sorted(xs)
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def bootstrap_grupos(filas: list[dict], grupo: str, estadistico: Callable[[list[dict]], Optional[float]],
                     b: int = registro.BOOTSTRAP_B, semilla: int = registro.BOOTSTRAP_SEMILLA):
    """IC95 remuestreando GRUPOS enteros (par o dia), no filas sueltas."""
    por_grupo = defaultdict(list)
    for f in filas:
        por_grupo[f[grupo]].append(f)
    claves = sorted(por_grupo)
    if len(claves) < 2:
        return None, None
    rng = random.Random(semilla)
    valores = []
    for _ in range(b):
        muestra = []
        for _ in claves:
            muestra.extend(por_grupo[claves[rng.randrange(len(claves))]])
        v = estadistico(muestra)
        if v is not None:
            valores.append(v)
    if len(valores) < b * 0.9:
        return None, None
    return cuantil(valores, 0.025), cuantil(valores, 0.975)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None

    def rangos(v):
        orden = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(orden):
            j = i
            while j < len(orden) and v[orden[j]] == v[orden[i]]:
                j += 1
            for k in range(i, j):
                r[orden[k]] = (i + j + 1) / 2
            i = j
        return r

    rx, ry = rangos(xs), rangos(ys)
    mx, my = media(rx), media(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


# --- Datos --------------------------------------------------------------------------


def _dia(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def _fecha(ms: Optional[int]) -> str:
    if not ms:
        return "—"
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def ventana(a: Almacen) -> tuple[Optional[int], Optional[int]]:
    inicio = a.meta("inicio_medicion_ms")
    if not inicio:
        return None, None
    return int(inicio), int(inicio) + registro.MEDICION_MS


def casos_de_la_ventana(a: Almacen) -> list[dict]:
    inicio, fin = ventana(a)
    if inicio is None:
        return []
    casos = a.filas("SELECT c.*, e.cobertura, e.meta_primero, e.resultado_meta_pct, "
                    "e.resultado_tp_pct, e.desenlace_tp, e.final, k.estado AS kronos_estado, "
                    "k.p_meta AS kronos_p "
                    "FROM casos c LEFT JOIN etiquetas e USING (caso_id) "
                    "LEFT JOIN kronos k USING (caso_id) "
                    "WHERE c.modo = 'MEDICION' AND c.as_of_ms >= ? AND c.as_of_ms < ? "
                    "ORDER BY c.as_of_ms", (inicio, fin))
    decisiones = defaultdict(dict)
    for d in a.filas("SELECT * FROM decisiones"):
        decisiones[d["caso_id"]][d["brazo"]] = d
    for c in casos:
        c["dia"] = _dia(c["as_of_ms"])
        c["decisiones"] = decisiones.get(c["caso_id"], {})
    return casos


def valido(c: dict) -> bool:
    """Etiqueta final con cobertura suficiente: entra en el analisis principal."""
    return bool(c.get("final")) and (c.get("cobertura") or 0) >= registro.COBERTURA_MINIMA


def decision_ok(c: dict, brazo: str) -> Optional[dict]:
    d = c["decisiones"].get(brazo)
    return d if d and d["estado"] == "OK" and d["a_tiempo"] else None


# --- Operativo (visible siempre) ---------------------------------------------------------


def operativo(a: Almacen, ahora_ms: int) -> dict:
    inicio_rodaje = a.meta("inicio_rodaje_ms")
    inicio, fin = ventana(a)
    casos = a.filas("SELECT modo, tardio FROM casos")
    por_brazo = {}
    for brazo in registro.BRAZOS_LLM:
        filas = a.filas("SELECT estado, a_tiempo, coste_usd, solicitado_ms, recibido_ms "
                        "FROM decisiones WHERE brazo = ?", (brazo,))
        lat = [(f["recibido_ms"] - f["solicitado_ms"]) / 1000 for f in filas
               if f["recibido_ms"] and f["solicitado_ms"]]
        estados = defaultdict(int)
        for f in filas:
            estados[f["estado"]] += 1
        por_brazo[brazo] = {"llamadas": len(filas), "a_tiempo": sum(f["a_tiempo"] for f in filas),
                            "estados": dict(estados),
                            "coste_usd": round(sum(f["coste_usd"] or 0 for f in filas), 4),
                            "latencia_p50_s": cuantil(lat, 0.5), "latencia_p95_s": cuantil(lat, 0.95)}
    kronos = a.filas("SELECT estado, latencia_ms FROM kronos")
    k_estados = defaultdict(int)
    for f in kronos:
        k_estados[f["estado"]] += 1
    k_lat = [f["latencia_ms"] / 1000 for f in kronos if f["latencia_ms"]]
    return {
        "advertencias": advertencias(a, ahora_ms),
        "modo": "MEDICION" if inicio else "RODAJE",
        "inicio_rodaje": _fecha(inicio_rodaje), "inicio_medicion": _fecha(inicio),
        "fin_medicion": _fecha(fin),
        "casos": {"total": len(casos), "rodaje": sum(c["modo"] == "RODAJE" for c in casos),
                  "medicion": sum(c["modo"] == "MEDICION" for c in casos),
                  "tardios": sum(c["tardio"] for c in casos)},
        "etiquetas": {"finales": a.uno("SELECT COUNT(*) FROM etiquetas WHERE final = 1"),
                      "cobertura_ok": a.uno("SELECT COUNT(*) FROM etiquetas WHERE final = 1 "
                                            "AND cobertura >= ?", (registro.COBERTURA_MINIMA,))},
        "kronos": {"estados": dict(k_estados), "latencia_p50_s": cuantil(k_lat, 0.5),
                   "latencia_p95_s": cuantil(k_lat, 0.95)},
        "brazos": por_brazo,
        "interferencia": interferencia(a),
        "huella_actual": registro.huella(),
        "huella_medicion": a.meta("huella_medicion"),
    }


def advertencias(a: Almacen, ahora_ms: int) -> list[str]:
    """Lo que el operador tiene que arreglar YA. No dice nada de resultados."""
    desde = ahora_ms - 24 * 3600_000
    salida = []
    for estado, texto in (
            ("SIN_CREDITOS", "OpenAI sin saldo: recarga creditos en "
                             "platform.openai.com/settings/organization/billing"),
            ("SIN_PRESUPUESTO", "se alcanzo el tope de gasto del servicio "
                                "(IA_TOPE_DIARIO_USD / IA_TOPE_TOTAL_USD)")):
        n = a.uno("SELECT COUNT(*) FROM decisiones WHERE estado = ? AND solicitado_ms >= ?",
                  (estado, desde)) or 0
        if n:
            salida.append(f"{texto} ({n} consultas perdidas en las ultimas 24 h)")
    return salida


def interferencia(a: Almacen) -> dict:
    salida = {}
    for modo in ("RODAJE", "MEDICION"):
        filas = a.filas("SELECT edad_vela_ms, carga_1m, rss_ia_mb, sac_pid FROM salud "
                        "WHERE modo = ? ORDER BY ts_ms", (modo,))
        edades = [f["edad_vela_ms"] for f in filas if f["edad_vela_ms"] is not None]
        pids = [f["sac_pid"] for f in filas if f["sac_pid"]]
        cambios = sum(1 for x, y in zip(pids, pids[1:]) if x != y)
        salida[modo] = {"muestras": len(filas),
                        "edad_vela_p95_ms": cuantil(edades, 0.95),
                        "carga_p95": cuantil([f["carga_1m"] for f in filas
                                              if f["carga_1m"] is not None], 0.95),
                        "rss_ia_max_mb": max([f["rss_ia_mb"] for f in filas
                                              if f["rss_ia_mb"] is not None], default=None),
                        "reinicios_sac": cambios}
    r, m = salida["RODAJE"]["edad_vela_p95_ms"], salida["MEDICION"]["edad_vela_p95_ms"]
    salida["delta_p95_ms"] = (m - r) if r is not None and m is not None else None
    return salida


# --- El veredicto ------------------------------------------------------------------------


def analisis(casos: list[dict]) -> dict:
    validos = [c for c in casos if valido(c)]
    principal = registro.BRAZO_PRINCIPAL
    res = {"n_casos": len(casos), "n_validos": len(validos), "brazos": {}}

    def auc_de(filas, clave):
        return auc([f[clave] for f in filas], [f["meta_primero"] for f in filas])

    for brazo in registro.BRAZOS_LLM:
        filas = []
        for c in validos:
            d = decision_ok(c, brazo)
            if d:
                filas.append({**c, "p": d["p_meta"], "entra": d["accion"] == "ENTRAR"})
        a_tiempo = len(filas) / len(validos) if validos else None
        punto = auc_de(filas, "p")
        lo_par, hi_par = bootstrap_grupos(filas, "symbol", lambda m: auc_de(m, "p"))
        lo_dia, hi_dia = bootstrap_grupos(filas, "dia", lambda m: auc_de(m, "p"))
        mitad = len(filas) // 2
        mitades = [auc_de(filas[:mitad], "p"), auc_de(filas[mitad:], "p")] if mitad else [None, None]
        aceptados = [f["resultado_meta_pct"] for f in filas if f["entra"]]
        rechazados = [f["resultado_meta_pct"] for f in filas if not f["entra"]]

        def dif(m):
            ac = [f["resultado_meta_pct"] for f in m if f["entra"]]
            re = [f["resultado_meta_pct"] for f in m if not f["entra"]]
            return media(ac) - media(re) if ac and re else None

        lo_dif, hi_dif = bootstrap_grupos(filas, "symbol", dif)
        todos = [c["resultado_meta_pct"] for c in validos]
        res["brazos"][brazo] = {
            "n": len(filas), "a_tiempo_frac": a_tiempo,
            "auc": punto, "auc_ic_par": [lo_par, hi_par], "auc_ic_dia": [lo_dia, hi_dia],
            "auc_mitades": mitades,
            "n_aceptados": len(aceptados), "media_aceptados_pct": media(aceptados),
            "media_rechazados_pct": media(rechazados),
            "dif_acept_rech_ic": [lo_dif, hi_dif],
            "media_todos_pct": media(todos),
            "spearman_con_score_sac": spearman([f["p"] for f in filas],
                                               [f["score"] or 0 for f in filas]),
        }

    kron = [{**c, "p": c["kronos_p"]} for c in validos
            if c.get("kronos_estado") == "OK" and c.get("kronos_p") is not None]
    res["brazos"][registro.BRAZO_KRONOS] = {
        "n": len(kron), "auc": auc_de(kron, "p"),
        "auc_ic_par": list(bootstrap_grupos(kron, "symbol", lambda m: auc_de(m, "p")))}

    casc = [c for c in validos if all(decision_ok(c, b) for b in ("LUNA", "SOL"))]
    ac = [c["resultado_meta_pct"] for c in casc
          if all(decision_ok(c, b)["accion"] == "ENTRAR" for b in ("LUNA", "SOL"))]
    res["brazos"][registro.BRAZO_CASCADA] = {"n": len(casc), "n_aceptados": len(ac),
                                             "media_aceptados_pct": media(ac)}
    res["referencia"] = {"n": len(validos),
                         "tasa_meta": media([c["meta_primero"] for c in validos]),
                         "media_pct": media([c["resultado_meta_pct"] for c in validos])}
    res["principal"] = principal
    return res


def veredicto(r: dict, interf: dict) -> tuple[str, list[str]]:
    s = r["brazos"].get(registro.BRAZO_PRINCIPAL, {})
    motivos = []
    delta = interf.get("delta_p95_ms")
    if delta is not None and delta > registro.ATRASO_VELA_P95_MAX_DELTA_MS:
        motivos.append(f"la ultima vela de SAC llega {delta / 1000:.1f} s mas tarde (p95)")
    if s.get("auc_ic_par") and s["auc_ic_par"][1] is not None and s["auc_ic_par"][1] < 0.5:
        motivos.append("el IC95 del AUC de Sol queda entero bajo 0,5")
    if s.get("dif_acept_rech_ic") and s["dif_acept_rech_ic"][1] is not None \
            and s["dif_acept_rech_ic"][1] < 0:
        motivos.append("lo que Sol acepta rinde menos que lo que rechaza (IC entero bajo 0)")
    if motivos:
        return "ENTORPECE", motivos

    faltan = []
    if s.get("n", 0) < registro.N_MINIMO:
        faltan.append(f"n = {s.get('n', 0)} < {registro.N_MINIMO}")
    for nombre in ("auc_ic_par", "auc_ic_dia"):
        lo = (s.get(nombre) or [None])[0]
        if lo is None or lo <= 0.5:
            faltan.append(f"limite inferior del AUC ({nombre[-3:]}) = {lo}")
    if any(m is None or m <= 0.5 for m in s.get("auc_mitades", [None])):
        faltan.append(f"AUC por mitades = {s.get('auc_mitades')}")
    ac, todos = s.get("media_aceptados_pct"), s.get("media_todos_pct")
    if ac is None or todos is None or ac <= todos:
        faltan.append(f"aceptados {ac} frente a todos {todos}")
    if (s.get("a_tiempo_frac") or 0) < registro.COBERTURA_A_TIEMPO_MIN:
        faltan.append(f"a tiempo {s.get('a_tiempo_frac')}")
    if not faltan:
        return "AYUDA", ["pasa todas las condiciones registradas"]
    return "INCONCLUSO", faltan


# --- Texto -----------------------------------------------------------------------------


def _f(x, pct=False, n=3):
    if x is None:
        return "—"
    return f"{x:+.2f} %" if pct else f"{x:.{n}f}"


def generar(a: Almacen, ahora_ms: int, desvelar: bool = False) -> str:
    op = operativo(a, ahora_ms)
    avisos_op = [f"**ATENCION: {x}**" for x in op["advertencias"]]
    lineas = [f"# IA en sombra · estudio {registro.ESTUDIO_VERSION}", "", *avisos_op,
              f"Modo: **{op['modo']}** · rodaje desde {op['inicio_rodaje']} · "
              f"medicion {op['inicio_medicion']} → {op['fin_medicion']}", "",
              "## Salud operativa", "",
              f"- Casos: {op['casos']}",
              f"- Etiquetas finales: {op['etiquetas']['finales']} "
              f"(con cobertura ≥ {registro.COBERTURA_MINIMA}: {op['etiquetas']['cobertura_ok']})",
              f"- Kronos: {op['kronos']}"]
    for brazo, b in op["brazos"].items():
        lineas.append(f"- {brazo}: {b}")
    lineas += [f"- Interferencia con SAC: {json.dumps(op['interferencia'])}", ""]

    inicio, fin = ventana(a)
    if inicio is None:
        return "\n".join(lineas + ["Sin medicion iniciada: no hay veredicto."])
    if ahora_ms < fin and not desvelar:
        return "\n".join(lineas + [f"**Cegado hasta {op['fin_medicion']}.** Lo que decidieron "
                                   "Luna y Sol y como les fue no se muestra antes del veredicto."])
    if desvelar and ahora_ms < fin:
        a.evento(ahora_ms, "DESVELADO_ANTES_DE_TIEMPO", "informe con --desvelar")
    if op["huella_medicion"] != op["huella_actual"]:
        return "\n".join(lineas + [f"**Sin veredicto:** la huella cambio despues de empezar "
                                   f"({op['huella_medicion']} → {op['huella_actual']}). "
                                   "Eso es otro estudio."])

    r = analisis(casos_de_la_ventana(a))
    v, motivos = veredicto(r, op["interferencia"])
    ref = r["referencia"]
    lineas += ["## Veredicto", "", f"**{v}**", ""] + [f"- {m}" for m in motivos] + [
        "", f"Referencia (todos los avisos validos): n = {ref['n']}, llegan a la meta antes "
            f"que al stop {_f(ref['tasa_meta'])}, media {_f(ref['media_pct'], pct=True)}", "",
        "| brazo | n | AUC | IC95 par | IC95 dia | mitades | aceptados | media acept. | media rech. |",
        "|---|---|---|---|---|---|---|---|---|"]
    for brazo, b in r["brazos"].items():
        ic_par = b.get("auc_ic_par") or [None, None]
        ic_dia = b.get("auc_ic_dia") or [None, None]
        mit = b.get("auc_mitades") or []
        lineas.append(
            f"| {brazo} | {b.get('n')} | {_f(b.get('auc'))} | [{_f(ic_par[0])}, {_f(ic_par[1])}] | "
            f"[{_f(ic_dia[0])}, {_f(ic_dia[1])}] | {', '.join(_f(m) for m in mit) or '—'} | "
            f"{b.get('n_aceptados', '—')} | {_f(b.get('media_aceptados_pct'), pct=True)} | "
            f"{_f(b.get('media_rechazados_pct'), pct=True)} |")
    s = r["brazos"].get(registro.BRAZO_PRINCIPAL, {})
    lineas += ["", f"Correlacion de Sol con el score de SAC (Spearman): "
                   f"{_f(s.get('spearman_con_score_sac'))}. Si es alta, Sol repite el score, "
                   "que ya se sabe que no ordena.", "",
               f"Predicho el {registro.FECHA_REGISTRO}: {registro.PREDICCIONES}"]
    return "\n".join(lineas)
