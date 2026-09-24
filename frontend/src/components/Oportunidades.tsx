import { useEffect, useState } from "react";
import { useContratoLectura } from "../domain/contratoContext";
import { percent, price } from "../domain/reading";

/**
 * Las oportunidades vivas, con lo necesario para elegir entre ellas.
 *
 * Medido el 22-sep: con 10 USDT y una sola posición se pueden abrir dos
 * operaciones al día y llegan diecisiete avisos. Se opera el 12 % y el 88 %
 * pasa de largo. El cuello de botella no es qué objetivo poner: es **cuál
 * tomar** — y los datos para decidirlo (episodio, los dos motores, conflicto
 * entre marcos, techo de por medio) existían solo dentro de la base.
 *
 * Esta vista NO ordena por calidad. La puntuación del sistema no ordena
 * resultados (AUC 0,535) y presentarla como ranking sería volver al problema
 * de origen. Están por hora de emisión, y los hechos al lado.
 */

interface Aviso { clave: string; nivel: "verde" | "ambar" | "info"; texto: string }
interface Motor {
  veredicto: string; familia: string | null; estado: string | null;
  razones: string[]; faltantes: string[];
  ancla_direccion: string | null; ancla_tendencia: string | null;
}
interface Oportunidad {
  symbol: string; ts_open: number | null; edad_min: number | null;
  precio: number | null; display_state: string | null;
  plan: {
    entry: number | null; take_profit: number | null; stop_loss: number | null;
    reward_neto_pct: number | null; risk_reward: number | null;
    soporte: number | null; resistencia: number | null;
    tp_bloqueado: boolean | null; sl_basis: string | null;
  };
  identidad: {
    plan_id?: number; episode_id?: number; ordinal?: number;
    planes_del_episodio?: number; avisado?: boolean; es_primera?: boolean | null;
  };
  motores: Record<string, Motor>;
  avisos: Aviso[];
}
interface Respuesta { n: number; oportunidades: Oportunidad[]; nota: string }

export default function Oportunidades({ onSelect }: { onSelect: (s: string) => void }) {
  const contrato = useContratoLectura();
  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [soloAvisadas, setSoloAvisadas] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let vivo = true;
    const cargar = () => {
      fetch(`/api/oportunidades?solo_avisadas=${soloAvisadas}`)
        .then(r => { if (!r.ok) throw new Error("oportunidades"); return r.json(); })
        .then(d => { if (vivo) { setDatos(d); setError(false); } })
        .catch(() => { if (vivo) setError(true); });
    };
    cargar();
    const t = setInterval(cargar, 20_000);
    return () => { vivo = false; clearInterval(t); };
  }, [soloAvisadas]);

  if (error) return <p className="muted">No se pudieron cargar las oportunidades.</p>;
  if (!datos) return <p className="muted">Cargando…</p>;

  return (
    <section className="oportunidades">
      <header className="oportunidades-head">
        <div>
          <h2>Oportunidades vivas</h2>
          <p className="muted">
            Con una posición a la vez se toman unas dos al día. Aquí está lo que
            hace falta para elegir cuál. Tu objetivo: {contrato.objetivo_operador.etiqueta}
            {" "}— el precio debe subir {contrato.objetivo_operador_bruto.etiqueta}.
          </p>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={soloAvisadas}
                 onChange={e => setSoloAvisadas(e.target.checked)} />
          Solo las que llegaron a Telegram
        </label>
      </header>

      {datos.n === 0 && <p className="muted">Ninguna viva ahora mismo.</p>}

      <div className="oportunidades-lista">
        {datos.oportunidades.map(o => {
          const p = o.plan;
          const cont = o.motores["continuacion"];
          const caida = o.motores["caida"];
          const corto = p.reward_neto_pct != null
            && p.reward_neto_pct < contrato.objetivo_operador.pct;
          return (
            <article key={o.symbol} className="oportunidad"
                     onClick={() => onSelect(o.symbol)}>
              <header>
                <strong>{o.symbol}</strong>
                {o.identidad.es_primera === true
                  ? <span className="tag verde">1.ª del episodio</span>
                  : o.identidad.ordinal != null
                    ? <span className="tag info">n.º {o.identidad.ordinal} del episodio</span>
                    : null}
                {o.identidad.avisado && <span className="tag info">Telegram</span>}
                {o.edad_min != null && <span className="muted">hace {o.edad_min.toFixed(0)} min</span>}
              </header>

              <div className="oportunidad-plan">
                <span>entrada <strong>{price(p.entry)}</strong></span>
                <span>TP <strong>{price(p.take_profit)}</strong></span>
                <span>SL <strong>{price(p.stop_loss)}</strong></span>
                <span className={corto ? "warning" : undefined}>
                  deja <strong>{percent(p.reward_neto_pct)} neto</strong>
                </span>
                {p.risk_reward != null && <span>R:R <strong>{p.risk_reward}</strong></span>}
              </div>

              <div className="oportunidad-motores">
                {cont && (
                  <span title={(cont.razones || []).join(" · ")}>
                    continuación: <strong>{cont.veredicto}</strong>
                    {cont.familia ? ` · ${cont.familia}` : ""}
                  </span>
                )}
                {caida && caida.estado && caida.estado !== "SIN_CAIDA" && (
                  <span title={(caida.razones || []).join(" · ")}>
                    caída: <strong>{caida.estado}</strong>
                  </span>
                )}
              </div>

              <ul className="oportunidad-avisos">
                {o.avisos.map(a => (
                  <li key={a.clave} className={a.nivel}>{a.texto}</li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>

      <p className="muted nota">{datos.nota}</p>
    </section>
  );
}
