export type TFTrend = "ALCISTA" | "NEUTRAL" | "BAJISTA";
export type DisplayState =
  | "CAYENDO"
  | "TOCÓ_FONDO"
  | "CONSOLIDANDO"
  | "SUBIENDO"
  | "BREAKOUT_INCIPIENTE"
  | "NEUTRAL";
export type Tier =
  | "NINGUNO"
  | "VIGILANCIA"
  | "MODERADA"
  | "FUERTE"
  | "EXTRA-FUERTE";

export interface MacroTrends {
  "15m": TFTrend;
  "1h": TFTrend;
  "4h": TFTrend;
  "1d": TFTrend;
}

export interface TradeLevels {
  valid: boolean;
  entry: number | null;
  take_profit: number | null;
  stop_loss: number | null;
  risk_reward: number | null;
  risk_pct: number | null;
  reward_pct: number | null;
  atr_pct: number | null;
  nearest_resistance: number | null;
  tp_blocked_by_resistance: boolean;
  sl_basis: string;
  reason: string;
}

export interface SRLevel {
  precio: number;
  toques: number;
}

export interface SRLevels {
  soportes: SRLevel[];
  resistencias: SRLevel[];
}

export interface ConsolidationInfo {
  consolidating: boolean;
  atr_pct: number | null;
  atr_percentile: number | null;
  ma_convergent: boolean;
  vol_declining: boolean;
  candles_in_state: number;
}

export type FaseImpulso =
  | "ACELERANDO"
  | "SOSTENIDA"
  | "DESACELERANDO"
  | "AGOTADA"
  | "SIN_DATOS";

/** Fuerza del impulso: la derivada (¿sigue subiendo?), no la magnitud. */
export interface Impulso {
  valid: boolean;
  fuerza: number;
  fase: FaseImpulso;
  aceleracion: number | null;
  cuerpo_ratio: number | null;
  vol_ratio: number | null;
  consumido_pct: number | null;
  reason: string;
}

/**
 * Alerta con entry CONGELADO en la emisión. `entry`, `take_profit` y
 * `stop_loss` no cambian nunca; `delta_pct` se mide siempre contra ese entry.
 */
export interface AlertaActiva {
  symbol: string;
  ts_emision: number;
  edad_min: number;
  entry: number;
  take_profit: number | null;
  stop_loss: number | null;
  tp_pct: number | null;
  sl_pct: number | null;
  score_emision: number;
  tier_emision: string;
  fase_emision: FaseImpulso;
  fuerza_emision: number;
  consumido_emision: number | null;
  estado: "VIVA" | "PERDIENDO_FUERZA" | "CERRADA";
  /** display_state del par ahora; si sale de los estados validos, la alerta decae */
  estado_actual?: string;
  precio_actual: number;
  delta_pct: number;
  mfe_pct: number;
  mae_pct: number;
  fase_actual: FaseImpulso;
  fuerza_actual: number;
  fuerza_tendencia: number;
  motivo_cierre: string;
}

export interface PairState {
  symbol: string;
  display_state: DisplayState;
  fsm_state: string;
  score: number;
  score_trend: number;
  tier: Tier;
  pos_en_rango: number;
  fading: boolean;
  macro_global: TFTrend;
  macro_gate_mult: number;
  macro_trends: MacroTrends;
  price: number;
  ret_1m_pct: number;
  z_drop: number;
  z_rise: number;
  velocity: number;
  vol_ratio: number;
  drawdown_pct: number;
  sigma_pct: number;
  buy_ratio_30s: number;
  flow_trades_30s: number;
  flow_confirm: boolean;
  rsi5: number | null;
  macd_rising: boolean | null;
  trend_up: boolean | null;
  n_candles_1m: number;
  fsm_since_ms: number;
  score_since_ms: number;
  slopes: Record<string, Record<string, number>>;
  trade_levels: TradeLevels;
  impulso?: Impulso;
  alerta?: AlertaActiva;
  consolidation: ConsolidationInfo;
  sr_levels: SRLevels;
  btc_regime: TFTrend;
  is_fakeout: boolean;
}

export interface StateEvent {
  ts: number;
  state: string;
  score: number;
  tier: string;
  macro: string;
  fsm: string;
}

export interface WSMessage {
  type:
    | "snapshot"
    | "update"
    | "alert"
    | "transition"
    | "early"
    | "watch"
    | "ping"
    | "alert_tendencia"
    | "alert_ignicion";
  ts: number;
  pairs?: PairState[];
  // En "update" el backend manda solo los pares que cambiaron; `removed` lista
  // los que dejaron de estar en el listado y hay que quitar del mapa.
  removed?: string[];
  // For single-pair events:
  symbol?: string;
  tier?: string;
  score?: number;
  display_state?: string;
  // Alertas de perfil (tendencia sostenida / ignicion)
  perfil?: string;
  perfil_score?: number;
  perfil_reason?: string;
}
