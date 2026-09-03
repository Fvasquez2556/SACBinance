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
    shortlist_max: int = Field(default=40)
    shortlist_z_threshold: float = Field(default=2.0)
    price_tape_seconds: int = Field(default=360)

    # --- Regularizador visual ---
    regularizer_window: int = Field(default=8)
    regularizer_deadband_pct: float = Field(default=0.20)

    # --- Ruta provisional ---
    live_min_interval: float = Field(default=2.0)
    tick_interval: float = Field(default=4.0)

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

    # --- Deteccion de fakeout ---
    fakeout_lookback_candles: int = Field(default=15)   # velas 1m tras breakout
    fakeout_penalty_minutes: int = Field(default=30)    # duracion de la penalizacion

    # --- Soporte / resistencia ---
    sr_pivot_window: int = Field(default=3)         # velas a cada lado para un pivote
    sr_cluster_pct: float = Field(default=0.6)      # % para agrupar pivotes en un nivel
    sr_min_touches: int = Field(default=2)          # toques minimos para validar un nivel
    sr_max_levels: int = Field(default=6)           # niveles a conservar por lado

    # --- API ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    log_level: str = Field(default="INFO")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
