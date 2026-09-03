import type { StateEvent } from "../types";

const STATE_COLOR: Record<string, string> = {
  CAYENDO: "#8b2020",
  "TOCÓ_FONDO": "#b8860b",
  CONSOLIDANDO: "#4a9ead",
  SUBIENDO: "#2d7a2d",
  BREAKOUT_INCIPIENTE: "#00ff41",
  NEUTRAL: "#555",
};

interface Props {
  history: StateEvent[];
}

export default function StateHistory({ history }: Props) {
  if (!history || history.length === 0) {
    return <p style={{ color: "#555", fontSize: 12, padding: 8 }}>Sin historial disponible.</p>;
  }

  return (
    <div style={{ maxHeight: 260, overflowY: "auto" }}>
      {[...history].reverse().map((ev, i) => {
        const d = new Date(ev.ts);
        const time = d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "4px 8px",
              borderBottom: "1px solid #1a1a1a",
              fontSize: 12,
            }}
          >
            <span style={{ color: "#555", minWidth: 60 }}>{time}</span>
            <span
              style={{
                color: STATE_COLOR[ev.state] ?? "#999",
                fontWeight: 700,
                minWidth: 120,
              }}
            >
              {ev.state}
            </span>
            <span style={{ color: "#77a" }}>{ev.score}</span>
            <span style={{ color: "#556", fontSize: 10 }}>{ev.tier}</span>
            <span style={{ color: "#445", fontSize: 10, marginLeft: "auto" }}>{ev.macro}</span>
          </div>
        );
      })}
    </div>
  );
}
