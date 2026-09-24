import { useEffect, useMemo, useState } from "react";
import { barrierOrder, coverageLabel, goalLabel, goalOrder, percent, price } from "../domain/reading";
import type { BarrierOrder, HistoryRow } from "../domain/reading";

type Filter = "ALL" | "TP_FIRST" | "SL_FIRST" | "AFTER_SL" | "AMBIGUOUS" | "PENDING";
const ORDER_LABEL: Record<BarrierOrder, string> = {
  TP_FIRST: "TP primero", SL_FIRST: "SL primero", AMBIGUOUS: "Misma vela · orden incierto",
  NEITHER: "Sin TP ni SL observado", PENDING: "En seguimiento", UNKNOWN: "Orden no disponible",
};
function duration(ms: number | null) {
  if (ms == null || ms < 0) return "—";
  const m = Math.floor(ms / 60000);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

export default function Historial({ onSelect }: { onSelect?: (symbol: string) => void }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      try {
        const response = await fetch("/api/historial?limit=400", { signal: controller.signal });
        if (!response.ok) throw new Error("history");
        const d = await response.json();
        if (!Array.isArray(d.historial)) throw new Error("history");
        if (!controller.signal.aborted) { setRows(d.historial); setFailed(false); }
      } catch { if (!controller.signal.aborted) setFailed(true); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    };
    void load(); const id = setInterval(() => void load(), 60000);
    return () => { controller.abort(); clearInterval(id); };
  }, [open]);

  const searched = useMemo(() => rows.filter(r => r.symbol.includes(search.trim().toUpperCase())), [rows, search]);
  const matches = (r: HistoryRow, f: Filter) => f === "ALL" || (f === "AFTER_SL"
    ? goalOrder(r) === "AFTER_SL" && barrierOrder(r) === "SL_FIRST"
    : f === "AMBIGUOUS" ? barrierOrder(r) === f || goalOrder(r) === f : barrierOrder(r) === f);
  const visible = searched.filter(r => matches(r, filter));
  const filters: [Filter, string][] = [["ALL", "Todas"], ["TP_FIRST", "TP primero"], ["SL_FIRST", "SL primero"], ["AFTER_SL", "+3.2% posterior al SL"], ["AMBIGUOUS", "Orden incierto"], ["PENDING", "En seguimiento"]];

  return <section className="history-section" aria-label="Historial de señales">
    <button className="section-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Historial de señales</button>
    {open && <>
      <p className="section-note">Orden de cruces observado en el seguimiento de hasta 24h. Las excursiones posteriores al cierre no son ganancias del plan. Los huecos de datos pueden ocultar un cruce previo.</p>
      <div className="history-controls">
        <label>Buscar par <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Ej. BTC" /></label>
        <span className="muted">{rows.length} señales recientes {loading && "· actualizando…"}</span>
      </div>
      <div className="filter-buttons">
        {filters.map(([key, label]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label} <span>{searched.filter(r => matches(r, key)).length}</span></button>)}
      </div>
      {failed && <p className="section-note warning" role="status">No se pudo actualizar el historial. {rows.length ? "Se conserva la última lectura." : "No hay una lectura disponible."}</p>}
      <div className="history-scroll">
        <table className="history-table">
          <thead><tr><th>Emisión / par</th><th>Plan de referencia</th><th>Orden observado</th><th>Recorrido de precio</th><th>Calidad del registro</th></tr></thead>
          <tbody>
            {!visible.length && <tr><td colSpan={5} className="empty-message">{loading ? "Cargando historial…" : failed ? "Historial no disponible." : "Sin señales para este filtro."}</td></tr>}
            {visible.map(row => {
              const order = barrierOrder(row);
              return <tr key={row.signal_id}>
                <td><button className="pair-name" aria-label={`Ver estado actual de ${row.symbol}`} onClick={() => onSelect?.(row.symbol)}>{row.symbol}</button><small className="muted">{new Date(row.ts_open).toLocaleString("es-GT")}</small></td>
                <td><div>Entrada {price(row.entry)}</div><small>TP {percent(row.tp_pct)} · SL {percent(row.sl_pct)}</small><small className="muted">{row.reward_neto_pct == null ? "Neto del TP no registrado" : `Si alcanza TP: neto estimado ${percent(row.reward_neto_pct)}`}</small></td>
                <td>
                  <strong className={order === "SL_FIRST" ? "negative" : order === "AMBIGUOUS" ? "warning" : ""}>{ORDER_LABEL[order]}</strong>
                  {order === "UNKNOWN" && <small className="muted">Registro anterior: {row.desenlace}</small>}
                  {(order === "TP_FIRST" || order === "SL_FIRST") && <small className="muted">Aprox. {duration(order === "TP_FIRST" ? row.ms_tp ?? null : row.ms_sl ?? null)}</small>}
                  {order === "AMBIGUOUS" && <small className="muted">No se cuenta como TP confirmado</small>}
                </td>
                <td><span className={goalOrder(row) === "AFTER_SL" ? "warning" : ""}>{goalLabel(row)}</span>
                  <small className="muted">Máx. {percent(row.mfe_pct)} · mín. {percent(row.mae_pct)}</small>
                  <small className="muted">{row.cerrado ? "Seguimiento finalizado" : "Extremos provisionales"}</small>
                </td>
                <td><span className="muted">{coverageLabel(row)}</span><small className="muted">{row.strategy_version ? `Versión ${row.strategy_version}` : "Versión no registrada"}</small></td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>
    </>}
  </section>;
}
