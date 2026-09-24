import { useEffect, useState } from "react";
import type { Operacion, ResumenOperaciones } from "../types";
import { horaLocal, percent, price } from "../domain/reading";
import { ETIQUETA_TIPO, distanciaANiveles, saldosPorTipo } from "../domain/operaciones";

/**
 * El diario, con los saldos separados por tipo.
 *
 * No hay un total. Un seguimiento simulado y una ejecucion declarada no se
 * suman: el dia que se sumen, el historial deja de significar nada.
 */
export default function MisOperaciones({ expandido = false }: { expandido?: boolean } = {}) {
  const [operaciones, setOperaciones] = useState<Operacion[]>([]);
  const [resumen, setResumen] = useState<ResumenOperaciones | null>(null);
  const [abierto, setAbierto] = useState(expandido);

  useEffect(() => {
    if (!abierto) return;
    const controller = new AbortController();
    const cargar = () => fetch("/api/operaciones?limite=100", { signal: controller.signal })
      .then(r => r.ok ? r.json() : Promise.reject(new Error("operaciones")))
      .then(d => { setOperaciones(d.operaciones ?? []); setResumen(d.resumen ?? null); })
      .catch(() => { if (!controller.signal.aborted) { setOperaciones([]); setResumen(null); } });
    cargar();
    const t = setInterval(cargar, 30_000);
    return () => { controller.abort(); clearInterval(t); };
  }, [abierto]);

  const saldos = saldosPorTipo(resumen);

  // Con una sola posicion a la vez, lo abierto no es una fila mas de la tabla:
  // es lo unico que exige atencion ahora. Va arriba y con las distancias a sus
  // dos barreras, que es lo que se mira para decidir si se aguanta o se sale.
  const abiertas = operaciones.filter(op => op.estado === "ABIERTA");

  const cuerpo = <>
    {expandido && abiertas.length > 0 && <div className="posiciones-abiertas">
      {abiertas.map(op => {
        const d = distanciaANiveles(op, op.precio_actual ?? null);
        return <div className="posicion" key={op.operacion_id}>
          <div className="posicion-cabecera">
            <strong>{op.symbol}</strong>
            <small className="muted">{ETIQUETA_TIPO[op.tipo]} · desde {horaLocal(op.ts_apertura)}</small>
          </div>
          <div className="posicion-cifras">
            <span>entrada <strong>{price(op.precio_entrada)}</strong></span>
            {op.precio_actual != null && <span>ahora <strong>{price(op.precio_actual)}</strong></span>}
            <span className={(op.no_realizado_pct ?? 0) >= 0 ? "positive" : "negative"}>
              <strong>{percent(op.no_realizado_pct)}</strong> no realizado
            </span>
            {d.objetivo != null && <span>al TP <strong>{percent(d.objetivo)}</strong></span>}
            {d.stop != null && <span>al SL <strong>{percent(d.stop)}</strong></span>}
          </div>
        </div>;
      })}
    </div>}
    {saldos.length === 0
      ? <p className="muted">Todavía no has registrado ninguna. Se registran desde el detalle de un par, con «Tomé esta entrada».</p>
      : <div className="saldos">
          {saldos.map(s => <div className="saldo" key={s.tipo}>
            <strong>{ETIQUETA_TIPO[s.tipo]}</strong>
            <span>{s.cerradas} cerrada(s){s.abiertas ? ` · ${s.abiertas} abierta(s)` : ""}</span>
            {s.cerradas > 0 && <>
              <span>Suma {percent(s.sumaPct)} · media {percent(s.mediaPct)}</span>
              <span>{s.positivas} de {s.cerradas} en positivo</span>
              {s.moneda != null && <span>Resultado declarado: {s.moneda.toFixed(2)}</span>}
            </>}
          </div>)}
          <p className="muted">Los tipos no se suman entre sí: el simulado dice si la lectura era buena, el declarado si ganaste dinero.</p>
        </div>}

    {operaciones.length > 0 && <table className="tabla-operaciones">
      <thead><tr><th>Par</th><th>Tipo</th><th>Abierta</th><th>Entrada</th><th>Estado</th><th>Resultado</th></tr></thead>
      <tbody>
        {operaciones.map(op => <tr key={op.operacion_id}>
          <td>{op.symbol}</td>
          <td><small>{ETIQUETA_TIPO[op.tipo]}</small></td>
          <td>{horaLocal(op.ts_apertura)}</td>
          <td>{price(op.precio_entrada)}{op.cantidad ? <small className="muted"> · {op.cantidad}</small> : null}</td>
          <td>{op.estado === "ABIERTA" ? "En curso"
            : op.estado === "CANCELADA" ? "Cancelada"
            : `Cerrada ${op.motivo_cierre ? `(${op.motivo_cierre.toLowerCase()})` : ""}`}</td>
          <td className={(op.resultado_pct ?? op.no_realizado_pct ?? 0) >= 0 ? "positive" : "negative"}>
            {op.estado === "ABIERTA"
              ? <>{percent(op.no_realizado_pct)} <small className="muted">no realizado</small></>
              : op.estado === "CANCELADA" ? <span className="muted">—</span>
              : percent(op.resultado_pct)}
          </td>
        </tr>)}
      </tbody>
    </table>}
  </>;

  if (expandido) {
    return <section className="mis-operaciones">
      <h2>Mi operación{resumen?.abiertas ? ` · ${resumen.abiertas} abierta(s)` : ""}</h2>
      {cuerpo}
    </section>;
  }
  return <details className="panel" onToggle={e => setAbierto((e.target as HTMLDetailsElement).open)}>
    <summary>Mis operaciones{resumen?.abiertas ? ` · ${resumen.abiertas} abierta(s)` : ""}</summary>
    {cuerpo}
  </details>;
}
