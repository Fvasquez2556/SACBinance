import { useEffect, useState } from "react";
import { percent } from "../domain/reading";

interface Stats {
  total: number; open: number; closed: number; tp: number; sl: number; expired: number;
  win_rate: number; avg_result_pct: number; pct_en_positivo?: number; pct_sobre_meta?: number;
}

export default function SignalStats() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const r = await fetch("/api/signals/stats", { signal: controller.signal });
        if (!r.ok) throw new Error("stats");
        const d: Stats = await r.json();
        if (!Number.isFinite(d.closed)) throw new Error("stats");
        setStats(d); setFailed(false);
      } catch { if (!controller.signal.aborted) setFailed(true); }
    };
    void load(); const id = setInterval(() => void load(), 30000);
    return () => { controller.abort(); clearInterval(id); };
  }, []);
  return <details className="signal-stats">
    <summary>Histórico de señales <span className="muted">{stats ? `· ${stats.closed} cerradas · ${stats.open} abiertas` : failed ? "· no disponible" : "· cargando…"}</span></summary>
    <p>Resultados registrados de planes anteriores, en bruto. No representan la probabilidad de la próxima señal ni acreditan operaciones ejecutadas.</p>
    {failed && <p role="status">No se pudo actualizar. {stats ? "Se conserva la última lectura." : "Intenta de nuevo al actualizar la página."}</p>}
    {stats && stats.closed > 0 && <>
      <div className="stats-grid">
        <div><span>Alcanzaron el TP</span><strong>{stats.win_rate}%</strong><small>{stats.tp} de {stats.closed} cerradas</small></div>
        <div><span>Cierre ≥ +3.2% bruto</span><strong>{stats.pct_sobre_meta == null ? "—" : `${stats.pct_sobre_meta}%`}</strong><small>Incluye cierres por vencimiento</small></div>
        <div><span>Cierre positivo bruto</span><strong>{stats.pct_en_positivo == null ? "—" : `${stats.pct_en_positivo}%`}</strong><small>Antes de comisión y deslizamiento</small></div>
        <div><span>Resultado medio bruto</span><strong>{percent(stats.avg_result_pct)}</strong><small>SL: {stats.sl} · vencidas: {stats.expired}</small></div>
      </div>
      <p className="muted">El denominador incluye TP, SL y vencidas. Las señales abiertas se excluyen. Este histórico combina versiones y condiciones de mercado.</p>
    </>}
    {stats?.closed === 0 && <p>Aún no hay señales cerradas para calcular estas frecuencias.</p>}
  </details>;
}
