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
  /** Retroceso tipico del par en ventanas de 1h, medido en 1m. El SL no baja de aqui. */
  ruido_1m_pct: number | null;
  /** ¿El TP ofrecido llega al objetivo del operador (+3.2%)? Solo medicion. */
  objetivo_alcanzable: boolean;
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
  /** Lectura direccional: una lista de precios no dice si va a seguir bajando. */
  dist_soporte_pct: number | null;
  dist_resistencia_pct: number | null;
  /** Pegado al soporte y por encima: lo esta probando. */
  apoyado: boolean;
  /** Rompio hacia abajo un nivel que era soporte y ahora estorba desde arriba. */
  perdido: boolean;
  lectura: string;
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
export type Marcador = "VERDE" | "MORADO" | "AMARILLO" | "ROJO";

/**
 * Fase accionable: VIVA, PERDIENDO_FUERZA.
 * Fase de seguimiento (ya no pide actuar, pero no desaparece del tablero):
 * EN_RETROCESO, EN_VALLE, RECUPERANDO, CUMPLIDA.
 */
export type EstadoAlerta =
  | "VIVA"
  | "PERDIENDO_FUERZA"
  | "EN_RETROCESO"
  | "EN_VALLE"
  | "RECUPERANDO"
  | "CUMPLIDA"
  | "CERRADA";

/**
 * El patron que si resulto: venir de una caida >=2% en los 40 min previos.
 * Llega a +3.2% en 3h el 30.1% de las veces contra 13.1% de base (n=1673).
 * La "marea tranquila" se midio y no aportaba nada: no esta aqui a proposito.
 */
export interface Retroceso {
  detectado: boolean;
  /** Nivel fuerte: ya rebota >=1% del suelo. 24.4% cobrable contra 19.5%. */
  confirmado: boolean;
  caida_pct: number | null;
  suelo: number | null;
  pico_previo: number | null;
  minutos_desde_suelo: number;
  rebote_pct: number | null;
  reason: string;
}

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
  estado: EstadoAlerta;
  /** La señal deja de pedir actuar pero sigue en seguimiento hasta las 24h. */
  accionable: boolean;
  /** Meta de referencia: +3.2% sobre el entry congelado. */
  meta: number;
  /** Nivel al que esperar un retroceso antes de entrar. El objetivo NO se
   *  mueve: sigue siendo la meta sobre el entry original. */
  entrada_alt: number;
  retroceso_pct: number;
  /** Lo que le falta al precio actual para la meta. */
  dist_meta_pct: number | null;
  /** Frecuencia OBSERVADA de llegar a la meta, por distancia Y edad de la
   *  señal. No es un modelo: es la tabla medida, con su n al lado. La edad
   *  importa — a 3.2% una alerta nueva vale 20% y una de 10 horas, 15%. */
  prob_meta: number;
  prob_meta_n: number;
  /** El par cumple ahora mismo el patron validado. */
  viene_de_caida: boolean;
  /** Entry de la PRIMERA señal del episodio: el "superado" se mide desde ahí. */
  entry_primera: number | null;
  delta_primera_pct: number | null;
  senal_n: number;
  minutos_en_estado: number | null;
  /** display_state del par ahora; si sale de los estados validos, la alerta decae */
  estado_actual?: string;
  precio_actual: number;
  delta_pct: number;
  mfe_pct: number;
  mae_pct: number;
  fase_actual: FaseImpulso;
  fuerza_actual: number;
  fuerza_tendencia: number;
  /** VERDE +3.2% · MORADO +4.2% · AMARILLO -1.2% · ROJO el SL del sistema.
   *  No excluyentes: bajar y luego subir da AMARILLO y VERDE a la vez. */
  marcadores?: Marcador[];
  motivo_cierre: string;
}

/**
 * Base corta post-caída y su ruptura ("flush → base → reclaim").
 * Lo que compression.py no ve porque mira 24h de velas 15m: estas bases
 * duran una hora y se miden en 1m.
 */
export interface BaseRebote {
  detected: boolean;
  score: number;
  caida_pct: number | null;
  base_velas: number;
  base_rango_pct: number | null;
  base_techo: number | null;
  base_piso: number | null;
  vol_dryup: number | null;
  rompio: boolean;
  ruptura_vol_ratio: number | null;
  dist_techo_pct: number | null;
  reason: string;
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
  base_rebote?: BaseRebote;
  retroceso?: Retroceso;
  /** Cuanto se movio el par en los 60 min previos. En las mediciones del
   *  9-sep separo mas que ninguna otra: <1% llega a la meta el 40.6%, con
   *  3.5-6% el 75.6%. Todavia NO decide nada — se muestra y se mide. */
  rango_1h_pct?: number | null;
  /** La enesima señal de este par. La 1a llega el 58.8%, la 5a o mas 49.0%. */
  senal_n?: number;
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
    | "alert_ignicion"
    | "alert_base_rebote"
    | "alerta_cambio";
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
  // "alerta_cambio" trae la alerta entera al cambiar de estado, para que las
  // transiciones de seguimiento se vean sin esperar al siguiente broadcast.
  alerta?: AlertaActiva;
}
