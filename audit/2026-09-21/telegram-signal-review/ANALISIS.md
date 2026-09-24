# Cómo se comportan las señales después del aviso

**Fecha de la medición:** 21-sep-2026, 22:04 UTC (22-sep 00:04 en el servidor).
**Fuente:** `/home/flox/sacbinance/backend/data/sacbinance.db` en producción, abierta en **solo lectura** (`mode=ro`, `PRAGMA query_only`, transacción revertida). No se escribió nada en el servidor ni se tocó el servicio.
**Ventana de evaluación:** 12 h por señal — el mismo `signal_expiry_hours` del sistema — reconstruida vela a vela con las velas de 1 minuto. Una vela cuenta solo si su minuto entero cae dentro de la ventana.
**Coste asumido:** 0,5 % por operación (`coste_operacion_pct`), restado a todo resultado.

---

## 1. Qué datos hay y hasta dónde llegan

| | |
|---|---|
| Avisos enviados a Telegram | **256** (11-sep 23:49 → 21-sep 22:03 UTC) |
| Con niveles válidos y velas | 255 |
| **Cohorte evaluable** (ventana de 12 h completa, o resuelta antes en TP/SL) | **229** |
| Excluidos por ventana aún abierta | 26 |
| Señales generadas en total (tabla `signals`) | 6.202 |
| **Señales evaluables** | **4.513** |
| Excluidas por no tener velas de 1 m (anteriores al 8-sep, purgadas) | 1.500 |
| Excluidas por ventana aún abierta | 189 |
| Cobertura media de velas en la cohorte de Telegram | 99,4 % |

**Validación contra el propio sistema.** La reconstrucción no inventa etiquetas: coincide con `notificacion_planes` en **46 TP, 46 SL y 88 VENCIDO, sin una sola discrepancia**, y con `signals.status` en 4.655 de 4.702 casos (99 %). Además, **en ninguna señal la misma vela de un minuto tocó el TP y el SL a la vez**, así que el orden de los toques no es ambiguo en ningún caso.

**El perfil de los planes enviados es distinto del de las señales en general**, y eso explica buena parte de lo que sigue:

| | TP mediano | SL mediano | Umbral «cerca del SL» (80 % del recorrido) | TP ≥ 3,2 % |
|---|---|---|---|---|
| Enviados a Telegram | **+6,72 %** | −3,36 % | −2,69 % | 98 % |
| Todas las señales | +2,85 % | −1,42 % | −1,14 % | 43 % |

El TP sale de `stop × 2` (`rr_target = 2,0`), así que cuanto más ancho es el stop, más lejos queda el TP. Los avisos se quedan con los planes de stop ancho.

---

## 2. Las cinco preguntas, sobre los avisos de Telegram (n = 229)

Las familias son excluyentes y cubren el 100 % de la cohorte. «Cerca del SL» = el precio llegó al 80 % del camino entre la entrada y el stop, el mismo umbral con el que el sistema manda el aviso `CERCA_SL`.

| | Familia | n | % | Aporte al resultado |
|---|---|---|---|---|
| **1** | **A · Camino tranquilo:** tocó TP con retroceso previo ≤ 1 % y sin acercarse al stop | **23** | 10,0 % | +122,7 pp |
| **2** | **B · Rozó el stop y aun así tocó el TP** | **8** | 3,5 % | +39,9 pp |
| — | C · Tocó TP con retroceso intermedio (> 1 %, sin rozar el stop) | 27 | 11,8 % | +163,4 pp |
| **3** | **D · Perforó el stop y después tocó el TP** | **8** | 3,5 % | −26,3 pp |
| **4** | **E · Tocó el stop y no volvió ni al +0,4 % sobre la entrada** | **41** | 17,9 % | −149,4 pp |
| — | F · Tocó el stop, rebotó por encima del +0,4 %, pero no llegó al TP | 26 | 11,4 % | −93,6 pp |
| — | G · Ni TP ni stop en 12 h | 96 | 41,9 % | +51,2 pp |
| | **Total** | **229** | | **+107,9 pp** (+0,47 pp por señal) |

Lo primero que salta: **la familia más numerosa no es ninguna de las cinco que preguntaste, es la G** — 42 de cada 100 avisos no resuelven nada en 12 horas. La segunda es la E: stop tocado y sin retorno.

### 2.1 · Variación pequeña (±1 %), sin acercarse al stop, y TP tocado — 23 casos (10,0 %)

Retroceso mediano antes del TP: **−0,28 %**. Tiempo mediano hasta el TP: **2,3 h**. Son los avisos que funcionaron como está previsto: entras y sube sin darte un susto. Veinte de los 23 ocurrieron entre el 18 y el 21 de septiembre, el tramo alcista del periodo.

### 2.2 · Rozaron el stop y llegaron al TP — 8 casos (3,5 %)

Retroceso mediano antes del TP: **−2,24 %**; tiempo mediano hasta el TP: **4,8 h**. Ninguno llegó a tocar el stop: el sistema mandó el aviso `CERCA_SL` y el plan acabó ganando. Si cierras al recibir ese aviso, estos ocho se convierten en pérdidas pequeñas.

### 2.3 · Tocaron el stop (o se pasaron poco) y después el TP — 8 casos (3,5 %)

| Cuánto se pasó del stop | Casos |
|---|---|
| Hasta 0,5 % por debajo | 2 |
| Entre 0,5 % y 1 % | 1 |
| Más de 1 % | 5 |

Exceso mediano por debajo del stop: **−1,11 %**. Tiempo mediano del stop al TP: **5,9 h**. De los ocho, solo tres se pasaron «por poco»; en los otros cinco el precio se hundió de verdad antes de girar, y aguantar habría significado ver caídas de −5 % y −9,5 %.

### 2.4 · Tocaron el stop y no se recuperaron ni al +0,4 % — 41 casos (17,9 %)

La familia que más pesa en negativo. Tiempo mediano hasta el stop: **4,1 h**. Caída total mediana: **−5,46 %**. Máximo posterior mediano: **−1,42 %** — ni se acercaron otra vez a la entrada. En 12 de los 41 el precio llegó a tocar el +3,2 % en algún momento de la ventana, casi siempre **después** del stop y sin llegar nunca al TP.

### 2.5 · Tocaron el +3,2 % y no tocaron el TP — 69 casos

De los 229 avisos, **134 (58,5 %) llegaron a tocar el +3,2 %**. **De esos 134, 69 (51,5 %) nunca tocaron su TP.** El TP mediano que pedían esos 69 era **+7,79 %** y el máximo que realmente alcanzaron fue **+4,99 %** de mediana. Veintiuno (30 %) acabaron tocando el stop después de haber pasado por el +3,2 %; el cierre mediano a las 12 h fue **+1,39 %**.

**Ese es el hallazgo central: más de la mitad de los avisos que dan la ganancia que tú buscas no la cobran nunca, porque el plan apunta al doble del stop y no a tu meta.**

---

## 3. Las mismas familias, con la meta del 3,2 % como objetivo

Objetivo = **+3,2 % fijo** (mismo stop, misma ventana):

| Familia | Objetivo = TP del plan | Objetivo = +3,2 % |
|---|---|---|
| A · Camino tranquilo hasta el objetivo | 23 (10,0 %) | **57 (24,9 %)** |
| B · Rozó el stop y llegó | 8 (3,5 %) | 12 (5,2 %) |
| C · Retroceso intermedio | 27 (11,8 %) | 53 (23,1 %) |
| D · Stop perforado y luego objetivo | 8 (3,5 %) | 12 (5,2 %) |
| E · Stop sin retorno (≤ +0,4 %) | 41 (17,9 %) | **29 (12,7 %)** |
| F · Stop con rebote parcial | 26 (11,4 %) | 18 (7,9 %) |
| G · Ni objetivo ni stop | 96 (41,9 %) | **48 (21,0 %)** |

- **Objetivo antes que stop:** 25,3 % con el TP del plan → **53,3 % con la meta del 3,2 %**.
- Esperanza por señal: **+0,47 %** (TP del plan) frente a **+0,36 %** (salida fija en 3,2 %) — pero la mediana pasa de **−0,13 %** a **+2,70 %** y las señales con resultado positivo, de 48,5 % a 59,0 %.

Dicho claro: apuntar al 3,2 % **no gana más en total, gana mucho más a menudo**. Con el TP del plan el resultado depende de un puñado de aciertos grandes (la familia C aporta +163 pp con 27 señales); con la meta fija, se reparte.

En la familia D del 3,2 %: de los 12 que perforaron el stop y luego alcanzaron el +3,2 %, **2 se pasaron menos del 0,5 %**, 2 entre 0,5 % y 1 %, y **8 más del 1 %**. Tiempo mediano del stop a la meta: 5,75 h.

---

## 4. Los stops, de cerca

| | Telegram (229) | Todas las señales (4.513) |
|---|---|---|
| Tocan el stop en algún momento | 80 (34,9 %) | 2.511 (55,6 %) |
| Lo tocan antes que el TP | 75 | 2.281 |
| De esos: después tocan el TP | **8 (10,7 %)** | 510 (22,4 %) |
| De esos: después tocan el +3,2 % | 14 (18,7 %) | 345 (15,1 %) |
| De esos: no pasan del +0,4 % | **41 (54,7 %)** | 1.149 (50,4 %) |
| Cuánto se pasan del stop (mediana / p90) | −2,14 % / −6,97 % | −1,52 % / −4,96 % |
| Tiempo mediano hasta el stop | 3,2 h | 2,5 h |
| Tiempo mediano hasta el TP | 4,8 h | 4,4 h |
| Tiempo mediano hasta el +3,2 % | 3,3 h | 4,8 h |

Cuando el stop se toca, **la mitad de las veces no hay vuelta**, y cuando la hay el precio suele haberse ido bastante más abajo antes de girar (mediana −2,14 %). «Aguantar un poco más del stop» sirvió en 8 de 75 casos.

---

## 5. Las señales generadas en general (n = 4.513)

| Familia (objetivo = TP del plan) | n | % |
|---|---|---|
| A · Camino tranquilo | 959 | 21,2 % |
| B · Rozó el stop y llegó al TP | 131 | 2,9 % |
| C · Retroceso intermedio | 155 | 3,4 % |
| D · Stop perforado y luego TP | 510 | 11,3 % |
| E · Stop sin retorno | 1.148 | 25,4 % |
| F · Stop con rebote parcial | 623 | 13,8 % |
| G · Ni TP ni stop | 987 | 21,9 % |

- Tocan el TP antes que el stop: **27,6 %**. Tocan el +3,2 % antes que el stop: **29,0 %**.
- Esperanza por señal: **−0,24 %** con el TP del plan y **−0,25 %** con la meta del 3,2 %. **El conjunto de las señales generadas pierde dinero**; la cohorte enviada a Telegram, no.
- El «camino tranquilo» es más frecuente que en Telegram (21,2 % frente a 10,0 %) por aritmética, no por calidad: su TP mediano es +2,85 %, menos de la mitad.

### El filtro de avisos sí selecciona (mismo periodo, alertas con niveles)

| | n | TP antes que stop | +3,2 % antes que stop | Esperanza (TP) | TP mediano |
|---|---|---|---|---|---|
| **Enviadas** | 229 | 25,3 % | **53,3 %** | +0,47 % | 6,72 % |
| Descartadas | 7.719 | 29,3 % | 33,2 % | +0,02 % | 3,09 % |

Medido contra la meta que a ti te importa —llegar al 3,2 % antes que al stop— **el filtro separa bien: 53 % frente a 33 %**.

### Qué descartó cada motivo

| Motivo del descarte | n | +3,2 % antes que stop | TP mediano |
|---|---|---|---|
| TP neto inferior a la meta configurada | 2.620 | 32,5 % | 2,32 % |
| Sin rebote confirmado | 2.593 | **20,3 %** | 2,31 % |
| **Resistencia antes del TP** | 1.118 | **50,4 %** | 5,95 % |
| Volumen insuficiente o sin medir | 444 | 38,5 % | 6,36 % |
| Score inferior al filtro | 354 | 41,2 % | 6,52 % |
| **Límite global de 3 oportunidades/hora** | 336 | **45,5 %** | 6,63 % |
| **Ya hay un plan notificado para ese par** | 214 | **56,5 %** | 8,27 % |
| *(referencia: enviadas)* | 229 | 53,3 % | 6,72 % |

El filtro de rebote confirmado hace su trabajo: lo que descarta es malo de verdad (20,3 %). Los tres en negrita, no. **«Resistencia antes del TP» y los dos topes de capacidad están tirando señales tan buenas como las que se envían** — «ya hay un plan notificado» descarta, de hecho, el mejor grupo de todos. El veto por resistencia protege un TP lejano que se cobra menos de la mitad de las veces; con objetivo de 3,2 % sobraría en muchos casos.

### Cortes dentro de la cohorte de Telegram

| Corte | n | TP antes que stop | +3,2 % antes que stop | Caída máxima mediana |
|---|---|---|---|---|
| Escenario SUBIENDO | 208 | 26,4 % | 55,3 % | −2,16 % |
| Escenario TOCÓ_FONDO | 20 | **10,0 %** | **35,0 %** | **−4,85 %** |
| Score 70–79 | 63 | 27,0 % | 49,2 % | −3,51 % |
| Score 80–89 | 153 | 26,1 % | 55,6 % | −2,12 % |
| Score 90–100 | 13 | **7,7 %** | 46,2 % | −1,80 % |
| TP < 4 % | 28 | 28,6 % | 39,3 % | −2,88 % |
| TP 4–7 % | 92 | 32,6 % | 55,4 % | −2,27 % |
| TP ≥ 7 % | 109 | 18,3 % | 55,0 % | −2,39 % |

Dos cosas. **El escenario de rebote (TOCÓ_FONDO) es claramente peor** en todo: menos aciertos y caídas el doble de profundas. Y **el score no ordena nada**: los de 90–100 no van mejor que los de 70–79. La fila de TP ≥ 7 % resume el informe entero: **misma tasa de llegar al 3,2 % (55 %) y la mitad de tasa de llegar al TP (18 %)**. El TP lejano no cambia el movimiento, solo deja de cobrarlo.

---

## 6. ¿La señal aporta algo, o es la marea?

Control: por cada aviso enviado, **10 entradas al azar en el mismo par**, con **las mismas distancias de TP y stop** y la misma ventana de 12 h, sorteadas dentro del mismo periodo (2.447 controles). Se aísla así lo único que aporta el sistema: **el momento de entrar**.

| | Señal (229) | Azar (2.447) | Diferencia (IC 95 %) |
|---|---|---|---|
| Toca el TP antes que el stop | 25,3 % | 17,9 % | **+7,4 pp [+1,6, +13,1]** |
| Toca el +3,2 % antes que el stop | 53,3 % | 40,5 % | **+12,8 pp [+6,1, +19,6]** |
| Esperanza (TP del plan) | +0,47 % | +0,24 % | +0,23 pp [−0,30, +0,75] |
| Esperanza (objetivo 3,2 %) | +0,36 % | −0,01 % | +0,37 pp [−0,01, +0,76] |
| Máximo a favor (mediana) | +3,90 % | +2,92 % | |
| Caída máxima (mediana) | −2,35 % | −1,92 % | |

**El momento de entrada aporta, y se puede demostrar:** las dos tasas de acierto baten al azar con intervalos que no tocan el cero. **La esperanza, no:** las dos diferencias incluyen el cero, porque la señal también entra en momentos más volátiles —cae más que el azar, −2,35 % frente a −1,92 %— y eso se come parte de la ventaja. Con 229 señales no se puede afirmar más.

---

## 7. Rejilla de objetivo y stop (cohorte de Telegram)

Esperanza media neta por señal con objetivo y stop **fijos** en porcentaje, ventana de 12 h, coste 0,5 %:

| | stop −1,0 | −1,5 | −2,0 | −2,5 | −3,0 | −3,5 | −4,0 | −5,0 | −6,0 |
|---|---|---|---|---|---|---|---|---|---|
| **TP +2,0 %** | −0,43 | −0,28 | −0,14 | +0,02 | +0,09 | +0,24 | +0,33 | +0,42 | +0,43 |
| **TP +3,2 %** | −0,41 | −0,25 | −0,09 | +0,11 | +0,26 | +0,38 | +0,47 | +0,52 | +0,53 |
| **TP +5,0 %** | −0,36 | −0,14 | +0,03 | +0,25 | +0,39 | +0,50 | +0,58 | **+0,64** | +0,63 |
| **TP +6,0 %** | −0,37 | −0,13 | +0,03 | +0,18 | +0,35 | +0,47 | +0,58 | **+0,64** | +0,63 |
| **TP +10,0 %** | −0,39 | −0,18 | −0,02 | +0,13 | +0,25 | +0,36 | +0,50 | +0,60 | +0,60 |

Y el contrafactual más directo — **mismo TP del plan, solo el stop más ancho**:

| Stop | TP antes que stop | Stops tocados | Esperanza |
|---|---|---|---|
| Actual (mediana −3,36 %) | 58 (25,3 %) | 75 | +0,47 % |
| +1 pp más ancho | 63 (27,5 %) | 55 | +0,59 % |
| +2 pp más ancho | 65 (28,4 %) | 38 | +0,65 % |
| +3 pp más ancho | 65 (28,4 %) | 26 | +0,63 % |

Con objetivo fijo en 3,2 % y stop 2 pp más ancho: **57,2 % de aciertos y +0,53 % de esperanza**, frente a 53,3 % y +0,36 % actuales.

**Cómo leer esto sin engañarse:** las diferencias entre celdas vecinas son centésimas sobre 229 señales — ruido, y el intervalo de confianza de la esperanza actual ya incluye el cero. Lo que sí es patrón, porque se repite en toda la rejilla y en el contrafactual: **los stops estrechos (−1 %, −1,5 %) destruyen el resultado en todas las filas**, y ensanchar el stop mejora tasa y esperanza a la vez. La superficie es plana entre +3 % y +6 % de objetivo con stop de −3 % a −5 %; el punto exacto no está determinado por estos datos.

---

## 8. Qué me llevo

1. **El TP está mal colocado para lo que buscas.** El 58,5 % de los avisos toca el +3,2 %, pero solo el 28,8 % toca su TP; de los que llegan al 3,2 %, **la mitad no cobra nunca** y uno de cada tres acaba en el stop después de haber estado en ganancias. Es consecuencia directa de `rr_target = 2,0`: el TP no es una meta, es el stop multiplicado.
2. **La cuenta de los stops es peor que su fama.** 75 avisos tocaron el stop antes que el TP; solo 8 se recuperaron hasta el TP, y en 5 de esos 8 había que tragarse más de un 1 % por debajo del stop. Aguantar no es una estrategia: es apostar a 8 de 75.
3. **Pero el problema es el stop estrecho, no el ancho.** Los stops de −1 % y −1,5 % pierden en todas las combinaciones. El sistema ya usa stops anchos en lo que envía (mediana −3,36 %) y aun así ensancharlos 1–2 pp mejora todo.
4. **La selección del momento funciona; la esperanza todavía no está demostrada.** +12,8 pp sobre el azar en llegar al 3,2 %, con intervalo que no toca el cero. La esperanza, con 229 señales, no se distingue de cero.
5. **Tres filtros están tirando señales buenas:** «resistencia antes del TP» (50,4 %), el tope de 3 avisos por hora (45,5 %) y «ya hay un plan notificado» (56,5 %, el mejor grupo de todos). Los dos últimos no son filtros de calidad, son límites de capacidad.
6. **El escenario de rebote (TOCÓ_FONDO) no está listo:** 10 % de aciertos al TP, 35 % al 3,2 % y caídas de −4,85 % de mediana, frente a −2,16 % en SUBIENDO. Son 20 casos, pero apuntan todos en la misma dirección.
7. **El score no ordena.** 70–79 y 80–89 rinden igual, 90–100 rinde peor. Como criterio de corte para avisar, hoy no aporta información.

## 9. Límites de esta medición

- **229 avisos en 11 días**, más de la mitad entre el 18 y el 21 de septiembre, un tramo alcista. El control aleatorio comparte periodo, así que compensa la marea pero no amplía la muestra.
- **Solo compras**, ventana fija de 12 h, entrada asumida exactamente en `entry` (en real hay deslizamiento; el sistema tolera hasta 0,5 % de desvío antes de enviar) y coste plano de 0,5 %.
- Dentro de una vela de 1 minuto no se sabe el orden de los precios. Aquí no importó: **ninguna señal tocó TP y stop en el mismo minuto**.
- 1.500 señales anteriores al 8-sep quedaron fuera porque la purga ya se llevó sus velas de 1 minuto. Es el mismo agujero que el inventario de auditorías tiene abierto como F12.
- Las familias se calculan sobre el recorrido del precio, no sobre operaciones reales: nadie ejecutó estas entradas.

---

### Reproducir

```
python paths_remote.py     # → datos/paths.json.gz    recorrido vela a vela (se ejecuta por ssh en el servidor, solo lectura)
python rejilla_remote.py   # → datos/rejilla.json.gz  primer toque de cada objetivo y cada stop fijo
python control_remote.py   # → datos/control.json.gz  10 entradas al azar por aviso, mismo par y mismas distancias
python clasificar.py       # familias y recuentos
python agregados.py        # validación, esperanza, la meta del 3,2 %
python control.py          # señal contra azar, con intervalos por bootstrap
python rejilla.py          # rejilla objetivo × stop y contrafactual del stop
python cortes.py           # escenario, score, distancia del TP, día, par, motivos de descarte
python finales.py          # resumen por familia y aporte al resultado
python tablas.py           # → tablas.md, las listas moneda a moneda
```

`detalle_telegram.txt` guarda el volcado completo de las siete familias con una línea por aviso.

---

## Anexo · Las listas, moneda a moneda

_Cohorte de Telegram, ventana de 12 h. «Retroceso antes del TP» es el mínimo alcanzado antes del primer toque del TP; «mínimo en 12 h» incluye lo que pasó después._

#### A · Camino tranquilo hasta el TP

| Par | Aviso (UTC) | TP | SL | Retroceso antes del TP | Mínimo en 12 h | Máx. a favor | t→TP | t→+3,2% | Escenario |
|---|---|---|---|---|---|---|---|---|---|
| KORUBUSDT | 11-Sep 12:37 | +2.62% | −1.31% | -0.22% | -0.48% | +3.52% | 0.3 h | 0.3 h | SUBIENDO |
| TREEUSDT | 12-Sep 13:10 | +5.05% | −2.52% | -0.46% | -3.20% | +5.72% | 1.1 h | 0.1 h | SUBIENDO |
| MSTRBUSDT | 17-Sep 13:54 | +2.18% | −1.08% | -0.28% | -1.48% | +2.65% | 0.5 h | — | BREAKOUT_INCIPIENTE |
| ZAMAUSDT | 18-Sep 07:00 | +5.10% | −2.55% | -0.55% | -0.55% | +18.52% | 0.7 h | 0.6 h | SUBIENDO |
| ETCUSDT | 18-Sep 11:33 | +3.87% | −1.93% | -0.76% | -0.76% | +4.17% | 8.3 h | 5.0 h | SUBIENDO |
| ETHFIUSDT | 18-Sep 11:34 | +8.50% | −4.25% | -0.91% | -0.91% | +9.22% | 6.3 h | 2.0 h | SUBIENDO |
| LINKUSDT | 18-Sep 12:34 | +4.52% | −2.26% | -0.67% | -0.67% | +4.83% | 7.4 h | 2.8 h | SUBIENDO |
| MORPHOUSDT | 18-Sep 21:54 | +7.50% | −3.75% | +0.04% | +0.04% | +17.75% | 2.6 h | 1.1 h | SUBIENDO |
| THETAUSDT | 19-Sep 00:02 | +7.86% | −3.93% | -0.67% | -0.67% | +8.63% | 6.9 h | 2.7 h | SUBIENDO |
| AVAXUSDT | 19-Sep 06:35 | +8.03% | −4.02% | -0.31% | -0.31% | +15.83% | 3.9 h | 2.3 h | SUBIENDO |
| VETUSDT | 19-Sep 06:35 | +7.32% | −3.66% | -0.06% | -0.06% | +7.64% | 0.9 h | 0.2 h | SUBIENDO |
| FILUSDT | 19-Sep 08:05 | +5.59% | −2.79% | +0.05% | +0.05% | +18.12% | 8.5 h | 3.7 h | SUBIENDO |
| STXUSDT | 19-Sep 10:08 | +9.25% | −4.63% | -0.20% | -0.20% | +11.60% | 1.8 h | 1.1 h | SUBIENDO |
| ONDOUSDT | 19-Sep 12:04 | +4.98% | −2.49% | -0.22% | -0.22% | +7.67% | 2.4 h | 0.7 h | SUBIENDO |
| SEIUSDT | 20-Sep 16:31 | +5.46% | −2.73% | -0.02% | -0.02% | +15.13% | 0.5 h | 0.4 h | SUBIENDO |
| SUSDT | 20-Sep 16:31 | +7.07% | −3.54% | -0.69% | -0.69% | +21.36% | 0.5 h | 0.2 h | SUBIENDO |
| MIRAUSDT | 20-Sep 17:33 | +8.43% | −4.22% | -0.59% | -0.59% | +13.81% | 8.5 h | 6.4 h | SUBIENDO |
| GENIUSUSDT | 20-Sep 18:09 | +5.28% | −2.64% | -0.17% | -0.17% | +11.35% | 0.9 h | 0.4 h | SUBIENDO |
| TUSDT | 20-Sep 18:59 | +4.23% | −2.12% | -0.20% | -1.39% | +5.16% | 5.0 h | 5.0 h | SUBIENDO |
| LDOUSDT | 20-Sep 19:03 | +6.59% | −3.29% | -0.53% | -0.53% | +8.47% | 5.8 h | 3.5 h | SUBIENDO |
| XPLUSDT | 21-Sep 02:38 | +3.73% | −1.86% | +0.21% | -0.57% | +12.75% | 0.2 h | 0.2 h | SUBIENDO |
| ARBUSDT | 21-Sep 08:24 | +6.05% | −3.02% | -0.14% | -0.14% | +15.36% | 2.3 h | 0.9 h | SUBIENDO |
| LTCUSDT | 21-Sep 11:33 | +5.02% | −2.51% | -0.92% | -0.92% | +5.24% | 1.6 h | 1.0 h | SUBIENDO |

#### B · Rozaron el stop y aun así tocaron el TP

| Par | Aviso (UTC) | TP | SL | Retroceso antes del TP | Mínimo en 12 h | Máx. a favor | t→TP | t→+3,2% | Escenario |
|---|---|---|---|---|---|---|---|---|---|
| RAYUSDT | 10-Sep 23:49 | +7.27% | −3.64% | -2.96% | -2.96% | +22.86% | 1.3 h | 1.0 h | SUBIENDO |
| MINAUSDT | 17-Sep 10:28 | +3.98% | −1.99% | -1.71% | -1.71% | +7.07% | 4.8 h | 4.0 h | SUBIENDO |
| ATOMUSDT | 18-Sep 15:49 | +4.57% | −2.28% | -2.13% | -2.13% | +5.32% | 11.0 h | 8.5 h | SUBIENDO |
| ALLOUSDT | 19-Sep 08:04 | +4.17% | −2.08% | -2.07% | -2.07% | +9.29% | 4.9 h | 4.7 h | SUBIENDO |
| IOSTUSDT | 20-Sep 04:37 | +8.23% | −4.12% | -3.67% | -3.67% | +10.09% | 2.5 h | 2.4 h | SUBIENDO |
| STRKUSDT | 20-Sep 15:17 | +6.56% | −3.28% | -3.26% | -3.26% | +9.91% | 2.8 h | 0.8 h | SUBIENDO |
| MITOUSDT | 20-Sep 22:56 | +4.06% | −2.03% | -1.70% | -1.70% | +4.66% | 5.4 h | 4.9 h | SUBIENDO |
| POLUSDT | 21-Sep 04:17 | +5.05% | −2.53% | -2.35% | -2.35% | +5.63% | 7.6 h | 6.7 h | SUBIENDO |

#### D · Perforaron el stop y después tocaron el TP

| Par | Aviso (UTC) | TP | SL | Retroceso antes del TP | Mínimo en 12 h | Máx. a favor | t→TP | t→+3,2% | Escenario |
|---|---|---|---|---|---|---|---|---|---|
| ETHFIUSDT | 11-Sep 08:25 | +5.76% | −2.88% | -9.50% | -9.50% | +6.73% | 9.0 h | 7.3 h | TOCÓ_FONDO |
| 牛来USDT | 17-Sep 17:11 | +8.78% | −4.39% | -5.39% | -5.39% | +14.56% | 10.7 h | 10.0 h | TOCÓ_FONDO |
| TAOUSDT | 19-Sep 03:22 | +4.68% | −2.34% | -2.75% | -2.75% | +5.80% | 7.7 h | 6.4 h | SUBIENDO |
| INJUSDT | 20-Sep 09:47 | +3.83% | −1.91% | -2.84% | -3.05% | +4.11% | 6.5 h | 6.4 h | SUBIENDO |
| GENIUSUSDT | 20-Sep 14:11 | +6.76% | −3.38% | -4.86% | -4.86% | +10.50% | 5.0 h | 4.5 h | SUBIENDO |
| HOMEUSDT | 21-Sep 02:38 | +3.83% | −1.92% | -2.71% | -2.71% | +7.84% | 3.6 h | 3.5 h | SUBIENDO |
| CUSDT | 21-Sep 05:47 | +6.52% | −3.26% | -4.97% | -4.97% | +8.80% | 8.7 h | 0.5 h | SUBIENDO |
| VETUSDT | 21-Sep 15:11 | +4.45% | −2.23% | -2.54% | -2.54% | +4.46% | 8.7 h | 7.0 h | SUBIENDO |

#### E · Tocaron el stop y no volvieron ni al +0,4%

| Par | Aviso (UTC) | SL | t→SL | Caída máxima | Máximo tras el stop | ¿Llegó a tocar +3,2%? |
|---|---|---|---|---|---|---|
| SYRUPUSDT | 11-Sep 16:06 | −1.74% | 0.2 h | -6.38% | -0.61% | no |
| JTOUSDT | 11-Sep 16:09 | −2.08% | 1.1 h | -4.34% | +0.36% | no |
| CHZUSDT | 12-Sep 04:25 | −5.06% | 4.1 h | -6.07% | -4.03% | no |
| MARSCOINUSDT | 13-Sep 03:38 | −3.62% | 5.7 h | -10.87% | -2.35% | sí, a las 2.8 h |
| TREEUSDT | 13-Sep 07:47 | −2.71% | 2.7 h | -6.05% | -0.22% | no |
| 牛来USDT | 13-Sep 09:40 | −5.18% | 3.2 h | -11.29% | -2.74% | no |
| KAVAUSDT | 13-Sep 15:34 | −5.33% | 2.2 h | -6.56% | +0.05% | no |
| ARUSDT | 14-Sep 03:15 | −4.26% | 2.1 h | -4.62% | -0.80% | no |
| GLMUSDT | 14-Sep 03:29 | −3.39% | 3.5 h | -8.80% | -2.61% | no |
| SENTUSDT | 14-Sep 20:48 | −4.46% | 7.5 h | -7.35% | -3.77% | no |
| 牛来USDT | 14-Sep 21:12 | −3.34% | 5.1 h | -12.10% | -2.56% | sí, a las 2.9 h |
| IOTAUSDT | 14-Sep 21:44 | −1.91% | 2.9 h | -3.69% | +0.00% | no |
| 牛来USDT | 14-Sep 22:53 | −2.88% | 3.4 h | -11.47% | -1.86% | sí, a las 1.2 h |
| WAXPUSDT | 15-Sep 03:22 | −4.24% | 2.0 h | -6.19% | -1.64% | no |
| QKCUSDT | 15-Sep 08:19 | −2.43% | 7.7 h | -4.71% | -1.06% | no |
| XLMUSDT | 15-Sep 14:56 | −1.82% | 3.7 h | -8.47% | -1.16% | no |
| ASTRUSDT | 15-Sep 18:55 | −3.31% | 5.4 h | -6.62% | -0.06% | no |
| MARSCOINUSDT | 16-Sep 08:43 | −3.72% | 4.4 h | -10.44% | -1.42% | sí, a las 1.4 h |
| MARSCOINUSDT | 18-Sep 04:13 | −4.06% | 1.2 h | -14.23% | -3.78% | no |
| DASHUSDT | 18-Sep 04:40 | −1.99% | 6.1 h | -5.46% | -0.27% | sí, a las 0.3 h |
| VTHOUSDT | 18-Sep 16:22 | −2.54% | 4.3 h | -6.28% | -0.28% | sí, a las 0.6 h |
| XPLUSDT | 18-Sep 23:13 | −5.52% | 5.4 h | -7.12% | -3.04% | no |
| GALAUSDT | 18-Sep 23:59 | −2.04% | 5.7 h | -3.47% | -0.83% | no |
| RENDERUSDT | 19-Sep 15:06 | −2.63% | 6.1 h | -4.88% | +0.19% | no |
| ICPUSDT | 19-Sep 16:08 | −1.88% | 5.9 h | -4.80% | -0.03% | sí, a las 2.8 h |
| SHIBUSDT | 19-Sep 17:03 | −2.14% | 4.1 h | -5.16% | -1.42% | no |
| ETCUSDT | 19-Sep 18:37 | −2.44% | 8.2 h | -3.86% | -1.99% | no |
| TRUMPUSDT | 19-Sep 22:50 | −1.88% | 3.9 h | -4.95% | -1.62% | no |
| INJUSDT | 20-Sep 00:07 | −2.82% | 2.8 h | -7.10% | -0.45% | sí, a las 0.5 h |
| MSTRBUSDT | 20-Sep 01:20 | −1.92% | 1.6 h | -4.99% | -1.55% | no |
| CFXUSDT | 20-Sep 01:40 | −3.36% | 7.0 h | -4.56% | -2.03% | no |
| ZKUSDT | 20-Sep 02:53 | −4.07% | 9.6 h | -5.60% | -3.31% | sí, a las 0.5 h |
| ZENUSDT | 20-Sep 03:06 | −2.11% | 11.2 h | -2.89% | -1.41% | no |
| ARKUSDT | 20-Sep 06:02 | −5.64% | 2.9 h | -7.69% | -2.56% | no |
| ESPUSDT | 20-Sep 06:22 | −2.43% | 2.9 h | -5.30% | -1.44% | no |
| ENSOUSDT | 20-Sep 17:45 | −3.73% | 10.3 h | -4.05% | -1.19% | sí, a las 6.3 h |
| OPUSDT | 21-Sep 06:25 | −2.10% | 9.0 h | -4.47% | +0.00% | sí, a las 6.2 h |
| LSKUSDT | 21-Sep 09:17 | −4.64% | 11.8 h | -4.68% | -3.65% | sí, a las 1.1 h |
| SKLUSDT | 21-Sep 12:28 | −1.95% | 2.9 h | -4.52% | -0.22% | no |
| BNCBUSDT | 21-Sep 16:14 | −3.53% | 3.7 h | -4.24% | -2.19% | no |
| ACEUSDT | 21-Sep 17:07 | −1.98% | 3.0 h | -3.63% | -1.08% | no |

#### Tocaron +3,2% y nunca el TP

| Par | Aviso (UTC) | TP pedido | Máximo alcanzado | t→+3,2% | ¿Stop después? | Cierre a 12 h |
|---|---|---|---|---|---|---|
| COTIUSDT | 11-Sep 06:48 | +6.05% | +5.52% | 1.8 h | no | -2.51% |
| BERAUSDT | 13-Sep 03:30 | +5.54% | +3.37% | 11.4 h | sí, antes | +1.86% |
| MARSCOINUSDT | 13-Sep 03:38 | +7.23% | +5.91% | 2.8 h | sí, después | -10.09% |
| 牛来USDT | 14-Sep 07:14 | +11.48% | +5.65% | 10.7 h | sí, antes | +0.51% |
| 牛来USDT | 14-Sep 21:12 | +6.68% | +3.28% | 2.9 h | sí, después | -7.08% |
| 牛来USDT | 14-Sep 22:53 | +5.76% | +4.02% | 1.2 h | sí, después | -6.89% |
| COTIUSDT | 15-Sep 07:26 | +3.84% | +3.38% | 1.5 h | sí, después | -3.90% |
| MARSCOINUSDT | 16-Sep 08:43 | +7.44% | +6.38% | 1.4 h | sí, después | -8.61% |
| LAUSDT | 16-Sep 11:51 | +3.94% | +3.90% | 0.8 h | sí, después | -1.05% |
| SAGAUSDT | 17-Sep 14:13 | +9.65% | +5.52% | 5.9 h | no | +4.29% |
| ROSEUSDT | 18-Sep 00:29 | +6.81% | +6.47% | 5.3 h | no | +4.17% |
| DASHUSDT | 18-Sep 04:40 | +3.99% | +3.98% | 0.3 h | sí, después | -3.00% |
| PUMPUSDT | 18-Sep 04:40 | +11.87% | +6.39% | 0.2 h | no | +4.45% |
| PENDLEUSDT | 18-Sep 05:35 | +11.39% | +7.38% | 0.9 h | no | +2.13% |
| SUIUSDT | 18-Sep 07:05 | +10.57% | +4.48% | 6.5 h | no | +2.86% |
| 牛来USDT | 18-Sep 08:03 | +11.33% | +3.39% | 0.4 h | sí, después | -3.12% |
| AAVEUSDT | 18-Sep 08:13 | +7.49% | +5.71% | 5.1 h | no | +3.49% |
| PROVEUSDT | 18-Sep 11:26 | +9.81% | +7.72% | 4.8 h | no | +6.21% |
| ZECUSDT | 18-Sep 12:35 | +10.18% | +8.49% | 2.7 h | no | +7.04% |
| PENGUUSDT | 18-Sep 13:35 | +7.88% | +6.06% | 1.3 h | no | +2.58% |
| SOLUSDT | 18-Sep 13:37 | +8.56% | +7.16% | 1.1 h | no | +5.89% |
| AXSUSDT | 18-Sep 13:39 | +7.92% | +5.27% | 10.4 h | no | +0.99% |
| CFGUSDT | 18-Sep 16:02 | +5.44% | +4.23% | 0.8 h | no | +3.90% |
| VTHOUSDT | 18-Sep 16:22 | +5.09% | +3.21% | 0.6 h | sí, después | -4.19% |
| ROSEUSDT | 18-Sep 16:59 | +8.69% | +3.24% | 5.9 h | no | -0.54% |
| LTCUSDT | 18-Sep 17:14 | +5.94% | +5.58% | 5.2 h | no | +4.07% |
| PLUMEUSDT | 18-Sep 18:09 | +7.04% | +3.70% | 8.4 h | no | +0.57% |
| AVAXUSDT | 18-Sep 18:28 | +9.23% | +7.24% | 7.2 h | no | +2.98% |
| ZKUSDT | 18-Sep 20:25 | +5.58% | +4.95% | 2.1 h | no | +1.19% |
| ORDIUSDT | 18-Sep 20:42 | +6.48% | +5.74% | 3.4 h | no | +1.97% |
| SEIUSDT | 19-Sep 01:25 | +9.00% | +4.15% | 9.7 h | no | +3.29% |
| POLUSDT | 19-Sep 01:25 | +11.69% | +4.55% | 1.1 h | no | +1.39% |
| REDUSDT | 19-Sep 06:30 | +7.31% | +3.35% | 2.3 h | no | -1.14% |
| XPLUSDT | 19-Sep 08:05 | +7.99% | +3.75% | 8.2 h | no | +2.07% |
| HOMEUSDT | 19-Sep 09:05 | +6.10% | +4.30% | 7.6 h | no | +3.34% |
| LDOUSDT | 19-Sep 09:47 | +9.71% | +5.16% | 3.2 h | no | +2.23% |
| 0GUSDT | 19-Sep 13:42 | +6.44% | +6.39% | 3.0 h | no | -0.72% |
| ALLOUSDT | 19-Sep 13:48 | +6.03% | +5.64% | 3.2 h | sí, después | +3.26% |
| ICPUSDT | 19-Sep 16:08 | +3.76% | +3.41% | 2.8 h | sí, después | -3.44% |
| HEIUSDT | 19-Sep 18:50 | +8.98% | +6.14% | 0.6 h | no | -0.82% |
| JTOUSDT | 19-Sep 20:06 | +8.34% | +5.14% | 2.7 h | no | +4.19% |
| TIAUSDT | 19-Sep 21:26 | +4.44% | +3.93% | 1.6 h | no | +1.86% |
| SUSDT | 19-Sep 23:17 | +10.99% | +9.47% | 6.2 h | no | +7.05% |
| INJUSDT | 20-Sep 00:07 | +5.64% | +3.90% | 0.5 h | sí, después | -2.69% |
| CFGUSDT | 20-Sep 01:41 | +6.24% | +3.56% | 9.7 h | no | -1.46% |
| ZKUSDT | 20-Sep 02:53 | +8.15% | +4.66% | 0.5 h | sí, después | -4.92% |
| PHAUSDT | 20-Sep 03:06 | +8.74% | +5.14% | 3.4 h | no | +4.00% |
| WLDUSDT | 20-Sep 04:39 | +4.15% | +3.99% | 11.8 h | sí, antes | +3.80% |
| LSKUSDT | 20-Sep 06:33 | +8.84% | +7.72% | 9.4 h | sí, antes | -3.51% |
| EIGENUSDT | 20-Sep 08:04 | +4.46% | +3.48% | 8.7 h | sí, antes | +1.96% |
| OPUSDT | 20-Sep 09:13 | +9.24% | +7.77% | 7.7 h | no | +0.73% |
| CELOUSDT | 20-Sep 12:03 | +8.13% | +3.93% | 10.3 h | no | +3.40% |
| APTUSDT | 20-Sep 12:06 | +10.89% | +4.36% | 5.5 h | no | +1.36% |
| JTOUSDT | 20-Sep 14:04 | +10.13% | +4.75% | 2.9 h | no | +0.66% |
| AEROUSDT | 20-Sep 15:02 | +6.56% | +5.30% | 9.5 h | no | +1.25% |
| BERAUSDT | 20-Sep 15:12 | +10.61% | +5.54% | 1.1 h | no | +2.91% |
| ENSOUSDT | 20-Sep 17:45 | +7.47% | +6.23% | 6.3 h | sí, después | -1.38% |
| XTZUSDT | 20-Sep 20:29 | +7.79% | +3.30% | 5.2 h | no | -1.55% |
| GRTUSDT | 20-Sep 21:07 | +11.71% | +5.07% | 4.2 h | no | +5.07% |
| PUMPUSDT | 20-Sep 21:17 | +7.86% | +6.15% | 3.5 h | no | +4.20% |
| HBARUSDT | 20-Sep 21:50 | +10.19% | +3.46% | 11.7 h | no | +3.01% |
| SKLUSDT | 21-Sep 00:06 | +6.55% | +5.57% | 9.3 h | no | +3.34% |
| MORPHOUSDT | 21-Sep 03:05 | +7.22% | +3.45% | 0.9 h | no | +0.18% |
| OPUSDT | 21-Sep 06:25 | +4.21% | +3.38% | 6.2 h | sí, después | -2.98% |
| HOMEUSDT | 21-Sep 07:39 | +9.81% | +6.73% | 2.7 h | no | +2.49% |
| TUSDT | 21-Sep 07:59 | +5.58% | +3.54% | 1.6 h | no | +1.38% |
| LSKUSDT | 21-Sep 09:17 | +9.27% | +8.18% | 1.1 h | sí, después | -3.84% |
| BOMEUSDT | 21-Sep 10:02 | +8.22% | +4.99% | 5.0 h | no | +0.85% |
| HBARUSDT | 21-Sep 11:27 | +4.77% | +3.62% | 4.6 h | no | +2.77% |