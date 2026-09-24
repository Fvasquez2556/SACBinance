"""
El contexto que ven Luna y Sol, congelado en el instante del aviso.

Tres reglas:
1. **Nada posterior a `as_of`.** El corte es `notificacion_planes.ts_activado`:
   el momento en que SAC selecciono el aviso. Las velas entran solo si estaban
   cerradas antes; la vela en curso nunca.
2. **Cada bloque dice de donde sale.** `mercado_sac` es la lectura de SAC al
   crear el plan (puede ser intravela); `marcos` se recalcula aqui sobre velas
   cerradas. No se mezclan bajo el mismo nombre.
3. **Desconocido es `null`, no cero.** El flujo de aggTrade solo existe para la
   shortlist: `flow_trades_30s = 0` con `buy_ratio = 0.5` es "sin datos"
   (F08 de la auditoria del 10-sep), y aqui se dice asi.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sac_ia import indicadores, registro
from sac_ia.fuente import TF_MS, FuenteSAC

VERSION = f"ctx-v1+{indicadores.VERSION}"

# Del snapshot plano de `planes`: escalares que SAC ya calculo. Lista cerrada
# para que un campo nuevo de SAC no entre en el estudio sin que nadie lo decida.
CAMPOS_SNAPSHOT = (
    "display_state", "fsm_state", "score", "score_trend", "tier",
    "pos_en_rango", "macro_global", "macro_gate_mult", "btc_regime",
    "ret_1m_pct", "z_drop", "z_rise", "velocity", "vol_ratio",
    "drawdown_pct", "sigma_pct", "rsi5", "rsi14_1m", "macd_rising", "trend_up",
    "rango_1h_pct", "senal_n", "is_fakeout", "vol_24h",
)
CAMPOS_SEÑAL = ("soporte", "sl_basis", "resistencia", "tp_bloqueado",
                "toques_soporte", "toques_resistencia", "trigger_tf",
                "ordinal_episodio", "episode_id", "plan_id")
LOOKBACK = {"1m": 120, "15m": 150, "1h": 150, "4h": 150}


def _json(texto) -> dict:
    if isinstance(texto, dict):
        return texto
    try:
        valor = json.loads(texto or "{}")
        return valor if isinstance(valor, dict) else {}
    except (TypeError, ValueError):
        return {}


def _r(x, n=4):
    return round(x, n) if isinstance(x, (int, float)) else None


def huella_contexto(contexto: dict) -> str:
    return hashlib.sha256(json.dumps(contexto, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def niveles(aviso: dict) -> dict:
    """Los niveles que el operador recibio, con la meta del estudio."""
    n = aviso["notificacion"]
    entrada, tp, stop = float(n["entry"]), float(n["take_profit"]), float(n["stop_loss"])
    meta = entrada * (1 + registro.META_BRUTA_PCT / 100)
    sl_pct = (1 - stop / entrada) * 100
    return {
        "entrada": entrada, "objetivo_tp": tp, "stop": stop,
        "meta_precio": meta,
        "meta_operador_pct": registro.OBJETIVO_OPERADOR_PCT,
        "coste_pct": registro.COSTE_PCT,
        "dist_meta_bruta_pct": registro.META_BRUTA_PCT,
        "tp_pct": _r((tp / entrada - 1) * 100),
        "sl_pct": _r(sl_pct),
        "meta_en_unidades_de_stop": _r(registro.META_BRUTA_PCT / sl_pct) if sl_pct > 0 else None,
        "tp_antes_que_meta": tp < meta,
        "horizonte_h": registro.HORIZONTE_MS // 3_600_000,
    }


def _flujo(snap: dict) -> dict:
    trades = snap.get("flow_trades_30s")
    if isinstance(trades, (int, float)) and trades > 0:
        return {"disponible": True, "trades_30s": trades,
                "buy_ratio_30s": snap.get("buy_ratio_30s")}
    return {"disponible": False, "trades_30s": None, "buy_ratio_30s": None}


def construir(aviso: dict, fuente: FuenteSAC, as_of_ms: int) -> dict:
    alerta, notif, plan = aviso["alerta"], aviso["notificacion"], aviso.get("plan")
    symbol = alerta["symbol"]
    ctx_notif = _json(notif.get("contexto"))
    snap = _json(plan.get("snapshot")) if plan else {}

    señal = {
        "escenario": alerta.get("display_state"),
        "score": alerta.get("score"),
        "tier": alerta.get("tier"),
        "senal_n": alerta.get("senal_n"),
        "reward_neto_pct": alerta.get("reward_neto_pct"),
        "macro_tendencias": ctx_notif.get("macro_trends") or None,
    }
    for campo in CAMPOS_SEÑAL:
        señal[campo] = ctx_notif.get(campo)
    if plan:
        señal["ordinal_episodio"] = señal["ordinal_episodio"] or plan.get("ordinal_episodio")
        señal["episode_id"] = señal["episode_id"] or plan.get("episode_id")
        señal["plan_id"] = señal["plan_id"] or plan.get("plan_id")
        señal["trigger_tf"] = señal["trigger_tf"] or plan.get("trigger_tf")

    marcos, calidad = {}, {}
    for tf, n in LOOKBACK.items():
        velas = fuente.velas_cerradas(symbol, tf, as_of_ms, n)
        marcos[tf] = indicadores.resumen_marco(velas, TF_MS[tf])
        esperadas = n
        calidad[tf] = {"velas": len(velas), "esperadas": esperadas,
                       "ultima_cierra_ms_antes": (as_of_ms - (velas[-1][0] + TF_MS[tf]))
                       if velas else None}

    precio = None
    ultima_1m = fuente.velas_cerradas(symbol, "1m", as_of_ms, 1)
    if ultima_1m:
        precio = ultima_1m[-1][4]
    lv = niveles(aviso)

    mercado_sac = {k: snap.get(k) for k in CAMPOS_SNAPSHOT} if snap else None
    if mercado_sac is not None:
        mercado_sac["flujo"] = _flujo(snap)

    return {
        "par": symbol,
        "as_of_utc": datetime.fromtimestamp(as_of_ms / 1000, timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": {**{k: _r(v, 8) if isinstance(v, float) else v for k, v in lv.items()},
                 "precio_ultimo_cierre_1m": precio,
                 "desvio_desde_entrada_pct": _r((precio / lv["entrada"] - 1) * 100)
                 if precio else None},
        "senal": señal,
        "mercado_sac": mercado_sac,
        "marcos": marcos,
        "calidad": calidad,
        "procedencia": {
            "plan": "notificacion_planes: niveles congelados que recibio el operador",
            "senal": "alertas_emitidas + notificacion_planes.contexto + planes",
            "mercado_sac": ("planes.snapshot: lectura de SAC al crear el plan, puede "
                            "ser intravela") if snap else None,
            "marcos": f"recalculado ({indicadores.VERSION}) sobre velas cerradas de SAC; "
                      "volumen en USDT",
            "kronos": None,
        },
        "kronos": {"disponible": False, "motivo": "pendiente"},
    }


def con_kronos(contexto: dict, resumen: Optional[dict], motivo: str = "") -> dict:
    """Copia del contexto con el bloque de Kronos. El original no se toca."""
    ctx = json.loads(json.dumps(contexto))
    if resumen:
        ctx["kronos"] = {"disponible": True, **resumen}
        ctx["procedencia"]["kronos"] = ("trayectorias simuladas; frecuencias sin "
                                        f"calibrar sobre velas de {registro.KRONOS['tf']} de Binance")
    else:
        ctx["kronos"] = {"disponible": False, "motivo": motivo or "no disponible"}
    return ctx


def sin_kronos(contexto: dict) -> dict:
    ctx = json.loads(json.dumps(contexto))
    ctx["kronos"] = {"disponible": False, "motivo": "este brazo no usa Kronos"}
    return ctx
