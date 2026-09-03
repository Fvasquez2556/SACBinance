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

export default function PairRow({ pair, onClick, selected }: Props) {
  const style = STATE_STYLE[pair.display_state] ?? STATE_STYLE.NEUTRAL;

  return (
    <tr
      onClick={() => onClick(pair.symbol)}
      style={{
        cursor: "pointer",
        background: selected ? "#1a2a1a" : style.bg,
        borderBottom: "1px solid #1e1e1e",
        transition: "background 0.15s, opacity 0.4s",
        opacity: pair.fading ? 0.5 : 1,
      }}
      title={pair.fading ? "Perdiendo fuerza — dejó de ser interesante" : undefined}
    >
      <td style={{ padding: "6px 10px", fontWeight: 700, color: "#ccc", fontSize: 13 }}>
        {pair.symbol.replace("USDT", "")}
        <span style={{ color: "#555", fontWeight: 400, fontSize: 10 }}>/USDT</span>
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
