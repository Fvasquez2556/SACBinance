"""
Informe de un par bajo demanda: ruptura y plan en cada marco temporal.

Es el camino de la CONSULTA MANUAL —se escribe un par y se mira— y no toca el
tablero, ni los avisos, ni el seguimiento. Dos razones para tenerlo separado:

  1. El tablero clasifica la ruptura sobre la FSM de 1m. Aqui se pregunta lo
     mismo en 5m, 15m, 1h y 4h contra la estructura de cada marco, que es lo
     que permite ver si el movimiento de 1m va a favor o en contra.
  2. El tablero solo mira el universo en vivo (volumen minimo, tope de pares).
     Un par fuera de ese universo no tiene buffers, asi que aqui se bajan sus
     velas de Binance en el momento.

Lo que este informe NO es: una medicion. Ninguna de sus lecturas ha pasado las
tres puertas de `criterios_sabado` — dinero, habilidad y terreno nuevo. Describe
estructura ya ocurrida y calcula niveles con aritmetica. Mientras no se mida en
sombra, se lee como contexto.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Dict, List, Optional, Tuple

from src.analysis.tf_rupture import (
    RUPTURA_ALCISTA,
    RUPTURA_BAJISTA,
    SIN_DATOS,
    LecturaTF,
    leer_tf,
    resumir,
)
from src.analysis.tf_estadistica import celda as celda_estadistica
from src.analysis.trade_levels import calcular_plan_direccional
from src.config.settings import get_settings
from src.indicators.calculator import indicators_from_candles
from src.utils.logger import get_logger

logger = get_logger(__name__)

FUENTE_MOTOR = "motor"
FUENTE_CONSULTA = "consulta_directa"

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")
_QUOTE = "USDT"

# Cache SOLO del camino REST. Un par del motor ya esta en memoria y se lee
# fresco; uno de fuera son cinco peticiones a Binance por consulta, y recargar
# la pantalla las repetiria todas.
_cache: Dict[str, Tuple[float, dict]] = {}

# Cache de la instantanea de tasas: es un agregado sobre decenas de miles de
# filas y el informe se pide a mano. Recalcularla en cada consulta no aporta
# nada — la ventana es de dias.
_stats_cache: Tuple[float, dict] = (0.0, {})

_NOTA_BASE = (
    "Lectura de estructura ya ocurrida, no un pronostico. Las tasas que la "
    "acompañan son frecuencias observadas en rupturas anteriores de este "
    "sistema, con su n y su ventana al lado — no son una probabilidad "
    "calibrada de esta ruptura."
)


def normalizar_symbol(raw: str) -> Optional[str]:
    """`btc` -> BTCUSDT; `ETHUSDT` -> ETHUSDT. None si no tiene forma de par."""
    if not raw:
        return None
    limpio = raw.strip().upper().replace("/", "").replace("-", "")
    if not _SYMBOL_RE.match(limpio):
        return None
    if not limpio.endswith(_QUOTE):
        limpio += _QUOTE
    return limpio if _SYMBOL_RE.match(limpio) else None


def construir_informe(
    symbol: str,
    price: float,
    buffers: Dict[str, list],
    candles_1m: Optional[list] = None,
    ind_htf: Optional[dict] = None,
    fuente: str = FUENTE_MOTOR,
    ts: Optional[int] = None,
    estadistica: Optional[dict] = None,
) -> dict:
    """
    buffers: {tf: velas CERRADAS} para cada marco del informe.
    ind_htf: {tf: IndSnap} ya calculado, si lo hay. Si falta, se calcula.

    Funcion pura: no toca red ni estado. Todo lo que necesita entra por aqui,
    que es lo que la hace comprobable con velas de mentira.
    """
    s = get_settings()
    ts = ts or int(time.time() * 1000)
    ind_htf = ind_htf or {}
    lecturas: List[LecturaTF] = []
    marcos: List[dict] = []

    for tf in s.informe_tfs_list:
        velas = list(buffers.get(tf) or ())
        ind = ind_htf.get(tf)
        if ind is None and velas:
            ind = indicators_from_candles(velas)
        lectura = leer_tf(tf, velas, price, ind)
        lecturas.append(lectura)

        plan = None
        if lectura.direccion in (RUPTURA_ALCISTA, RUPTURA_BAJISTA):
            plan = calcular_plan_direccional(
                lectura.direccion, price, velas, lectura.nivel_roto,
                tf=tf, niveles_sr=lectura.niveles, candles_1m=candles_1m,
            ).to_dict()

        marco = lectura.to_dict()
        marco["plan"] = plan
        marco["estadistica"] = _estadistica_marco(estadistica, lectura)
        marcos.append(marco)

    resumen = resumir(lecturas)
    resumen["estadistica"] = _estadistica_resumen(estadistica, resumen)

    advertencias = [_NOTA_BASE]
    if fuente == FUENTE_CONSULTA:
        advertencias.append(
            "Par fuera del universo en vivo: las velas se bajaron en el momento. "
            "No tiene seguimiento, ni flujo agresor, ni estadistica adaptativa."
        )
    sin_datos = [l.tf for l in lecturas if l.direccion == SIN_DATOS]
    if sin_datos:
        advertencias.append(
            f"Sin historia suficiente en {', '.join(sin_datos)}: ese marco no opina."
        )
    if resumen["en_conflicto"]:
        advertencias.append(_aviso_conflicto(resumen))
    if any(l.direccion == RUPTURA_BAJISTA for l in lecturas):
        advertencias.append(
            "Hay lectura bajista. Todo lo medido en este proyecto es comprador: "
            "un plan vendedor es aritmetica sobre la estructura, sin medicion detras."
        )
    aviso_intradia = _aviso_horizonte(marcos, estadistica)
    if aviso_intradia:
        advertencias.append(aviso_intradia)

    return {
        "symbol": symbol,
        "price": price,
        "ts": ts,
        "fuente": fuente,
        "resumen": resumen,
        "timeframes": marcos,
        "advertencias": advertencias,
    }


def _estadistica_marco(instantanea: Optional[dict], lectura) -> Optional[dict]:
    """Lo que paso en rupturas anteriores de ESTE marco y ESTA direccion."""
    if not instantanea or lectura.direccion not in (RUPTURA_ALCISTA, RUPTURA_BAJISTA):
        return None
    return {
        "ventana_dias": instantanea.get("ventana_dias"),
        "min_n": instantanea.get("min_n"),
        "horizonte_h": instantanea.get("horizonte_h"),
        "marco": celda_estadistica(instantanea, "por_marco", lectura.tf, lectura.direccion),
        # Las dos celdas del nivel que estorba, para que la pantalla pueda
        # comparar en vez de repetir un aviso que los datos no sostienen.
        "estorbo_si": celda_estadistica(instantanea, "por_estorbo", 1, lectura.direccion),
        "estorbo_no": celda_estadistica(instantanea, "por_estorbo", 0, lectura.direccion),
    }


def _estadistica_resumen(instantanea: Optional[dict], resumen: dict) -> Optional[dict]:
    """
    La confluencia es lo unico que ordena en la medicion: 0, 1, 2, 3 o 4 marcos
    confirmados dan 44,5 / 46,0 / 51,4 / 58,5 / 62,4 % de tocar el TP antes que
    el stop. Por eso la celda del resumen es la del numero de marcos, no la del
    marco que «manda».
    """
    if not instantanea:
        return None
    direccion = resumen.get("direccion_dominante")
    if direccion not in (RUPTURA_ALCISTA, RUPTURA_BAJISTA):
        direccion = RUPTURA_ALCISTA
    return {
        "ventana_dias": instantanea.get("ventana_dias"),
        "min_n": instantanea.get("min_n"),
        "direccion": direccion,
        "n_confirmadas": resumen.get("n_confirmadas"),
        "confluencia": celda_estadistica(instantanea, "por_confluencia",
                                         resumen.get("n_confirmadas"), direccion),
        "conflicto_si": celda_estadistica(instantanea, "por_conflicto", 1, direccion),
        "conflicto_no": celda_estadistica(instantanea, "por_conflicto", 0, direccion),
    }


def _aviso_conflicto(resumen: dict) -> str:
    """
    El desacuerdo entre marcos no anticipa peor resultado.

    El aviso anterior daba a entender lo contrario. Medido: las rupturas con
    marcos en conflicto acaban mejor que las que van de acuerdo, no peor. Se
    siguen enseñando los dos lados sin promediar — eso no cambia —, pero el
    texto ya no insinua un riesgo que los datos no muestran.
    """
    est = (resumen.get("estadistica") or {})
    si, no = est.get("conflicto_si"), est.get("conflicto_no")
    base = "Marcos en desacuerdo: se enseñan los dos y no se promedian."
    if si and no and si.get("fiable") and no.get("fiable"):
        return (f"{base} Medido en los ultimos {est.get('ventana_dias')} dias, el "
                f"desacuerdo no anticipa peor resultado: {si['tp_antes_sl']}% de las "
                f"rupturas en conflicto tocaron su TP antes que el stop (n={si['n']}) "
                f"frente al {no['tp_antes_sl']}% de las que iban de acuerdo (n={no['n']}).")
    return f"{base} Sin muestra suficiente para decir si el desacuerdo cambia el resultado."


def _aviso_horizonte(marcos: List[dict], instantanea: Optional[dict]) -> str:
    """
    Este sistema es intradia: el plan tiene que caber en la jornada.

    Medido: el TP de una ruptura de 5m llega en 5,05 h de mediana y el 82,5 %
    cabe en 12 h; el de 1h tarda 10,08 h y solo cabe el 58,1 %. El aviso
    anterior hablaba de "dias" y de una ventana de 24 h que ya no existe.
    """
    if not instantanea:
        return ""
    lentos = []
    for marco in marcos:
        est = (marco.get("estadistica") or {}).get("marco")
        if not est or not est.get("fiable") or est.get("pct_dentro_horizonte") is None:
            continue
        if est["pct_dentro_horizonte"] < 70.0:
            lentos.append(f"{marco['tf']} ({est['pct_dentro_horizonte']}%, "
                          f"mediana {est['horas_mediana']} h)")
    if not lentos:
        return ""
    return (f"Horizonte: este sistema mide en {instantanea.get('horizonte_h')} h y cierra "
            f"la ventana ahi. En {', '.join(lentos)} menos del 70% de las rupturas "
            f"anteriores llego a su TP dentro de ese plazo — el plan existe, pero pide "
            f"mas tiempo del que el seguimiento le da.")


async def _buffers_rest(symbol: str) -> Tuple[Dict[str, list], list]:
    """Baja de Binance los marcos del informe mas 1m, en paralelo."""
    from src.data_ingestion.hydrator import fetch_candles

    s = get_settings()
    tfs = s.informe_tfs_list
    pedidos = [("1m", s.candle_buffer_1m)] + [
        (tf, getattr(s, f"candle_buffer_{tf}", 200)) for tf in tfs
    ]
    resultados = await asyncio.gather(
        *(fetch_candles(symbol, tf, limite) for tf, limite in pedidos),
        return_exceptions=True,
    )
    buffers: Dict[str, list] = {}
    for (tf, _), velas in zip(pedidos, resultados):
        buffers[tf] = [] if isinstance(velas, BaseException) else velas
    return {tf: buffers.get(tf, []) for tf in tfs}, buffers.get("1m", [])


def _estadistica_vigente() -> dict:
    """
    Tasas base de `rupturas_tf`, cacheadas.

    Si la base no esta disponible se devuelve vacio y el informe se enseña como
    antes, sin cifras: una consulta manual no puede caerse porque falte una
    estadistica que es un anadido.
    """
    global _stats_cache
    s = get_settings()
    ahora = time.monotonic()
    if _stats_cache[1] and ahora - _stats_cache[0] < s.informe_stats_cache_seconds:
        return _stats_cache[1]
    try:
        from src.persistence.db import get_db
        instantanea = get_db().estadistica_rupturas().instantanea()
    except Exception as e:
        logger.debug(f"estadistica de rupturas no disponible: {type(e).__name__}")
        instantanea = {}
    _stats_cache = (ahora, instantanea)
    return instantanea


async def obtener_informe(symbol: str, engine=None) -> Optional[dict]:
    """
    Informe del par. Devuelve None si no hay datos en ninguna de las dos vias
    (par inexistente, o Binance sin respuesta).

    Primero el motor: si el par ya se sigue, sus buffers estan en memoria, con
    su historia reparada y sus indicadores por TF ya calculados. Solo si no
    esta se baja de Binance.
    """
    s = get_settings()
    st = engine.get_symbol(symbol) if engine is not None else None
    if st is not None and st.candles:
        buffers = {tf: list(st.get_candles_tf(tf)) for tf in s.informe_tfs_list}
        ind_htf = {tf: st.ind_htf.get(tf) for tf in s.informe_tfs_list}
        return construir_informe(
            symbol, st.metrics.price, buffers, list(st.candles),
            ind_htf=ind_htf, fuente=FUENTE_MOTOR,
            estadistica=_estadistica_vigente(),
        )

    ahora = time.monotonic()
    guardado = _cache.get(symbol)
    if guardado is not None and ahora - guardado[0] < s.informe_cache_seconds:
        return guardado[1]

    buffers, candles_1m = await _buffers_rest(symbol)
    if not candles_1m or not any(buffers.values()):
        logger.info(f"[{symbol}] consulta directa sin velas: par desconocido o REST caido")
        return None

    informe = construir_informe(
        symbol, candles_1m[-1].c, buffers, candles_1m,
        fuente=FUENTE_CONSULTA, ts=candles_1m[-1].t,
        estadistica=_estadistica_vigente(),
    )
    _cache[symbol] = (ahora, informe)
    # El cache es de consultas manuales: crece con lo que se escriba a mano y
    # nunca se vacia solo. Cien pares distintos es techo de sobra.
    if len(_cache) > 100:
        viejos = sorted(_cache.items(), key=lambda kv: kv[1][0])[:50]
        for clave, _ in viejos:
            _cache.pop(clave, None)
    return informe
