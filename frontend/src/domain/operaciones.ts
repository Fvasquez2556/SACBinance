/**
 * Las cuentas del diario, sin mezclar lo que no se puede mezclar.
 *
 * Una operacion simulada y una declarada responden a preguntas distintas: la
 * primera dice si la lectura era buena, la segunda si ganaste dinero. Sumarlas
 * produce un historial que no describe nada. Por eso aqui no hay ninguna
 * funcion que devuelva "el total".
 */
import type { Operacion, ResumenOperaciones, TipoOperacion } from "../types";

export const ETIQUETA_TIPO: Record<TipoOperacion, string> = {
  SIMULADA: "Seguimiento simulado",
  DECLARADA: "Ejecución declarada",
  IMPORTADA: "Importada del exchange",
};

/** Lo que llevaría la posicion si se cerrara ahora. No es una ganancia. */
export function noRealizadoPct(
  precio: number | null | undefined,
  entrada: number | null | undefined,
  costePct = 0,
): number | null {
  if (precio == null || entrada == null) return null;
  if (!Number.isFinite(precio) || !Number.isFinite(entrada) || entrada <= 0) return null;
  // Cuatro decimales, como el backend: asi el mismo numero no sale distinto
  // segun quien lo calcule, y la coma flotante no ensucia las comparaciones.
  return Math.round(((precio / entrada - 1) * 100 - costePct) * 1e4) / 1e4;
}

/** Distancia a los niveles que la operacion copio al abrirse, no a los del plan de ahora. */
export function distanciaANiveles(op: Operacion, precio: number | null | undefined) {
  if (precio == null || !Number.isFinite(precio)) return { objetivo: null, stop: null };
  return {
    objetivo: op.objetivo ? (op.objetivo / precio - 1) * 100 : null,
    stop: op.stop ? (op.stop / precio - 1) * 100 : null,
  };
}

/** El motivo por el que el diario rechazaria esta apertura, o null si la acepta. */
export function motivoParaNoAbrir(precio: string, cantidad: string): string | null {
  const p = Number(precio);
  if (!precio.trim() || !Number.isFinite(p) || p <= 0) return "Indica el precio al que entraste.";
  if (cantidad.trim()) {
    const c = Number(cantidad);
    if (!Number.isFinite(c) || c <= 0) return "La cantidad, si la pones, tiene que ser mayor que cero.";
  }
  return null;
}

export interface SaldoTipo {
  tipo: TipoOperacion;
  cerradas: number;
  abiertas: number;
  positivas: number;
  sumaPct: number | null;
  mediaPct: number | null;
  moneda: number | null;
}

/** Un saldo por tipo. Nunca uno solo: ver el comentario de arriba. */
export function saldosPorTipo(resumen: ResumenOperaciones | null | undefined): SaldoTipo[] {
  if (!resumen) return [];
  const mapa = new Map<TipoOperacion, SaldoTipo>();
  for (const fila of resumen.por_tipo ?? []) {
    const tipo = fila.tipo as TipoOperacion;
    const actual = mapa.get(tipo) ?? {
      tipo, cerradas: 0, abiertas: 0, positivas: 0, sumaPct: null, mediaPct: null, moneda: null,
    };
    if (fila.estado === "CERRADA") {
      actual.cerradas += fila.n;
      actual.positivas += fila.positivas ?? 0;
      actual.sumaPct = (actual.sumaPct ?? 0) + (fila.suma_pct ?? 0);
      actual.mediaPct = fila.media_pct ?? null;
    } else if (fila.estado === "ABIERTA") {
      actual.abiertas += fila.n;
    }
    mapa.set(tipo, actual);
  }
  for (const fila of resumen.moneda_por_tipo ?? []) {
    const actual = mapa.get(fila.tipo as TipoOperacion);
    if (actual) actual.moneda = fila.suma ?? null;
  }
  return [...mapa.values()].sort((a, b) => a.tipo.localeCompare(b.tipo));
}

/**
 * Lo que le pasa al plan cuando entras en otro precio.
 *
 * El caso real que lo pidio: un plan de PYTH ofrecia arriesgar 1,84 % para
 * ganar 3,69 % —R:R 2,0— y la entrada se hizo un 1,4 % mas arriba. Desde ese
 * precio el riesgo pasaba a 3,32 % y el recorrido a 2,20 %: **R:R 0,66**. La
 * misma operacion, al reves, y en ningun sitio se decia.
 *
 * El aviso no mira el porcentaje de desvio, que no significa nada por si solo:
 * mira lo que queda a un lado y al otro. Por debajo de 1 arriesgas mas de lo
 * que puedes ganar.
 */
export interface DesvioEntrada {
  desviacionPct: number;
  riesgoPct: number | null;
  recorridoPct: number | null;
  rrPlan: number | null;
  rrReal: number | null;
  /** El precio quedo fuera del plan: por debajo del stop o por encima del TP. */
  fueraDelPlan: boolean;
  /** Se arriesga mas de lo que queda por ganar. */
  grave: boolean;
}

export function desvioDeEntrada(
  precio: number | null | undefined,
  plan: { entry?: number | null; objetivo?: number | null; stop?: number | null } | null | undefined,
): DesvioEntrada | null {
  const entrada = plan?.entry, objetivo = plan?.objetivo, stop = plan?.stop;
  if (precio == null || !Number.isFinite(precio) || precio <= 0) return null;
  if (entrada == null || !Number.isFinite(entrada) || entrada <= 0) return null;
  const desviacionPct = (precio / entrada - 1) * 100;
  const tiene = objetivo != null && stop != null && Number.isFinite(objetivo) && Number.isFinite(stop);
  if (!tiene || !(stop! < entrada && entrada < objetivo!)) {
    return { desviacionPct, riesgoPct: null, recorridoPct: null, rrPlan: null,
             rrReal: null, fueraDelPlan: false, grave: false };
  }
  const rrPlan = (objetivo! - entrada) / (entrada - stop!);
  const fueraDelPlan = precio <= stop! || precio >= objetivo!;
  // Los dos porcentajes se miden sobre TU precio, que es el capital que
  // pones: si se mide el riesgo sobre el stop y el recorrido sobre la entrada,
  // el cociente sale distinto del R:R real y el aviso miente por poco.
  const riesgoPct = (1 - stop! / precio) * 100;
  const recorridoPct = (objetivo! / precio - 1) * 100;
  const rrReal = fueraDelPlan ? null : (objetivo! - precio) / (precio - stop!);
  return {
    desviacionPct,
    riesgoPct: Math.round(riesgoPct * 100) / 100,
    recorridoPct: Math.round(recorridoPct * 100) / 100,
    rrPlan: Math.round(rrPlan * 100) / 100,
    rrReal: rrReal == null ? null : Math.round(rrReal * 100) / 100,
    fueraDelPlan,
    grave: fueraDelPlan || (rrReal != null && rrReal < 1),
  };
}

/** El aviso en una frase, o null cuando no hay nada que avisar. */
export function textoDesvio(d: DesvioEntrada | null): string | null {
  if (!d) return null;
  if (d.fueraDelPlan) {
    return d.desviacionPct > 0
      ? "Ese precio está en el objetivo del plan o por encima: ya no queda recorrido que tomar."
      : "Ese precio está en el stop del plan o por debajo: el plan ya estaría invalidado.";
  }
  if (d.rrPlan == null || d.rrReal == null) return null;
  if (Math.abs(d.desviacionPct) < 0.1) return null;
  const arriba = d.desviacionPct > 0;
  const cabecera = `Entras ${Math.abs(d.desviacionPct).toFixed(2)}% ${arriba ? "por encima" : "por debajo"} de la entrada del plan.`;
  return `${cabecera} Desde tu precio arriesgas ${d.riesgoPct?.toFixed(2)}% para ganar ${d.recorridoPct?.toFixed(2)}%: R:R ${d.rrReal.toFixed(2)} en vez de ${d.rrPlan.toFixed(2)}.`;
}
