import assert from "node:assert/strict";
import test from "node:test";
import { barrierOrder, cambioDesdeEntrada, coverageLabel, desfaseDelta, displayPlan, goalAfterExitTP, goalLabel, goalOrder, horaLocal, inicioDelDiaLocal, nivelesDelPlan, percent, profiles, textoSoporte, textoTecho } from "../src/domain/reading.ts";
import type { HistoryRow } from "../src/domain/reading.ts";
import type { PairState } from "../src/types/index.ts";

function row(changes: Partial<HistoryRow> = {}): HistoryRow {
  return { signal_id: 1, symbol: "TESTUSDT", ts_open: 1_000_000, entry: 100,
    take_profit: 103.2, stop_loss: 98, tp_pct: 3.2, sl_pct: -2,
    desenlace: "ABIERTA", ms_resuelto: null, ms_tp: null, ms_sl: null, ms_meta: null,
    mfe_pct: 0, mae_pct: 0, llego_meta: false, supero: false, cerrado: 0, ...changes };
}

test("a recovery after the stop remains SL first", () => {
  const r = row({ ms_sl: 60_000, ms_tp: 300_000, ms_meta: 300_000, llego_meta: true, mfe_pct: 5 });
  assert.equal(barrierOrder(r), "SL_FIRST");
  assert.equal(goalOrder(r), "AFTER_SL");
  assert.equal(goalLabel(r), "+3.2% después del SL");
});
test("target before a later stop is distinguished from a stopped trade", () => {
  const r = row({ ms_tp: 60_000, ms_sl: 300_000, ms_meta: 60_000, llego_meta: true });
  assert.equal(barrierOrder(r), "TP_FIRST");
  assert.equal(goalOrder(r), "BEFORE_SL");
});
test("TP and SL in one candle are ambiguous, never a confirmed win", () => {
  const r = row({ ms_tp: 60_000, ms_sl: 60_000, ms_meta: 60_000, llego_meta: true, desenlace: "SL" });
  assert.equal(barrierOrder(r), "AMBIGUOUS");
  assert.equal(goalOrder(r), "AMBIGUOUS");
});
test("a zero-millisecond first touch is retained", () => {
  assert.equal(barrierOrder(row({ ms_tp: 0, ms_sl: 60_000 })), "TP_FIRST");
  assert.equal(goalOrder(row({ ms_meta: 0, llego_meta: true })), "BEFORE_SL");
});
test("older API data cannot establish the order even if it reports TP", () => {
  const r = row({ ms_tp: undefined, ms_sl: undefined, desenlace: "TP", ms_meta: 60_000, llego_meta: true });
  assert.equal(barrierOrder(r), "UNKNOWN");
  assert.equal(goalOrder(r), "UNKNOWN");
});
test("invalid and out-of-window timestamps do not establish an order", () => {
  for (const ms of [-1, Infinity, NaN, 86_400_001]) {
    assert.equal(barrierOrder(row({ ms_tp: ms })), "UNKNOWN");
    const r = row({ ms_tp: 60_000, ms_meta: ms, llego_meta: true });
    assert.equal(goalOrder(r), "UNKNOWN");
    assert.equal(goalAfterExitTP(r), false);
  }
});
test("unfinished observations are not labeled as failed trades", () => {
  assert.equal(barrierOrder(row()), "PENDING");
  assert.equal(barrierOrder(row({ cerrado: 1 })), "NEITHER");
});
test("a short TP exit does not claim the later +3.2% as plan profit", () => {
  const r = row({ tp_pct: 2, take_profit: 102, ms_tp: 60_000, ms_meta: 300_000, llego_meta: true });
  assert.equal(goalAfterExitTP(r), true);
  assert.equal(goalLabel(r), "+3.2% posterior al TP del plan");
});
test("goal before SL does not mean the offered TP was reached", () => {
  const r = row({ tp_pct: 5, take_profit: 105, ms_meta: 60_000, ms_sl: 300_000, llego_meta: true });
  assert.equal(goalOrder(r), "BEFORE_SL");
  assert.equal(barrierOrder(r), "SL_FIRST");
});
test("an absent stop is described as unobserved, not a known later event", () => {
  assert.equal(goalLabel(row({ ms_meta: 60_000, llego_meta: true })), "+3.2% tocado · SL no observado");
});
test("missing coverage is distinct from measured zero, partial, and complete", () => {
  assert.equal(coverageLabel(row({ cerrado: 1 })), "Cobertura no registrada");
  assert.equal(coverageLabel(row({ cobertura_velas: 0 })), "Cobertura parcial · 0.0%");
  assert.equal(coverageLabel(row({ cobertura_velas: 0.95 })), "Cobertura parcial · 95.0%");
  assert.equal(coverageLabel(row({ cobertura_velas: 1 })), "Velas completas · 100.0%");
  assert.equal(coverageLabel(row({ cobertura_velas: 1.2 })), "Cobertura no válida");
});
test("live recalculation cannot replace a frozen plan or its unknown costs", () => {
  const pair = { alerta: { entry: 100, take_profit: 103.2, stop_loss: 98, tp_pct: 3.2, sl_pct: -2 },
    trade_levels: { valid: true, entry: 105, take_profit: 110, stop_loss: 102, reward_neto_pct: 4 } } as PairState;
  const plan = displayPlan(pair);
  assert.equal(plan?.entry, 100);
  assert.equal(plan?.tp, 103.2);
  assert.equal(plan?.netPct, null);
  assert.equal(plan?.frozen, true);
});
test("a current proposal is identified separately when no alert exists", () => {
  const pair = { trade_levels: { valid: true, entry: 100, risk_pct: 2, reward_pct: 4, reward_neto_pct: 3.5 } } as PairState;
  assert.equal(displayPlan(pair)?.frozen, false);
  assert.equal(displayPlan(pair)?.netPct, 3.5);
  assert.equal(displayPlan({} as PairState), null);
});
test("coincident rebound and sustained trend are both kept", () => {
  const pair = { retroceso: { confirmado: true }, grind: { detected: true } } as PairState;
  assert.deepEqual(profiles(pair), ["Rebote confirmado", "Tendencia sostenida"]);
  assert.deepEqual(profiles({} as PairState), ["En observación"]);
});
test("missing numeric values do not become zero performance", () => {
  assert.equal(percent(undefined), "—"); assert.equal(percent(NaN), "—"); assert.equal(percent(0), "0.00%");
});

test("the change shown is computed from the price shown, not from the backend delta", () => {
  // Produccion, 22-sep: MUBARAKUSDT enseñaba +35.86% junto a un precio que
  // implicaba +36.54%. El delta venia del ultimo cierre de 1m y el precio del
  // minuto en curso: dos instantes, no un dato roto.
  assert.equal(cambioDesdeEntrada(0.0466, 0.03413)?.toFixed(2), "36.54");
  assert.equal(cambioDesdeEntrada(0.2305, 0.2237)?.toFixed(2), "3.04");
  assert.equal(cambioDesdeEntrada(100, 0), null);
  assert.equal(cambioDesdeEntrada(null, 100), null);
  assert.equal(cambioDesdeEntrada(100, undefined), null);
});

test("the lag against the candle close is reported, not hidden", () => {
  assert.equal(desfaseDelta(0.04641, 0.046741035)?.toFixed(3), "-0.708");
  assert.equal(desfaseDelta(100, 100), 0);
  assert.equal(desfaseDelta(100, null), null);
  assert.equal(desfaseDelta(100, 0), null);
});

test("the day starts at the operator's midnight, not at the server's", () => {
  const mediodia = new Date(2026, 8, 22, 12, 34, 56, 789).getTime();
  const inicio = new Date(inicioDelDiaLocal(mediodia));
  assert.equal(inicio.getHours(), 0);
  assert.equal(inicio.getMinutes(), 0);
  assert.equal(inicio.getSeconds(), 0);
  assert.equal(inicio.getDate(), 22);
  assert.ok(inicioDelDiaLocal(mediodia) <= mediodia);
});

test("a missing timestamp does not print an invalid date", () => {
  assert.equal(horaLocal(null), "—");
  assert.equal(horaLocal(undefined), "—");
  assert.equal(horaLocal(Number.NaN), "—");
  assert.match(horaLocal(new Date(2026, 8, 22, 9, 5).getTime()), /09[:.]05/);
});

test("the plan explains what holds the stop and what has to break", () => {
  const n = nivelesDelPlan(100, { soporte: 97.5, sl_basis: "soporte estructural",
    resistencia: 104, tp_bloqueado: true, toques_soporte: 4, toques_resistencia: 3 });
  assert.equal(n?.soportePct?.toFixed(2), "-2.50");
  assert.equal(n?.techoPct?.toFixed(2), "4.00");
  assert.equal(n?.techoEstorba, true);
  assert.match(textoSoporte(n) ?? "", /97\.5 \(-2\.50%\) · 4 toques · soporte estructural/);
  assert.match(textoTecho(n) ?? "", /104 \(\+4\.00%\) · 3 toques/);
});

test("an older alert without those levels shows nothing instead of zeros", () => {
  assert.equal(nivelesDelPlan(100, {}), null);
  assert.equal(nivelesDelPlan(100, null), null);
  assert.equal(nivelesDelPlan(null, { soporte: 97.5 }), null);
  assert.equal(nivelesDelPlan(0, { soporte: 97.5 }), null);
  assert.equal(textoSoporte(null), null);
  assert.equal(textoTecho(null), null);
});

test("a ceiling above the target is still reported, without the alarm", () => {
  const n = nivelesDelPlan(100, { resistencia: 110, tp_bloqueado: false });
  assert.equal(n?.techoEstorba, false);
  assert.equal(n?.soporte, null);
  assert.match(textoTecho(n) ?? "", /110 \(\+10\.00%\)/);
  assert.equal(textoSoporte(n), null);
});
