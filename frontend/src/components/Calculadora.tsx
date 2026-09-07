import { useState } from "react";

/**
 * Calculadora de niveles: metes el precio al que compraste y salen el TP, el
 * SL y el nivel de retroceso.
 *
 * Los porcentajes NO son los que el sistema calcula por par —esos salen del
 * ATR y de la estructura de cada moneda— sino los de referencia que Felix
 * usa: +3.2% de objetivo y -1.2% de stop. Son editables por si quiere probar
 * otros.
 *
 * Aviso medido que conviene tener a la vista: un stop del 1.2% quedo por
 * debajo del |MAE| mediano de las senales (1.83%), y saltaba antes de llegar
 * al objetivo en el 33% de las que SI lo alcanzaron. Por eso el campo del SL
 * avisa cuando se queda corto en vez de callarse.
 */

const NUM = (s: string) => {
  const v = parseFloat(s.replace(",", "."));
  return Number.isFinite(v) ? v : null;
};

/** Redondeo por magnitud, igual que el backend, para no mostrar 12 decimales. */
function redondear(p: number): string {
  if (p >= 100) return p.toFixed(2);
  if (p >= 1) return p.toFixed(4);
  if (p >= 0.01) return p.toFixed(6);
  return p.toFixed(8);
}

const caja: React.CSSProperties = {
  background: "#0f0f0f",
  border: "1px solid #222",
  borderRadius: 4,
  color: "#ccc",
  fontFamily: "monospace",
  fontSize: 12,
  padding: "4px 6px",
  width: "100%",
  boxSizing: "border-box",
};

export default function Calculadora() {
  const [abierta, setAbierta] = useState(false);
  const [precio, setPrecio] = useState("");
  const [tpPct, setTpPct] = useState("3.2");
  const [slPct, setSlPct] = useState("1.2");
  const [apalanca, setApalanca] = useState("5");

  const p = NUM(precio);
  const tp = NUM(tpPct) ?? 3.2;
  const sl = NUM(slPct) ?? 1.2;
  const lev = NUM(apalanca) ?? 1;
  const retro = 1.8;

  const filas =
    p && p > 0
      ? [
          { et: "objetivo", v: p * (1 + tp / 100), d: `+${tp}%`, c: "#22c55e" },
          { et: "stop", v: p * (1 - sl / 100), d: `-${sl}%`, c: "#dc2626" },
          {
            et: "esperar",
            v: p * (1 - retro / 100),
            d: `-${retro}%`,
            c: "#7a8a9a",
          },
        ]
      : [];

  return (
    <div style={{ borderTop: "1px solid #1e1e1e", background: "#0c0c0c" }}>
      <button
        onClick={() => setAbierta((a) => !a)}
        style={{
          background: "none",
          border: "none",
          color: "#667",
          cursor: "pointer",
          fontFamily: "monospace",
          fontSize: 11,
          padding: "6px 16px",
          width: "100%",
          textAlign: "left",
        }}
      >
        {abierta ? "▾" : "▸"} CALCULADORA DE NIVELES
      </button>

      {abierta && (
        <div style={{ padding: "0 16px 12px" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
            <label style={{ fontSize: 10, color: "#667", flex: "2 1 140px" }}>
              precio de compra
              <input
                value={precio}
                onChange={(e) => setPrecio(e.target.value)}
                placeholder="0.4503"
                inputMode="decimal"
                autoFocus
                style={{ ...caja, marginTop: 3 }}
              />
            </label>
            {([
              ["TP %", tpPct, setTpPct],
              ["SL %", slPct, setSlPct],
              ["apalanc.", apalanca, setApalanca],
            ] as const).map(([et, val, set]) => (
              <label key={et} style={{ fontSize: 10, color: "#667", flex: "1 1 62px" }}>
                {et}
                <input
                  value={val}
                  onChange={(e) => set(e.target.value)}
                  inputMode="decimal"
                  style={{ ...caja, marginTop: 3 }}
                />
              </label>
            ))}
          </div>

          {filas.length > 0 && (
            <table style={{ marginTop: 10, width: "100%", fontSize: 12 }}>
              <tbody>
                {filas.map((f) => (
                  <tr key={f.et}>
                    <td style={{ color: "#667", fontSize: 10, padding: "2px 0" }}>
                      {f.et}
                    </td>
                    <td
                      style={{
                        color: f.c,
                        fontWeight: 700,
                        textAlign: "right",
                        padding: "2px 8px",
                      }}
                    >
                      {redondear(f.v)}
                    </td>
                    <td style={{ color: "#556", fontSize: 10, width: 48 }}>{f.d}</td>
                    <td style={{ color: "#556", fontSize: 10 }}>
                      {lev > 1 && f.et !== "esperar"
                        ? `${f.et === "objetivo" ? "+" : "-"}${(
                            (f.et === "objetivo" ? tp : sl) * lev
                          ).toFixed(1)}% del capital a x${lev}`
                        : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* Un dato medido, no una opinion: el stop de 1.2% quedo por debajo
              del movimiento en contra tipico de las senales. */}
          {sl < 1.83 && (
            <div style={{ marginTop: 8, fontSize: 10, color: "#8a6a3a", lineHeight: 1.5 }}>
              ⚠ un stop de {sl}% queda por debajo del |MAE| mediano medido
              (1.83%). Saltaba antes del objetivo en el 33% de las señales que
              SÍ llegaron.
            </div>
          )}
          <div style={{ marginTop: 6, fontSize: 10, color: "#445", lineHeight: 1.5 }}>
            «esperar» es el nivel de retroceso: entrando ahí el rendimiento por
            operación sube de +0,54% a +0,87%, pero solo se ejecuta el 42% de
            las veces. El objetivo no se mueve — sigue siendo +{tp}% sobre el
            precio de arriba.
          </div>
        </div>
      )}
    </div>
  );
}
