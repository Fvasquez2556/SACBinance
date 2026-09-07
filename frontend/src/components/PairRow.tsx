import type { PairState, Tier } from "../types";
import TFConfluence from "./TFConfluence";

const STATE_STYLE: Record<string, { bg: string; color: string }> = {
  CAYENDO:            { bg: "#1a0505", color: "#8b2020" },
  "TOCÓ_FONDO":      { bg: "#1a1400", color: "#b8860b" },
  CONSOLIDANDO:       { bg: "#0a1520", color: "#4a9ead" },
  SUBIENDO:           { bg: "#0a1a0a", color: "#2d7a2d" },
  BREAKOUT_INCIPIENTE: { bg: "#001a00", color: "#00ff41" },
  NEUTRAL:            { bg: "#111", color: "#555" },
};

const TIER_COLOR: Record<Tier, string> = {
  NINGUNO: "#444",
  VIGILANCIA: "#557",
  MODERADA: "#668",
  FUERTE: "#77a",
  "EXTRA-FUERTE": "#99f",
};

const STATE_LABEL: Record<string, string> = {
  CAYENDO: "CAYENDO",
  "TOCÓ_FONDO": "TOCÓ FONDO",
  CONSOLIDANDO: "CONSOLIDANDO",
  SUBIENDO: "SUBIENDO",
  BREAKOUT_INCIPIENTE: "BREAKOUT",
  NEUTRAL: "NEUTRAL",
};

function timeAgo(tsMs: number): string {
  if (!tsMs) return "—";
  const secs = Math.floor((Date.now() - tsMs) / 1000);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h`;
}

interface Props {
  pair: PairState;
  onClick: (symbol: string) => void;
  selected: boolean;
}

// Hasta donde llego el precio desde el entry congelado. No excluyentes:
// una alerta que bajo -1.2% y luego subio +3.2% muestra los dos puntos.
const MARCA_STYLE: Record<string, { color: string; titulo: string }> = {
  MORADO: { color: "#8b5cf6", titulo: "Llegó a +4.2%" },
  VERDE: { color: "#22c55e", titulo: "Llegó a +3.2%" },
  AMARILLO: { color: "#eab308", titulo: "Cayó a -1.2% (SL medio observado)" },
  ROJO: { color: "#dc2626", titulo: "Tocó el SL que fijó el sistema" },
};

// Estados de la alerta. Los cuatro ultimos son de SEGUIMIENTO: la señal ya no
// pide actuar, pero sigue en el tablero hasta cumplir sus 24h. Antes
// desaparecia y con ella toda su historia.
const ALERTA_STYLE: Record<string, { color: string; texto: string }> = {
  VIVA: { color: "#2d9c4a", texto: "ALERTA VIVA" },
  PERDIENDO_FUERZA: { color: "#d04040", texto: "PERDIENDO FUERZA" },
  EN_RETROCESO: { color: "#8a6a3a", texto: "EN RETROCESO" },
  EN_VALLE: { color: "#6a7a8a", texto: "EN VALLE" },
  RECUPERANDO: { color: "#4a8a6a", texto: "RECUPERANDO" },
  CUMPLIDA: { color: "#22c55e", texto: "CUMPLIDA +3.2%" },
};

const FASE_STYLE: Record<string, { color: string; icono: string }> = {
  ACELERANDO: { color: "#2d9c4a", icono: "▲▲" },
  SOSTENIDA: { color: "#8a9a3a", icono: "▲" },
  DESACELERANDO: { color: "#c07a1a", icono: "▼" },
  AGOTADA: { color: "#a02020", icono: "▼▼" },
  SIN_DATOS: { color: "#555", icono: "·" },
};

export default function PairRow({ pair, onClick, selected }: Props) {
  const style = STATE_STYLE[pair.display_state] ?? STATE_STYLE.NEUTRAL;
  const alerta = pair.alerta && pair.alerta.entry ? pair.alerta : null;
  const enDeclive = alerta?.estado === "PERDIENDO_FUERZA";
  const fase = FASE_STYLE[pair.impulso?.fase ?? "SIN_DATOS"] ?? FASE_STYLE.SIN_DATOS;
  const br = pair.base_rebote;
  const rt = pair.retroceso;
  // El unico patron que batio al grupo de control: venir de una caida >=2%.
  // Por eso el tablero lo ordena arriba y aqui se marca en grande.
  const patron = !!rt?.detectado;
  // Nivel fuerte: cayo Y ya rebota. Es la diferencia entre 24.4% y 19.5% de
  // acierto cobrable, asi que merece verse distinto y ordenarse mas arriba.
  const confirmado = !!rt?.confirmado;
  const est = alerta ? ALERTA_STYLE[alerta.estado] : undefined;
  const enSeguimiento = !!alerta && alerta.accionable === false;
  const sr = pair.sr_levels;
  // El detector solo calcula `dist_techo_pct` cuando la caída previa Y el
  // secado de volumen ya pasaron: significa que solo falta la ruptura. Filtrar
  // por `base_velas` no servía — la base casi siempre ocupa la ventana entera
  // (mediana 89 de 90 velas), así que marcaba 84 de 99 pares.
  const enBase = !!br && !br.detected && !br.rompio && br.dist_techo_pct != null;
  const faltaPct = enBase ? Math.abs(br!.dist_techo_pct!) : null;
  const inminente = faltaPct != null && faltaPct <= 1.0;

  return (
    <tr
      onClick={() => onClick(pair.symbol)}
      style={{
        cursor: "pointer",
        background: selected ? "#1a2a1a" : enDeclive ? "#2a1414" : style.bg,
        borderBottom: "1px solid #1e1e1e",
        // La barra naranja marca el patron validado; es lo que sube la fila
        // al principio del tablero, asi que conviene que se vea por que.
        borderLeft: confirmado
          ? "3px solid #2d9c4a"
          : patron
            ? "3px solid #c2703a"
          : enDeclive
            ? "3px solid #a02020"
            : "3px solid transparent",
        // En seguimiento la fila se atenua: sigue ahi, pero ya no pide actuar.
        filter: enSeguimiento ? "saturate(0.55)" : undefined,
        transition: "background 0.15s, opacity 0.4s",
        opacity: pair.fading && !alerta ? 0.5 : 1,
      }}
      title={
        enDeclive
          ? `PERDIENDO FUERZA — ${pair.impulso?.reason ?? ""}. Entry congelado ${alerta?.entry}`
          : alerta
            ? `Alerta viva desde hace ${alerta.edad_min} min — entry congelado ${alerta.entry}`
            : pair.fading
              ? "Dejó de ser interesante"
              : undefined
      }
    >
      <td style={{ padding: "6px 10px", fontWeight: 700, color: "#ccc", fontSize: 13 }}>
        {pair.symbol.replace("USDT", "")}
        <span style={{ color: "#555", fontWeight: 400, fontSize: 10 }}>/USDT</span>
        {patron && (
          <div style={{ fontSize: 9, marginTop: 2, whiteSpace: "nowrap" }} title={rt?.reason}>
            <span
              style={{
                background: confirmado ? "#1f5a2d" : "#5a2d1a",
                color: confirmado ? "#8dffab" : "#ffb27a",
                padding: "1px 5px",
                borderRadius: 3,
                fontWeight: 700,
                letterSpacing: "0.04em",
              }}
            >
              {confirmado
                ? `▲ REBOTA +${rt?.rebote_pct}%`
                : `▼ CAYO ${rt?.caida_pct}%`}
            </span>
            <span style={{ color: "#7a6a5a", marginLeft: 4 }}>
              {confirmado
                ? `cayo ${rt?.caida_pct}%`
                : rt?.rebote_pct != null && rt.rebote_pct > 0
                  ? `+${rt.rebote_pct}% del suelo`
                  : ""}
            </span>
          </div>
        )}
        {alerta && est && (
          <div style={{ fontSize: 9, marginTop: 2, whiteSpace: "nowrap" }}>
            <span style={{ color: est.color, fontWeight: 700 }}>{est.texto}</span>
            <span style={{ color: "#666", fontWeight: 400 }}> · {alerta.edad_min}min</span>
          </div>
        )}
        {br?.detected && (
          <div
            style={{ fontSize: 9, marginTop: 2, whiteSpace: "nowrap" }}
            title={br.reason}
          >
            <span
              style={{
                background: "#4a2d7a",
                color: "#c9a9ff",
                padding: "1px 5px",
                borderRadius: 3,
                fontWeight: 700,
                letterSpacing: "0.04em",
              }}
            >
              ◔ VALLE {br.score}
            </span>
          </div>
        )}
        {enBase && (
          <div
            style={{
              fontSize: 9,
              marginTop: 2,
              color: inminente ? "#a98ad0" : "#5a4d73",
              fontWeight: inminente ? 700 : 400,
              whiteSpace: "nowrap",
            }}
            title={br?.reason}
          >
            {inminente ? "◔ " : ""}falta {faltaPct!.toFixed(2)}% → {br?.base_techo}
            <span style={{ color: "#4a4055", fontWeight: 400 }}>
              {" "}· rango {br?.base_rango_pct}% · vol {br?.vol_dryup}x
            </span>
          </div>
        )}
        {sr && (sr.apoyado || sr.perdido) && (
          <div
            style={{
              fontSize: 9,
              marginTop: 2,
              whiteSpace: "nowrap",
              color: sr.perdido ? "#a05050" : "#4a8a6a",
            }}
            title={sr.lectura}
          >
            {sr.perdido
              ? `✕ soporte perdido · estorba a +${sr.dist_resistencia_pct}%`
              : `⌐ probando soporte · a -${sr.dist_soporte_pct}%`}
          </div>
        )}
        {alerta && alerta.marcadores && alerta.marcadores.length > 0 && (
          <div style={{ marginTop: 3, display: "flex", gap: 3 }}>
            {alerta.marcadores.map((m) => {
              const e = MARCA_STYLE[m];
              if (!e) return null;
              return (
                <span
                  key={m}
                  title={e.titulo}
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: e.color,
                    display: "inline-block",
                  }}
                />
              );
            })}
          </div>
        )}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <span
          style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: 4,
            background: style.bg,
            color: style.color,
            border: `1px solid ${style.color}33`,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.04em",
          }}
        >
          {STATE_LABEL[pair.display_state] ?? pair.display_state}
        </span>
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right", whiteSpace: "nowrap" }}>
        <span style={{ color: style.color, fontWeight: 700, fontSize: 14 }}>
          {pair.score}
        </span>
        {pair.score_trend !== 0 && (
          <span
            style={{
              fontSize: 9,
              marginLeft: 3,
              color: pair.score_trend > 0 ? "#2d7a2d" : "#8b2020",
            }}
          >
            {pair.score_trend > 0 ? "▲" : "▼"}
            {Math.abs(pair.score_trend)}
          </span>
        )}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <span style={{ color: TIER_COLOR[pair.tier], fontSize: 11 }}>
          {pair.tier === "NINGUNO" ? "—" : pair.tier}
        </span>
      </td>
      {/* Impulso: la derivada. Dice si el movimiento gana o pierde fuerza. */}
      <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>
        {pair.impulso?.valid ? (
          <span title={pair.impulso.reason}>
            <span style={{ color: fase.color, fontSize: 10, fontWeight: 700 }}>
              {fase.icono} {pair.impulso.fuerza}
            </span>
            {pair.impulso.consumido_pct != null && (
              <span style={{ color: "#666", fontSize: 9, marginLeft: 4 }}>
                {pair.impulso.consumido_pct.toFixed(1)}%rec
              </span>
            )}
          </span>
        ) : (
          <span style={{ color: "#444", fontSize: 10 }}>—</span>
        )}
      </td>
      {/* Entry CONGELADO en la emisión + delta en vivo contra ese entry */}
      <td style={{ padding: "6px 8px", textAlign: "right", whiteSpace: "nowrap" }}>
        {alerta ? (
          <>
            <div style={{ color: "#889", fontSize: 11 }}>{alerta.entry}</div>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: alerta.delta_pct >= 0 ? "#2d9c4a" : "#c04040",
              }}
            >
              {alerta.delta_pct >= 0 ? "+" : ""}
              {alerta.delta_pct.toFixed(2)}%
            </div>
            {/* Entrada alternativa: esperar el retroceso sube el rendimiento
                POR OPERACION de +0.54% a +0.87%, pero solo se ejecuta el 42%
                de las veces. Sirve cuando lo que limita es el capital. */}
            {alerta.entrada_alt > 0 && (
              <div
                style={{ fontSize: 9, marginTop: 1, color: "#7a8a9a", whiteSpace: "nowrap" }}
                title={`Esperar a que caiga ${alerta.retroceso_pct}% desde el entry y entrar ahi. El objetivo sigue siendo ${alerta.meta} (+3.2% sobre el entry original), asi que entrar mas abajo lo acerca. Solo se ejecuta ~42% de las veces.`}
              >
                ↓{alerta.retroceso_pct}% · {alerta.entrada_alt}
              </div>
            )}
            {/* La puntuacion que baja: no es un invento, es la frecuencia
                observada de llegar a la meta desde esa distancia. Si el precio
                se aleja baja, si se acerca sube. */}
            {alerta.dist_meta_pct != null && (
              <div
                style={{ fontSize: 9, marginTop: 1, whiteSpace: "nowrap" }}
                title={`Meta +3.2% = ${alerta.meta}. Probabilidad medida sobre ${alerta.prob_meta_n} casos con esta misma distancia Y esta misma edad (horizonte 6h). No es un modelo: es la frecuencia observada.`}
              >
                <span style={{ color: "#667" }}>
                  {alerta.dist_meta_pct <= 0
                    ? "meta hecha"
                    : `falta ${alerta.dist_meta_pct.toFixed(2)}%`}
                </span>
                <span
                  style={{
                    marginLeft: 4,
                    fontWeight: 700,
                    color:
                      alerta.prob_meta >= 60
                        ? "#22c55e"
                        : alerta.prob_meta >= 30
                          ? "#b8860b"
                          : "#7a5a5a",
                  }}
                >
                  {alerta.prob_meta.toFixed(0)}%
                </span>
              </div>
            )}
          </>
        ) : (
          <span style={{ color: "#444", fontSize: 10 }}>—</span>
        )}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <TFConfluence trends={pair.macro_trends} />
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right", color: "#667", fontSize: 11 }}>
        {pair.macro_gate_mult !== 1 ? `×${pair.macro_gate_mult.toFixed(2)}` : "—"}
      </td>
      <td style={{ padding: "6px 10px", color: "#555", fontSize: 11 }}>
        {timeAgo(pair.score_since_ms)}
      </td>
    </tr>
  );
}
