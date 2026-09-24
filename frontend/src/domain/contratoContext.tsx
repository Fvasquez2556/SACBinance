import { createContext, useContext } from "react";
import { CONTRATO_PROVISIONAL, type Contrato } from "./contrato.ts";

/**
 * El contrato de lectura, disponible en cualquier componente.
 *
 * Es contexto y no props porque lo necesitan tarjetas, detalle, avisos y
 * estadísticas a la vez, y pasarlo a mano por seis niveles invita justo a lo
 * que esta fase corrige: que alguien escriba el número otra vez.
 */
export const ContratoContext = createContext<Contrato>(CONTRATO_PROVISIONAL);

export function useContratoLectura(): Contrato {
  return useContext(ContratoContext);
}
