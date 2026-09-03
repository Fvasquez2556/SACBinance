import { useEffect, useState } from "react";

interface Stats {
  total: number;
  open: number;
  closed: number;
  tp: number;
  sl: number;
  expired: number;
  win_rate: number;
  avg_result_pct: number;
}

export default function SignalStats() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    const load = () => {
      fetch("/api/signals/stats")
        .then((r) => r.json())
        .then(setStats)
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  if (!stats || stats.closed === 0) {
    return (
      <span style={{ color: "#445", fontSize: 11 }}>
        Señales: {stats?.open ?? 0} abiertas · sin cerrar aún
      </span>
    );
  }

  const wrColor =
    stats.win_rate >= 55 ? "#2d7a2d" : stats.win_rate >= 45 ? "#b8860b" : "#8b2020";

  return (
    <span style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 11 }}>
      <span style={{ color: "#445" }}>
        Señales <span style={{ color: "#778" }}>{stats.closed}</span>
      </span>
      <span style={{ color: "#557" }}>
        Win rate{" "}
        <span style={{ color: wrColor, fontWeight: 700 }}>{stats.win_rate}%</span>
      </span>
      <span style={{ color: "#2d7a2d" }}>TP {stats.tp}</span>
      <span style={{ color: "#8b2020" }}>SL {stats.sl}</span>
      <span style={{ color: "#557" }}>exp {stats.expired}</span>
      <span style={{ color: stats.avg_result_pct >= 0 ? "#2d7a2d" : "#8b2020" }}>
        prom {stats.avg_result_pct > 0 ? "+" : ""}
        {stats.avg_result_pct}%
      </span>
      <span style={{ color: "#445" }}>· {stats.open} abiertas</span>
    </span>
  );
}
