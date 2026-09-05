"""
Configuracion centralizada de SACBinance v3.

Combina la logica adaptativa de v2 (z-scores por moneda, EWMA sigma) con el
analisis macro de tendencia (pendiente MA por TF, gate con multiplicador de score).
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # --- Binance ---
    binance_rest_base: str = Field(default="https://api.binance.com")
    binance_ws_raw: str = Field(default="wss://stream.binance.com:9443/ws")

    # --- Universo ---
    min_volume_24h: float = Field(default=1_000_000)
    max_pairs_to_scan: int = Field(default=250)
    universe_refresh_seconds: int = Field(default=3600)

    # --- Hidratacion historica ---
    history_days: int = Field(default=5)
    hydration_concurrency: int = Field(default=20)  # requests simultaneos REST

    # --- Buffers por TF ---
    # Todos >= 160: analizar_tf() necesita 103 velas para la MA99. Los de
    # 4h/1d antes eran 30/10 -> su tendencia nunca se calculaba (bug).
    candle_buffer_1m: int = Field(default=320)   # ~5.3h de velas 1m
    candle_buffer_5m: int = Field(default=350)   # ~29h de velas 5m
    candle_buffer_15m: int = Field(default=260)  # ~65h de velas 15m
    candle_buffer_1h: int = Field(default=180)   # ~7.5 dias de velas 1h
    candle_buffer_4h: int = Field(default=180)   # ~30 dias de velas 4h
    candle_buffer_1d: int = Field(default=180)   # 180 dias de velas 1d

    # --- Scanner / shortlist (hereda de v2) ---
    # La shortlist decide que pares reciben stream aggTrade (flujo agresor).
    # Hasta ahora update_shortlist() no la llamaba NADIE: _shortlist quedaba
    # vacia para siempre -> cero streams aggTrade -> flow_snap siempre default
    # -> `confirmed` siempre False -> todo par capado a 79. Ahora hay un loop
    # en main.py que la recalcula cada shortlist_refresh_seconds.
    shortlist_max: int = Field(default=40)
    shortlist_z_threshold: float = Field(default=2.0)
    shortlist_refresh_seconds: int = Field(default=180)
    shortlist_min_churn: float = Field(default=0.25)  # % de cambio para reconectar WS-A
    price_tape_seconds: int = Field(default=360)

    # --- Regularizador visual ---
    regularizer_window: int = Field(default=8)
    regularizer_deadband_pct: float = Field(default=0.20)

    # --- Ruta provisional ---
    live_min_interval: float = Field(default=1.0)
    tick_interval: float = Field(default=4.0)

    # --- Velas HTF en formacion (nuevo) ---
    # Binance dibuja la vela 15m/1h EN FORMACION y recalcula sus indicadores
    # tick a tick. Antes descartabamos k["x"]==False, asi que la tendencia 15m
    # podia tener 15 min de antiguedad y la de 1h hasta 60 min: esa era la
    # causa real del "desfase" contra la app, no la carga de CPU.
    htf_live_enabled: bool = Field(default=True)
    htf_live_min_interval: float = Field(default=3.0)   # recalculo por par/TF
    htf_live_tfs: str = Field(default="15m,1h")

    # --- Throttling de analisis pesado ---
    # S/R sobre 1h y consolidacion sobre 15m no cambian en 60 segundos. Para
    # pares no interesantes se recalculan cada heavy_interval en vez de en
    # cada vela 1m de cada uno de los ~250 pares.
    heavy_analysis_interval: float = Field(default=300.0)
    engine_yield_every: int = Field(default=25)  # cede el event loop cada N velas

    # --- Persistencia diferida ---
    db_flush_interval: float = Field(default=5.0)
    db_flush_max_pending: int = Field(default=500)

    # --- Flujo agresor (aggTrade) ---
    flow_min_trades: int = Field(default=8)

    # --- Persistencia SQLite ---
    # Relativo al directorio backend/ por defecto (portable Linux/Windows).
    # Override con la variable de entorno DB_PATH en .env si se quiere otra ruta.
    db_path: str = Field(default="data/sacbinance.db")
    history_rolling_days: int = Field(default=30)     # retencion de symbol_states
    log_retention_days: int = Field(default=14)       # retencion de analysis_log
    prune_interval_minutes: int = Field(default=60)   # cada cuanto se purga

    # --- Estadistica adaptativa (hereda de v2) ---
    ewma_alpha: float = Field(default=0.05)
    sigma_min: float = Field(default=0.0008)
    warmup_candles: int = Field(default=20)

    # --- FSM (en unidades de sigma, hereda de v2) ---
    drop_z: float = Field(default=-2.2)
    drop_window: int = Field(default=2)
    bottoming_decel: float = Field(default=0.4)
    valley_stabilize_candles: int = Field(default=3)
    valley_band_sigma: float = Field(default=1.0)
    rise_z: float = Field(default=2.0)
    rise_window: int = Field(default=3)
    blowoff_z: float = Field(default=4.5)
    blowoff_vol_ratio: float = Field(default=3.0)
    neutral_decay_candles: int = Field(default=5)

    # --- Macro gate (NUEVO en v3) ---
    # Pesos de cada TF para la tendencia global (deben sumar 1.0)
    macro_weight_1d: float = Field(default=0.35)
    macro_weight_4h: float = Field(default=0.30)
    macro_weight_1h: float = Field(default=0.25)
    macro_weight_15m: float = Field(default=0.10)

    # Umbral de slope (% cambio en N periodos) para clasificar ALCISTA/BAJISTA
    slope_alcista: float = Field(default=0.15)   # >+0.15% = ALCISTA
    slope_bajista: float = Field(default=-0.15)  # <-0.15% = BAJISTA
    slope_lookback: int = Field(default=3)       # ultimos N cierres para slope

    # Multiplicadores del gate sobre el score base
    gate_bajista_rising_mult: float = Field(default=0.10)   # RISING + macro bajista = casi suprimido
    gate_bajista_valley_mult: float = Field(default=0.40)   # VALLEY + macro bajista = vigilar
    gate_alcista_rising_mult: float = Field(default=1.30)   # RISING + macro alcista = amplificado
    gate_alcista_valley_mult: float = Field(default=1.20)   # VALLEY + macro alcista
    gate_neutral_score_floor: int = Field(default=75)       # umbral mas alto cuando macro neutral
    gate_bajista_score_floor: int = Field(default=85)       # ir contra la macro: lo mas exigente

    # --- Consolidacion (ATR adaptativo) ---
    atr_period: int = Field(default=14)
    atr_percentil_consolidacion: int = Field(default=20)    # ATR% < P20 = compresion
    consolidacion_min_velas_4h: int = Field(default=4)
    consolidacion_min_velas_1h: int = Field(default=2)
    consolidacion_min_velas_15m: int = Field(default=2)

    # --- Breakout ---
    breakout_vol_mult: float = Field(default=1.5)   # volumen > X× SMA para breakout
    breakout_score_min: int = Field(default=70)     # score minimo para BREAKOUT_INCIPIENTE
    breakout_cross_lookback: int = Field(default=6) # velas 1m para detectar el cruce de MA99

    # --- Niveles de trading (entry / take profit / stop loss) ---
    swing_lookback_15m: int = Field(default=12)     # velas 15m para el swing low estructural
    sl_buffer_atr: float = Field(default=0.3)       # buffer (×ATR) por debajo del swing low
    sl_atr_mult: float = Field(default=2.0)         # SL fallback = entry - N×ATR
    rr_target: float = Field(default=2.0)           # ratio beneficio/riesgo objetivo
    max_risk_pct: float = Field(default=6.0)        # riesgo maximo aceptable (% del entry)
    min_risk_atr: float = Field(default=0.5)        # riesgo minimo = N×ATR (evita SL pegado)

    # --- Clasificacion de estado visible (filtro de contexto) ---
    # "TOCÓ FONDO" / "CONSOLIDANDO" solo si el precio esta en la zona baja del
    # rango 15m. Por encima de esto, un dip de 1m es un pullback, no un fondo.
    toco_fondo_max_pos: float = Field(default=0.40)   # 0=minimo del rango, 1=maximo
    rango_lookback_15m: int = Field(default=50)       # velas 15m para medir el rango

    # --- Persistencia visual del dashboard ---
    # Una moneda que deja de ser interesante no desaparece de golpe: sigue
    # visible "perdiendo fuerza" durante este tiempo.
    dashboard_retention_minutes: int = Field(default=20)

    # --- Niveles de alerta (score 0-100) ---
    tier_vigilancia: int = Field(default=60)
    tier_moderada: int = Field(default=70)
    tier_fuerte: int = Field(default=80)
    tier_extra: int = Field(default=90)
    score_min_dashboard: int = Field(default=60)

    # --- Gate BTC (regimen global) ---
    btc_symbol: str = Field(default="BTCUSDT")
    btc_bajista_mult: float = Field(default=0.55)   # penaliza señales alcistas si BTC bajista
    btc_alcista_mult: float = Field(default=1.10)   # leve amplificacion si BTC alcista

    # --- Auto-evaluacion de señales ---
    signal_expiry_hours: int = Field(default=12)    # cierra como EXPIRED tras N horas

    # --- Fuerza del impulso (derivada, no magnitud) ---
    # El score mide cuanto subio; esto mide si SIGUE subiendo. Se compara la
    # mitad reciente de la ventana contra la previa en 1m / 3m / 5m.
    impulso_min_velas: int = Field(default=40)
    impulso_ventana_1m: int = Field(default=12)   # 12 min
    impulso_ventana_3m: int = Field(default=10)   # 30 min
    impulso_ventana_5m: int = Field(default=8)    # 40 min
    impulso_peso_1m: float = Field(default=0.25)  # rapido pero ruidoso
    impulso_peso_3m: float = Field(default=0.40)
    impulso_peso_5m: float = Field(default=0.35)

    # Umbrales de fase. Se exigen DOS señales flojas de tres para declarar
    # DESACELERANDO: una sola es ruido de una vela suelta.
    impulso_acel_min: float = Field(default=0.75)     # bajo esto, pierde ritmo
    impulso_acel_fuerte: float = Field(default=1.25)  # sobre esto, acelera
    impulso_cuerpo_min: float = Field(default=0.80)   # cuerpos encogiendo
    impulso_vol_min: float = Field(default=0.75)      # volumen secandose
    impulso_rsi_techo: float = Field(default=78.0)
    impulso_lookback_consumido: int = Field(default=60)   # velas 1m
    impulso_consumido_penaliza: float = Field(default=4.0)   # % desde el minimo
    impulso_consumido_agotado: float = Field(default=12.0)   # % = ya es tarde

    # --- Alertas congeladas (ciclo de vida propio) ---
    # Una alerta se emite UNA vez con entry/TP/SL fijos. No se recalcula ni se
    # re-emite mas arriba: eso era perseguir el precio, no confirmar la señal.
    alerta_congelada_enabled: bool = Field(default=True)
    # Velas 1m seguidas con impulso degradado antes de marcarla en declive
    alerta_velas_declive: int = Field(default=3)
    # Minutos que sigue visible en "PERDIENDO FUERZA" antes de retirarse
    alerta_minutos_declive: int = Field(default=10)
    # Vida maxima de una alerta sin desenlace
    alerta_vida_horas: int = Field(default=6)
    # Espera antes de admitir una alerta nueva del mismo par
    alerta_recooldown_minutos: int = Field(default=45)
    # Recorrido maximo ya consumido para admitir una alerta NUEVA. Es una
    # puerta distinta de la fase: en el caso COTI del 4-sep el impulso seguia
    # vivo a las 11:13 (el techo no llego hasta las 11:17), pero el movimiento
    # ya llevaba un 4.2% recorrido — entrar ahi es perseguir, no anticipar.
    # Para MANTENER viva una alerta ya emitida no se aplica: solo la fase.
    alerta_consumido_max: float = Field(default=3.5)

    # --- Base corta post-caida ("flush -> base -> reclaim") ---
    # compression.py mira 96 velas de 15m (24h) y se pierde las bases de una
    # hora. Estos parametros salen de medir CHIPUSDT el 5-sep: caida -2.93%
    # en 32 min, base de 56 min con rango 3.01% y volumen al 61%, ruptura del
    # techo con volumen 3.9x.
    base_lookback_velas: int = Field(default=180)     # 3h de velas 1m
    base_min_velas: int = Field(default=20)           # base minima
    base_max_velas: int = Field(default=90)           # base maxima
    base_rango_max_pct: float = Field(default=3.5)    # ancho maximo de la base
    base_caida_min_velas: int = Field(default=10)     # historial previo minimo
    base_caida_min_pct: float = Field(default=2.0)    # caida previa minima
    base_vol_dryup_max: float = Field(default=0.85)   # vol base / vol caida
    base_ruptura_vol_min: float = Field(default=2.0)  # volumen en la ruptura
    base_max_sobre_techo_pct: float = Field(default=1.0)  # si no, llega tarde
    base_score_min: int = Field(default=60)

    # --- Medicion de outcomes (camino completo de cada señal) ---
    # A diferencia de signal_expiry_hours, esta ventana NO cierra la señal:
    # sigue el precio pase lo que pase con TP/SL, para poder responder que
    # hizo despues de tocar el stop.
    outcome_window_hours: int = Field(default=24)
    # Retroceso (%) a partir del cual el camino deja de considerarse "directo"
    forma_dip_umbral: float = Field(default=1.0)

    # --- Deteccion de fakeout ---
    fakeout_lookback_candles: int = Field(default=15)   # velas 1m tras breakout
    fakeout_penalty_minutes: int = Field(default=30)    # duracion de la penalizacion

    # --- Soporte / resistencia ---
    sr_pivot_window: int = Field(default=3)         # velas a cada lado para un pivote
    sr_cluster_pct: float = Field(default=0.6)      # % para agrupar pivotes en un nivel
    sr_min_touches: int = Field(default=2)          # toques minimos para validar un nivel
    sr_max_levels: int = Field(default=6)           # niveles a conservar por lado

    # --- Ancla diaria fija (00:00 UTC) ---
    # Reemplaza la ventana rolling 24h de Binance, cuyo denominador se mueve
    # solo y hace que el % cambie aunque el precio no haga nada.
    daily_anchor_enabled: bool = Field(default=True)

    # --- ALERTA A: tendencia sostenida (grind) ---
    grind_window_15m: int = Field(default=16)          # 16 velas 15m = 4 horas
    grind_r2_min: float = Field(default=0.70)          # que tan "recta" la subida
    grind_slope_min_pct_h: float = Field(default=0.25) # minimo %/hora
    grind_slope_max_pct_h: float = Field(default=3.0)  # por encima ya es ignicion
    grind_max_pullback_pct: float = Field(default=2.5) # retroceso maximo tolerado
    grind_min_above_ema: float = Field(default=0.70)   # % de cierres sobre EMA25
    grind_score_min: int = Field(default=65)

    # --- ALERTA B: ignicion (explosion) ---
    ignition_window_1m: int = Field(default=5)
    ignition_roc_min_pct: float = Field(default=1.2)
    ignition_vol_mult: float = Field(default=2.5)
    ignition_z_min: float = Field(default=2.0)
    ignition_rsi_max: float = Field(default=82.0)
    ignition_max_consumido_pct: float = Field(default=6.0)
    ignition_pct_dia_alto: float = Field(default=12.0)  # % desde open diario ya "caro"
    ignition_score_min: int = Field(default=70)

    # --- CAPA 1: compresion con contracciones progresivas ---
    compresion_window: int = Field(default=96)          # 96 velas 15m = 24h
    compresion_pivot_k: int = Field(default=2)          # fractal: k velas a cada lado
    compresion_atr_period: int = Field(default=14)
    compresion_atr_percentil_max: int = Field(default=35)
    compresion_min_contracciones: int = Field(default=2)
    compresion_max_contracciones: int = Field(default=5)
    compresion_min_profundidad_pct: float = Field(default=0.8)
    compresion_ratio_max: float = Field(default=0.85)   # progresiva: cada una < anterior
    compresion_half_min: float = Field(default=0.30)    # "regla de la mitad"
    compresion_half_max: float = Field(default=0.70)
    compresion_rango_max_pct: float = Field(default=12.0)
    compresion_vol_dryup_max: float = Field(default=0.75)
    compresion_cerca_pivot_pct: float = Field(default=1.5)
    compresion_base_velas: int = Field(default=20)
    compresion_score_min: int = Field(default=60)

    # --- CAPA 1: taxonomia ---
    # % desde el ancla diaria por debajo del cual una base se considera
    # "post-caida" y no acumulacion tranquila
    taxonomia_caida_dia_pct: float = Field(default=-3.0)

    # Cooldown por par y por tipo de alerta (evita spam de la misma senal)
    alert_cooldown_minutes: int = Field(default=30)

    # --- API ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    log_level: str = Field(default="INFO")

    @property
    def htf_live_tfs_list(self) -> List[str]:
        return [t.strip() for t in self.htf_live_tfs.split(",") if t.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
