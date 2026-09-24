import assert from "node:assert/strict";
import test from "node:test";
import { ETIQUETA_TIPO, desvioDeEntrada, distanciaANiveles, motivoParaNoAbrir, noRealizadoPct, saldosPorTipo, textoDesvio } from "../src/domain/operaciones.ts";
import type { Operacion, ResumenOperaciones } from "../src/types/index.ts";

function op(changes: Partial<Operacion> = {}): Operacion {
  return { operacion_id: 1, plan_id: 5, episode_id: 2, symbol: "TESTUSDT", tipo: "SIMULADA",
    estado: "ABIERTA", ts_apertura: 1_790_000_000_000, precio_entrada: 100, cantidad: null,
    cantidad_abierta: null, objetivo: 104.87, stop: 97.55, coste_pct: 0.5, ts_cierre: null,
    precio_salida: null, motivo_cierre: null, resultado_pct: null, resultado_moneda: null,
    nota: null, ...changes };
}

test("the unrealised number discounts costs and never invents one", () => {
  assert.equal(noRealizadoPct(103, 100, 0.5), 2.5);
  assert.equal(noRealizadoPct(97, 100, 0.5)?.toFixed(2), "-3.50");
  assert.equal(noRealizadoPct(null, 100, 0.5), null);
  assert.equal(noRealizadoPct(103, 0, 0.5), null);
  assert.equal(noRealizadoPct(103, 100), 3);
});

test("the distance is measured against the levels the trade copied", () => {
  const d = distanciaANiveles(op(), 102);
  assert.equal(d.objetivo?.toFixed(2), "2.81");
  assert.equal(d.stop?.toFixed(2), "-4.36");
  assert.deepEqual(distanciaANiveles(op({ objetivo: null, stop: null }), 102),
    { objetivo: null, stop: null });
  assert.deepEqual(distanciaANiveles(op(), null), { objetivo: null, stop: null });
});

test("the form refuses what the journal would refuse", () => {
  assert.match(motivoParaNoAbrir("", "") ?? "", /precio/i);
  assert.match(motivoParaNoAbrir("0", "") ?? "", /precio/i);
  assert.match(motivoParaNoAbrir("abc", "") ?? "", /precio/i);
  assert.match(motivoParaNoAbrir("100", "-2") ?? "", /cantidad/i);
  assert.equal(motivoParaNoAbrir("100", ""), null);
  assert.equal(motivoParaNoAbrir("0.00000428", "10"), null);
});

test("simulated and declared are never added together", () => {
  const resumen: ResumenOperaciones = {
    por_tipo: [
      { tipo: "SIMULADA", estado: "CERRADA", n: 3, media_pct: 1.5, suma_pct: 4.5, positivas: 2 },
      { tipo: "SIMULADA", estado: "ABIERTA", n: 1, media_pct: null, suma_pct: null, positivas: null },
      { tipo: "DECLARADA", estado: "CERRADA", n: 2, media_pct: -1, suma_pct: -2, positivas: 0 },
    ],
    moneda_por_tipo: [{ tipo: "DECLARADA", suma: -20.5 }],
    abiertas: 1,
  };
  const saldos = saldosPorTipo(resumen);
  assert.equal(saldos.length, 2);
  const declarada = saldos.find(s => s.tipo === "DECLARADA");
  const simulada = saldos.find(s => s.tipo === "SIMULADA");
  assert.equal(declarada?.sumaPct, -2);
  assert.equal(declarada?.moneda, -20.5);
  assert.equal(simulada?.sumaPct, 4.5);
  assert.equal(simulada?.abiertas, 1);
  assert.equal(simulada?.moneda, null);     // lo simulado no tiene dinero
  assert.equal(saldosPorTipo(null).length, 0);
});

test("every type has a label, so nothing renders as a raw code", () => {
  assert.equal(ETIQUETA_TIPO.SIMULADA, "Seguimiento simulado");
  assert.equal(ETIQUETA_TIPO.DECLARADA, "Ejecución declarada");
  assert.ok(ETIQUETA_TIPO.IMPORTADA.length > 0);
});

test("entering above the plan quietly flips the reward-to-risk, and it is said", () => {
  // El caso real de PYTH: plan 0.06307 / TP 0.065397 / SL 0.061907, entrada en 0.06396.
  const d = desvioDeEntrada(0.06396, { entry: 0.06307, objetivo: 0.065397, stop: 0.061907 });
  assert.equal(d?.desviacionPct.toFixed(2), "1.41");
  assert.equal(d?.rrPlan, 2);
  assert.equal(d?.rrReal, 0.7);
  assert.equal(d?.riesgoPct, 3.21);     // medido sobre tu precio, no sobre el stop
  assert.equal(d?.recorridoPct, 2.25);
  assert.equal(d?.grave, true);
  assert.match(textoDesvio(d) ?? "", /1\.41% por encima/);
  assert.match(textoDesvio(d) ?? "", /R:R 0\.70 en vez de 2\.00/);
});

test("entering at the plan price says nothing", () => {
  const d = desvioDeEntrada(100, { entry: 100, objetivo: 106, stop: 97 });
  assert.equal(d?.rrReal, 2);
  assert.equal(d?.grave, false);
  assert.equal(textoDesvio(d), null);
});

test("entering better than the plan is reported as what it is", () => {
  const d = desvioDeEntrada(99, { entry: 100, objetivo: 106, stop: 97 });
  assert.ok((d?.rrReal ?? 0) > 2);
  assert.equal(d?.grave, false);
  assert.match(textoDesvio(d) ?? "", /1\.00% por debajo/);
});

test("a price outside the plan is refused as a comparison, not scored", () => {
  const alto = desvioDeEntrada(107, { entry: 100, objetivo: 106, stop: 97 });
  assert.equal(alto?.fueraDelPlan, true);
  assert.equal(alto?.rrReal, null);
  assert.match(textoDesvio(alto) ?? "", /ya no queda recorrido/);
  const bajo = desvioDeEntrada(96, { entry: 100, objetivo: 106, stop: 97 });
  assert.match(textoDesvio(bajo) ?? "", /plan ya estaría invalidado/);
});

test("without levels there is no ratio to compare and nothing is invented", () => {
  const d = desvioDeEntrada(101, { entry: 100 });
  assert.equal(d?.rrPlan, null);
  assert.equal(textoDesvio(d), null);
  assert.equal(desvioDeEntrada(null, { entry: 100, objetivo: 106, stop: 97 }), null);
  assert.equal(desvioDeEntrada(101, null), null);
});
