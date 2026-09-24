import { useEffect, useState } from "react";
import { CONTRATO_PROVISIONAL, type Contrato } from "../domain/contrato";

/**
 * El contrato de lectura, traído de la API.
 *
 * Mientras no responde se usa el provisional, que son los valores por defecto
 * del backend — no una suposición. `confirmado` dice cuál de los dos está en
 * uso, para que nada presente como seguro un número que todavía no llegó.
 */
export function useContrato(): { contrato: Contrato; confirmado: boolean } {
  const [contrato, setContrato] = useState<Contrato>(CONTRATO_PROVISIONAL);
  const [confirmado, setConfirmado] = useState(false);
  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/contrato", { signal: ac.signal })
      .then(r => { if (!r.ok) throw new Error("contrato"); return r.json(); })
      .then((c: Contrato) => { setContrato(c); setConfirmado(true); })
      .catch(() => { /* se queda el provisional; `confirmado` lo dice */ });
    return () => ac.abort();
  }, []);
  return { contrato, confirmado };
}
