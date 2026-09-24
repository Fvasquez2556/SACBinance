import { useEffect, useState } from "react";
import { percent } from "../domain/reading";

/**
 * Lo medido, por población, con horizonte y coste al lado.
 *
 * «¿Cuánto acierta el sistema?» no tiene una respuesta: tiene cuatro, y la
 * que se elegía en silencio era la más grande — la que mejor suena y menos
 * significa. Verlas juntas es el punto: la diferencia entre poblaciones suele
 * ser mayor que cualquier mejora que se discuta.
 */
interface Poblacion {
  poblacion: string; etiqueta: string; planes: number; pares: number;
  completas: number; abiertas: number; objetivo: number; stop: number;
  vencido: number; resueltas: number; acierto_pct: number | null;
  media_pct: number | null; horizonte_horas: number; coste_pct: number;
  cobertura_minima: number; mal_observadas: number;
  nota: string;
}

export default function Resultados() {
  const [datos, setDatos] = useState<{ poblaciones: Poblacion[]; aviso: string } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/resultados", { signal: ac.signal })
      .then(r => { if (!r.ok) throw new Error("resultados"); return r.json(); })
      .then(setDatos)
      .catch(() => { if (!ac.signal.aborted) setError(true); });
    return () => ac.abort();
  }, []);

  if (error) return <p className="muted">No se pudieron cargar los resultados.</p>;
  if (!datos) return <p className="muted">Cargando…</p>;
  const h = datos.poblaciones[0];

  return (
    <section className="resultados">
      <h2>Resultados</h2>
      <p className="muted">
        Ventana de {h?.horizonte_horas} h · coste supuesto {h?.coste_pct} puntos
        {h?.cobertura_minima != null && <> · solo ventanas observadas al{" "}
        {(h.cobertura_minima * 100).toFixed(0)} % o más</>}.
        Solo ventanas cerradas: una operación abierta no es un empate.
      </p>
      <table className="tabla-resultados">
        <thead>
          <tr>
            <th>población</th><th>planes</th><th>pares</th>
            <th>acierto</th><th>media</th><th>abiertas</th><th>vencidas</th>
            <th title="ventana cerrada por reloj pero con demasiadas velas ausentes: no es un fallo ni un acierto, es una medición que no existe">mal observadas</th>
          </tr>
        </thead>
        <tbody>
          {datos.poblaciones.map(p => (
            <tr key={p.poblacion} className={p.poblacion === "DECISORIA" ? "decisoria" : undefined}>
              <td><strong>{p.etiqueta}</strong></td>
              <td>{p.planes}</td>
              <td>{p.pares}</td>
              <td>{p.acierto_pct == null ? "—" : `${p.acierto_pct}%`}
                  {p.resueltas > 0 && <small className="muted"> de {p.resueltas}</small>}</td>
              <td>{p.media_pct == null ? "—" : percent(p.media_pct)}</td>
              <td>{p.abiertas}</td>
              <td>{p.vencido}</td>
              <td>{p.mal_observadas}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted nota">{h?.nota}</p>
      <p className="muted nota">{datos.aviso}</p>
    </section>
  );
}
