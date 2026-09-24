/**
 * El contrato de lectura: qué significa cada porcentaje que sale en pantalla.
 *
 * Por qué existe este archivo
 * ---------------------------
 * El número 3,2 estaba escrito a mano en quince sitios del frontend y hacía
 * DOS trabajos distintos:
 *
 *   - el objetivo del operador, que es NETO (ya descuenta coste)
 *   - el hito con el que se mide la forma del recorrido, que es BRUTO
 *
 * Con un coste de 0,5 puntos NO son lo mismo: tu objetivo de +3,2 % neto
 * necesita un movimiento de +3,7 % bruto, y el hito de +3,2 % bruto solo te
 * deja +2,7 % netos. Medido sobre 502 recorridos completos de producción,
 * **37 señales (el 15,5 % de las que el tablero daba por meta cumplida) nunca
 * llegaron al objetivo real**. Mismo número, misma pinta, media vuelta de
 * diferencia.
 *
 * A partir de aquí ningún porcentaje se escribe sin decir si es bruto o neto,
 * y ninguno se escribe a mano.
 */

export type TipoPct = "BRUTO" | "NETO";

export interface Porcentaje {
  pct: number;
  tipo: TipoPct;
  etiqueta: string;
  coste_pct: number;
}

export interface Contrato {
  objetivo_operador: Porcentaje;
  objetivo_operador_bruto: Porcentaje;
  hito_referencia: Porcentaje;
  hito_referencia_neto: Porcentaje;
  coinciden: boolean;
  coste_pct: number;
  horizonte_horas: number;
  episodio_horas: number;
  exigir_objetivo: boolean;
  aviso: string;
}

/**
 * El contrato que se usa mientras la API no ha respondido todavía.
 *
 * Son los valores por defecto del backend, no una suposición: si la API
 * cambia el objetivo, la primera respuesta lo corrige. Se marca como
 * provisional para que nada lo presente como confirmado.
 */
export const CONTRATO_PROVISIONAL: Contrato = {
  objetivo_operador: { pct: 3.2, tipo: "NETO", etiqueta: "+3.2 % neto", coste_pct: 0.5 },
  objetivo_operador_bruto: { pct: 3.7, tipo: "BRUTO", etiqueta: "+3.7 % bruto", coste_pct: 0.5 },
  hito_referencia: { pct: 3.2, tipo: "BRUTO", etiqueta: "+3.2 % bruto", coste_pct: 0.5 },
  hito_referencia_neto: { pct: 2.7, tipo: "NETO", etiqueta: "+2.7 % neto", coste_pct: 0.5 },
  coinciden: false,
  coste_pct: 0.5,
  horizonte_horas: 12,
  episodio_horas: 12,
  exigir_objetivo: false,
  aviso: "",
};

/** «+3.2 % neto». Nunca un porcentaje suelto. */
export function texto(p: Porcentaje | null | undefined): string {
  if (!p) return "—";
  return p.etiqueta;
}

/**
 * El hito de medición, dicho con las dos caras.
 *
 * «+3.2 % bruto (te deja +2.7 % neto)». Es la frase que evita que un
 * movimiento de precio se lea como dinero embolsado.
 */
export function textoHito(c: Contrato): string {
  return `${c.hito_referencia.etiqueta} (te deja ${c.hito_referencia_neto.etiqueta})`;
}

/** Lo que el precio tiene que moverse para que cobres tu objetivo. */
export function textoObjetivo(c: Contrato): string {
  if (c.coinciden) return c.objetivo_operador.etiqueta;
  return `${c.objetivo_operador.etiqueta} — el precio debe subir ${c.objetivo_operador_bruto.etiqueta}`;
}

/** ¿El TP neto de un plan llega a tu objetivo? */
export function llegaAlObjetivo(rewardNetoPct: number | null | undefined,
                                c: Contrato): boolean | null {
  if (rewardNetoPct == null || !Number.isFinite(rewardNetoPct)) return null;
  return rewardNetoPct >= c.objetivo_operador.pct;
}

/** El aviso cuando un plan se queda corto, con los dos números. */
export function avisoObjetivoCorto(rewardNetoPct: number | null | undefined,
                                   c: Contrato): string | null {
  if (llegaAlObjetivo(rewardNetoPct, c) !== false) return null;
  return `El TP deja ${rewardNetoPct!.toFixed(2)} % neto, por debajo de tu objetivo de ${c.objetivo_operador.etiqueta}.`;
}

/**
 * ¿Un recorrido que tocó el hito llegó de verdad a tu objetivo?
 *
 * Es la pregunta que el tablero contestaba mal: tocar el hito bruto no es
 * cumplir el objetivo neto mientras el coste sea mayor que cero.
 */
export function hitoCumpleObjetivo(mfePct: number | null | undefined,
                                   c: Contrato): "SI" | "SOLO_HITO" | "NO" | null {
  if (mfePct == null || !Number.isFinite(mfePct)) return null;
  if (mfePct >= c.objetivo_operador_bruto.pct) return "SI";
  if (mfePct >= c.hito_referencia.pct) return "SOLO_HITO";
  return "NO";
}
