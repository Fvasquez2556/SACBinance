import { useState } from "react";
import { percent, price } from "../domain/reading";

const number = (text: string) => text.trim() ? Number(text.replace(",", ".")) : NaN;

export default function Calculadora() {
  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState("");
  const [tp, setTp] = useState("3.2");
  const [sl, setSl] = useState("1.2");
  const [leverage, setLeverage] = useState("1");
  const p = number(entry), target = number(tp), stop = number(sl), lev = number(leverage);
  const valid = [p, target, stop, lev].every(Number.isFinite) && p > 0 && target > 0 && stop > 0 && stop < 100 && lev >= 1;

  return <section className="calculator">
    <button className="section-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Calculadora de niveles hipotéticos</button>
    {open && <div className="calculator-content">
      <p className="muted">Introduce una entrada para calcular niveles con porcentajes manuales. Esta simulación no usa el stop estructural de una señal ni estima su probabilidad de éxito.</p>
      <div className="calculator-inputs">
        {([
          ["Precio de entrada", entry, setEntry], ["Objetivo TP (%)", tp, setTp],
          ["Stop SL (%)", sl, setSl], ["Apalancamiento (×)", leverage, setLeverage],
        ] as const).map(([label, value, set]) => <label key={label}>{label}<input inputMode="decimal" value={value} onChange={e => set(e.target.value)} /></label>)}
      </div>
      {entry && !valid && <p className="warning" role="status">Usa números válidos: entrada y TP positivos, SL entre 0 y 100%, y apalancamiento de al menos 1.</p>}
      {valid && <div className="plan-grid">
        <div><small>Entrada hipotética</small><strong>{price(p)}</strong></div>
        <div><small>Objetivo TP</small><strong>{price(p * (1 + target / 100))}</strong><small>{percent(target)} bruto</small></div>
        <div><small>Stop loss manual</small><strong>{price(p * (1 - stop / 100))}</strong><small>{percent(-stop)} bruto</small></div>
      </div>}
      {valid && lev > 1 && <p className="muted">Sobre el margen inicial a ×{lev}: TP {percent(target * lev)} y SL {percent(-stop * lev)}, estimación aritmética antes de costes. No modela liquidación ni ejecución.</p>}
      <p className="muted">Los porcentajes son movimientos del precio, antes de comisiones y deslizamiento. Un objetivo de +3.2% bruto no equivale a +3.2% neto.</p>
    </div>}
  </section>;
}
