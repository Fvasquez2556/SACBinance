import { useEffect, useMemo, useState } from "react";

/**
 * Historial de señales con su desenlace.
 *
 * El tablero solo enseñaba el presente: los pares vivos ahora. Cuando una
 * señal se archivaba a las 24h desaparecia con todo lo que habia hecho, y la
 * unica forma de mirar atras era consultar la base a mano.
 *
 * Sale de `outcomes` y no de `signals`, y eso cambia lo que se puede contar.
 * `signals` cierra la señal en cuanto toca TP o SL; `outcomes` la sigue las 24
 * horas enteras. Por eso aqui una fila puede decir "SL" y a la vez llevar la
 * marca de haber llegado a +3.2%: pasa en el 42% de las paradas, y era
 * precisamente lo que no se veia por ningun lado.
 */

interface Fila {
  signal_id: number;
  symbol: string;
  ts_open: number;
  senal_n: number | null;
  tier: string | null;
  score: number | null;
  display_state: string | null;
  entry: number | null;
  take_profit: number | null;
  stop_loss: number | null;
  tp_pct: number | null;
  sl_pct: number | null;
  desenlace: "TP" | "SL" | "NADA" | "ABIERTA";
  ms_resuelto: number | null;
  mfe_pct: number | null;
  mae_pct: number | null;
  llego_meta: boolean;
  supero: boolean;
  ms_meta: number | null;
  cerrado: number;
  hoyo_ms: number | null;
  hoyo_celda: string | null;
  hoyo_c3: string | null;
}

type Filtro = "TODAS" | "TP" | "SL" | "META" | "ABIERTAS";

const COLOR_DESENLACE: Record<string, string> = {
  TP: "#2d7a2d",
  SL: "#8b2020",
  NADA: "#555",
  ABIERTA: "#4a9ead",
};

/** Redondeo por magnitud: un precio de 0.00000412 no se ve con 2 decimales. */
function precio(p: number | null): string {
  if (p == null) return "—";
  if (p >= 100) return p.toFixed(2);
  if (p >= 1) return p.toFixed(4);
  if (p >= 0.01) return p.toFixed(6);
  return p.toFixed(8);
}

function dur(ms: number | null): string {
  if (ms == null) return "—";
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
}

function hora(ts: number): string {
  return new Date(ts).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const btn = (activo: boolean): React.CSSProperties => ({
  padding: "3px 10px",
  fontSize: 11,
  background: activo ? "#1a1a2e" : "#0f0f0f",
  color: activo ? "#99f" : "#556",
  border: `1px solid ${activo ? "#99f66" : "#222"}`,
  borderRadius: 4,
  cursor: "pointer",
});

const th: React.CSSProperties = { padding: "5px 8px", textAlign: "left" };
const thR: React.CSSProperties = { ...th, textAlign: "right" };
const td: React.CSSProperties = { padding: "4px 8px", whiteSpace: "nowrap" };
const tdR: React.CSSProperties = { ...td, textAlign: "right" };

export default function Historial({ onSelect }: { onSelect?: (s: string) => void }) {
  const [abierto, setAbierto] = useState(false);
  const [filas, setFilas] = useState<Fila[]>([]);
  const [filtro, setFiltro] = useState<Filtro>("TODAS");
  const [busca, setBusca] = useState("");
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    const load = () => {
      setCargando(true);
      fetch("/api/historial?limit=400")
        .then((r) => r.json())
        .then((d) => setFilas(d.historial ?? []))
        .catch(() => {})
        .finally(() => setCargando(false));
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [abierto]);

  const resumen = useMemo(() => {
    const n = filas.length;
    const c = (f: (x: Fila) => boolean) => filas.filter(f).length;
    const cerradas = c((x) => x.cerrado === 1);
    return {
      n,
      tp: c((x) => x.desenlace === "TP"),
      sl: c((x) => x.desenlace === "SL"),
      abiertas: c((x) => x.desenlace === "ABIERTA"),
      meta: c((x) => x.llego_meta),
      // Lo que no se veia: paradas que acabaron llegando igual al objetivo.
      rescatadas: c((x) => x.desenlace === "SL" && x.llego_meta),
      cerradas,
    };
  }, [filas]);

  const visibles = useMemo(() => {
    const q = busca.trim().toUpperCase();
    return filas.filter((f) => {
      if (q && !f.symbol.includes(q)) return false;
      if (filtro === "TP") return f.desenlace === "TP";
      if (filtro === "SL") return f.desenlace === "SL";
      if (filtro === "ABIERTAS") return f.desenlace === "ABIERTA";
      if (filtro === "META") return f.llego_meta;
      return true;
    });
  }, [filas, filtro, busca]);

  if (!abierto) {
    return (
      <div style={{ padding: "6px 10px", borderBottom: "1px solid #1e1e1e" }}>
        <button onClick={() => setAbierto(true)} style={btn(false)}>
          ▸ Historial de señales
        </button>
      </div>
    );
  }

  return (
    <div style={{ borderBottom: "1px solid #1e1e1e", background: "#0b0b0b" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
          padding: "6px 10px",
        }}
      >
        <button onClick={() => setAbierto(false)} style={btn(true)}>
          ▾ Historial de señales
        </button>

        <span style={{ color: "#556", fontSize: 11 }}>
          {resumen.n} señales · {resumen.cerradas} cerradas
          {cargando && " · actualizando…"}
        </span>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {(
            [
              ["TODAS", `todas ${resumen.n}`],
              ["TP", `cumplió TP ${resumen.tp}`],
              ["SL", `paradas ${resumen.sl}`],
              ["META", `llegó a +3.2% ${resumen.meta}`],
              ["ABIERTAS", `abiertas ${resumen.abiertas}`],
            ] as [Filtro, string][]
          ).map(([k, etq]) => (
            <button key={k} style={btn(filtro === k)} onClick={() => setFiltro(k)}>
              {etq}
            </button>
          ))}
        </div>

        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="filtrar par…"
          style={{
            background: "#0f0f0f",
            border: "1px solid #222",
            borderRadius: 4,
            color: "#ccc",
            fontFamily: "monospace",
            fontSize: 11,
            padding: "3px 6px",
            width: 110,
          }}
        />

        {resumen.rescatadas > 0 && (
          <span
            style={{ color: "#b8860b", fontSize: 11 }}
            title="Tocaron su stop y aun asi llegaron a +3.2% dentro de las 24h. Es el caso que el tablero no enseñaba."
          >
            {resumen.rescatadas} paradas llegaron igual a +3.2%
          </span>
        )}
      </div>

      <div style={{ maxHeight: 320, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead>
            <tr
              style={{
                borderBottom: "1px solid #1e1e1e",
                fontSize: 10,
                color: "#557",
                position: "sticky",
                top: 0,
                background: "#0b0b0b",
              }}
            >
              <th style={th}>CUÁNDO</th>
              <th style={th}>PAR</th>
              <th style={thR} title="Qué número de señal es para ese par">Nº</th>
              <th style={th}>TIER</th>
              <th style={thR}>SCORE</th>
              <th style={thR}>ENTRADA</th>
              <th style={thR}>TP</th>
              <th style={thR}>SL</th>
              <th style={th}>DESENLACE</th>
              <th style={thR} title="Lo máximo que subió y bajó desde la entrada">MFE / MAE</th>
              <th style={th} title="Marcas independientes del desenlace">MARCAS</th>
            </tr>
          </thead>
          <tbody>
            {visibles.length === 0 && (
              <tr>
                <td colSpan={11} style={{ ...td, color: "#445", padding: 12 }}>
                  {cargando ? "Cargando…" : "Nada que enseñar con este filtro."}
                </td>
              </tr>
            )}
            {visibles.map((f) => (
              <tr
                key={f.signal_id}
                onClick={() => onSelect?.(f.symbol)}
                style={{
                  borderBottom: "1px solid #141414",
                  cursor: onSelect ? "pointer" : "default",
                  color: "#aab",
                }}
              >
                <td style={{ ...td, color: "#667" }}>{hora(f.ts_open)}</td>
                <td style={{ ...td, color: "#ccd", fontWeight: 600 }}>
                  {f.symbol.replace("USDT", "")}
                </td>
                <td
                  style={{
                    ...tdR,
                    color:
                      (f.senal_n ?? 0) >= 7
                        ? "#8b2020"
                        : (f.senal_n ?? 0) <= 2 && (f.senal_n ?? 0) > 0
                        ? "#4a9ead"
                        : "#667",
                  }}
                  title="La 1ª señal de un par cumple su TP el 43%; de la 7ª en adelante, el 29%."
                >
                  {f.senal_n ? `${f.senal_n}ª` : "—"}
                </td>
                <td style={{ ...td, color: "#778" }}>{f.tier ?? "—"}</td>
                <td style={tdR}>{f.score ?? "—"}</td>
                <td style={tdR}>{precio(f.entry)}</td>
                <td style={{ ...tdR, color: "#2d7a2d" }}>
                  {f.tp_pct != null ? `+${f.tp_pct.toFixed(1)}%` : "—"}
                </td>
                <td style={{ ...tdR, color: "#8b2020" }}>
                  {f.sl_pct != null ? `${f.sl_pct.toFixed(1)}%` : "—"}
                </td>
                <td style={{ ...td, color: COLOR_DESENLACE[f.desenlace] }}>
                  {f.desenlace === "NADA" ? "ni TP ni SL" : f.desenlace}
                  {f.ms_resuelto != null && (
                    <span style={{ color: "#556" }}> · {dur(f.ms_resuelto)}</span>
                  )}
                </td>
                <td style={tdR}>
                  <span style={{ color: "#2d7a2d" }}>
                    {f.mfe_pct != null ? `+${f.mfe_pct.toFixed(1)}` : "—"}
                  </span>
                  <span style={{ color: "#445" }}> / </span>
                  <span style={{ color: "#8b2020" }}>
                    {f.mae_pct != null ? f.mae_pct.toFixed(1) : "—"}
                  </span>
                </td>
                <td style={td}>
                  {f.llego_meta && (
                    <span
                      style={{ color: "#2d7a2d", marginRight: 6 }}
                      title={`Llegó a +3.2%${f.ms_meta != null ? ` a los ${dur(f.ms_meta)}` : ""}`}
                    >
                      ●3.2
                    </span>
                  )}
                  {f.supero && (
                    <span style={{ color: "#9b59b6", marginRight: 6 }} title="Superó +4.2%">
                      ●4.2
                    </span>
                  )}
                  {f.hoyo_ms != null && (
                    <span
                      style={{ color: "#666", marginRight: 6 }}
                      title={`Sombra: el precio bajó al hoyo a los ${dur(f.hoyo_ms)} · celda ${f.hoyo_celda ?? "?"} · regla C3 ${f.hoyo_c3 ?? "sin resolver"}`}
                    >
                      ◇{f.hoyo_c3 ?? "…"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
