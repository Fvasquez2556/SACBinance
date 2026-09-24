# Despliegue del panel de referencias · 22-sep-2026, 03:14 UTC

El desfase que Felix vio en el tablero, explicado y corregido, más los indicadores que pidió. Sin cambio de esquema: solo una consulta nueva, un endpoint y el frontend recompilado.

## El desfase: qué era

En sus capturas, MUBARAKUSDT enseñaba precio 0,0466 y «+35,86 %» sobre una entrada de 0,03413, cuando la división da **+36,54 %**. MEGAUSDT igual (+0,22 % frente a +0,15 %); BERAUSDT cuadraba.

La causa está en dos relojes distintos:

- `price` sale de la vela **en curso** (`SymbolState._compute` usa el cierre parcial del minuto).
- `alerta.delta_pct` lo calcula `AlertManager.actualizar()`, que **solo corre cuando cierra una vela de 1 minuto**.

Los dos números son correctos. Lo que no lo era es enseñarlos juntos como si fueran del mismo instante. Medido en producción sobre las 64 alertas vivas de ese momento:

| Diferencia entre el precio mostrado y el implícito por el porcentaje | |
|---|---|
| Mediana | 0,110 % |
| Percentil 90 | 0,317 % |
| Máximo | 0,861 % |

Signos en las dos direcciones y esa magnitud: es el movimiento de un minuto, no un dato viejo. BERAUSDT cuadraba porque en ese instante la vela en curso valía lo mismo que el último cierre.

**Y la etiqueta engañaba:** «Cambio desde la entrada de referencia» se calcula contra la entrada congelada del plan, no contra otra referencia. Ahora se llama «Cambio desde la entrada del plan».

## Qué se cambió

| Archivo | Cambio |
|---|---|
| `frontend/src/domain/reading.ts` | `cambioDesdeEntrada`, `desfaseDelta`, `inicioDelDiaLocal`, `horaLocal` — funciones puras, con prueba |
| `frontend/src/components/PairDetail.tsx` | El cambio se calcula con el precio que se muestra; la entrada es un botón que despliega cuándo se fijó; filas de primera señal del día, alertas del día y primer plan del episodio |
| `frontend/src/components/PairCard.tsx` | «Desde entrada» calculado con el precio mostrado |
| `frontend/src/components/PairRow.tsx` | Igual, y etiqueta corregida |
| `frontend/src/components/Dashboard.css` | Estilo del valor explicable y de su detalle |
| `frontend/src/types/index.ts` | `ReferenciasPar`, `EpisodioPar`, `AlertaDelDia`, `PlanDeEpisodio` |
| `backend/src/persistence/db.py` | `referencias_par(symbol, desde_ms)` |
| `backend/src/api/routes.py` | `GET /api/pair/{symbol}/referencias?desde_ms=` |
| `backend/tests/test_referencias.py` | 4 pruebas nuevas |
| `frontend/tests/reading.test.ts` | 4 pruebas nuevas, una con los números exactos de la captura |

**El día es el del operador, no el del servidor.** El navegador manda su medianoche local en `desde_ms`. En UTC el corte caería seis horas antes y entre las 18:00 y medianoche GT la «primera del día» sería la equivocada.

## Despliegue

Copia previa en `/home/flox/.cache/sacbinance-referencias-deploy/20260922T031332Z/` (los dos archivos de backend y el `dist` anterior completo). Pruebas en el servidor: **101 en backend**, más 29 en frontend en local. Reinicio por `kill -TERM`; el arranque tardó ~2 min (hidratación de 248 pares más el backfill de calentamiento), sin errores.

Los ficheros `dist/assets` anteriores se dejaron en su sitio a propósito: una pestaña abierta los sigue pidiendo hasta que recarga.

## Verificado en la interfaz de producción

Abriendo el tablero real y el detalle de PEPEUSDT:

- Tarjeta: precio 0,0000051 y «Desde entrada +19,16 %» — la división da exactamente eso.
- Detalle: «Cambio desde la entrada del plan **+19,39 %**» con «Precio actual 0,00000511» — coincide al céntimo.
- Al pulsar la entrada: *«Entrada fijada a las 06:59 a. m. · hace 860 min»*, *«Precio del último cierre de 1m 0,0000051»*, *«Cambio con ese cierre +19,16 %»* y la explicación: *«El precio de arriba es el del minuto en curso y este es el del último minuto cerrado: +0,20 % de diferencia. No es un desfase del dato, son dos instantes distintos.»*
- *«Primera señal del día 12:20 a. m. · entrada 0,00000405 · +26,17 % desde entonces»* y *«Alertas del día en este par: 3 · ninguna a Telegram»*.

Estado del servicio al cerrar: activo, 0 errores, esquema 17, **75 alertas en la última hora y las 75 con identidad**, 60 recorridos evaluados y 9 con desenlace.

Detalle menor corregido sobre la marcha: tras un reinicio, las alertas rehidratadas traen `senal_n = 0`, así que esa fila solo aparece cuando el contador dice algo.
