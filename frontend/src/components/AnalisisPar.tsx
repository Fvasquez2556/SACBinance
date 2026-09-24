import { useCallback, useState } from "react";
import type { AnalisisPar as Analisis, LecturaTF } from "../types";
import { percent, price } from "../domain/reading";
import {
  avisosPlan,
  DIRECCION_LABEL,
  esRuptura,
  estadoTF,
  horizonteApretado,
  motivoSinPlan,
  normalizarSymbol,
  rangoEntrada,
  textoConfluencia,
  textoHorizonte,
  textoTasa,
  tituloResumen,
} from "../domain/analysis";

function MarcoTF({ lectura }: { lectura: LecturaTF }) {
  const plan = lectura.plan;
  const sinPlan = motivoSinPlan(lectura);
  const clase = `tf-card tf-${lectura.direccion.toLowerCase()}`;

  return (
    <article className={clase}>
      <header>
        <h4>{lectura.tf}</h4>
        <span className={`tf-badge tf-badge-${lectura.direccion.toLowerCase()}`}>
          {DIRECCION_LABEL[lectura.direccion]}
        </span>
      </header>
      <p className="tf-estado">{estadoTF(lectura)}</p>
      <p className="muted tf-razon">{lectura.razon}</p>

      {esRuptura(lectura.direccion) && <p className="muted tf-razon">
        Volumen y velas sostenidas se muestran como descripción: medidos sobre 19.565 rupturas
        de este sistema, ninguno de los dos anticipa si el movimiento continúa (AUC 0,48–0,51).
      </p>}

      {esRuptura(lectura.direccion) && lectura.estadistica && <div className="tf-tasa">
        <small className="muted">En rupturas anteriores de {lectura.tf} en esta dirección</small>
        <strong>{textoTasa(lectura.estadistica.marco, lectura.estadistica.ventana_dias)}</strong>
        {textoHorizonte(lectura.estadistica) && <small className={horizonteApretado(lectura.estadistica) ? "warning" : "muted"}>
          {textoHorizonte(lectura.estadistica)}</small>}
      </div>}

      {esRuptura(lectura.direccion) && <dl className="tf-meta">
        <div><dt>Nivel roto</dt><dd>{price(lectura.nivel_roto)}{lectura.toques_nivel ? ` · ${lectura.toques_nivel} toques` : ""}</dd></div>
        <div><dt>Velas sostenidas</dt><dd>{lectura.velas_desde_ruptura ?? "—"}</dd></div>
        <div><dt>Volumen de la ruptura</dt><dd>{lectura.vol_ratio != null
          ? `${lectura.vol_ratio}× la media de 20 velas` : "sin dato"}</dd></div>
        <div><dt>Distancia al nivel</dt><dd>{percent(lectura.distancia_nivel_pct)}</dd></div>
        <div><dt>Tendencia del marco</dt><dd>{lectura.tendencia}</dd></div>
      </dl>}

      {plan?.valid && <>
        <div className="plan-grid">
          <div><small>Rango de entrada</small><strong>{rangoEntrada(plan)}</strong>
            {plan.rellena_en_retest && <small>hasta {percent(plan.mejora_max_pct)} mejor que a mercado</small>}</div>
          <div><small>Stop loss</small><strong>{price(plan.stop_loss)}</strong><small>{percent(plan.risk_pct == null ? null : -plan.risk_pct)}</small></div>
          <div><small>Objetivo TP</small><strong>{price(plan.take_profit)}</strong><small>{percent(plan.reward_pct)} bruto</small></div>
        </div>
        <dl className="tf-meta tf-estructura">
          <div><dt>Soporte que sostiene el SL</dt>
            <dd>{plan.nivel_apoyo ? `${price(plan.nivel_apoyo)}${plan.toques_apoyo ? ` · ${plan.toques_apoyo} toques` : ""}` : "—"}
              {plan.sl_basis ? <small className="muted"> · {plan.sl_basis}</small> : null}</dd></div>
          <div><dt>{plan.tp_bloqueado ? "Techo que debe romper antes del TP" : "Techo más cercano"}</dt>
            <dd className={plan.tp_bloqueado ? "warning" : ""}>
              {plan.nivel_estorbo ? price(plan.nivel_estorbo) : "sin nivel entre la entrada y el TP"}</dd></div>
        </dl>
        <p className="muted tf-plan-nota">
          Riesgo y beneficio medidos entrando a mercado en {price(plan.entrada_ref)}, no en el mejor
          extremo del rango. R:R {plan.risk_reward ?? "—"} · neto tras costes {percent(plan.reward_neto_pct)} · {plan.sl_basis}.
        </p>
        {avisosPlan(plan, lectura.estadistica).map(aviso => <p className="warning tf-aviso" key={aviso}>{aviso}</p>)}
      </>}

      {sinPlan && <p className="muted tf-plan-nota">Sin plan en este marco: {sinPlan}</p>}
    </article>
  );
}

export default function AnalisisPar() {
  const [open, setOpen] = useState(false);
  const [entrada, setEntrada] = useState("");
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const consultar = useCallback(async (raw: string) => {
    const symbol = normalizarSymbol(raw);
    if (!symbol) {
      setError("Escribe un par, por ejemplo BTC o BTCUSDT.");
      setAnalisis(null);
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const r = await fetch(`/api/pair/${encodeURIComponent(symbol)}/analisis`);
      if (r.status === 404) throw new Error(`${symbol} no existe en Binance o no devolvió velas.`);
      if (!r.ok) throw new Error("No se pudo construir el análisis de este par.");
      setAnalisis(await r.json());
    } catch (e) {
      setAnalisis(null);
      setError(e instanceof Error ? e.message : "No se pudo consultar el par.");
    } finally {
      setCargando(false);
    }
  }, []);

  return <section className="analisis-par">
    <button className="section-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
      {open ? "▾" : "▸"} Analizar un par por marcos (5m · 15m · 1h · 4h)
    </button>
    {open && <div className="analisis-content">
      <p className="muted">
        Lectura de la estructura de cada marco: qué nivel se rompió, hacia dónde, y qué rango de
        entrada, stop y objetivo salen de esa estructura. Describe lo que ya ocurrió en el gráfico;
        no es un pronóstico ni una orden, y no tiene medición propia todavía.
      </p>
      <form className="analisis-form" onSubmit={e => { e.preventDefault(); consultar(entrada); }}>
        <label>Par
          <input
            placeholder="BTC, ETHUSDT, SOL…"
            value={entrada}
            onChange={e => setEntrada(e.target.value)}
            aria-label="Par a analizar"
          />
        </label>
        <button type="submit" disabled={cargando || !entrada.trim()}>
          {cargando ? "Analizando…" : "Analizar"}
        </button>
      </form>

      {error && <p className="warning" role="status">{error}</p>}

      {analisis && <div className="analisis-resultado">
        <header className="analisis-resumen">
          <div>
            <h3>{analisis.symbol}</h3>
            <small className="muted">Precio {price(analisis.price)} · {new Date(analisis.ts).toLocaleTimeString("es-GT")}
              {analisis.fuente === "consulta_directa" ? " · velas bajadas al consultar" : " · par en seguimiento"}</small>
          </div>
          <strong className={analisis.resumen.en_conflicto ? "warning" : ""}>{tituloResumen(analisis)}</strong>
        </header>
        <p className="muted">{analisis.resumen.lectura}</p>
        {textoConfluencia(analisis) && <p className="analisis-confluencia">{textoConfluencia(analisis)}</p>}

        <div className="tf-grid">
          {analisis.timeframes.map(lectura => <MarcoTF key={lectura.tf} lectura={lectura} />)}
        </div>

        <ul className="analisis-avisos">
          {analisis.advertencias.map(aviso => <li key={aviso}>{aviso}</li>)}
        </ul>
      </div>}
    </div>}
  </section>;
}
