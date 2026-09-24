import type { PairState } from "../types";
import { hitoCumpleObjetivo } from "../domain/contrato";
import { useContratoLectura } from "../domain/contratoContext";
import { cambioDesdeEntrada, classifySignalRoute, displayPlan, nivelesDelPlan, percent, price, profiles, textoSoporte, textoTecho } from "../domain/reading";

const STATES: Record<string, string> = {
  CAYENDO: "Cayendo",
  "TOCÓ_FONDO": "Mínimo local",
  CONSOLIDANDO: "Consolidando",
  SUBIENDO: "Subiendo",
  BREAKOUT_INCIPIENTE: "Ruptura incipiente",
  NEUTRAL: "Neutral",
};

const CLOSURE_LABELS: Record<string, string> = {
  META_32_ALCANZADA: "Precio tocó +3.2% · en seguimiento",
  TP_CORTO_SIN_EXTENSION: "TP corto sin extensión",
  TP_ALCANZADO: "TP alcanzado",
  SL_ALCANZADO: "SL alcanzado",
  IMPULSO_AGOTADO: "Impulso agotado",
  ESTADO_DEGRADADO: "Estado degradado",
  CADUCADA: "Ventana accionable cerrada",
  REINICIO: "Seguimiento recuperado",
};

function continuationLabel(percentile: number | null, range: number | null | undefined) {
  if (range == null || !Number.isFinite(range) || percentile == null) {
    return "Rango no disponible";
  }
  if (percentile >= 80) return "Tramo alto entre los pares recibidos";
  return "Movimiento observado en la última hora";
}

export default function PairCard({
  pair,
  continuationPercentile,
  onClick,
  selected,
}: {
  pair: PairState;
  continuationPercentile: number | null;
  onClick: (symbol: string) => void;
  selected: boolean;
}) {
  const contrato = useContratoLectura();
  const alert = pair.alerta?.entry ? pair.alerta : undefined;
  const plan = displayPlan(pair);
  const range = pair.rango_1h_pct ?? null;
  const route = classifySignalRoute(pair);
  // `mfe_pct` es una excursion de PRECIO, o sea bruta. Tocar el hito no es
  // cobrar el objetivo: con 0,5 de coste, +3,2 % bruto deja +2,7 % netos.
  // Medido sobre 502 recorridos, 37 de los que el tablero daba por meta
  // cumplida no llegaban al objetivo real.
  const meta = hitoCumpleObjetivo(alert?.mfe_pct, contrato);
  const hitMeta = meta === "SI" || meta === "SOLO_HITO";
  const hitSL = !!alert && alert.stop_loss != null && alert.mae_pct <= (alert.stop_loss / alert.entry - 1) * 100;
  const lifecycle = !alert
    ? "Sin alerta activa"
    : alert.accionable
      ? alert.tp_corto_en_observacion
        ? `TP corto observado · ${Math.round(alert.minutos_desde_tp_corto ?? 0)} min`
        : "Señal accionable"
      : CLOSURE_LABELS[alert.motivo_cierre] ?? "En seguimiento";

  return (
    <article className={`signal-card${selected ? " selected" : ""}`}>
      <button
        type="button"
        className="signal-card-action"
        onClick={() => onClick(pair.symbol)}
        aria-label={`Ver detalle de ${pair.symbol}`}
      >
        <span className="signal-card-topline">
          <span className="signal-symbol">{pair.symbol.replace(/USDT$/, "")}<small>/USDT</small></span>
          <span className={`tier-badge tier-${pair.tier.toLowerCase()}`}>{pair.tier === "NINGUNO" ? "Sin nivel" : pair.tier}</span>
        </span>

        <span className="signal-state-row">
          <span className="signal-state">{STATES[pair.display_state] ?? pair.display_state}</span>
          <span className="signal-score" title="Puntuación técnica, no probabilidad"><small>Puntuación </small>{pair.score}<small>/100</small></span>
        </span>

        <span className="signal-profiles">
          {profiles(pair).slice(0, 2).map((profile) => <span key={profile}>{profile}</span>)}
        </span>

        <span className="signal-price-row">
          <span><small>Precio</small><strong>{price(pair.price)}</strong></span>
          <span className={(cambioDesdeEntrada(pair.price, alert?.entry) ?? 0) < 0 ? "negative" : "positive"}>
            <small>Desde entrada</small><strong>{alert ? percent(cambioDesdeEntrada(pair.price, alert.entry)) : "—"}</strong>
          </span>
        </span>

        {plan && <small className="muted">{plan.source} · porcentajes brutos</small>}
        {plan && <span className="signal-levels">
          <span><small>Entrada</small><strong>{price(plan.entry)}</strong></span>
          <span><small>TP</small><strong>{price(plan.tp)}</strong><em>{percent(plan.tpPct)}</em></span>
          <span><small>SL</small><strong>{price(plan.sl)}</strong><em>{percent(plan.slPct)}</em></span>
        </span>}
        {(() => {
          // Los dos niveles que explican el plan: sobre que se apoya el stop y
          // que hay que romper para llegar al TP.
          const niveles = nivelesDelPlan(plan?.entry, alert);
          if (!niveles) return null;
          return <span className="signal-estructura">
            {textoSoporte(niveles) && <span><small>Soporte del SL</small><strong>{textoSoporte(niveles)}</strong></span>}
            {textoTecho(niveles) && <span className={niveles.techoEstorba ? "warning" : ""}>
              <small>{niveles.techoEstorba ? "Techo a romper antes del TP" : "Techo más cercano"}</small>
              <strong>{textoTecho(niveles)}</strong></span>}
          </span>;
        })()}

        <span className={`signal-lifecycle${alert?.accionable ? " active" : ""}`}>{lifecycle}</span>
        {(hitMeta || hitSL) && <span className="signal-observation">
          <strong>{hitSL && hitMeta ? `Precio tocó el SL y ${contrato.hito_referencia.etiqueta}` : hitSL ? "Precio tocó el SL" : `Precio tocó ${contrato.hito_referencia.etiqueta}`}{meta === "SOLO_HITO" && ` — no llegó a tu objetivo (${contrato.objetivo_operador_bruto.etiqueta})`}</strong>
          <small>Recorrido de precio. Consulta el orden de cruces en el historial.</small>
        </span>}

        <span className="signal-models">
          <span className={`shadow-reading route-reading route-${route.route.toLowerCase()}`}>
            <small>Clasificación</small>
            <strong>{route.label}</strong>
            <em>{route.reason}</em>
          </span>
          <span className={continuationPercentile != null && continuationPercentile >= 80 ? "shadow-reading highlighted" : "shadow-reading"}>
            <small>Rango 1h</small>
            <strong>{percent(range)}</strong>
            <em>{continuationLabel(continuationPercentile, range)}</em>
          </span>
        </span>
      </button>
    </article>
  );
}
