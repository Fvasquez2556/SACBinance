"""
Las oportunidades vivas, con TODO lo que hace falta para elegir entre ellas.

Por que esta vista existe
-------------------------
Medido el 22-sep: con 10 USDT y una sola posicion, se pueden abrir como mucho
dos operaciones al dia, y llegan 17 avisos decisorios. Se opera el 12 % y el
88 % pasa de largo. El cuello de botella no es que objetivo poner: es **cual de
las diecisiete tomar**.

Y para elegir hacia falta mirar cosas que el sistema ya calcula y no enseña en
ninguna pantalla:

- si es la PRIMERA oportunidad de su episodio o la quinta repeticion
- que ve cada uno de los dos motores, y **que les falta** para disparar
- si los marcos se contradicen
- si hay un techo entre la entrada y el TP
- si el TP neto llega al objetivo del operador
- cuanto se ha movido el precio desde que se emitio

Nada de esto es nuevo: son las fases 1 a 4 saliendo a la superficie. Esta vista
no decide ni ordena por un score — la puntuacion no ordena resultados
(AUC 0,535) y fingir lo contrario seria volver al problema de origen. Pone los
hechos juntos para que decida quien opera.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from src.presentacion.contrato import contrato_de_lectura


def _lectura_motores(db, alerta_id: Optional[int], symbol: str) -> dict:
    """
    Lo que los dos motores dijeron de este par. La lectura atada a SU alerta si
    existe; si no, la ultima que haya del simbolo.
    """
    if db is None:
        return {}
    out = {}
    try:
        filas = []
        if alerta_id:
            filas = list(db.execute(
                """SELECT motor, veredicto, familia, estado, razones, faltantes,
                          datos, ts_ms
                   FROM motor_lecturas WHERE alerta_id = ?""", (alerta_id,)))
        if not filas:
            filas = list(db.execute(
                """SELECT motor, veredicto, familia, estado, razones, faltantes,
                          datos, ts_ms
                   FROM motor_lecturas WHERE symbol = ?
                   GROUP BY motor HAVING ts_ms = MAX(ts_ms)""", (symbol,)))
        for motor, veredicto, familia, estado, razones, faltantes, datos, ts in filas:
            try:
                d = json.loads(datos or "{}")
            except Exception:
                d = {}
            out[motor] = {
                "veredicto": veredicto, "familia": familia, "estado": estado,
                "razones": json.loads(razones or "[]"),
                "faltantes": json.loads(faltantes or "[]"),
                "ancla_direccion": d.get("ancla_direccion"),
                "ancla_tendencia": d.get("ancla_tendencia"),
                "marcos_alcistas": d.get("marcos_alcistas"),
                "marcos_bajistas": d.get("marcos_bajistas"),
                "ts_ms": ts,
            }
    except Exception:
        return out
    return out


def _identidad(db, alerta_id: Optional[int]) -> dict:
    """Episodio y ordinal: ¿es la primera de este movimiento o la quinta?"""
    if db is None or not alerta_id:
        return {}
    try:
        fila = db.execute(
            """SELECT p.plan_id, p.episode_id, p.ordinal_episodio, e.n_planes,
                      e.ts_apertura, a.telegram
               FROM planes p
               LEFT JOIN episodios e ON e.episode_id = p.episode_id
               LEFT JOIN alertas_emitidas a ON a.id = p.legacy_alerta_id
               WHERE p.legacy_alerta_id = ?""", (alerta_id,)).fetchone()
    except Exception:
        return {}
    if not fila:
        return {}
    return {"plan_id": fila[0], "episode_id": fila[1], "ordinal": fila[2],
            "planes_del_episodio": fila[3], "episodio_desde_ms": fila[4],
            "avisado": fila[5] == "enviado",
            "es_primera": fila[2] == 1 if fila[2] is not None else None}


def _avisos(alerta: dict, plan_id_info: dict, motores: dict,
            contrato: dict, precio: Optional[float]) -> list:
    """
    Lo que un operador con una sola posicion deberia mirar antes de gastarla.

    Cada aviso dice el hecho y su numero. Ninguno dice "no entres": la decision
    es del operador, y este proyecto ya midio que sus vetos automaticos casi
    todos no distinguen nada.
    """
    avisos = []
    entry = alerta.get("entry")
    tp = alerta.get("take_profit")
    neto = alerta.get("reward_neto_pct")
    objetivo = contrato["objetivo_operador"]

    if neto is not None and neto < objetivo["pct"]:
        avisos.append({
            "clave": "objetivo_corto", "nivel": "ambar",
            "texto": (f"el TP deja {neto:+.2f} % neto, por debajo de tu objetivo "
                      f"de {objetivo['etiqueta']}")})

    if alerta.get("tp_bloqueado") and alerta.get("resistencia"):
        r = alerta["resistencia"]
        pct = ((r / entry - 1) * 100) if entry else None
        avisos.append({
            "clave": "techo_en_medio", "nivel": "info",
            "texto": (f"hay un techo en {r}"
                      + (f" ({pct:+.2f} %)" if pct is not None else "")
                      + " entre la entrada y el TP. Medido, no empeora el "
                        "resultado: es para que lo sepas")})

    if plan_id_info.get("es_primera") is False:
        avisos.append({
            "clave": "repeticion", "nivel": "info",
            "texto": (f"es la oportunidad n.º {plan_id_info['ordinal']} de este "
                      f"episodio, no la primera. Medido, el ordinal no predice "
                      f"el resultado; cuenta como unidad, no como calidad")})

    cont = motores.get("continuacion") or {}
    if cont.get("veredicto") == "CONFLICTO":
        alc = ", ".join(cont.get("marcos_alcistas") or [])
        baj = ", ".join(cont.get("marcos_bajistas") or [])
        avisos.append({"clave": "conflicto", "nivel": "ambar",
                       "texto": f"los marcos se contradicen: suben {alc}, bajan {baj}"})
    elif cont.get("familia") == "EXTENDIDO":
        avisos.append({"clave": "extendido", "nivel": "ambar",
                       "texto": "el motor de continuacion ve el movimiento ya gastado"})
    elif cont.get("veredicto") == "CANDIDATO":
        avisos.append({"clave": "candidato", "nivel": "verde",
                       "texto": (f"el motor de continuacion tambien lo ve, por "
                                 f"{cont.get('familia')}")})

    if cont.get("ancla_direccion") == "RUPTURA_ALCISTA":
        avisos.append({"clave": "ancla_1h", "nivel": "verde",
                       "texto": ("el marco de 1h tiene ruptura alcista — es el "
                                 "unico marco que batio a su control (+8,46 pp)")})

    caida = motores.get("caida") or {}
    if caida.get("estado") and caida["estado"] not in ("SIN_CAIDA",):
        avisos.append({"clave": "en_caida", "nivel": "ambar",
                       "texto": f"el motor de caida lo tiene en {caida['estado']}"})

    if not plan_id_info:
        # Alerta rehidratada tras un reinicio: se reconstruye desde `outcomes`,
        # que no guarda identidad de episodio ni recompensa neta. No se rellena
        # con los datos de hoy —mezclar un plan congelado con estructura actual
        # es justo lo que este sistema evita— pero tampoco se deja el hueco sin
        # explicar. Desaparece en cuanto la alerta se sustituye.
        avisos.append({
            "clave": "rehidratada", "nivel": "info",
            "texto": ("alerta recuperada tras un reinicio: sin episodio ni "
                      "recompensa neta hasta que se sustituya")})

    if precio and entry:
        desvio = (precio / entry - 1) * 100
        if abs(desvio) >= 0.5:
            avisos.append({
                "clave": "desvio", "nivel": "ambar" if desvio > 0 else "info",
                "texto": (f"el precio ya esta {desvio:+.2f} % de la entrada del "
                          f"plan: entrar aqui no es el plan que se midio")})
    return avisos


def oportunidades_vivas(engine, db=None, solo_avisadas: bool = False) -> dict:
    """
    Las alertas vivas con su contexto completo, ordenadas por lo mas reciente.

    No se ordena por score a proposito: la puntuacion no ordena resultados y
    presentarla como ranking seria justo el error que este proyecto lleva
    meses desmontando.
    """
    contrato = contrato_de_lectura()
    ahora = int(time.time() * 1000)
    filas = []
    if engine is None:
        return {"contrato": contrato, "oportunidades": [], "n": 0}

    for symbol, st in engine.states.items():
        alerta = getattr(st, "alerta", None)
        if not alerta or not alerta.get("entry"):
            continue
        ident = _identidad(db, alerta.get("alerta_id"))
        if solo_avisadas and not ident.get("avisado"):
            continue
        motores = _lectura_motores(db, alerta.get("alerta_id"), symbol)
        precio = getattr(st.metrics, "price", None)
        edad_min = ((ahora - alerta["ts_open"]) / 60_000.0
                    if alerta.get("ts_open") else None)
        filas.append({
            "symbol": symbol,
            "ts_open": alerta.get("ts_open"),
            "edad_min": round(edad_min, 1) if edad_min is not None else None,
            "precio": precio,
            "plan": {
                "entry": alerta.get("entry"),
                "take_profit": alerta.get("take_profit"),
                "stop_loss": alerta.get("stop_loss"),
                "reward_neto_pct": alerta.get("reward_neto_pct"),
                "risk_reward": alerta.get("risk_reward"),
                "soporte": alerta.get("soporte"),
                "resistencia": alerta.get("resistencia"),
                "tp_bloqueado": alerta.get("tp_bloqueado"),
                "sl_basis": alerta.get("sl_basis"),
            },
            "identidad": ident,
            "motores": motores,
            "avisos": _avisos(alerta, ident, motores, contrato, precio),
            "display_state": getattr(st, "display_state", None),
        })

    filas.sort(key=lambda f: -(f["ts_open"] or 0))
    return {
        "contrato": contrato,
        "n": len(filas),
        "oportunidades": filas,
        "nota": ("No hay orden de calidad: la puntuacion del sistema no ordena "
                 "resultados (AUC 0,535). Estan por hora de emision."),
    }
