"""
Luna y Sol: una llamada, un JSON estricto, y todo lo que puede salir mal con nombre.

La forma la garantiza Structured Outputs (esquema estricto en `text.format`);
el contenido no. Por eso, ademas del esquema, se valida aqui cada campo, y
cualquier cosa que no sea una respuesta completa y valida se guarda como lo que
es — INCOMPLETA, RECHAZO_MODELO, INVALIDA, TIMEOUT, SIN_PRESUPUESTO — y nunca
como una decision. Una abstencion no es un acierto ni un fallo: es cobertura
que falta, y el informe la cuenta aparte.

Sin reintentos automaticos del SDK (`max_retries=0`): cada reintento seria
otro gasto que el presupuesto no ha reservado.
"""
from __future__ import annotations

import json
import math
import time
import uuid
from typing import Callable, Optional

from sac_ia import registro
from sac_ia.presupuesto import Presupuesto, coste_usd, reserva_usd

NOMBRE_ESQUEMA = "decision_aviso"


def ahora_ms() -> int:
    return int(time.time() * 1000)


def leer_clave(cfg) -> str | None:
    """La clave del fichero de secretos, o None. No necesita la libreria de OpenAI."""
    if not cfg.clave_openai.is_file():
        return None
    return cfg.clave_openai.read_text(encoding="utf-8").strip() or None


def crear_cliente(cfg):
    """None si no hay clave: el servicio sigue, las decisiones quedan NO_EJECUTADA."""
    clave = leer_clave(cfg)
    if clave is None:
        return None
    from openai import OpenAI
    return OpenAI(api_key=clave, max_retries=0, timeout=cfg.llm_timeout_s)


def validar(d) -> Optional[str]:
    """Motivo por el que la salida no vale, o None."""
    if not isinstance(d, dict):
        return "no es un objeto"
    if set(d) != set(registro.ESQUEMA_DECISION["required"]):
        return f"claves inesperadas: {sorted(set(d) ^ set(registro.ESQUEMA_DECISION['required']))}"
    if d["accion"] not in registro.ACCIONES:
        return "accion fuera de la lista"
    p = d["p_meta"]
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) \
            or not 0 <= p <= 1:
        return "p_meta fuera de [0, 1]"
    if d["confianza"] not in registro.CONFIANZAS:
        return "confianza fuera de la lista"
    if not isinstance(d["codigos"], list) or any(c not in registro.CODIGOS for c in d["codigos"]):
        return "codigo fuera de la lista"
    if not isinstance(d["razon"], str):
        return "razon no es texto"
    return None


def _rechazo(resp) -> Optional[str]:
    for salida in getattr(resp, "output", None) or []:
        if getattr(salida, "type", None) != "message":
            continue
        for item in getattr(salida, "content", None) or []:
            if getattr(item, "type", None) == "refusal":
                return getattr(item, "refusal", "") or "rechazo"
    return None


def _uso(resp) -> dict:
    u = getattr(resp, "usage", None)
    if u is None:
        return {"entrada": 0, "cache": 0, "salida": 0, "razonamiento": 0}
    det_in = getattr(u, "input_tokens_details", None)
    det_out = getattr(u, "output_tokens_details", None)
    return {"entrada": int(getattr(u, "input_tokens", 0) or 0),
            "cache": int(getattr(det_in, "cached_tokens", 0) or 0) if det_in else 0,
            "salida": int(getattr(u, "output_tokens", 0) or 0),
            "razonamiento": int(getattr(det_out, "reasoning_tokens", 0) or 0) if det_out else 0}


# Lo que OpenAI devuelve cuando la cuenta se queda sin saldo (429). No es un
# limite de ritmo que pase solo: hasta que alguien recargue, fallara siempre.
CODIGOS_SIN_CREDITO = {"credit_balance_exhausted", "insufficient_quota"}


def _clasificar_error(exc: Exception) -> tuple[str, bool]:
    """(estado, pudo_cobrarse). Un 4xx no llega al modelo; un timeout, quiza si."""
    codigo = getattr(exc, "status_code", None)
    nombre = type(exc).__name__
    if {getattr(exc, "code", None), getattr(exc, "type", None)} & CODIGOS_SIN_CREDITO:
        return "SIN_CREDITOS", False
    if "Timeout" in nombre:
        return "TIMEOUT", True
    if codigo is not None:
        return f"ERROR_HTTP_{codigo}", codigo >= 500
    return "ERROR", True


def decidir(cliente, brazo: str, contexto: dict, caso_id: int, deadline_ms: int,
            presupuesto: Presupuesto, timeout_s: float,
            reloj: Callable[[], int] = ahora_ms) -> dict:
    cfg = registro.BRAZOS_LLM[brazo]
    modelo = cfg["modelo"]
    instrucciones = registro.prompt_decision()
    entrada = json.dumps(contexto, ensure_ascii=False, sort_keys=True)
    fila = {"caso_id": caso_id, "brazo": brazo, "modelo": modelo,
            "prompt_sha256": registro.sha256_texto(instrucciones), "a_tiempo": 0}

    if cliente is None:
        return {**fila, "estado": "NO_EJECUTADA", "motivo": "sin clave de OpenAI"}
    t0 = reloj()
    plazo_s = min(timeout_s, (deadline_ms - t0) / 1000 - 2)
    if plazo_s < 3:
        return {**fila, "estado": "NO_EJECUTADA", "motivo": "sin tiempo antes del plazo"}

    request_id = f"{caso_id}:{brazo}:{uuid.uuid4().hex[:10]}"
    if not presupuesto.reservar(request_id, caso_id, brazo, modelo,
                                reserva_usd(modelo, instrucciones + entrada, cfg["max_salida"]),
                                t0):
        return {**fila, "estado": "SIN_PRESUPUESTO", "motivo": "tope diario o total alcanzado"}
    fila.update(solicitado_ms=t0, request_id=request_id)

    try:
        resp = cliente.responses.create(
            model=modelo,
            instructions=instrucciones,
            input=[{"role": "user", "content": entrada}],
            text={"format": {"type": "json_schema", "name": NOMBRE_ESQUEMA,
                             "schema": registro.ESQUEMA_DECISION, "strict": True}},
            reasoning={"effort": cfg["esfuerzo"]},
            max_output_tokens=cfg["max_salida"],
            store=False,
            timeout=plazo_s,
        )
    except Exception as exc:                                    # noqa: BLE001
        estado, cobrable = _clasificar_error(exc)
        (presupuesto.incierto if cobrable else presupuesto.liberar)(request_id)
        return {**fila, "estado": estado, "recibido_ms": reloj(),
                "motivo": f"{type(exc).__name__}: {str(exc)[:300]}"}

    recibido = reloj()
    uso = _uso(resp)
    coste = coste_usd(modelo, uso["entrada"], uso["cache"], uso["salida"])
    presupuesto.liquidar(request_id, coste)
    texto = getattr(resp, "output_text", "") or ""
    fila.update(recibido_ms=recibido, tokens_entrada=uso["entrada"], tokens_cache=uso["cache"],
                tokens_salida=uso["salida"], tokens_razonamiento=uso["razonamiento"],
                coste_usd=round(coste, 6),
                respuesta_json=json.dumps({"id": getattr(resp, "id", None),
                                           "status": getattr(resp, "status", None),
                                           "output_text": texto[:4000]}, ensure_ascii=False))

    status = getattr(resp, "status", None)
    if status != "completed":
        detalle = getattr(getattr(resp, "incomplete_details", None), "reason", None)
        return {**fila, "estado": "INCOMPLETA", "motivo": f"{status}: {detalle}"}
    rechazo = _rechazo(resp)
    if rechazo:
        return {**fila, "estado": "RECHAZO_MODELO", "motivo": rechazo[:300]}
    try:
        datos = json.loads(texto)
    except ValueError:
        return {**fila, "estado": "INVALIDA", "motivo": "JSON ilegible"}
    error = validar(datos)
    if error:
        return {**fila, "estado": "INVALIDA", "motivo": error}
    return {**fila, "estado": "OK", "accion": datos["accion"], "p_meta": float(datos["p_meta"]),
            "confianza": datos["confianza"],
            "codigos_json": json.dumps(datos["codigos"], ensure_ascii=False),
            "razon": datos["razon"][:registro.RAZON_MAX_CHARS],
            "a_tiempo": int(recibido <= deadline_ms)}
