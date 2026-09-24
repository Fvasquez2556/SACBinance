"""
El adaptador: convierte el estado vivo en `Observacion`, corre los dos motores
y decide que merece guardarse.

Los motores son funciones puras y no saben que existe una base de datos ni un
reloj. Todo lo que tiene efecto —leer el estado del simbolo, cachear el ancla
de 1h, deduplicar, muestrear el universo, escribir— vive aqui. Asi las pruebas
del comportamiento no necesitan base, y este archivo solo tiene que acertar en
el fontanero.

Nada de lo que hay aqui puede cambiar una emision. Se llama DESPUES de que el
motor de produccion ya decidio, igual que el registro de identidad de la fase 1,
y cualquier excepcion suya se traga antes de llegar al operador.
"""
from __future__ import annotations

import time
from typing import Optional

from src.analysis.tf_rupture import leer_tf, resumir
from src.config.settings import get_settings
from src.motores.almacen import AlmacenMotores
from src.motores.caida import EstadoCaida, avanzar_caida
from src.motores.continuacion import evaluar_continuacion
from src.motores.contrato import (
    CANDIDATO,
    CONFLICTO,
    MOTOR_CAIDA,
    MOTOR_CONTINUACION,
    ORIGEN_ALERTA,
    ORIGEN_MUESTRA,
    ORIGEN_TRANSICION,
    ORIGEN_VETO,
    Observacion,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ServicioMotores:
    def __init__(self, almacen: AlmacenMotores) -> None:
        self.almacen = almacen
        self._ancla: dict = {}          # symbol -> (dict, ts_ms)
        self._marcos: dict = {}         # symbol -> {tf: LecturaTF}
        self._ultimo: dict = {}         # (symbol, motor) -> clave_cambio()
        self._ultimo_ms: dict = {}      # (symbol, motor) -> cuando se escribio
        self._caida: dict = almacen.cargar_estados_caida()
        self._muestra_ms: int = 0
        self._muestra_cursor: int = 0
        self._escritas_pasada: int = 0
        self._pasada_ms: int = 0

    # --- El ancla de marco lento -------------------------------------------

    def refrescar_ancla(self, symbol: str, st, tf: str, now_ms: int) -> None:
        """
        Se llama al CERRAR una vela de `tf`. Una ruptura de un marco solo puede
        cambiar cuando cierra una vela de ESE marco: releerla en cada vela de
        1m de cada par seria el mayor gasto del minuto y no cambiaria nada.

        Guarda la lectura de cualquier marco vigilado —para poder componer la
        confluencia— y ademas la del marco ancla aparte, que es la que decide.
        """
        s = get_settings()
        if tf not in s.informe_tfs_list and tf != s.motores_ancla_tf:
            return
        try:
            lectura = leer_tf(tf, list(st.get_candles_tf(tf)), st.metrics.price,
                              st.ind_htf.get(tf))
        except Exception as exc:
            logger.debug(f"[{symbol}] lectura de {tf} fallo: {exc}")
            return
        self._marcos.setdefault(symbol, {})[tf] = lectura
        if tf == s.motores_ancla_tf:
            self._ancla[symbol] = (lectura.to_dict(), now_ms)

    def _confluencia(self, symbol: str) -> dict:
        """
        Cuantos marcos apuntan a cada lado ahora mismo.

        Se guarda pero **no pondera nada**: medida contra su control, ninguna
        celda de confluencia bate al azar (AUC 0,506). Se conserva porque es
        barata y porque con mas regimen podria cambiar — no porque hoy sirva.
        """
        lecturas = list((self._marcos.get(symbol) or {}).values())
        if not lecturas:
            return {}
        try:
            r = resumir(lecturas)
        except Exception:
            return {}
        return {"dominante": r.get("direccion_dominante"),
                "tf_dominante": r.get("tf_dominante"),
                "alcistas": r.get("n_alcistas"), "bajistas": r.get("n_bajistas"),
                "confirmadas": r.get("n_confirmadas"),
                "en_conflicto": r.get("en_conflicto"),
                "marcos": sorted(self._marcos.get(symbol) or {})}

    def armar(self, states: dict) -> int:
        """
        Siembra el ancla al arrancar. Sin esto, los motores dirian «falta la
        lectura de 1h» durante la primera hora entera, que es cierto pero
        evitable: las velas ya estan en el buffer.
        """
        s = get_settings()
        now_ms = int(time.time() * 1000)
        n = 0
        for symbol, st in states.items():
            if not st.candles:
                continue
            for tf in dict.fromkeys(list(s.informe_tfs_list) + [s.motores_ancla_tf]):
                self.refrescar_ancla(symbol, st, tf, now_ms)
            n += 1
        logger.info(f"Motores en sombra: ancla de {s.motores_ancla_tf} sembrada "
                    f"en {n} pares")
        return n

    # --- Observacion --------------------------------------------------------

    def observar(self, symbol: str, st, now_ms: int) -> Observacion:
        s = get_settings()
        ancla, ancla_ts = self._ancla.get(symbol, ({}, 0))
        edad = (now_ms - ancla_ts) / 60_000.0 if ancla_ts else None
        ind = getattr(st, "ind", None)
        return Observacion(
            symbol=symbol, ts_ms=now_ms, precio=float(st.metrics.price or 0.0),
            velas_1m=len(st.candles),
            fsm_state=st.fsm_state, display_state=st.display_state,
            tendencias=dict(getattr(st, "macro_trends", {}) or {}),
            taxonomia=dict(getattr(st, "taxonomia", {}) or {}),
            impulso=dict(getattr(st, "impulso", {}) or {}),
            retroceso=dict(getattr(st, "retroceso", {}) or {}),
            compresion=dict(getattr(st, "compresion", {}) or {}),
            grind=dict(getattr(st, "grind", {}) or {}),
            ignicion=dict(getattr(st, "ignition", {}) or {}),
            base_rebote=dict(getattr(st, "base_rebote", {}) or {}),
            consolidacion=dict(getattr(st, "consolidation_info", {}) or {}),
            niveles=dict(getattr(st, "sr_levels", {}) or {}),
            plan=dict(getattr(st, "trade_levels", {}) or {}),
            flujo=(st.flow_snap.to_dict()
                   if hasattr(getattr(st, "flow_snap", None), "to_dict") else {}),
            ancla=ancla, ancla_tf=s.motores_ancla_tf, ancla_edad_min=edad,
            confluencia=self._confluencia(symbol),
            pos_en_rango=getattr(st, "pos_en_rango", None),
            atr_pct=getattr(ind, "atr_pct", None),
            vol_ratio=getattr(st.metrics, "vol_ratio", None),
            rango_1h_pct=getattr(st, "rango_1h_pct", None),
            drawdown_pct=getattr(st.metrics, "drawdown_from_peak", None),
            btc_regime=getattr(st, "btc_regime", "") or "",
        )

    # --- Pasada -------------------------------------------------------------

    def procesar(self, symbol: str, st, now_ms: int, *,
                 origen: Optional[str] = None, alerta_id: Optional[int] = None,
                 plan_id: Optional[int] = None,
                 episode_id: Optional[int] = None) -> Optional[dict]:
        """
        Corre los dos motores sobre un simbolo. Devuelve los veredictos, o None
        si no habia nada que hacer. `origen` fuerza el guardado (una alerta o un
        veto se guardan siempre, cambien o no de veredicto).
        """
        s = get_settings()
        if not s.motores_enabled:
            return None
        if now_ms - self._pasada_ms >= 60_000:
            self._pasada_ms = now_ms
            self._escritas_pasada = 0

        obs = self.observar(symbol, st, now_ms)
        veredictos = {}

        # --- Motor A ---
        lec_a = evaluar_continuacion(obs)
        veredictos[MOTOR_CONTINUACION] = lec_a
        self._quiza_guardar(lec_a, origen, alerta_id, plan_id, episode_id)

        # --- Motor B ---
        previo = self._caida.get(symbol) or EstadoCaida(symbol=symbol)
        nuevo, lec_b, motivo = avanzar_caida(previo, obs)
        veredictos[MOTOR_CAIDA] = lec_b
        # El estado en memoria se guarda SIEMPRE, no solo al cambiar de fase:
        # mientras la caida sigue activa el suelo baja sin que haya transicion,
        # y perder ese suelo es perder la referencia que invalida el rebote.
        # En la tabla solo se escribe al transicionar; si un reinicio recupera
        # un suelo mas alto del real, el motor invalida antes, que es el lado
        # seguro del error.
        self._caida[symbol] = nuevo
        if motivo is not None:
            try:
                self.almacen.transicion(
                    symbol, MOTOR_CAIDA, previo.estado, nuevo.estado, motivo,
                    now_ms, obs.precio, lec_b.datos)
                self.almacen.guardar_estado_caida(nuevo, now_ms)
            except Exception as exc:
                logger.debug(f"[{symbol}] transicion de caida no guardada: {exc}")
        self._quiza_guardar(lec_b, origen, alerta_id, plan_id, episode_id,
                            forzar=motivo is not None)
        return veredictos

    def _quiza_guardar(self, lectura, origen, alerta_id, plan_id, episode_id,
                       forzar: bool = False) -> None:
        s = get_settings()
        clave = (lectura.symbol, lectura.motor)
        cambio = self._ultimo.get(clave) != lectura.clave_cambio()
        if origen in (ORIGEN_ALERTA, ORIGEN_VETO, ORIGEN_MUESTRA):
            destino = origen
        elif cambio or forzar:
            destino = ORIGEN_TRANSICION
        else:
            return
        # Un par que oscila entre dos veredictos escribiria una fila por vela.
        # El enfriamiento lo corta, salvo para los dos veredictos que importan
        # y son raros: un candidato o un conflicto se guardan siempre.
        if (destino == ORIGEN_TRANSICION
                and lectura.veredicto not in (CANDIDATO, CONFLICTO)
                and lectura.ts_ms - self._ultimo_ms.get(clave, 0)
                < s.motores_transicion_cooldown_min * 60_000):
            self._ultimo[clave] = lectura.clave_cambio()
            return
        # El tope por pasada existe para que una rafaga no inunde la tabla, y
        # por eso se aplica SOLO a las transiciones, que son la unica fuente
        # sin limite propio. Las otras tres ya estan acotadas —las alertas y
        # los vetos por el ritmo de emision, la muestra por su configuracion— y
        # ademas son las unicas filas que llevan identidad: `alerta_id`,
        # `plan_id`, `episode_id`.
        #
        # Antes el tope las descartaba tambien a ellas, y ese enlace no se
        # recupera: la fila del minuto siguiente es otra observacion, sin la
        # alerta detras. Medido en produccion tras el despliegue, **36 de 100
        # alertas se quedaron sin lectura vinculada** por esta via. La muestra
        # es la poblacion de referencia de toda la fase: perder filas suyas en
        # silencio la sesga justo donde mas trabajo hay.
        if (destino == ORIGEN_TRANSICION
                and self._escritas_pasada >= s.motores_max_filas_por_pasada):
            return
        self._ultimo[clave] = lectura.clave_cambio()
        self._ultimo_ms[clave] = lectura.ts_ms
        try:
            self.almacen.guardar(lectura, destino, alerta_id=alerta_id,
                                 plan_id=plan_id, episode_id=episode_id)
            self._escritas_pasada += 1
        except Exception as exc:
            logger.debug(f"[{lectura.symbol}] lectura no guardada: {exc}")

    # --- Muestra del universo ----------------------------------------------

    def muestrear(self, states: dict, now_ms: int) -> int:
        """
        Guarda una tajada del universo mire lo que mire, pase lo que pase.

        Es la referencia contra la que se miden las otras filas. Rota sobre la
        lista ordenada para que en unas horas pasen todos los pares y ninguno
        quede sistematicamente fuera.
        """
        s = get_settings()
        if not s.motores_enabled or s.motores_muestra_por_pasada <= 0:
            return 0
        if now_ms - self._muestra_ms < s.motores_muestra_cada_min * 60_000:
            return 0
        self._muestra_ms = now_ms
        simbolos = sorted(states)
        if not simbolos:
            return 0
        n = min(s.motores_muestra_por_pasada, len(simbolos))
        tomados = 0
        for i in range(n):
            symbol = simbolos[(self._muestra_cursor + i) % len(simbolos)]
            st = states[symbol]
            if not st.candles:
                continue
            try:
                self.procesar(symbol, st, now_ms, origen=ORIGEN_MUESTRA)
                tomados += 1
            except Exception as exc:
                logger.debug(f"[{symbol}] muestra fallo: {exc}")
        self._muestra_cursor = (self._muestra_cursor + n) % len(simbolos)
        return tomados
