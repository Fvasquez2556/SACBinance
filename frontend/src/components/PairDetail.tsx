import { useEffect, useState } from "react";
import type { PairState, ReferenciasPar, StateEvent } from "../types";
import { cambioDesdeEntrada, desfaseDelta, displayPlan, horaLocal, inicioDelDiaLocal, nivelesDelPlan, percent, price, profiles, textoSoporte, textoTecho } from "../domain/reading";
import { useContratoLectura } from "../domain/contratoContext";
import MiOperacion from "./MiOperacion";
import ProbabilityContext from "./ProbabilityContext";
import StateHistory from "./StateHistory";

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div className="detail-row"><span className="muted">{label}</span><span>{value ?? "—"}</span></div>;
}
export default function PairDetail({ pair, onClose }: { pair: PairState; onClose: () => void }) {
  const contrato = useContratoLectura();
  const [history, setHistory] = useState<StateEvent[]>([]);
  const [failed, setFailed] = useState(false);
  const [refs, setRefs] = useState<ReferenciasPar | null>(null);
  const [abierto, setAbierto] = useState(false);
  const plan = displayPlan(pair);
  const cambio = cambioDesdeEntrada(pair.price, plan?.entry);
  const desfase = desfaseDelta(pair.price, pair.alerta?.precio_actual);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/pair/${encodeURIComponent(pair.symbol)}/history`, { signal: controller.signal })
      .then(r=>{ if(!r.ok) throw new Error("history"); return r.json(); })
      .then(d=>setHistory((d.history ?? []).map((e: StateEvent & { ts_ms?: number }) => ({ ...e, ts: e.ts ?? e.ts_ms })).filter((e: StateEvent) => Number.isFinite(e.ts))))
      .catch(()=>{ if (!controller.signal.aborted) setFailed(true); });
    return ()=>controller.abort();
  }, [pair.symbol]);
  useEffect(() => {
    const controller = new AbortController();
    const desde = inicioDelDiaLocal();
    fetch(`/api/pair/${encodeURIComponent(pair.symbol)}/referencias?desde_ms=${desde}`, { signal: controller.signal })
      .then(r=>{ if(!r.ok) throw new Error("referencias"); return r.json(); })
      .then(setRefs)
      .catch(()=>{ if (!controller.signal.aborted) setRefs(null); });
    return ()=>controller.abort();
  }, [pair.symbol]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return ()=>window.removeEventListener("keydown", close);
  }, [onClose]);

  return <aside className="pair-detail" aria-label={`Detalle actual de ${pair.symbol}`}>
    <header><div><small className="muted">Detalle actual</small><h2>{pair.symbol}</h2></div><button autoFocus onClick={onClose} aria-label="Cerrar detalle">✕</button></header>
    <div className="detail-content">
      <div className="profile-list">{profiles(pair).map(p=><span className="profile-label" key={p}>{p}</span>)}</div>
      <Row label="Precio actual" value={price(pair.price)} />
      {plan && <Row label={`Cambio desde la entrada ${plan.frozen ? "del plan" : "propuesta"}`} value={percent(cambio)} />}
      {plan ? <section>
        <h3>{plan.source}</h3><p className="muted">{plan.frozen ? "Entrada y niveles fijados al emitir la alerta. No acreditan una orden ejecutada." : "Niveles calculados ahora. Pueden variar al cambiar el mercado."}</p>
        <div className="plan-grid"><div><small>Entrada</small>
          <button type="button" className="valor-explicable" aria-expanded={abierto}
                  onClick={()=>setAbierto(v=>!v)}
                  title="Ver cuándo se fijó esta entrada">{price(plan.entry)}</button></div><div><small>Objetivo TP</small><strong>{price(plan.tp)}</strong><small>{percent(plan.tpPct)} bruto</small></div><div><small>Stop loss</small><strong>{price(plan.sl)}</strong><small>{percent(plan.slPct)}</small></div></div>
        {abierto && <div className="valor-detalle">
          {plan.frozen && pair.alerta ? <>
            <Row label="Entrada fijada a las" value={`${horaLocal(pair.alerta.ts_emision)} · hace ${Math.round(pair.alerta.edad_min)} min`} />
            {pair.alerta.senal_n > 0 && <Row label="Señal del par en esta ventana" value={`nº ${pair.alerta.senal_n}`} />}
            <Row label="Precio del último cierre de 1m" value={price(pair.alerta.precio_actual)} />
            <Row label="Cambio con ese cierre" value={percent(pair.alerta.delta_pct)} />
            <p className="muted">El precio de arriba es el del minuto en curso y este es el del último minuto cerrado{desfase != null ? `: ${percent(desfase)} de diferencia` : ""}. No es un desfase del dato, son dos instantes distintos.</p>
          </> : <p className="muted">Niveles calculados con el último cierre de 1 minuto; se recalculan al cerrar cada vela.</p>}
        </div>}
        {refs?.primera_del_dia && <Row
          label="Primera señal del día"
          value={`${horaLocal(refs.primera_del_dia.ts_ms)} · entrada ${price(refs.primera_del_dia.entry)} · ${percent(cambioDesdeEntrada(pair.price, refs.primera_del_dia.entry))} desde entonces`} />}
        {refs && <Row label="Alertas del día en este par"
          value={`${refs.alertas_del_dia}${refs.enviadas_del_dia ? ` · ${refs.enviadas_del_dia} a Telegram` : " · ninguna a Telegram"}`} />}
        {refs?.episodio?.primer_plan && <Row label="Primer plan del episodio"
          value={`${horaLocal(refs.episodio.primer_plan.ts_creado)} · entrada ${price(refs.episodio.primer_plan.entry)} · ${refs.episodio.n_planes} plan(es), episodio ${refs.episodio.fase.toLowerCase()}`} />}
        {(() => {
          const niveles = nivelesDelPlan(plan.entry, pair.alerta);
          if (!niveles) return null;
          return <>
            {textoSoporte(niveles) && <Row label="Soporte que sostiene el SL" value={textoSoporte(niveles)} />}
            {textoTecho(niveles) && <Row
              label={niveles.techoEstorba ? "Techo que debe romper antes del TP" : "Techo más cercano"}
              value={textoTecho(niveles)} />}
            {niveles.techoEstorba && <p className="muted">Ese techo está entre la entrada y el TP: el precio tiene que atravesarlo para cobrar el objetivo.</p>}
          </>;
        })()}
        {plan.tpPct != null && plan.tpPct < contrato.objetivo_operador_bruto.pct && <p className="warning">El TP de este plan sube {percent(plan.tpPct)} bruto: por debajo de los {contrato.objetivo_operador_bruto.etiqueta} que hacen falta para cobrar tu objetivo de {contrato.objetivo_operador.etiqueta}.</p>}
        <p className="muted">{plan.netPct == null ? "Neto del TP no registrado en este plan. El rendimiento bruto no descuenta costes." : `Si alcanza el TP: ${percent(plan.netPct)} neto estimado, según los costes configurados.`}</p>
        {!plan.frozen && pair.trade_levels?.tp_blocked_by_resistance && <p className="warning">Resistencia en {price(pair.trade_levels.nearest_resistance)} antes del TP.</p>}
        {pair.alerta != null && pair.alerta.entrada_alt > 0 && <details><summary>Entrada alternativa en retroceso</summary><p>Referencia hipotética: {price(pair.alerta.entrada_alt)}. El objetivo original sigue en {price(pair.alerta.meta)}. No acredita que se haya ejecutado una entrada.</p></details>}
      </section> : <p className="muted">No hay un plan válido en este momento.</p>}
      <MiOperacion pair={pair} planId={pair.alerta?.plan_id ?? null}
                   entradaSugerida={plan?.entry ?? null}
                   objetivo={plan?.tp ?? null} stop={plan?.sl ?? null} />
      <ProbabilityContext alerta={pair.alerta?.entry ? pair.alerta : undefined} />
      {pair.alerta?.entry && <section>
        <h3>Recorrido desde la emisión</h3>
        <Row label="Máximo observado (MFE)" value={percent(pair.alerta.mfe_pct)} />
        <Row label="Mínimo observado (MAE)" value={percent(pair.alerta.mae_pct)} />
        <p className="muted">El seguimiento continúa después del TP o SL. Consulta el historial para ver el orden observado de los cruces y su cobertura.</p>
      </section>}
      <details className="technical-details"><summary>Indicadores y contexto técnico</summary>
        <Row label="Puntuación técnica (no probabilidad)" value={`${pair.score} / 100`} />
        <Row label="Estado / FSM" value={`${pair.display_state} / ${pair.fsm_state}`} />
        <Row label="Nivel de alerta" value={pair.tier} />
        <Row label="Régimen BTC" value={pair.btc_regime} />
        <Row label="Macro global" value={pair.macro_global} />
        <Row label="Multiplicador macro" value={`×${pair.macro_gate_mult}`} />
        <Row label="Retorno de 1m" value={percent(pair.ret_1m_pct,3)} />
        <Row label="Z-rise / Z-drop" value={`${pair.z_rise?.toFixed(2)} / ${pair.z_drop?.toFixed(2)}`} />
        <Row label="Velocidad" value={pair.velocity?.toFixed(2)} />
        <Row label="Volumen relativo" value={pair.vol_ratio?.toFixed(2)} />
        <Row label="Drawdown previo" value={percent(pair.drawdown_pct)} />
        <Row label="Sigma" value={percent(pair.sigma_pct,3)} />
        <Row label="RSI5" value={pair.rsi5} />
        <Row label="MACD ascendente" value={pair.macd_rising == null ? "—" : pair.macd_rising ? "Sí" : "No"} />
        <Row label="Tendencia de indicadores" value={pair.trend_up == null ? "—" : pair.trend_up ? "Alcista" : "No alcista"} />
        <Row label="Compras / operaciones en 30s" value={`${(pair.buy_ratio_30s*100).toFixed(1)}% / ${pair.flow_trades_30s}`} />
        <Row label="Posición en rango 15m" value={pair.pos_en_rango == null ? "—" : `${Math.round(pair.pos_en_rango*100)}%`} />
        {pair.is_fakeout && <p className="warning">Ruptura fallida reciente: puntuación penalizada.</p>}
        {pair.impulso?.valid && <p className="muted">{pair.impulso.reason}</p>}
        {pair.grind?.detected && <Row label="Pendiente sostenida por hora" value={percent(pair.grind.slope_pct_h)} />}
        {pair.macro_trends && Object.entries(pair.macro_trends).map(([tf,t])=><Row key={tf} label={`Tendencia ${tf}`} value={t} />)}
        {pair.consolidation?.consolidating && <>
          <Row label="ATR" value={percent(pair.consolidation.atr_pct)} />
          <Row label="Percentil de ATR" value={pair.consolidation.atr_percentile} />
          <Row label="Medias convergentes" value={pair.consolidation.ma_convergent ? "Sí" : "No"} />
          <Row label="Volumen decreciente" value={pair.consolidation.vol_declining ? "Sí" : "No"} />
        </>}
        {pair.sr_levels && <><h3>Soportes y resistencias actuales</h3>
          {pair.sr_levels.resistencias?.slice(0,3).map((r,i)=><Row key={`r${i}`} label={`Resistencia · ${r.toques} toques`} value={price(r.precio)} />)}
          {pair.sr_levels.soportes?.slice(0,3).map((r,i)=><Row key={`s${i}`} label={`Soporte · ${r.toques} toques`} value={price(r.precio)} />)}
          <p className="muted">{pair.sr_levels.lectura}</p>
        </>}
      </details>
      <details><summary>Cambios de estado · últimas 24h</summary>{failed ? <p role="status">No se pudo cargar el historial de estados.</p> : <StateHistory history={history} />}</details>
    </div>
  </aside>;
}
