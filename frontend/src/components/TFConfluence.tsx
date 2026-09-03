import type { MacroTrends, TFTrend } from "../types";

const DOT_COLOR: Record<TFTrend, string> = {
  ALCISTA: "#2d7a2d",
  NEUTRAL: "#555",
  BAJISTA: "#8b2020",
};

const DOT_LABEL: Record<TFTrend, string> = {
  ALCISTA: "▲",
  NEUTRAL: "—",
  BAJISTA: "▼",
};

interface Props {
  trends: MacroTrends;
}

const TFS: Array<keyof MacroTrends> = ["15m", "1h", "4h", "1d"];

export default function TFConfluence({ trends }: Props) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      {TFS.map((tf) => {
        const t = trends[tf] ?? "NEUTRAL";
        return (
          <span
            key={tf}
            title={`${tf}: ${t}`}
            style={{
              display: "inline-flex",
              flexDirection: "column",
              alignItems: "center",
              fontSize: 9,
              color: DOT_COLOR[t],
              gap: 1,
              minWidth: 22,
            }}
          >
            <span style={{ fontSize: 11 }}>{DOT_LABEL[t]}</span>
            <span style={{ opacity: 0.6 }}>{tf}</span>
          </span>
        );
      })}
    </div>
  );
}
