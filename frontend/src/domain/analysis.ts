import { CONTRATO_PROVISIONAL, type Contrato } from "./contrato.ts";
import type { AnalisisPar, DireccionTF, EstadisticaCelda, EstadisticaMarco, LecturaTF, PlanDireccional } from "../types";
import { percent, price } from "./reading.ts";

export const DIRECCION_LABEL: Record<DireccionTF, string> = {
  RUPTURA_ALCISTA: "Ruptura alcista",
  RUPTURA_BAJISTA: "Ruptura bajista",
  SIN_RUPTURA: "Sin ruptura",
  SIN_DATOS: "Sin datos",
};

/** Lo que el usuario escribe. `btc` y `BTC/USDT` son el mismo par. */
export function normalizarSymbol(raw: string): string | null {
  const limpio = raw.trim().toUpperCase().replace(/[/\-\s]/g, "");
  if (!/^[A-Z0-9]{2,20}$/.test(limpio)) return null;
  return limpio.endsWith("USDT") ? limpio : `${limpio}USDT`;
}

export function esRuptura(direccion: DireccionTF): boolean {
  return direccion === "RUPTURA_ALCISTA" || direccion === "RUPTURA_BAJISTA";
}

/**
 * Como se lee el estado de un marco en una linea.
 *
 * "Confirmada" no quiere decir que vaya a seguir: quiere decir que el precio
 * cerro varias velas al otro lado del nivel y la tendencia del marco no va en
 * contra. Es descripcion de lo ocurrido.
 */
export function estadoTF(lectura: LecturaTF): string {
  if (lectura.direccion === "SIN_DATOS") return "Sin historia suficiente";
  if (lectura.direccion === "SIN_RUPTURA") return "Rango intacto";
  const base = DIRECCION_LABEL[lectura.direccion];
  return lectura.confirmada ? `${base} · sostenida` : `${base} · sin confirmar`;
}

/**
 * El rango de entrada en texto. Cuando el precio ya paso el nivel no queda
 * retest que esperar, y decir "entrada 100-100" esconde justo eso.
 */
export function rangoEntrada(plan: PlanDireccional): string {
  if (!plan.valid || plan.entrada_min == null || plan.entrada_max == null) return "—";
  if (!plan.rellena_en_retest) return `${price(plan.entrada_ref)} · solo a mercado`;
  return `${price(plan.entrada_min)} – ${price(plan.entrada_max)}`;
}

/**
 * Por que un marco con ruptura puede no traer plan. El motivo mas comun no es
 * un fallo: es que el stop honesto no cabe dentro del riesgo maximo, y ahi el
 * backend prefiere no emitir a recortar el stop hasta meterlo en el ruido.
 */
export function motivoSinPlan(lectura: LecturaTF): string | null {
  if (!esRuptura(lectura.direccion)) return null;
  if (lectura.plan?.valid) return null;
  return lectura.plan?.reason ?? "No se pudo calcular un plan en este marco.";
}

/**
 * Los avisos que van pegados a un plan concreto, no al informe entero.
 * Se devuelven en una lista para que la pantalla los enseñe todos: son las
 * razones por las que un plan puede verse bien y no serlo.
 */
export function avisosPlan(plan: PlanDireccional, est?: EstadisticaMarco | null,
                           contrato: Contrato = CONTRATO_PROVISIONAL): string[] {
  const objetivo = contrato.objetivo_operador;
  const avisos: string[] = [];
  if (plan.advertencia) avisos.push(plan.advertencia);
  if (plan.tp_bloqueado && plan.nivel_estorbo != null) {
    // El aviso describe el obstaculo; el numero dice lo que paso con el.
    // Medido sobre las rupturas de este sistema, tener un nivel de por medio
    // NO empeoro el resultado, asi que el texto no puede insinuar lo contrario.
    const si = est?.estorbo_si, no = est?.estorbo_no;
    const comparacion = si?.fiable && no?.fiable
      ? ` Medido en ${est?.ventana_dias} días: con un nivel de por medio, ${si.tp_antes_sl}% tocó el TP antes que el stop (n=${si.n}); sin él, ${no.tp_antes_sl}% (n=${no.n}).`
      : "";
    avisos.push(`Nivel en ${price(plan.nivel_estorbo)} entre la entrada y el TP: el precio tiene que atravesarlo.${comparacion}`);
  }
  if (!plan.objetivo_alcanzable && plan.reward_neto_pct != null) {
    // El objetivo lo pone el contrato de lectura, no una constante escrita
    // aqui: si cambia a +4,2 % neto, este texto cambia con el.
    avisos.push(`El TP deja ${percent(plan.reward_neto_pct)} neto tras costes, por debajo de tu objetivo de ${objetivo.etiqueta}.`);
  }
  if (!plan.rellena_en_retest) {
    avisos.push("El precio ya se alejó del nivel: no queda zona de retest, solo entrada a mercado.");
  }
  return avisos;
}

/**
 * Una frase para el resumen. El backend ya manda `resumen.lectura`; esto añade
 * el desacuerdo entre marcos cuando lo hay, porque es la unica parte del
 * informe que cambia como hay que leer todo lo demas.
 */
export function tituloResumen(analisis: AnalisisPar): string {
  const { resumen } = analisis;
  if (resumen.en_conflicto) return "Marcos en desacuerdo";
  if (resumen.direccion_dominante === "SIN_RUPTURA") return "Sin ruptura confirmada";
  return `${DIRECCION_LABEL[resumen.direccion_dominante]} en ${resumen.tf_dominante}`;
}

/**
 * La tasa medida de una celda, o por que no hay tasa.
 *
 * Nunca se rellena con una celda mas ancha: si la muestra no llega al minimo,
 * se dice, con el n a la vista. Un porcentaje sin muestra es un adorno.
 */
export function textoTasa(celda: EstadisticaCelda | null | undefined,
                          ventanaDias?: number): string {
  if (!celda) return "Sin observaciones de este tipo todavía.";
  if (!celda.fiable || celda.tp_antes_sl == null) {
    return `Sin estimación fiable: solo ${celda.n} observación(es).`;
  }
  const ventana = ventanaDias ? ` · ${ventanaDias} días` : "";
  const fill = celda.pct_fill != null ? ` · llenó la entrada el ${celda.pct_fill}%` : "";
  return `${celda.tp_antes_sl}% tocó el TP antes que el stop · n=${celda.n}${ventana}${fill}`;
}

/**
 * Si lo que este marco suele tardar cabe en la jornada.
 *
 * El sistema es intradia: un plan que pide mas horas de las que el seguimiento
 * da no es mejor ni peor, es otra cosa, y hay que decirlo antes de tomarlo.
 */
export function textoHorizonte(est: EstadisticaMarco | null | undefined): string | null {
  const celda = est?.marco;
  if (!celda?.fiable || celda.horas_mediana == null || celda.pct_dentro_horizonte == null) {
    return null;
  }
  return `TP en ${celda.horas_mediana} h de mediana · ${celda.pct_dentro_horizonte}% cupo en ${est?.horizonte_h} h`;
}

/** Cuando el horizonte no da: el marco propone mas tiempo del que hay. */
export function horizonteApretado(est: EstadisticaMarco | null | undefined): boolean {
  const celda = est?.marco;
  return !!celda?.fiable && celda.pct_dentro_horizonte != null && celda.pct_dentro_horizonte < 70;
}

/**
 * La confluencia es lo unico que ordena en la medicion: 0, 1, 2, 3 o 4 marcos
 * confirmados dieron 44,5 / 46,0 / 51,4 / 58,5 / 62,4 %. Por eso el resumen
 * lleva su celda, y no la del marco que "manda".
 */
export function textoConfluencia(analisis: AnalisisPar): string | null {
  const est = analisis.resumen.estadistica;
  if (!est) return null;
  const marcos = est.n_confirmadas === 1 ? "1 marco confirmado" : `${est.n_confirmadas} marcos confirmados`;
  return `Con ${marcos}: ${textoTasa(est.confluencia, est.ventana_dias)}`;
}
