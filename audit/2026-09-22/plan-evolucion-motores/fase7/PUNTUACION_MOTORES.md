# ¿Aciertan los dos motores? · 24-sep-2026

Cierra el pendiente que la fase 4 dejó abierto: **«predicciones en sombra sobre datos nuevos»**. Los motores llevaban desde el 22-sep 06:41 UTC escribiendo lecturas y nunca se había puntuado ninguna.

No es un flequillo. La fase 5 mide **objetivos de salida**; la **selección** —cuál de las diecisiete tomar, que con una posición es la palanca real— depende de estos motores. Si no aciertan, la fase 7 no tiene nada que activar por ese lado.

**Respuesta corta: el veredicto del motor de continuación no ordena (AUC 0,501). Sus etiquetas de detalle sí separan, y el ancla de 1h se queda a medio camino de lo que la fase 4 prometía.**

---

## 0 · Antes de nada: un sesgo que inflaba todo lo anterior

La primera pasada dio números preciosos. Uno de ellos era imposible: las lecturas **DATOS_INSUFICIENTES** —las que dicen «me falta el dato de 1h»— acertaban el 79 % y sacaban **+45,91 pp** de habilidad. Algo que declara no saber nada no puede ser lo que mejor predice.

No lo era. Esos 53 planes tenían una **cobertura media de 0,694**, y uno de 0,351.

`plan_recorrido` marca `completa = 1` cuando la ventana de 12 h **vence**, sin mirar cuántas velas llegó a ver. Y las velas que faltan no se pierden al azar:

> Una vela ausente borra la barrera que más se toca, y la que más se toca es **la más cercana**. En estos planes la más cercana es el stop. **Faltar datos fabrica objetivos.**

Medido sobre 1.681 recorridos resueltos:

| cobertura | n | acierta | base geométrica | habilidad aparente |
|---|---|---|---|---|
| < 0,50 | 43 | 39,5 % | 33,3 % | +6,20 pp |
| 0,50 – 0,75 | 39 | 59,0 % | 33,3 % | **+25,64 pp** |
| 0,75 – 0,90 | 10 | 60,0 % | 33,3 % | **+26,67 pp** |
| 0,90 – 0,99 | 146 | 47,9 % | 33,3 % | +14,61 pp |
| **≥ 0,99** | **1.443** | **35,8 %** | 33,3 % | **+2,49 pp** |

La habilidad aparente cae de forma monótona conforme sube la cobertura, y en el tramo limpio es **+2,49 pp**: casi nada, que es lo que uno espera de un sistema que todavía no ha demostrado saber elegir.

**Qué se lleva por delante:** todo número retrospectivo sacado de `plan_recorrido` sin filtrar cobertura. El 38,02 % de acierto de la tabla de poblaciones de la fase 6 **es 35,8 %** con el suelo puesto. Dos puntos y medio de aire.

**Qué NO se lleva por delante:** la fase 5. Tiene su propio suelo (`COBERTURA_MINIMA = 0,90`) y, medido ahora, solo **33 de sus 14.642 medidas (0,2 %)** están por debajo de 0,99 — y las 33 resolvieron en STOP, o sea en la dirección contraria al sesgo. **El registro congelado no se toca y no hace falta tocarlo.**

Todo lo que sigue lleva **suelo de cobertura ≥ 0,99**.

## 1 · El motor de continuación no ordena

1.907 planes, 262 pares.

| veredicto | n | pares | acierta | habilidad | IC 95 % |
|---|---|---|---|---|---|
| todas (referencia) | 1.907 | 262 | 31,4 % | −1,98 pp | [−4,95, +1,03] |
| **CANDIDATO** | 95 | 58 | 32,6 % | **−0,71 pp** | [−10,88, +8,82] |
| ESPERAR | 310 | 149 | 38,1 % | +4,73 pp | [−1,90, +11,14] |
| CONFLICTO | 33 | 20 | 42,4 % | +9,09 pp | [−13,98, +30,77] |
| SIN_TESIS | 1.441 | 253 | 28,9 % | −4,41 pp | [−7,24, **−1,27**] |

**CANDIDATO contra todo lo demás: +1,34 pp. AUC 0,501.**

Es el mismo número que tumbó a la puntuación antigua. El veredicto de alto nivel del motor **no separa las buenas de las malas**, y por lo tanto no sirve hoy como filtro de selección. Decir lo contrario sería repetir exactamente el error que este proyecto lleva meses desmontando.

Lo que sí separa, en negativo: **SIN_TESIS** (−4,41 pp, intervalo por debajo de cero). El motor sabe reconocer cuándo *no* hay nada, aunque no sepa reconocer cuándo sí.

## 2 · Las familias sí dicen algo

| familia | n | pares | acierta | habilidad | IC 95 % |
|---|---|---|---|---|---|
| **RUPTURA_RETEST** | 162 | 96 | 45,7 % | **+12,34 pp** | [**+2,97**, +21,62] |
| EXPANSION_COMPRESION | 10 | 9 | 50,0 % | +16,63 pp | [−15,14, +55,50] |
| RUPTURA_SOSTENIDA | 234 | 110 | 31,6 % | −1,71 pp | [−9,03, +5,88] |
| EXTENDIDO | 32 | 29 | 31,2 % | −2,09 pp | [−17,21, +15,05] |

**RUPTURA_RETEST es la única cuyo intervalo excluye el cero**, sobre 96 pares distintos. Es la familia que espera a que el precio vuelva al nivel roto y lo confirme.

Salvedad obligatoria: son **cuatro familias miradas a la vez**, y con cuatro comparaciones una sale bonita por azar más a menudo de lo que el 95 % sugiere. No es un hallazgo: es un candidato a prueba prospectiva, y hasta que la pase no se le da ningún peso.

## 3 · El ancla de 1h se queda a medio camino

La fase 4 midió **+8,46 pp [+4,23, +12,69]** para la ruptura alcista de 1h contra control pareado, y aguantó al partir la muestra. Fue el primer resultado de este proyecto que sobrevivió a esa prueba.

Sobre planes reales:

| dirección del ancla | n | pares | acierta | habilidad | IC 95 % |
|---|---|---|---|---|---|
| RUPTURA_ALCISTA | 412 | 147 | 37,6 % | **+4,28 pp** | [**−1,33**, +9,92] |
| SIN_RUPTURA | 1.149 | 246 | 29,7 % | −3,67 pp | [−7,04, −0,18] |
| RUPTURA_BAJISTA | 318 | 137 | 26,4 % | −6,92 pp | [−12,09, **−1,40**] |

**La mitad del efecto, y el intervalo ya toca el cero.** Sigue siendo lo mejor que hay y el orden es el correcto, pero sobre esta población no se sostiene como se sostenía sobre rupturas.

Lo que sí se reproduce con fuerza es el lado feo: **una ruptura bajista de 1h predice que el plan comprador va a fallar** (−6,92 pp, intervalo entero por debajo de cero). La fase 4 ya lo había dicho al revés de la regla popular; aquí se confirma sobre planes de verdad.

## 4 · El motor de caída: cero disparos, y eso está bien

**0 candidatos de compra en dos días.** Es lo que se le pidió: no anticipar suelos.

Sus **estados** sí clasifican:

| estado | n | pares | acierta | habilidad | IC 95 % |
|---|---|---|---|---|---|
| **BASE_EN_FORMACION** | 205 | 115 | 22,0 % | **−11,39 pp** | [−18,76, **−3,62**] |
| RECUPERACION | 734 | 193 | 33,9 % | +0,60 pp | [−3,77, +5,19] |
| SIN_CAIDA | 939 | 231 | 31,6 % | −1,73 pp | [−6,01, +2,50] |

**Comprar mientras el motor ve una base formándose es claramente peor** que la media. Es el hallazgo más limpio de toda esta medición, y es un filtro **negativo** — el tipo que este proyecto ya sabe que suele ser más fiable que los positivos.

Sin el suelo de cobertura, RECUPERACION salía con **+14,33 pp [+9,06, +19,66]** y parecía el gran hallazgo. Con el suelo es **+0,60 pp**. Era el sesgo entero.

## 5 · Un residuo que no sé explicar

Con cobertura ≥ 0,99 siguen quedando **28 lecturas DATOS_INSUFICIENTES** que aciertan el 64,3 % (habilidad +30,95 pp, n=28, 20 pares).

Lo comprobado: no se concentran en ningún reinicio (el motor no tuvo ni un hueco de más de 20 min en tres días), están repartidas por todo el periodo, y su geometría es normal (objetivo 4,97 %, stop 2,49 % de mediana, base 33,4 %).

Hipótesis, **no hallazgo**: al ancla de 1h se le exige tener menos de 4 h (`motores_ancla_max_edad_min = 240`). Un par sin lectura reciente de 1h es un par que **cotiza poco**, y los pares delgados alcanzan un ±5 % más a menudo. Si es eso, «me falta el dato» está funcionando como un proxy accidental de liquidez.

Con n=28 y una de cinco celdas miradas, no da para más que anotarlo y vigilarlo.

## 6 · Qué significa esto para la fase 7

| | |
|---|---|
| ¿Sirve el veredicto del motor como filtro de selección? | **No.** AUC 0,501 |
| ¿Hay algo que sí separe? | RUPTURA_RETEST (+12,34), y en negativo SIN_TESIS, BASE_EN_FORMACION y el ancla bajista |
| ¿Se activa algo con esto? | **No.** Es retrospectivo, dos días, un régimen y comparaciones múltiples |
| ¿Cambia el plan? | No. La fase 7a sigue congelada y apagada; su puerta 1 es el informe de la fase 5 |

Lo que estos números aportan es **una lista de candidatos para la siguiente prueba prospectiva**, no un filtro para encender. Y aportan algo más valioso: el suelo de cobertura, que a partir de ahora hay que poner en cualquier medición retrospectiva de este sistema.

## Salvedades

- Retrospectivo sobre lecturas ya guardadas: es de donde sale la pregunta, no el veredicto.
- **Dos días, un solo régimen.** La tasa base de este sistema se movió 15 puntos en una semana.
- La habilidad descuenta la geometría del plan, **no** el régimen.
- Cuatro familias y cinco veredictos mirados a la vez: con nueve celdas, alguna cruza el cero por azar.

Reproducir:

```bash
ssh sac '/home/flox/sacbinance/backend/venv/bin/python - 0.99' < puntuar_motores_remote.py
```
