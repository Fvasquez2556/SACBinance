import assert from "node:assert/strict";
import test from "node:test";
import {
  CONTRATO_PROVISIONAL, avisoObjetivoCorto, hitoCumpleObjetivo,
  llegaAlObjetivo, textoHito, textoObjetivo, type Contrato,
} from "../src/domain/contrato.ts";

const C: Contrato = CONTRATO_PROVISIONAL;

test("the gross milestone and the net goal are not the same thing", () => {
  // Es el defecto que esta fase corrige: mismo numero, distinto significado.
  assert.equal(C.hito_referencia.pct, C.objetivo_operador.pct);
  assert.equal(C.hito_referencia.tipo, "BRUTO");
  assert.equal(C.objetivo_operador.tipo, "NETO");
  assert.equal(C.coinciden, false);
  // Media vuelta de diferencia, que es el coste.
  assert.equal(C.objetivo_operador_bruto.pct - C.hito_referencia.pct, C.coste_pct);
});

test("every percentage says out loud whether it is gross or net", () => {
  assert.match(C.objetivo_operador.etiqueta, /neto/);
  assert.match(C.hito_referencia.etiqueta, /bruto/);
  assert.match(textoHito(C), /bruto.*neto/);
  assert.match(textoObjetivo(C), /\+3\.2 % neto/);
  assert.match(textoObjetivo(C), /\+3\.7 % bruto/);
});

test("touching the milestone is not the same as reaching the goal", () => {
  // 502 recorridos reales: 37 tocaron el hito y no llegaron al objetivo.
  assert.equal(hitoCumpleObjetivo(3.4, C), "SOLO_HITO");
  assert.equal(hitoCumpleObjetivo(3.8, C), "SI");
  assert.equal(hitoCumpleObjetivo(2.9, C), "NO");
  assert.equal(hitoCumpleObjetivo(null, C), null);
});

test("a plan whose net reward falls short says so with both numbers", () => {
  assert.equal(llegaAlObjetivo(3.5, C), true);
  assert.equal(llegaAlObjetivo(2.1, C), false);
  assert.equal(llegaAlObjetivo(null, C), null);
  const aviso = avisoObjetivoCorto(2.1, C);
  assert.match(aviso ?? "", /2\.10 % neto/);
  assert.match(aviso ?? "", /\+3\.2 % neto/);
  assert.equal(avisoObjetivoCorto(3.5, C), null);
  assert.equal(avisoObjetivoCorto(null, C), null);
});

test("a goal moved to 4.2 net changes every text, with no hardcoded 3.2 left", () => {
  const movido: Contrato = {
    ...C,
    objetivo_operador: { pct: 4.2, tipo: "NETO", etiqueta: "+4.2 % neto", coste_pct: 0.5 },
    objetivo_operador_bruto: { pct: 4.7, tipo: "BRUTO", etiqueta: "+4.7 % bruto", coste_pct: 0.5 },
  };
  assert.match(textoObjetivo(movido), /\+4\.2 % neto/);
  assert.match(textoObjetivo(movido), /\+4\.7 % bruto/);
  assert.equal(llegaAlObjetivo(3.5, movido), false);      // antes pasaba
  assert.equal(hitoCumpleObjetivo(4.0, movido), "SOLO_HITO");
});
