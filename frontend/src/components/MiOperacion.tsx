import { useCallback, useEffect, useState } from "react";
import type { Operacion, PairState, TipoOperacion } from "../types";
import { horaLocal, percent, price } from "../domain/reading";
import { ETIQUETA_TIPO, desvioDeEntrada, distanciaANiveles, motivoParaNoAbrir, noRealizadoPct, textoDesvio } from "../domain/operaciones";

/**
 * «Tomé esta entrada»: el único sitio desde el que nace una operación.
 *
 * Ni la emisión de la alerta, ni el envío a Telegram, ni que el precio toque la
 * entrada registran nada. Si el diario se llenara solo dejaría de responder a
 * la pregunta para la que existe — qué tomaste tú.
 */
export default function MiOperacion({ pair, planId, entradaSugerida, objetivo, stop }:
  { pair: PairState; planId: number | null; entradaSugerida: number | null;
    objetivo: number | null; stop: number | null }) {
  const [abiertas, setAbiertas] = useState<Operacion[]>([]);
  const [form, setForm] = useState(false);
  const [precioTxt, setPrecio] = useState("");
  const [cantidadTxt, setCantidad] = useState("");
  const [tipo, setTipo] = useState<TipoOperacion>("SIMULADA");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(() => {
    fetch(`/api/operaciones?estado=ABIERTA&symbol=${encodeURIComponent(pair.symbol)}`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error("operaciones")))
      .then(d => setAbiertas(d.operaciones ?? []))
      .catch(() => setAbiertas([]));
  }, [pair.symbol]);

  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => { setPrecio(entradaSugerida ? String(entradaSugerida) : ""); }, [entradaSugerida, pair.symbol]);

  // El desvio se calcula mientras escribes, no despues de registrar: entrar
  // 1,4% mas arriba convierte un 2:1 en un 0,66:1 sin que nada lo diga.
  const desvio = desvioDeEntrada(Number(precioTxt), { entry: entradaSugerida, objetivo, stop });

  const abrir = async () => {
    const motivo = motivoParaNoAbrir(precioTxt, cantidadTxt);
    if (motivo) { setError(motivo); return; }
    setEnviando(true); setError(null);
    try {
      const r = await fetch("/api/operaciones", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: pair.symbol, precio_entrada: Number(precioTxt), tipo, plan_id: planId,
          cantidad: cantidadTxt.trim() ? Number(cantidadTxt) : null,
          // Sin plan_id —una alerta rehidratada tras un reinicio— los niveles
          // viajan igual: la operacion nunca se queda sin objetivo ni stop.
          objetivo, stop,
        }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "No se pudo registrar");
      setForm(false); setCantidad(""); cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar");
    } finally { setEnviando(false); }
  };

  const cerrar = async (op: Operacion) => {
    setEnviando(true); setError(null);
    try {
      const r = await fetch(`/api/operaciones/${op.operacion_id}/cierre`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ precio: pair.price, motivo: "MANUAL" }),
      });
      if (!r.ok) throw new Error("No se pudo cerrar");
      cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cerrar");
    } finally { setEnviando(false); }
  };

  return <section className="mi-operacion">
    <h3>Mi operación</h3>
    {abiertas.length === 0 && !form && <>
      <p className="muted">No has registrado ninguna entrada en este par. Registrarla no ejecuta nada: solo deja constancia de qué tomaste y con qué niveles.</p>
      <button type="button" onClick={()=>setForm(true)}>Tomé esta entrada</button>
    </>}

    {form && <div className="operacion-form">
      <label>Precio de entrada
        <input inputMode="decimal" value={precioTxt} onChange={e=>setPrecio(e.target.value)}
               placeholder={entradaSugerida ? String(entradaSugerida) : "0.00"} />
      </label>
      <label>Cantidad <small className="muted">(opcional)</small>
        <input inputMode="decimal" value={cantidadTxt} onChange={e=>setCantidad(e.target.value)}
               placeholder="sin cantidad, solo se mide en %" />
      </label>
      <fieldset>
        <legend>Qué estás registrando</legend>
        {(["SIMULADA", "DECLARADA"] as TipoOperacion[]).map(t =>
          <label key={t} className="radio">
            <input type="radio" name="tipo-operacion" checked={tipo===t} onChange={()=>setTipo(t)} />
            {ETIQUETA_TIPO[t]}
          </label>)}
      </fieldset>
      {textoDesvio(desvio) && <p className={desvio?.grave ? "warning" : "muted"} role="status">
        {textoDesvio(desvio)}</p>}
      <p className="muted">El simulado no cuenta como dinero y nunca se suma con el declarado.</p>
      {error && <p className="warning" role="alert">{error}</p>}
      <div className="acciones">
        <button type="button" onClick={abrir} disabled={enviando}>Registrar</button>
        <button type="button" className="secundario" onClick={()=>{setForm(false); setError(null);}}>Cancelar</button>
      </div>
    </div>}

    {abiertas.map(op => {
      const vivo = noRealizadoPct(pair.price, op.precio_entrada, op.coste_pct);
      const d = distanciaANiveles(op, pair.price);
      return <div className="operacion-viva" key={op.operacion_id}>
        <div className="detail-row"><span className="muted">{ETIQUETA_TIPO[op.tipo]}</span>
          <span>desde {horaLocal(op.ts_apertura)}</span></div>
        <div className="detail-row"><span className="muted">Entrada registrada</span>
          <span>{price(op.precio_entrada)}{op.cantidad ? ` · ${op.cantidad}` : ""}</span></div>
        <div className="detail-row"><span className="muted">No realizado</span>
          <span className={(vivo ?? 0) >= 0 ? "positive" : "negative"}>{percent(vivo)}</span></div>
        {op.objetivo && <div className="detail-row"><span className="muted">Le falta al objetivo</span>
          <span>{percent(d.objetivo)} · {price(op.objetivo)}</span></div>}
        {op.stop && <div className="detail-row"><span className="muted">Distancia al stop</span>
          <span>{percent(d.stop)} · {price(op.stop)}</span></div>}
        {(() => {
          const d = desvioDeEntrada(op.precio_entrada, { entry: entradaSugerida, objetivo: op.objetivo, stop: op.stop });
          return textoDesvio(d) ? <p className={d?.grave ? "warning" : "muted"}>{textoDesvio(d)}</p> : null;
        })()}
        <p className="muted">Niveles copiados al registrarla. Una alerta posterior de este par no los cambia ni altera su resultado.</p>
        {error && <p className="warning" role="alert">{error}</p>}
        <button type="button" onClick={()=>cerrar(op)} disabled={enviando}>
          Cerrar al precio actual ({price(pair.price)})
        </button>
      </div>;
    })}
    {abiertas.length > 0 && !form &&
      <button type="button" className="secundario" onClick={()=>setForm(true)}>Registrar otra entrada</button>}
  </section>;
}
