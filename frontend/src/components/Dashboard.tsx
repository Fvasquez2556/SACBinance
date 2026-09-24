import { useEffect, useMemo, useState } from "react";
import type { DisplayState, PairState, Tier } from "../types";
import PairDetail from "./PairDetail";
import PairCard from "./PairCard";
import Calculadora from "./Calculadora";
import AnalisisPar from "./AnalisisPar";
import SignalStats from "./SignalStats";
import Historial from "./Historial";
import MisOperaciones from "./MisOperaciones";
import { classifySignalRoute, type SignalRoute } from "../domain/reading";
import { textoHito, textoObjetivo } from "../domain/contrato";
import { ContratoContext } from "../domain/contratoContext";
import { useContrato } from "../hooks/useContrato";
import Oportunidades from "./Oportunidades";
import Resultados from "./Resultados";
import "./Dashboard.css";

const INTERESTING: DisplayState[] = ["CAYENDO", "TOCÓ_FONDO", "CONSOLIDANDO", "SUBIENDO", "BREAKOUT_INCIPIENTE"];
const ROUTES: SignalRoute[] = ["RUPTURA_ALCISTA", "RUPTURA_BAJISTA", "SIN_RUTA"];
const ROUTE_TITLES: Record<SignalRoute, string> = {
  RUPTURA_ALCISTA: "Ruptura alcista continua",
  RUPTURA_BAJISTA: "Ruptura bajista corta",
  SIN_RUTA: "Sin ruptura confirmada",
};
interface Props {
  pairs: Map<string, PairState>; connected: boolean; lastTs: number;
  notifPermission: string; onRequestNotif: () => void;
}
export default function Dashboard({ pairs, connected, lastTs, notifPermission, onRequestNotif }: Props) {
  const { contrato } = useContrato();
  const [vista, setVista] = useState<"tablero" | "oportunidades" | "operacion" | "resultados">("tablero");
  const [stateFilter, setStateFilter] = useState<DisplayState | "TODOS">("TODOS");
  const [minScore, setMinScore] = useState(60);
  const [tierFilter, setTierFilter] = useState<Tier | "TODOS">("TODOS");
  const [profileFilter, setProfileFilter] = useState("TODOS");
  const [routeFilter, setRouteFilter] = useState<SignalRoute | "TODOS">("TODOS");
  const [search, setSearch] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [loadedPair, setLoadedPair] = useState<PairState | null>(null);
  const [detailError, setDetailError] = useState(false);
  const inMap = selectedSymbol ? pairs.has(selectedSymbol) : false;
  useEffect(() => {
    if (!selectedSymbol || inMap) return;
    const controller = new AbortController();
    fetch(`/api/pair/${encodeURIComponent(selectedSymbol)}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error("pair"); return r.json(); })
      .then(setLoadedPair)
      .catch(() => { if (!controller.signal.aborted) setDetailError(true); });
    return () => controller.abort();
  }, [selectedSymbol, inMap]);
  const select = (symbol: string) => { setDetailError(false); setLoadedPair(null); setSelectedSymbol(symbol); };
  const continuationPercentiles = useMemo(() => {
    const ranked = Array.from(pairs.values())
      .filter(pair => Number.isFinite(pair.rango_1h_pct))
      .sort((left, right) => (right.rango_1h_pct ?? -Infinity) - (left.rango_1h_pct ?? -Infinity));
    const total = ranked.length;
    const values = new Map<string, number>();
    ranked.forEach((pair, index) => values.set(
      pair.symbol,
      Math.round(((total - index) / Math.max(total, 1)) * 100),
    ));
    return values;
  }, [pairs]);
  const filtered = useMemo(() => Array.from(pairs.values()).filter(p => {
    if (!p.symbol.includes(search.trim().toUpperCase())) return false;
    if (stateFilter === "TODOS" ? !(INTERESTING.includes(p.display_state) || p.fading || p.alerta?.entry || p.grind?.detected) : p.display_state !== stateFilter) return false;
    if (p.score < minScore && !p.fading) return false;
    if (tierFilter !== "TODOS" && p.tier !== tierFilter) return false;
    if (profileFilter === "REBOTE" && !(p.retroceso?.detectado || p.base_rebote?.detected)) return false;
    if (profileFilter === "TENDENCIA" && !p.grind?.detected) return false;
    if (routeFilter !== "TODOS" && classifySignalRoute(p).route !== routeFilter) return false;
    return true;
  }).sort((left, right) => (
    (continuationPercentiles.get(right.symbol) ?? -1)
    - (continuationPercentiles.get(left.symbol) ?? -1)
    || right.score - left.score
  )), [pairs, search, stateFilter, minScore, tierFilter, profileFilter, routeFilter, continuationPercentiles]);
  const grouped = useMemo(() => ROUTES.map(route => ({
    route,
    pairs: filtered.filter(pair => classifySignalRoute(pair).route === route),
  })).filter(group => group.pairs.length > 0), [filtered]);
  const selectedPair = selectedSymbol ? pairs.get(selectedSymbol) ?? (loadedPair?.symbol === selectedSymbol ? loadedPair : null) : null;

  return <main className="dashboard">
    <ContratoContext.Provider value={contrato}>
    <header className="dashboard-header">
      <div><h1>SACBinance</h1><p className="muted">Señales y seguimiento de pares USDT</p></div>
      <div className="connection" role="status"><span className={connected ? "connected" : "disconnected"} />{connected ? "Conectado" : "Reconectando"}
        <small className="muted">{lastTs ? `Último dato: ${new Date(lastTs).toLocaleTimeString("es-GT")}` : "Esperando datos"}</small>
      </div>
      {notifPermission !== "granted" && notifPermission !== "unsupported" && <button onClick={onRequestNotif}>Activar notificaciones</button>}
      {notifPermission === "granted" && <span className="muted">Notificaciones activadas</span>}
    </header>
    <nav className="vistas">
      <button className={vista === "oportunidades" ? "activa" : undefined}
              onClick={() => setVista("oportunidades")}>Oportunidades</button>
      <button className={vista === "tablero" ? "activa" : undefined}
              onClick={() => setVista("tablero")}>Mercado</button>
      <button className={vista === "operacion" ? "activa" : undefined}
              onClick={() => setVista("operacion")}>Mi operación</button>
      <button className={vista === "resultados" ? "activa" : undefined}
              onClick={() => setVista("resultados")}>Resultados</button>
    </nav>
    {vista === "oportunidades" && <Oportunidades onSelect={select} />}
    {vista === "operacion" && <MisOperaciones expandido />}
    {vista === "resultados" && <Resultados />}
    {vista === "tablero" && <>
    <div className="reading-note"><strong>Cómo leer las señales</strong><span>La puntuación y las categorías describen lo observado. Tocar {textoHito(contrato)} puede ocurrir después del stop.</span><span>Tu objetivo: {textoObjetivo(contrato)}.</span><span>Probabilidad de TP antes del SL por horizonte: <strong>todavía no disponible.</strong></span></div>
    <SignalStats />
    <div className="dashboard-filters">
      <label>Par<input placeholder="Buscar par" value={search} onChange={e=>setSearch(e.target.value)} /></label>
      <label>Ruptura<select value={routeFilter} onChange={e=>setRouteFilter(e.target.value as SignalRoute | "TODOS")}><option value="TODOS">Todas las lecturas</option><option value="RUPTURA_ALCISTA">Alcista continua</option><option value="RUPTURA_BAJISTA">Bajista corta</option><option value="SIN_RUTA">Sin ruptura</option></select></label>
      <label>Oportunidad<select value={profileFilter} onChange={e=>setProfileFilter(e.target.value)}><option value="TODOS">Todos los perfiles</option><option value="REBOTE">Caída y rebote</option><option value="TENDENCIA">Tendencia sostenida</option></select></label>
      <label>Estado<select value={stateFilter} onChange={e=>setStateFilter(e.target.value as DisplayState | "TODOS")}><option value="TODOS">Estados de interés</option><option value="CAYENDO">Cayendo</option><option value="TOCÓ_FONDO">Mínimo local</option><option value="CONSOLIDANDO">Consolidando</option><option value="SUBIENDO">Subiendo</option><option value="BREAKOUT_INCIPIENTE">Ruptura incipiente</option></select></label>
      <label>Nivel de alerta<select value={tierFilter} onChange={e=>setTierFilter(e.target.value as Tier | "TODOS")}>{["TODOS","VIGILANCIA","MODERADA","FUERTE","EXTRA-FUERTE"].map(t=><option value={t} key={t}>{t === "TODOS" ? "Todos los niveles" : t}</option>)}</select></label>
      <label>Puntuación mínima: {minScore}<input type="range" min={0} max={100} step={5} value={minScore} onChange={e=>setMinScore(Number(e.target.value))} /></label>
    </div>
    <div className="table-caption"><strong>{filtered.length} pares visibles</strong><span className="muted">de {pairs.size} recibidos · por dirección observada; dentro de cada grupo, mayor rango previo de 1h</span></div>
    {filtered.length ? <div className="route-groups" aria-label="Señales agrupadas por clasificación">
      {grouped.map(group => <section className={`route-group route-group-${group.route.toLowerCase()}`} key={group.route}>
        <header><h2>{ROUTE_TITLES[group.route]}</h2><span>{group.pairs.length}</span></header>
        <div className="signal-grid">
          {group.pairs.map(pair => <PairCard
            key={pair.symbol}
            pair={pair}
            selected={pair.symbol === selectedSymbol}
            continuationPercentile={continuationPercentiles.get(pair.symbol) ?? null}
            onClick={select}
          />)}
        </div>
      </section>)}
    </div> : <p className="empty-message">{connected ? "No hay pares que coincidan con estos filtros." : "Esperando conexión para recibir los pares."}</p>}
    {detailError && <p className="section-note warning" role="status">El estado actual de {selectedSymbol} ya no está disponible. Sus niveles históricos permanecen en el historial.</p>}
    <Historial onSelect={select} />
    <AnalisisPar />
    <Calculadora />
    </>}
    {selectedPair && <PairDetail key={selectedPair.symbol} pair={selectedPair} onClose={()=>setSelectedSymbol(null)} />}
    </ContratoContext.Provider>
  </main>;
}
