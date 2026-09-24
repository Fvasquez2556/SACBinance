import type { PairState } from "../types";
import { cambioDesdeEntrada, displayPlan, percent, price, profiles } from "../domain/reading";
import TFConfluence from "./TFConfluence";

const STATES: Record<string, string> = {
  CAYENDO: "Cayendo", "TOCÓ_FONDO": "Mínimo local", CONSOLIDANDO: "Consolidando",
  SUBIENDO: "Subiendo", BREAKOUT_INCIPIENTE: "Ruptura incipiente", NEUTRAL: "Neutral",
};
const PHASES: Record<string, string> = {
  ACELERANDO: "Gana impulso", SOSTENIDA: "Impulso sostenido", DESACELERANDO: "Pierde impulso",
  AGOTADA: "Impulso agotado", SIN_DATOS: "Sin medida de impulso",
};

export default function PairRow({ pair, onClick, selected }: {
  pair: PairState; onClick: (symbol: string) => void; selected: boolean;
}) {
  const a = pair.alerta?.entry ? pair.alerta : undefined;
  const plan = displayPlan(pair);
  const hitMeta = a && a.mfe_pct >= 3.2;
  const hitSL = a && a.stop_loss != null && a.mae_pct <= (a.stop_loss / a.entry - 1) * 100;
  return <tr className={`pair-row${selected ? " selected" : ""}`} onClick={() => onClick(pair.symbol)}>
    <td>
      <button className="pair-name" aria-label={`Ver ${pair.symbol}`}>{pair.symbol.replace(/USDT$/, "")}<small>/USDT</small></button>
      {profiles(pair).map((label) => <span className="profile-label" key={label}>{label}</span>)}
      {pair.retroceso?.detectado && <small className="muted">Caída {percent(pair.retroceso.caida_pct)} · rebote {percent(pair.retroceso.rebote_pct)}</small>}
    </td>
    <td>
      <strong>{STATES[pair.display_state] ?? pair.display_state}</strong>
      <small className="muted">{a ? a.accionable ? "Alerta activa" : "En seguimiento" : "Sin alerta activa"}</small>
      <TFConfluence trends={pair.macro_trends} />
    </td>
    <td>
      <span title="Puntuación de indicadores. No es una probabilidad de éxito."><strong>{pair.score}</strong><small> / 100 puntos</small></span>
      <small className="muted">{pair.tier === "NINGUNO" ? "Sin nivel de alerta" : pair.tier}</small>
      <small className="muted">{PHASES[pair.impulso?.fase ?? "SIN_DATOS"]}</small>
      {pair.rango_1h_pct != null && <small className="muted">Rango previo 1h: {percent(pair.rango_1h_pct)}</small>}
    </td>
    <td className="plan-cell">
      {plan ? <><small className="muted">{plan.source}</small>
        <div>Entrada <strong>{price(plan.entry)}</strong></div>
        <div>TP <span>{price(plan.tp)} <small>({percent(plan.tpPct)})</small></span></div>
        <div>SL <span>{price(plan.sl)} <small>({percent(plan.slPct)})</small></span></div>
      </> : <span className="muted">Sin plan disponible</span>}
    </td>
    <td>
      <strong>{price(pair.price)}</strong>
      {a && (() => { const c = cambioDesdeEntrada(pair.price, a.entry); return <>
        <span className={(c ?? 0) >= 0 ? "positive" : "negative"}>{percent(c)}</span>
        <small className="muted">desde la entrada del plan</small></>; })()}
    </td>
    <td>
      {a ? <>
        {hitMeta && <span className="observation">Precio tocó +3.2%</span>}
        {hitSL && <span className="observation warning">Precio tocó el SL</span>}
        {!hitMeta && !hitSL && <span className="muted">Seguimiento en curso</span>}
        {(hitMeta || hitSL) && <small className="muted">Orden de cruces: ver historial</small>}
        <small className="muted">Máx. {percent(a.mfe_pct)} · mín. {percent(a.mae_pct)}</small>
      </> : <span className="muted">Se inicia al emitir una alerta</span>}
    </td>
    <td><span>{a ? `${Math.round(a.edad_min)} min` : "—"}</span><small className="muted">{a ? "desde la emisión" : "sin emisión"}</small></td>
  </tr>;
}
