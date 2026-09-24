import { CONTRATO_PROVISIONAL } from "../src/domain/contrato.ts";
import assert from "node:assert/strict";
import test from "node:test";
import {
  avisosPlan, esRuptura, estadoTF, horizonteApretado, motivoSinPlan, normalizarSymbol,
  rangoEntrada, textoConfluencia, textoHorizonte, textoTasa, tituloResumen,
} from "../src/domain/analysis.ts";
import type { AnalisisPar, EstadisticaCelda, EstadisticaMarco, LecturaTF, PlanDireccional } from "../src/types/index.ts";

function celda(changes: Partial<EstadisticaCelda> = {}): EstadisticaCelda {
  return { n: 2474, rellenadas: 1976, pct_fill: 79.9, tp_antes_sl: 58.5,
    horas_mediana: 5.05, pct_dentro_horizonte: 82.5, fiable: true, ...changes };
}

function estadistica(changes: Partial<EstadisticaMarco> = {}): EstadisticaMarco {
  return { ventana_dias: 14, min_n: 50, horizonte_h: 12, marco: celda(),
    estorbo_si: celda({ tp_antes_sl: 50, n: 15200 }),
    estorbo_no: celda({ tp_antes_sl: 46.4, n: 3878 }), ...changes };
}

function plan(changes: Partial<PlanDireccional> = {}): PlanDireccional {
  return {
    valid: true, direccion: "RUPTURA_ALCISTA", tf: "15m",
    entrada_min: 102, entrada_max: 103.5, entrada_ref: 103.5, rango_pct: 1.45,
    mejora_max_pct: 1.45, rellena_en_retest: true,
    stop_loss: 99.9, take_profit: 110.7, risk_pct: 3.5, reward_pct: 7,
    reward_neto_pct: 6.5, risk_reward: 2, atr_pct: 1.1, ruido_1m_pct: 0.9,
    sl_basis: "soporte estructural", nivel_estorbo: null, tp_bloqueado: false,
    objetivo_alcanzable: true, advertencia: "", reason: "ok", ...changes,
  };
}

function lectura(changes: Partial<LecturaTF> = {}): LecturaTF {
  return {
    tf: "15m", direccion: "RUPTURA_ALCISTA", etiqueta: "Ruptura alcista",
    razon: "cierre por encima de 102", confirmada: true, nivel_roto: 102,
    toques_nivel: 3, velas_desde_ruptura: 4, distancia_nivel_pct: 1.4,
    tendencia: "ALCISTA", slope_ma7: 0.3, slope_ma25: 0.2, slope_ma99: 0.1,
    atr_pct: 1.1, vol_ratio: 1.4, rsi14: 61, macd_rising: true, trend_up: true,
    n_velas: 260, niveles: null, plan: plan(), ...changes,
  };
}

test("el par se completa con USDT y se limpia el separador", () => {
  assert.equal(normalizarSymbol("btc"), "BTCUSDT");
  assert.equal(normalizarSymbol(" eth/usdt "), "ETHUSDT");
  assert.equal(normalizarSymbol("SOLUSDT"), "SOLUSDT");
});

test("lo que no tiene forma de par se rechaza antes de pedirlo al backend", () => {
  for (const malo of ["", "   ", "b", "../etc", "BTC USDT!"]) {
    assert.equal(normalizarSymbol(malo), null, malo);
  }
});

test("una ruptura sin sostener no se enseña como sostenida", () => {
  assert.equal(estadoTF(lectura()), "Ruptura alcista · sostenida");
  assert.equal(estadoTF(lectura({ confirmada: false })), "Ruptura alcista · sin confirmar");
  assert.equal(estadoTF(lectura({ direccion: "SIN_DATOS" })), "Sin historia suficiente");
  assert.equal(estadoTF(lectura({ direccion: "SIN_RUPTURA" })), "Rango intacto");
});

test("sin zona de retest el rango no se disfraza de rango", () => {
  assert.match(rangoEntrada(plan()), /102(.*)103/);
  const aMercado = rangoEntrada(plan({ rellena_en_retest: false, entrada_min: 103.5 }));
  assert.match(aMercado, /solo a mercado/);
});

test("el plan bajista arrastra su advertencia de que no está medido", () => {
  const avisos = avisosPlan(plan({ direccion: "RUPTURA_BAJISTA", advertencia: "Direccion bajista: sin medicion." }));
  assert.ok(avisos.some(a => a.includes("Direccion bajista")));
});

test("un TP que no llega al objetivo tras costes se dice, no se calla", () => {
  const avisos = avisosPlan(plan({ objetivo_alcanzable: false, reward_neto_pct: 1.4 }));
  // El aviso nombra el objetivo CON SU TIPO. Antes decia "+3.2%" a secas, y
  // ese numero estaba escrito a mano: mover el objetivo dejaba el texto
  // mintiendo.
  assert.ok(avisos.some(a => a.includes("+3.2 % neto")));
  assert.equal(avisosPlan(plan()).length, 0);
});

test("mover el objetivo mueve el aviso, porque ya no hay ningun 3.2 escrito", () => {
  const movido = {
    ...CONTRATO_PROVISIONAL,
    objetivo_operador: { pct: 4.2, tipo: "NETO" as const, etiqueta: "+4.2 % neto", coste_pct: 0.5 },
  };
  const avisos = avisosPlan(plan({ objetivo_alcanzable: false, reward_neto_pct: 3.5 }),
                            null, movido);
  assert.ok(avisos.some(a => a.includes("+4.2 % neto")));
  assert.ok(!avisos.some(a => a.includes("3.2")));
});

test("un nivel entre la entrada y el TP se avisa", () => {
  const avisos = avisosPlan(plan({ tp_bloqueado: true, nivel_estorbo: 106 }));
  assert.ok(avisos.some(a => a.includes("106")));
});

test("una ruptura sin plan explica por qué, en vez de quedarse vacía", () => {
  const sinPlan = motivoSinPlan(lectura({ plan: plan({ valid: false, reason: "el stop pediria 8% de riesgo" }) }));
  assert.match(sinPlan ?? "", /8%/);
  assert.equal(motivoSinPlan(lectura()), null);
  assert.equal(motivoSinPlan(lectura({ direccion: "SIN_RUPTURA", plan: null })), null);
});

test("el desacuerdo entre marcos manda sobre la dirección dominante", () => {
  const base: AnalisisPar = {
    symbol: "BTCUSDT", price: 100, ts: 1, fuente: "motor",
    resumen: {
      direccion_dominante: "RUPTURA_ALCISTA", tf_dominante: "4h",
      n_alcistas: 1, n_bajistas: 0, n_confirmadas: 1, en_conflicto: false,
      lectura: "Ruptura alcista confirmada en 4h.",
    },
    timeframes: [], advertencias: [],
  };
  assert.equal(tituloResumen(base), "Ruptura alcista en 4h");
  assert.equal(
    tituloResumen({ ...base, resumen: { ...base.resumen, en_conflicto: true, n_bajistas: 2 } }),
    "Marcos en desacuerdo",
  );
});

test("solo las dos direcciones cuentan como ruptura", () => {
  assert.ok(esRuptura("RUPTURA_ALCISTA") && esRuptura("RUPTURA_BAJISTA"));
  assert.ok(!esRuptura("SIN_RUPTURA") && !esRuptura("SIN_DATOS"));
});

test("a measured rate always arrives with its sample and its window", () => {
  assert.match(textoTasa(celda(), 14), /58\.5% tocó el TP antes que el stop · n=2474 · 14 días/);
  assert.match(textoTasa(celda(), 14), /llenó la entrada el 79\.9%/);
});

test("without enough sample it says so instead of showing a number", () => {
  assert.match(textoTasa(celda({ fiable: false, tp_antes_sl: null, n: 12 })), /Sin estimación fiable: solo 12/);
  assert.match(textoTasa(null), /Sin observaciones/);
  assert.match(textoTasa(undefined), /Sin observaciones/);
});

test("the horizon line says whether the frame fits the trading day", () => {
  assert.match(textoHorizonte(estadistica()) ?? "", /TP en 5\.05 h de mediana · 82\.5% cupo en 12 h/);
  assert.equal(horizonteApretado(estadistica()), false);
  const lento = estadistica({ marco: celda({ pct_dentro_horizonte: 58.1, horas_mediana: 10.08 }) });
  assert.equal(horizonteApretado(lento), true);
  assert.equal(textoHorizonte({ ...estadistica(), marco: null }), null);
  assert.equal(horizonteApretado(null), false);
});

test("the blocking level is described without claiming a harm the data denies", () => {
  const p = plan({ tp_bloqueado: true, nivel_estorbo: 105 });
  const conNumero = avisosPlan(p, estadistica()).find(a => a.includes("entre la entrada y el TP"));
  assert.match(conNumero ?? "", /con un nivel de por medio, 50% tocó el TP antes que el stop \(n=15200\)/);
  assert.match(conNumero ?? "", /sin él, 46\.4% \(n=3878\)/);
  const sinNumero = avisosPlan(p).find(a => a.includes("entre la entrada y el TP"));
  assert.match(sinNumero ?? "", /tiene que atravesarlo\.$/);
});

test("the summary is conditioned on how many frames confirm", () => {
  const base = { symbol: "TESTUSDT", price: 100, ts: 1, fuente: "motor",
    timeframes: [], advertencias: [] } as unknown as AnalisisPar;
  const analisis = { ...base, resumen: { direccion_dominante: "RUPTURA_ALCISTA", tf_dominante: "1h",
    n_alcistas: 3, n_bajistas: 0, n_confirmadas: 3, en_conflicto: false, lectura: "",
    estadistica: { ventana_dias: 14, min_n: 50, direccion: "RUPTURA_ALCISTA", n_confirmadas: 3,
      confluencia: celda(), conflicto_si: null, conflicto_no: null } } } as unknown as AnalisisPar;
  assert.match(textoConfluencia(analisis) ?? "", /Con 3 marcos confirmados: 58\.5%/);
  assert.equal(textoConfluencia({ ...base, resumen: { ...analisis.resumen, estadistica: undefined } } as AnalisisPar), null);
});
