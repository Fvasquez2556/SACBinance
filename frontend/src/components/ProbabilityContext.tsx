import type { AlertaActiva } from "../types";

export default function ProbabilityContext({ alerta }: { alerta?: AlertaActiva }) {
  const hasHistory = alerta && alerta.dist_meta_pct != null && alerta.dist_meta_pct > 0 &&
    Number.isFinite(alerta.prob_meta) && alerta.prob_meta >= 0 && alerta.prob_meta <= 100 && alerta.prob_meta_n > 0;
  return <section className="probability-context" aria-label="Lectura de probabilidades">
    <h3>Probabilidad de TP antes del SL</h3>
    <strong className="muted">Estimación no disponible</strong>
    <p>La evaluación por tipo de oportunidad, volatilidad y horizonte todavía no ofrece una probabilidad validada para este plan.</p>
    {hasHistory && <details>
      <summary>Referencia histórica de toque · 6 horas</summary>
      <p><strong>{alerta.prob_meta.toFixed(0)}%</strong> de {alerta.prob_meta_n.toLocaleString("es-GT")} observaciones de la tabla histórica tocaron +3.2% desde la entrada de referencia en las siguientes 6 horas, según distancia y edad. Ese umbral puede diferir del TP del plan.</p>
      <p>Incluye casos con SL previo. Las observaciones se repiten durante la vida de una señal; no son operaciones independientes. Es una referencia de precio, no una probabilidad de beneficio.</p>
    </details>}
  </section>;
}
