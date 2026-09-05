"""
Alertas con entry congelado y ciclo de vida propio.

El problema que resuelve
------------------------
`calcular_niveles()` hace `entry = price`, y el engine lo recalculaba en CADA
vela 1m cerrada. Resultado: el entry, el TP y el SL se movian con el precio.
Lo que parecia "la alerta se actualiza" era en realidad el sistema
persiguiendo el precio hacia arriba y ofreciendo una entrada cada vez peor.

Caso real (COTIUSDT, 4-sep-2026):
    11:04  SUBIENDO score=86  entry 0.01412
    11:13  SUBIENDO score=86  entry 0.01430   <- +1.3% mas arriba
    11:17  techo real 0.01436
La segunda "alerta" ofrecia entrar a un 0.4% del techo.

Como funciona ahora
-------------------
Una AlertaActiva se crea UNA vez y congela entry/TP/SL en ese instante. A
partir de ahi solo se actualiza el precio vivo y el delta CONTRA ESE ENTRY.
Nunca se re-emite el mismo par mas arriba mientras siga viva.

Ciclo de vida:

    VIVA              el impulso aguanta Y el par sigue en un estado que
                      sostenga la señal (subida, fondo o consolidacion)
    PERDIENDO_FUERZA  se degrado durante N velas seguidas — por impulso o
                      porque el par cayo a NEUTRAL; sigue visible unos
                      minutos para que se vea que murio, en vez de que la
                      fila desaparezca sin explicacion
    CERRADA           toco TP o SL, se agoto el declive, el par paso a
                      CAYENDO, o caduco

Las dos condiciones se miran por separado a proposito: una alerta seguia
VIVA con el par ya en NEUTRAL porque el ciclo solo consultaba el impulso.

La puerta de entrada y la de salida son distintas a proposito: para EMITIR se
exige impulso sano y poco recorrido consumido; para MANTENER solo se mira la
fase. Si no, una alerta buena se caeria sola por el simple hecho de avanzar.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.analysis.impulse import FASES_OK, FASE_AGOTADA, FASE_DESACELERANDO
from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

ESTADO_VIVA = "VIVA"
ESTADO_DECLIVE = "PERDIENDO_FUERZA"
ESTADO_CERRADA = "CERRADA"

# Setups cuya tesis es el GIRO, no la continuacion del impulso. En estos el
# precio bajo la EMA7 es la condicion normal, no una señal de agotamiento.
_SETUPS_DE_GIRO = {"TOCÓ_FONDO", "CONSOLIDANDO"}

# Estados que sostienen una alerta viva. Si el par se sale de aqui, la
# tesis de la señal ya no se cumple, aunque el impulso siga marcando bien.
_ESTADOS_VALIDOS = {"TOCÓ_FONDO", "CONSOLIDANDO", "SUBIENDO", "BREAKOUT_INCIPIENTE"}
# CAYENDO no espera al contador: la tesis esta rota, no debilitada.
_ESTADO_ROTO = "CAYENDO"

MOTIVO_TP = "TP_ALCANZADO"
MOTIVO_SL = "SL_ALCANZADO"
MOTIVO_IMPULSO = "IMPULSO_AGOTADO"
MOTIVO_CADUCA = "CADUCADA"
MOTIVO_ESTADO = "ESTADO_DEGRADADO"

# Marcadores del tablero. No son excluyentes: una alerta puede haber caido a
# -1.2% y despues subir a +3.2%, y ver los dos a la vez es justo el dato.
MARCA_VERDE_PCT = 3.2      # objetivo
MARCA_MORADO_PCT = 4.2     # objetivo holgado
MARCA_AMARILLO_PCT = -1.2  # SL medio observado en las señales que se torcieron


@dataclass
class AlertaActiva:
    symbol: str
    signal_id: Optional[int]
    ts_emision: int

    # --- CONGELADOS en la emision: no se recalculan nunca ---
    entry: float
    take_profit: Optional[float]
    stop_loss: Optional[float]
    score_emision: int
    tier_emision: str
    estado_emision: str
    macro_emision: str
    fase_emision: str
    fuerza_emision: int
    consumido_emision: Optional[float]

    # --- Vivos ---
    estado: str = ESTADO_VIVA
    precio_actual: float = 0.0
    delta_pct: float = 0.0          # contra el entry CONGELADO
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    fase_actual: str = ""
    fuerza_actual: int = 0
    velas_degradadas: int = 0
    es_giro: bool = False   # setup de fondo/consolidacion, no de continuacion
    estado_actual: str = ""  # display_state del par ahora mismo
    ts_declive: Optional[int] = None
    ts_cierre: Optional[int] = None
    motivo_cierre: str = ""
    historia_fuerza: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal_id": self.signal_id,
            "ts_emision": self.ts_emision,
            "edad_min": round((int(time.time() * 1000) - self.ts_emision) / 60000.0, 1),
            # congelados
            "entry": self.entry,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "tp_pct": (round((self.take_profit - self.entry) / self.entry * 100, 2)
                       if self.take_profit else None),
            "sl_pct": (round((self.stop_loss - self.entry) / self.entry * 100, 2)
                       if self.stop_loss else None),
            "score_emision": self.score_emision,
            "tier_emision": self.tier_emision,
            "estado_emision": self.estado_emision,
            "fase_emision": self.fase_emision,
            "fuerza_emision": self.fuerza_emision,
            "consumido_emision": self.consumido_emision,
            # vivos
            "estado": self.estado,
            "precio_actual": self.precio_actual,
            "delta_pct": round(self.delta_pct, 2),
            "mfe_pct": round(self.mfe_pct, 2),
            "mae_pct": round(self.mae_pct, 2),
            "es_giro": self.es_giro,
            "estado_actual": self.estado_actual,
            "fase_actual": self.fase_actual,
            "fuerza_actual": self.fuerza_actual,
            "fuerza_tendencia": self._tendencia(),
            "marcadores": self.marcadores(),
            "motivo_cierre": self.motivo_cierre,
        }

    def marcadores(self) -> list:
        """
        Colores segun hasta donde llego el precio desde el entry CONGELADO.
        ROJO usa el SL que el sistema fijo para esta señal, no un % fijo.
        """
        m = []
        if self.mfe_pct >= MARCA_MORADO_PCT:
            m.append("MORADO")
        if self.mfe_pct >= MARCA_VERDE_PCT:
            m.append("VERDE")
        if self.mae_pct <= MARCA_AMARILLO_PCT:
            m.append("AMARILLO")
        if self.stop_loss and self.entry > 0:
            sl_pct = (self.stop_loss - self.entry) / self.entry * 100.0
            if self.mae_pct <= sl_pct:
                m.append("ROJO")
        return m

    def _tendencia(self) -> int:
        """Diferencia de fuerza contra hace unas velas: signo del declive."""
        h = self.historia_fuerza
        if len(h) < 4:
            return 0
        return h[-1] - h[-4]


class AlertManager:
    """
    Guarda las alertas activas por simbolo. Una viva por simbolo: mientras
    dure, el par no vuelve a emitir (era justo lo que producia la cascada de
    entries cada vez mas altos).
    """

    def __init__(self) -> None:
        self._activas: Dict[str, AlertaActiva] = {}
        self._ultimo_cierre: Dict[str, int] = {}

    # --- Consulta ---------------------------------------------------------

    def get(self, symbol: str) -> Optional[AlertaActiva]:
        return self._activas.get(symbol)

    def activas(self) -> List[dict]:
        return [a.to_dict() for a in self._activas.values()]

    def tiene_activa(self, symbol: str) -> bool:
        return symbol in self._activas

    # --- Emision ----------------------------------------------------------

    def puede_emitir(self, symbol: str, impulso, now_ms: int,
                     display_state: str = "") -> tuple:
        """
        Devuelve (bool, motivo).

        El criterio depende del TIPO de setup, y esto es lo que fallaba antes:
        se aplicaba el test de "subida que se apaga" a TODOS los estados. Un
        TOCÓ_FONDO o un CONSOLIDANDO tienen el precio bajo la EMA7 por
        definicion — acaban de caer o estan laterales — asi que el test los
        marcaba AGOTADA siempre. Bloqueo 84 setups de fondo y consolidacion en
        las primeras horas: un error de categoria, no un filtro.

          SUBIENDO / BREAKOUT   la tesis es la continuacion del impulso, asi
                                que se exige impulso vivo y poco recorrido.
          TOCÓ_FONDO / CONSOLID. la tesis es el giro, no la continuacion. Lo
                                que hay que evitar es el cuchillo cayendo, no
                                la falta de impulso alcista (que es normal).
        """
        s = get_settings()
        if symbol in self._activas:
            return False, "ya hay una alerta viva para el par"

        ultimo = self._ultimo_cierre.get(symbol)
        if ultimo and now_ms - ultimo < s.alerta_recooldown_minutos * 60_000:
            restante = (s.alerta_recooldown_minutos * 60_000 - (now_ms - ultimo)) / 60000.0
            return False, f"en cooldown ({restante:.0f} min)"

        if not impulso.valid:
            return False, "impulso no evaluable"

        if display_state in _SETUPS_DE_GIRO:
            # La FSM ya exige que la caida se desacelere para llegar a
            # BOTTOMING/VALLEY. Aqui solo se veta lo que esa comprobacion no
            # ve: que la caida siga yendo a mas en los TFs lentos.
            if impulso.caida_acelerando:
                return False, "la caida sigue acelerando (cuchillo cayendo)"
            return True, ""

        # Setups de continuacion: el impulso es la tesis
        if impulso.fase not in FASES_OK:
            return False, f"impulso {impulso.fase} — {impulso.reason}"
        if (impulso.consumido_pct is not None
                and impulso.consumido_pct > s.alerta_consumido_max):
            return False, (f"movimiento ya consumido {impulso.consumido_pct}% "
                           f"(max {s.alerta_consumido_max}%)")
        return True, ""

    def emitir(self, symbol: str, signal_id: Optional[int], now_ms: int,
               snapshot: dict, trade_levels: dict, impulso) -> Optional[AlertaActiva]:
        entry = trade_levels.get("entry")
        if not entry or entry <= 0:
            return None

        a = AlertaActiva(
            symbol=symbol,
            signal_id=signal_id,
            ts_emision=now_ms,
            entry=float(entry),
            take_profit=trade_levels.get("take_profit"),
            stop_loss=trade_levels.get("stop_loss"),
            score_emision=snapshot.get("score", 0),
            tier_emision=snapshot.get("tier", "NINGUNO"),
            estado_emision=snapshot.get("display_state", ""),
            macro_emision=snapshot.get("macro_global", ""),
            fase_emision=impulso.fase,
            fuerza_emision=impulso.fuerza,
            consumido_emision=impulso.consumido_pct,
            precio_actual=float(entry),
            fase_actual=impulso.fase,
            fuerza_actual=impulso.fuerza,
            es_giro=snapshot.get("display_state", "") in _SETUPS_DE_GIRO,
        )
        a.historia_fuerza.append(impulso.fuerza)
        self._activas[symbol] = a
        logger.info(
            f"[{symbol}] ALERTA EMITIDA | entry={entry} (CONGELADO) "
            f"TP={a.take_profit} SL={a.stop_loss} | score={a.score_emision} "
            f"{a.tier_emision} | impulso {impulso.fase} fuerza={impulso.fuerza} "
            f"consumido={impulso.consumido_pct}%"
        )
        return a

    # --- Actualizacion ----------------------------------------------------

    def actualizar(self, symbol: str, now_ms: int, high: float, low: float,
                   close: float, impulso,
                   display_state: str = "") -> Optional[AlertaActiva]:
        """
        Refresca la alerta viva con la vela recien cerrada. Devuelve la alerta
        si acaba de cambiar de estado (para emitir el evento), si no None.
        """
        a = self._activas.get(symbol)
        if a is None:
            return None

        s = get_settings()
        a.precio_actual = close
        a.delta_pct = (close - a.entry) / a.entry * 100.0
        a.mfe_pct = max(a.mfe_pct, (high - a.entry) / a.entry * 100.0)
        a.mae_pct = min(a.mae_pct, (low - a.entry) / a.entry * 100.0)

        if impulso is not None and impulso.valid:
            a.fase_actual = impulso.fase
            a.fuerza_actual = impulso.fuerza
            a.historia_fuerza.append(impulso.fuerza)
            if len(a.historia_fuerza) > 30:
                a.historia_fuerza.pop(0)

        # --- Desenlace por precio: TP/SL contra los niveles CONGELADOS ---
        if a.stop_loss and low <= a.stop_loss:
            return self._cerrar(a, now_ms, MOTIVO_SL)
        if a.take_profit and high >= a.take_profit:
            return self._cerrar(a, now_ms, MOTIVO_TP)

        # --- Caducidad ---
        if now_ms - a.ts_emision >= s.alerta_vida_horas * 3600_000:
            return self._cerrar(a, now_ms, MOTIVO_CADUCA)

        # --- El par dejo de estar en un estado que sostenga la alerta ---
        # Una alerta seguia VIVA con el par ya en NEUTRAL porque el ciclo de
        # vida solo miraba la fase de impulso. Pero si la FSM ya no ve ni
        # subida ni fondo ni consolidacion, la tesis de la señal se acabo,
        # marque lo que marque el impulso.
        if display_state:
            a.estado_actual = display_state
            if display_state == _ESTADO_ROTO:
                # Cayendo: no es debilidad, es lo contrario de la tesis.
                a.estado = ESTADO_DECLIVE
                a.ts_declive = a.ts_declive or now_ms
                return self._cerrar(a, now_ms, MOTIVO_ESTADO)
            if display_state not in _ESTADOS_VALIDOS:
                a.velas_degradadas += 1
                if (a.estado == ESTADO_VIVA
                        and a.velas_degradadas >= s.alerta_velas_declive):
                    a.estado = ESTADO_DECLIVE
                    a.ts_declive = now_ms
                    logger.info(
                        f"[{symbol}] alerta PERDIENDO FUERZA | el par paso a "
                        f"{display_state} | delta {a.delta_pct:+.2f}%"
                    )
                    return a
                if a.estado == ESTADO_DECLIVE and a.ts_declive and (
                        now_ms - a.ts_declive >= s.alerta_minutos_declive * 60_000):
                    return self._cerrar(a, now_ms, MOTIVO_ESTADO)
                return None
            # Estado valido otra vez. Se reinicia aqui porque un setup de
            # giro salta el bloque de impulso de abajo y su contador no
            # se limpiaria nunca.
            if a.velas_degradadas and a.es_giro:
                a.velas_degradadas = 0
                if a.estado == ESTADO_DECLIVE:
                    a.estado = ESTADO_VIVA
                    a.ts_declive = None
                    logger.info(
                        f"[{symbol}] alerta recupera estado ({display_state}) "
                        f"| delta {a.delta_pct:+.2f}%"
                    )
                    return a

        # --- Degradacion del impulso ---
        # En un setup de giro no se aplica: su fase es AGOTADA por
        # construccion (precio bajo la EMA7 tras la caida), asi que la alerta
        # entraria en declive en la vela siguiente a emitirse. Ahi el
        # desenlace lo marcan TP/SL y la caducidad.
        if impulso is not None and impulso.valid and not a.es_giro:
            degradada = impulso.fase in (FASE_DESACELERANDO, FASE_AGOTADA)
            if degradada:
                a.velas_degradadas += 1
            else:
                # Se recupero: vuelve a estar viva y se reinicia el contador.
                a.velas_degradadas = 0
                if a.estado == ESTADO_DECLIVE:
                    a.estado = ESTADO_VIVA
                    a.ts_declive = None
                    logger.info(
                        f"[{symbol}] alerta recupera impulso ({impulso.fase}) "
                        f"| delta {a.delta_pct:+.2f}%"
                    )
                    return a

            # AGOTADA no espera: es techo confirmado, no perdida de ritmo.
            umbral = 1 if impulso.fase == FASE_AGOTADA else s.alerta_velas_declive
            if a.estado == ESTADO_VIVA and a.velas_degradadas >= umbral:
                a.estado = ESTADO_DECLIVE
                a.ts_declive = now_ms
                logger.info(
                    f"[{symbol}] alerta PERDIENDO FUERZA | {impulso.fase} "
                    f"fuerza={impulso.fuerza} | delta {a.delta_pct:+.2f}% "
                    f"| {impulso.reason}"
                )
                return a

        # --- Fin del periodo de aviso ---
        if (a.estado == ESTADO_DECLIVE and a.ts_declive
                and now_ms - a.ts_declive >= s.alerta_minutos_declive * 60_000):
            return self._cerrar(a, now_ms, MOTIVO_IMPULSO)

        return None

    def _cerrar(self, a: AlertaActiva, now_ms: int, motivo: str) -> AlertaActiva:
        a.estado = ESTADO_CERRADA
        a.ts_cierre = now_ms
        a.motivo_cierre = motivo
        self._activas.pop(a.symbol, None)
        self._ultimo_cierre[a.symbol] = now_ms
        logger.info(
            f"[{a.symbol}] ALERTA CERRADA -> {motivo} | entry={a.entry} "
            f"final={a.precio_actual} delta={a.delta_pct:+.2f}% | "
            f"MFE {a.mfe_pct:+.2f}% MAE {a.mae_pct:+.2f}% | "
            f"vivio {(now_ms - a.ts_emision)/60000.0:.0f} min"
        )
        return a
