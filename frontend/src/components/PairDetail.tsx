import { useEffect, useState } from "react";
import type { PairState, StateEvent } from "../types";
import StateHistory from "./StateHistory";

interface Props {
  pair: PairState;
  onClose: () => void;
}

function Row({ label, value, color }: { label: string; value: string | number | null; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid #1a1a1a", fontSize: 12 }}>
      <span style={{ color: "#668" }}>{label}</span>
      <span style={{ color: color ?? "#aaa", fontWeight: 500 }}>{value ?? "—"}</span>
    </div>
  );
}

export default function PairDetail({ pair, onClose }: Props) {
  const [history, setHistory] = useState<StateEvent[]>([]);

  useEffect(() => {
    fetch(`/api/pair/${pair.symbol}/history`)
      .then((r) => r.json())
      .then((d) => setHistory(d.history ?? []))
      .catch(() => {});
  }, [pair.symbol]);

  return (
    <div
      style={{
        position: "fixed",
        right: 0,
        top: 0,
        bottom: 0,
        width: 340,
        background: "#0d0d0d",
        borderLeft: "1px solid #2a2a2a",
        display: "flex",
        flexDirection: "column",
        zIndex: 100,
        boxShadow: "-4px 0 20px rgba(0,0,0,0.5)",
      }}
    >
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid #1e1e1e",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 16, color: "#ccc" }}>
          {pair.symbol}
        </span>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", color: "#777", fontSize: 18, cursor: "pointer" }}
        >
          ✕
        </button>
      </div>

      <div style={{ padding: "12px 16px", flex: 1, overflowY: "auto" }}>
        <section>
          <h4 style={{ color: "#557", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
            ESTADO
          </h4>
          <Row label="Display" value={pair.display_state} color="#aae" />
          <Row label="FSM" value={pair.fsm_state} />
          <Row label="Score" value={pair.score} color="#99f" />
          <Row label="Tier" value={pair.tier} />
          <Row label="Macro global" value={pair.macro_global} />
          <Row label="Gate mult" value={`×${pair.macro_gate_mult}`} />
          <Row
            label="Régimen BTC"
            value={pair.btc_regime}
            color={pair.btc_regime === "ALCISTA" ? "#2d7a2d" : pair.btc_regime === "BAJISTA" ? "#8b2020" : "#666"}
          />
          <Row
            label="Posición en rango 15m"
            value={`${Math.round((pair.pos_en_rango ?? 0.5) * 100)}%`}
            color={
              (pair.pos_en_rango ?? 0.5) <= 0.4
                ? "#4a9ead"
                : (pair.pos_en_rango ?? 0.5) >= 0.7
                ? "#b8860b"
                : "#888"
            }
          />
          {pair.is_fakeout && (
            <div style={{ marginTop: 6, padding: "4px 8px", background: "#1a0505", border: "1px solid #8b202066", borderRadius: 4, color: "#c0392b", fontSize: 11 }}>
              ⚠ Breakout fallido reciente — score penalizado
            </div>
          )}
        </section>

        {pair.trade_levels?.valid && (
          <section style={{ marginTop: 12 }}>
            <h4 style={{ color: "#4a9", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
              NIVELES DE TRADING
            </h4>
            <div style={{ display: "flex", gap: 6 }}>
              <div style={{ flex: 1, background: "#0a1a0a", border: "1px solid #2d7a2d33", borderRadius: 4, padding: "6px 8px", textAlign: "center" }}>
                <div style={{ color: "#557", fontSize: 9 }}>ENTRADA</div>
                <div style={{ color: "#ccc", fontSize: 13, fontWeight: 700 }}>{pair.trade_levels.entry}</div>
              </div>
              <div style={{ flex: 1, background: "#001a00", border: "1px solid #00ff4133", borderRadius: 4, padding: "6px 8px", textAlign: "center" }}>
                <div style={{ color: "#557", fontSize: 9 }}>TAKE PROFIT</div>
                <div style={{ color: "#00ff41", fontSize: 13, fontWeight: 700 }}>{pair.trade_levels.take_profit}</div>
                <div style={{ color: "#2d7a2d", fontSize: 9 }}>+{pair.trade_levels.reward_pct}%</div>
              </div>
              <div style={{ flex: 1, background: "#1a0505", border: "1px solid #8b202033", borderRadius: 4, padding: "6px 8px", textAlign: "center" }}>
                <div style={{ color: "#557", fontSize: 9 }}>STOP LOSS</div>
                <div style={{ color: "#c0392b", fontSize: 13, fontWeight: 700 }}>{pair.trade_levels.stop_loss}</div>
                <div style={{ color: "#8b2020", fontSize: 9 }}>-{pair.trade_levels.risk_pct}%</div>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 11 }}>
              <span style={{ color: "#668" }}>Ratio Beneficio/Riesgo</span>
              <span style={{ color: pair.trade_levels.risk_reward && pair.trade_levels.risk_reward >= 2 ? "#2d7a2d" : "#b8860b", fontWeight: 700 }}>
                {pair.trade_levels.risk_reward} : 1
              </span>
            </div>
            {pair.trade_levels.tp_blocked_by_resistance && pair.trade_levels.nearest_resistance && (
              <div style={{ marginTop: 4, color: "#b8860b", fontSize: 10 }}>
                ⚠ Resistencia en {pair.trade_levels.nearest_resistance} antes del TP
              </div>
            )}
            <div style={{ color: "#445", fontSize: 9, marginTop: 4 }}>{pair.trade_levels.reason}</div>
          </section>
        )}

        <section style={{ marginTop: 12 }}>
          <h4 style={{ color: "#557", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
            MÉTRICAS 1M
          </h4>
          <Row label="Precio" value={pair.price} />
          <Row label="Retorno 1m" value={`${pair.ret_1m_pct?.toFixed(3)}%`} color={pair.ret_1m_pct > 0 ? "#2d7a2d" : "#8b2020"} />
          <Row label="Z-rise" value={pair.z_rise?.toFixed(2)} />
          <Row label="Z-drop" value={pair.z_drop?.toFixed(2)} />
          <Row label="Velocity" value={pair.velocity?.toFixed(2)} />
          <Row label="Vol ratio" value={pair.vol_ratio?.toFixed(2)} />
          <Row label="Drawdown" value={`${pair.drawdown_pct?.toFixed(2)}%`} />
          <Row label="Sigma" value={`${pair.sigma_pct?.toFixed(3)}%`} />
        </section>

        <section style={{ marginTop: 12 }}>
          <h4 style={{ color: "#557", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
            INDICADORES
          </h4>
          <Row label="RSI5" value={pair.rsi5} color={pair.rsi5 != null && pair.rsi5 > 70 ? "#8b2020" : pair.rsi5 != null && pair.rsi5 > 50 ? "#2d7a2d" : "#aaa"} />
          <Row label="MACD rising" value={pair.macd_rising == null ? "—" : pair.macd_rising ? "Sí" : "No"} />
          <Row label="Trend up" value={pair.trend_up == null ? "—" : pair.trend_up ? "Sí" : "No"} />
          <Row label="Flujo compras 30s" value={`${(pair.buy_ratio_30s * 100).toFixed(1)}%`} />
          <Row label="Trades 30s" value={pair.flow_trades_30s} />
          <Row label="Flow confirmado" value={pair.flow_confirm ? "Sí" : "No"} color={pair.flow_confirm ? "#2d7a2d" : "#8b2020"} />
        </section>

        <section style={{ marginTop: 12 }}>
          <h4 style={{ color: "#557", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
            TENDENCIAS MACRO
          </h4>
          {pair.macro_trends && Object.entries(pair.macro_trends).map(([tf, t]) => (
            <Row key={tf} label={tf} value={t} color={t === "ALCISTA" ? "#2d7a2d" : t === "BAJISTA" ? "#8b2020" : "#666"} />
          ))}
        </section>

        {pair.sr_levels && (pair.sr_levels.soportes?.length > 0 || pair.sr_levels.resistencias?.length > 0) && (
          <section style={{ marginTop: 12 }}>
            <h4 style={{ color: "#557", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
              SOPORTE / RESISTENCIA
            </h4>
            {(pair.sr_levels.resistencias ?? []).slice(0, 3).reverse().map((n, i) => (
              <div key={`r${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0", fontSize: 11 }}>
                <span style={{ color: "#8b2020" }}>Resistencia</span>
                <span style={{ color: "#aaa" }}>{n.precio.toFixed(6)}</span>
                <span style={{ color: "#556", fontSize: 9 }}>{n.toques} toques</span>
              </div>
            ))}
            <div style={{ borderTop: "1px dashed #2a2a2a", margin: "3px 0" }} />
            {(pair.sr_levels.soportes ?? []).slice(0, 3).map((n, i) => (
              <div key={`s${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0", fontSize: 11 }}>
                <span style={{ color: "#2d7a2d" }}>Soporte</span>
                <span style={{ color: "#aaa" }}>{n.precio.toFixed(6)}</span>
                <span style={{ color: "#556", fontSize: 9 }}>{n.toques} toques</span>
              </div>
            ))}
          </section>
        )}

        {pair.consolidation?.consolidating && (
          <section style={{ marginTop: 12 }}>
            <h4 style={{ color: "#4a9ead", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
              CONSOLIDACIÓN
            </h4>
            <Row label="ATR%" value={pair.consolidation.atr_pct} />
            <Row label="Percentil ATR" value={pair.consolidation.atr_percentile != null ? `P${pair.consolidation.atr_percentile}` : "—"} color="#4a9ead" />
            <Row label="MAs convergentes" value={pair.consolidation.ma_convergent ? "Sí" : "No"} />
            <Row label="Volumen decreciente" value={pair.consolidation.vol_declining ? "Sí" : "No"} />
            <Row label="Velas en rango" value={pair.consolidation.candles_in_state} />
          </section>
        )}

        <section style={{ marginTop: 12 }}>
          <h4 style={{ color: "#557", fontSize: 11, letterSpacing: "0.1em", marginBottom: 6, marginTop: 0 }}>
            HISTORIAL 24H
          </h4>
          <StateHistory history={history} />
        </section>
      </div>
    </div>
  );
}
