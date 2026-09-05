import type { PairState, Tier } from "../types";
import TFConfluence from "./TFConfluence";

const STATE_STYLE: Record<string, { bg: string; color: string }> = {
  CAYENDO:            { bg: "#1a0505", color: "#8b2020" },
  "TOCÓ_FONDO":      { bg: "#1a1400", color: "#b8860b" },
  CONSOLIDANDO:       { bg: "#0a1520", color: "#4a9ead" },
  SUBIENDO:           { bg: "#0a1a0a", color: "#2d7a2d" },
  BREAKOUT_INCIPIENTE: { bg: "#001a00", color: "#00ff41" },
  NEUTRAL:            { bg: "#111", color: "#555" },
};

const TIER_COLOR: Record<Tier, string> = {
  NINGUNO: "#444",
  VIGILANCIA: "#557",
  MODERADA: "#668",
  FUERTE: "#77a",
  "EXTRA-FUERTE": "#99f",
};

const STATE_LABEL: Record<string, string> = {
  CAYENDO: "CAYENDO",
  "TOCÓ_FONDO": "TOCÓ FONDO",
  CONSOLIDANDO: "CONSOLIDANDO",
  SUBIENDO: "SUBIENDO",
  BREAKOUT_INCIPIENTE: "BREAKOUT",
  NEUTRAL: "NEUTRAL",
};

function timeAgo(tsMs: number): string {
  if (!tsMs) return "—";
  const secs = Math.floor((Date.now() - tsMs) / 1000);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h`;
}

interface Props {
  pair: PairState;
  onClick: (symbol: string) => void;
  selected: boolean;
}

// Hasta donde llego el precio desde el entry congelado. No excluyentes:
// una alerta que bajo -1.2% y luego subio +3.2% muestra los dos puntos.
const MARCA_STYLE: Record<string, { color: string; titulo: string }> = {
  MORADO: { color: "#8b5cf6", titulo: "Llegó a +4.2%" },
  VERDE: { color: "#22c55e", titulo: "Llegó a +3.2%" },
  AMARILLO: { color: "#eab308", titulo: "Cayó a -1.2% (SL medio observado)" },
  ROJO: { color: "#dc2626", titulo: "Tocó el SL que fijó el sistema" },
};

const FASE_STYLE: Record<string, { color: string; icono: string }> = {
  ACELERANDO: { color: "#2d9c4a", icono: "▲▲" },
  SOSTENIDA: { color: "#8a9a3a", icono: "▲" },
  DESACELERANDO: { color: "#c07a1a", icono: "▼" },
  AGOTADA: { color: "#a02020", icono: "▼▼" },
  SIN_DATOS: { color: "#555", icono: "·" },
};

export default function PairRow({ pair, onClick, selected }: Props) {
  const style = STATE_STYLE[pair.display_state] ?? STATE_STYLE.NEUTRAL;
  const alerta = pair.alerta && pair.alerta.entry ? pair.alerta : null;
  const enDeclive = alerta?.estado === "PERDIENDO_FUERZA";
  const fase = FASE_STYLE[pair.impulso?.fase ?? "SIN_DATOS"] ?? FASE_STYLE.SIN_DATOS;

  return (
    <tr
      onClick={() => onClick(pair.symbol)}
      style={{
        cursor: "pointer",
        background: selected ? "#1a2a1a" : enDeclive ? "#2a1414" : style.bg,
        borderBottom: "1px solid #1e1e1e",
        borderLeft: enDeclive ? "3px solid #a02020" : "3px solid transparent",
        transition: "background 0.15s, opacity 0.4s",
        opacity: pair.fading && !alerta ? 0.5 : 1,
      }}
      title={
        enDeclive
          ? `PERDIENDO FUERZA — ${pair.impulso?.reason ?? ""}. Entry congelado ${alerta?.entry}`
          : alerta
            ? `Alerta viva desde hace ${alerta.edad_min} min — entry congelado ${alerta.entry}`
            : pair.fading
              ? "Dejó de ser interesante"
              : undefined
      }
    >
      <td style={{ padding: "6px 10px", fontWeight: 700, color: "#ccc", fontSize: 13 }}>
        {pair.symbol.replace("USDT", "")}
        <span style={{ color: "#555", fontWeight: 400, fontSize: 10 }}>/USDT</span>
        {alerta && (
          <div style={{ fontSize: 9, marginTop: 2, whiteSpace: "nowrap" }}>
            <span style={{ color: enDeclive ? "#d04040" : "#2d9c4a", fontWeight: 700 }}>
              {enDeclive ? "PERDIENDO FUERZA" : "ALERTA VIVA"}
            </span>
            <span style={{ color: "#666", fontWeight: 400 }}> · {alerta.edad_min}min</span>
          </div>
        )}
        {alerta && alerta.marcadores && alerta.marcadores.length > 0 && (
          <div style={{ marginTop: 3, display: "flex", gap: 3 }}>
            {alerta.marcadores.map((m) => {
              const e = MARCA_STYLE[m];
              if (!e) return null;
              return (
                <span
                  key={m}
                  title={e.titulo}
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: e.color,
                    display: "inline-block",
                  }}
                />
              );
            })}
          </div>
        )}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <span
          style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: 4,
            background: style.bg,
            color: style.color,
            border: `1px solid ${style.color}33`,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.04em",
          }}
        >
          {STATE_LABEL[pair.display_state] ?? pair.display_state}
        </span>
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right", whiteSpace: "nowrap" }}>
        <span style={{ color: style.color, fontWeight: 700, fontSize: 14 }}>
          {pair.score}
        </span>
        {pair.score_trend !== 0 && (
          <span
            style={{
              fontSize: 9,
              marginLeft: 3,
              color: pair.score_trend > 0 ? "#2d7a2d" : "#8b2020",
            }}
          >
            {pair.score_trend > 0 ? "▲" : "▼"}
            {Math.abs(pair.score_trend)}
          </span>
        )}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <span style={{ color: TIER_COLOR[pair.tier], fontSize: 11 }}>
          {pair.tier === "NINGUNO" ? "—" : pair.tier}
        </span>
      </td>
      {/* Impulso: la derivada. Dice si el movimiento gana o pierde fuerza. */}
      <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>
        {pair.impulso?.valid ? (
          <span title={pair.impulso.reason}>
            <span style={{ color: fase.color, fontSize: 10, fontWeight: 700 }}>
              {fase.icono} {pair.impulso.fuerza}
            </span>
            {pair.impulso.consumido_pct != null && (
              <span style={{ color: "#666", fontSize: 9, marginLeft: 4 }}>
                {pair.impulso.consumido_pct.toFixed(1)}%rec
              </span>
            )}
          </span>
        ) : (
          <span style={{ color: "#444", fontSize: 10 }}>—</span>
        )}
      </td>
      {/* Entry CONGELADO en la emisión + delta en vivo contra ese entry */}
      <td style={{ padding: "6px 8px", textAlign: "right", whiteSpace: "nowrap" }}>
        {alerta ? (
          <>
            <div style={{ color: "#889", fontSize: 11 }}>{alerta.entry}</div>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: alerta.delta_pct >= 0 ? "#2d9c4a" : "#c04040",
              }}
            >
              {alerta.delta_pct >= 0 ? "+" : ""}
              {alerta.delta_pct.toFixed(2)}%
            </div>
          </>
        ) : (
          <span style={{ color: "#444", fontSize: 10 }}>—</span>
        )}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <TFConfluence trends={pair.macro_trends} />
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right", color: "#667", fontSize: 11 }}>
        {pair.macro_gate_mult !== 1 ? `×${pair.macro_gate_mult.toFixed(2)}` : "—"}
      </td>
      <td style={{ padding: "6px 10px", color: "#555", fontSize: 11 }}>
        {timeAgo(pair.score_since_ms)}
      </td>
    </tr>
  );
}
