import { useMemo, useState } from "react";
import type { DisplayState, PairState, Tier } from "../types";
import PairDetail from "./PairDetail";
import PairRow from "./PairRow";
import SignalStats from "./SignalStats";

const INTERESTING_STATES: DisplayState[] = ["TOCÓ_FONDO", "CONSOLIDANDO", "SUBIENDO", "BREAKOUT_INCIPIENTE"];

interface Props {
  pairs: Map<string, PairState>;
  connected: boolean;
  lastTs: number;
  notifPermission: string;
  onRequestNotif: () => void;
}

type FilterState = DisplayState | "TODOS";

export default function Dashboard({
  pairs,
  connected,
  lastTs,
  notifPermission,
  onRequestNotif,
}: Props) {
  const [stateFilter, setStateFilter] = useState<FilterState>("TODOS");
  const [minScore, setMinScore] = useState<number>(60);
  const [tierFilter, setTierFilter] = useState<Tier | "TODOS">("TODOS");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let list = Array.from(pairs.values());

    // Estado (las "fading" siguen visibles aunque ya no sean interesantes)
    if (stateFilter === "TODOS") {
      list = list.filter(
        (p) => INTERESTING_STATES.includes(p.display_state) || p.fading
      );
    } else {
      list = list.filter((p) => p.display_state === stateFilter);
    }

    // Score mínimo — las "fading" se muestran igual para ver cómo pierden fuerza
    list = list.filter((p) => p.score >= minScore || p.fading);

    // Tier
    if (tierFilter !== "TODOS") {
      list = list.filter((p) => p.tier === tierFilter);
    }

    return list.sort((a, b) => b.score - a.score);
  }, [pairs, stateFilter, minScore, tierFilter]);

  const selectedPair = selectedSymbol ? pairs.get(selectedSymbol) : null;

  const btnStyle = (active: boolean): React.CSSProperties => ({
    padding: "4px 12px",
    fontSize: 11,
    background: active ? "#1e2e1e" : "#111",
    color: active ? "#4a9" : "#557",
    border: `1px solid ${active ? "#4a9" : "#2a2a2a"}`,
    borderRadius: 4,
    cursor: "pointer",
    transition: "all 0.15s",
  });

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0a0a0a", color: "#ccc", fontFamily: "monospace" }}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header */}
        <div
          style={{
            padding: "10px 16px",
            borderBottom: "1px solid #1e1e1e",
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div>
            <span style={{ fontWeight: 700, fontSize: 15, color: "#99f" }}>SACBinance</span>
            <span style={{ color: "#335", fontSize: 11, marginLeft: 6 }}>v3</span>
          </div>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: connected ? "#2d7a2d" : "#8b2020" }} />
          <span style={{ color: "#446", fontSize: 11 }}>
            {pairs.size} pares | {filtered.length} visibles
            {lastTs > 0 && ` | ${new Date(lastTs).toLocaleTimeString("es-ES")}`}
          </span>

          <SignalStats />

          {notifPermission !== "granted" && notifPermission !== "unsupported" && (
            <button
              onClick={onRequestNotif}
              style={{
                padding: "4px 12px",
                fontSize: 11,
                background: "#1a1400",
                color: "#b8860b",
                border: "1px solid #b8860b66",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              🔔 Activar alertas
            </button>
          )}
          {notifPermission === "granted" && (
            <span style={{ color: "#2d7a2d", fontSize: 11 }}>🔔 Alertas activas</span>
          )}

          {/* Filtros de estado */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(["TODOS", "TOCÓ_FONDO", "CONSOLIDANDO", "SUBIENDO", "BREAKOUT_INCIPIENTE"] as const).map((s) => (
              <button key={s} style={btnStyle(stateFilter === s)} onClick={() => setStateFilter(s)}>
                {s === "TODOS" ? "Interesantes" : s === "TOCÓ_FONDO" ? "TOCÓ FONDO" : s}
              </button>
            ))}
          </div>

          {/* Tier filter */}
          <div style={{ display: "flex", gap: 6 }}>
            {(["TODOS", "VIGILANCIA", "MODERADA", "FUERTE", "EXTRA-FUERTE"] as const).map((t) => (
              <button key={t} style={btnStyle(tierFilter === t)} onClick={() => setTierFilter(t)}>
                {t === "TODOS" ? "Todo tier" : t}
              </button>
            ))}
          </div>

          {/* Score slider */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "#557", fontSize: 11 }}>Score ≥ {minScore}</span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              style={{ width: 80, accentColor: "#99f" }}
            />
          </div>
        </div>

        {/* Tabla */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e1e1e", fontSize: 10, color: "#557", textAlign: "left" }}>
                <th style={{ padding: "6px 10px" }}>PAR</th>
                <th style={{ padding: "6px 8px" }}>ESTADO</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>SCORE</th>
                <th style={{ padding: "6px 8px" }}>TIER</th>
                <th style={{ padding: "6px 8px" }} title="Fuerza del impulso y % ya recorrido del movimiento">
                  IMPULSO
                </th>
                <th style={{ padding: "6px 8px", textAlign: "right" }} title="Entry congelado en la emisión y delta actual contra él">
                  ENTRY · Δ
                </th>
                <th style={{ padding: "6px 8px" }}>15M · 1H · 4H · 1D</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>GATE</th>
                <th style={{ padding: "6px 10px" }}>DESDE</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: "40px", textAlign: "center", color: "#333", fontSize: 13 }}>
                    Sin pares interesantes actualmente.
                  </td>
                </tr>
              ) : (
                filtered.map((p) => (
                  <PairRow
                    key={p.symbol}
                    pair={p}
                    selected={p.symbol === selectedSymbol}
                    onClick={setSelectedSymbol}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Panel de detalle */}
      {selectedPair && (
        <PairDetail pair={selectedPair} onClose={() => setSelectedSymbol(null)} />
      )}
    </div>
  );
}
