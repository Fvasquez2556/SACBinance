import type { PairState } from "../types";

export type SignalRoute = "RUPTURA_ALCISTA" | "RUPTURA_BAJISTA" | "SIN_RUTA";

export interface SignalRouteReading {
  route: SignalRoute;
  label: string;
  reason: string;
}

export interface HistoryRow {
  signal_id: number;
  symbol: string;
  ts_open: number;
  entry: number | null;
  take_profit: number | null;
  stop_loss: number | null;
  tp_pct: number | null;
  sl_pct: number | null;
  desenlace: "TP" | "SL" | "NADA" | "ABIERTA";
  ms_resuelto: number | null;
  // undefined means an older API; null means no observed touch.
  ms_tp?: number | null;
  ms_sl?: number | null;
  ms_meta: number | null;
  mfe_pct: number | null;
  mae_pct: number | null;
  llego_meta: boolean;
  supero: boolean;
  cerrado: number;
  cobertura_velas?: number | null;
  strategy_version?: string | null;
  reward_neto_pct?: number | null;
}

export type BarrierOrder = "TP_FIRST" | "SL_FIRST" | "AMBIGUOUS" | "NEITHER" | "PENDING" | "UNKNOWN";
export type GoalOrder = "BEFORE_SL" | "AFTER_SL" | "AMBIGUOUS" | "NOT_TOUCHED" | "UNKNOWN";

const validTime = (value: number | null | undefined) =>
  value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 86_400_000);

// These are observations from the existing 24h tracker, not calibrated odds.
export function barrierOrder(row: HistoryRow): BarrierOrder {
  if (!validTime(row.ms_tp) || !validTime(row.ms_sl)) return "UNKNOWN";
  const tp = row.ms_tp as number | null;
  const sl = row.ms_sl as number | null;
  if (tp !== null && sl !== null && tp === sl) return "AMBIGUOUS";
  if (tp !== null && (sl === null || tp < sl)) return "TP_FIRST";
  if (sl !== null) return "SL_FIRST";
  return row.cerrado ? "NEITHER" : "PENDING";
}

export function goalOrder(row: HistoryRow): GoalOrder {
  if (!row.llego_meta) return "NOT_TOUCHED";
  if (row.ms_meta === null || !validTime(row.ms_meta) || !validTime(row.ms_sl)) return "UNKNOWN";
  if (row.ms_sl === null || row.ms_meta < row.ms_sl!) return "BEFORE_SL";
  return row.ms_meta === row.ms_sl ? "AMBIGUOUS" : "AFTER_SL";
}

export function goalAfterExitTP(row: HistoryRow): boolean {
  return row.llego_meta && validTime(row.ms_meta) && barrierOrder(row) === "TP_FIRST" && row.ms_meta !== null && row.ms_tp != null && row.ms_meta > row.ms_tp;
}

export function goalLabel(row: HistoryRow): string {
  if (goalAfterExitTP(row)) return "+3.2% posterior al TP del plan";
  switch (goalOrder(row)) {
    case "AFTER_SL": return "+3.2% después del SL";
    case "BEFORE_SL": return row.ms_sl === null ? "+3.2% tocado · SL no observado" : "+3.2% antes del SL observado";
    case "AMBIGUOUS": return "+3.2% y SL en la misma vela";
    case "UNKNOWN": return "+3.2% tocado · orden no disponible";
    default: return row.cerrado ? "+3.2% no observado" : "+3.2% aún no observado";
  }
}

export function coverageLabel(row: HistoryRow): string {
  const value = row.cobertura_velas;
  if (value == null || !Number.isFinite(value)) return row.cerrado ? "Cobertura no registrada" : "Cobertura aún no evaluada";
  if (value < 0 || value > 1) return "Cobertura no válida";
  return `${value < 1 ? "Cobertura parcial" : "Velas completas"} · ${(value * 100).toFixed(1)}%`;
}

export function profiles(pair: PairState): string[] {
  const result: string[] = [];
  if (pair.retroceso?.confirmado || pair.base_rebote?.detected) result.push("Rebote confirmado");
  else if (pair.retroceso?.detectado) result.push("Caída · espera rebote");
  if (pair.grind?.detected) result.push("Tendencia sostenida");
  if (pair.ignition?.detected) result.push("Aceleración");
  return result.length ? result : ["En observación"];
}

/** Rutas direccionales observadas, no ordenes ni pronosticos. */
export function classifySignalRoute(pair: PairState): SignalRouteReading {
  if (pair.display_state === "CAYENDO") {
    if (pair.impulso?.caida_acelerando) {
      return { route: "RUPTURA_BAJISTA", label: "Ruptura bajista corta", reason: "Caída acelerando en 3m y 5m" };
    }
    if (pair.sr_levels?.perdido) {
      return { route: "RUPTURA_BAJISTA", label: "Ruptura bajista corta", reason: "Soporte perdido y caída activa" };
    }
    return { route: "RUPTURA_BAJISTA", label: "Ruptura bajista corta", reason: "Caída activa detectada por el sistema" };
  }

  const impulsoContinuo = pair.impulso?.valid && ["ACELERANDO", "SOSTENIDA"].includes(pair.impulso.fase);
  const rupturaAlcista = pair.display_state === "BREAKOUT_INCIPIENTE"
    || (pair.display_state === "SUBIENDO" && pair.trend_up === true && impulsoContinuo);
  if (rupturaAlcista && !pair.is_fakeout) {
    const reason = pair.display_state === "BREAKOUT_INCIPIENTE"
      ? `Ruptura detectada con impulso ${pair.impulso?.fase?.toLowerCase() ?? "activo"}`
      : `Subida continua con impulso ${pair.impulso?.fase?.toLowerCase() ?? "activo"}`;
    return { route: "RUPTURA_ALCISTA", label: "Ruptura alcista continua", reason };
  }

  return { route: "SIN_RUTA", label: "Sin ruptura confirmada", reason: "No hay dirección corta confirmada" };
}

export function displayPlan(pair: PairState) {
  const a = pair.alerta;
  if (a && a.entry > 0) {
    return { source: "Plan de la alerta", frozen: true, entry: a.entry,
      tp: a.take_profit, sl: a.stop_loss, tpPct: a.tp_pct, slPct: a.sl_pct,
      netPct: null, reason: "Niveles fijados al emitir. La entrada es una referencia; no acredita una orden ejecutada." };
  }
  const t = pair.trade_levels;
  if (!t?.valid || !t.entry) return null;
  return { source: "Propuesta actual", frozen: false, entry: t.entry,
    tp: t.take_profit, sl: t.stop_loss, tpPct: t.reward_pct,
    slPct: t.risk_pct == null ? null : -t.risk_pct, netPct: t.reward_neto_pct,
    reason: t.reason };
}

/**
 * El cambio que se muestra se calcula SIEMPRE con el precio que se muestra.
 *
 * `alerta.delta_pct` lo calcula el backend con el cierre de la ultima vela de
 * 1 minuto; `pair.price` es el precio del minuto en curso. Los dos son
 * correctos y no son el mismo numero: medido en produccion sobre 64 alertas
 * vivas, la diferencia es de 0,11 % de mediana, 0,32 % en el percentil 90 y
 * 0,86 % en el peor caso. Enseñar el precio vivo al lado de un porcentaje
 * calculado con otro precio parece un desfase; calcularlo aqui lo elimina, y
 * el numero del backend queda donde se puede explicar: en el detalle.
 */
export function cambioDesdeEntrada(
  precio: number | null | undefined,
  entrada: number | null | undefined,
): number | null {
  if (precio == null || entrada == null) return null;
  if (!Number.isFinite(precio) || !Number.isFinite(entrada) || entrada <= 0) return null;
  return (precio / entrada - 1) * 100;
}

/** Cuanto se ha movido el precio desde el cierre con el que se calculo el delta. */
export function desfaseDelta(
  precio: number | null | undefined,
  precioDeLaVela: number | null | undefined,
): number | null {
  if (precio == null || precioDeLaVela == null) return null;
  if (!Number.isFinite(precio) || !Number.isFinite(precioDeLaVela) || precioDeLaVela <= 0) return null;
  return (precio / precioDeLaVela - 1) * 100;
}

/**
 * Medianoche del dia del OPERADOR, no del servidor.
 *
 * El backend guarda todo en UTC; en Guatemala eso adelanta el corte seis horas
 * y "la primera del dia" saldria mal entre las 18:00 y la medianoche.
 */
export function inicioDelDiaLocal(ahora: number = Date.now()): number {
  const d = new Date(ahora);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function horaLocal(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return "—";
  return new Date(ts).toLocaleTimeString("es-GT", { hour: "2-digit", minute: "2-digit" });
}

export function price(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("es-GT", { maximumFractionDigits: value >= 100 ? 2 : value >= 1 ? 4 : 8 }).format(value);
}

export function percent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

/**
 * Los dos niveles del plan, en palabras.
 *
 * El stop no es un porcentaje redondo: sale de un soporte con toques, menos un
 * colchon de ATR. Y entre la entrada y el TP puede haber un techo que el precio
 * tiene que atravesar. Las dos cosas se calculaban desde el principio y no se
 * enseñaban en ninguna pantalla.
 */
export interface NivelesDelPlan {
  soporte: number | null;
  soportePct: number | null;
  toquesSoporte: number | null;
  slBasis: string | null;
  techo: number | null;
  techoPct: number | null;
  toquesTecho: number | null;
  techoEstorba: boolean;
}

export function nivelesDelPlan(
  entrada: number | null | undefined,
  fuente: { soporte?: number | null; sl_basis?: string | null; resistencia?: number | null;
            tp_bloqueado?: boolean; toques_soporte?: number | null;
            toques_resistencia?: number | null } | null | undefined,
): NivelesDelPlan | null {
  if (!fuente || entrada == null || !Number.isFinite(entrada) || entrada <= 0) return null;
  const pct = (nivel: number | null | undefined) =>
    nivel != null && Number.isFinite(nivel) ? (nivel / entrada - 1) * 100 : null;
  const niveles: NivelesDelPlan = {
    soporte: fuente.soporte ?? null,
    soportePct: pct(fuente.soporte),
    toquesSoporte: fuente.toques_soporte ?? null,
    slBasis: fuente.sl_basis ?? null,
    techo: fuente.resistencia ?? null,
    techoPct: pct(fuente.resistencia),
    toquesTecho: fuente.toques_resistencia ?? null,
    techoEstorba: !!fuente.tp_bloqueado,
  };
  return niveles.soporte == null && niveles.techo == null ? null : niveles;
}

/** «Soporte que sostiene el SL 97.5 (−2.50%) · 4 toques · soporte estructural» */
export function textoSoporte(n: NivelesDelPlan | null): string | null {
  if (!n?.soporte) return null;
  const toques = n.toquesSoporte ? ` · ${n.toquesSoporte} toques` : "";
  const base = n.slBasis ? ` · ${n.slBasis}` : "";
  return `${price(n.soporte)} (${percent(n.soportePct)})${toques}${base}`;
}

/** El techo, diciendo si estorba al TP o si queda por encima de el. */
export function textoTecho(n: NivelesDelPlan | null): string | null {
  if (!n?.techo) return null;
  const toques = n.toquesTecho ? ` · ${n.toquesTecho} toques` : "";
  return `${price(n.techo)} (${percent(n.techoPct)})${toques}`;
}
