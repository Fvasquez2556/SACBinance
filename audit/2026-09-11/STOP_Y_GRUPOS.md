# ¿Qué stop llega mejor al 3,2%? ¿Y se pueden agrupar las monedas?

**11-sep-2026.** Sobre las operaciones **cerradas** (ventana de 24h vencida) del snapshot del 10-sep. La cohorte nueva no sirve para esto: no ha madurado.

## Cómo está medido

Reproduzco cada operación **vela a vela** sobre sus 24h de klines de 1m, en vez de usar la escalera de la tabla — que solo tiene barrotes en 1,0 / 1,2 / 2,0 / 3,2 — para poder barrer el ancho de stop en pasos de 0,1%.

Reglas, las mismas que el tracker en vivo: se entra al precio de la señal, solo cuentan las velas que abren después de la emisión, y si una vela toca stop y objetivo a la vez se cuenta como **stop** (el orden dentro del minuto no se sabe). El coste de 0,5 puntos se descuenta siempre.

**Validación:** el replay reproduce **exactamente** la escalera guardada — 234/775 llegan a +3,2%, cero discrepancias. Las conclusiones no dependen de mi código de simulación.

Muestra: **775** operaciones con velas completas (últimos 3 días) para el barrido fino, y **2.197** para el contraste de 6 días con la escalera.

## 1. No hay un 1,9 ni un 2,2

Esperaba una curva con un máximo. No lo hay:

| Stop | Llega a 3,2% | Parado | Esperanza neta |
|---|---|---|---|
| **0,8%** | 12,0% | 86,3% | **−0,799%** |
| 1,2% | 15,6% | 81,3% | −0,969% |
| 1,6% | 19,4% | 75,2% | −1,075% |
| 2,0% | 21,4% | 71,5% | −1,240% |
| 2,4% | 23,0% | 66,8% | −1,384% |
| 3,0% | 25,8% | 58,5% | −1,511% |
| 4,0% | 27,9% | 48,8% | −1,778% |

La curva **baja de forma continua**. No hay punto óptimo interior, y el "mejor" stop es el más estrecho que probé simplemente porque **pierde menos por pérdida**. Eso es la firma de una ventaja negativa: cuando el sistema pierde dinero, el optimizador siempre dice "arriesga lo mínimo", que en el límite significa "no operes".

Lo contrasté con los 6 días completos usando la escalera (n=2.197). Ahí la pendiente sale al revés (mejora al ensanchar, de −0,590% a −0,214%), pero **es un artefacto de mi supuesto**: en esa versión las operaciones que no tocan nada se cierran planas, y con stops anchos son muchas. La versión de velas usa el precio real de salida y es la que hay que creer. **En lo que coinciden las dos, que es lo importante: la esperanza es negativa con cualquier ancho.**

### La tabla que sí sirve para decidir

Qué tasa de acierto haría falta para no perder dinero:

| Stop | Hace falta que lleguen | Llegan de verdad | Falta |
|---|---|---|---|
| 0,8% | 32,5% | 12,0% | −20,5 pts |
| 1,0% | 35,7% | 13,4% | −22,3 pts |
| 1,5% | 42,6% | 18,3% | −24,3 pts |
| 2,0% | 48,1% | 21,4% | −26,7 pts |
| 3,0% | 56,5% | 25,8% | −30,7 pts |

El hueco no se cierra con el stop: **se ensancha**. Ningún ajuste de gestión de riesgo tapa 20 puntos.

### El dato que explica el hueco

**El 43,0% de las señales toca +3,2% en algún momento de las 24h. Pero solo el 21,4% lo hace antes de caer un 2%.**

La diferencia entre esos dos números es todo el problema: **el movimiento existe, pero la bajada llega primero**. De las que llegaron a la meta, el **52,2% bajó antes de subir** (`DIP_Y_SUBE`) y solo el 47,8% fue directo. Más de la mitad de las ganadoras te habrían sacado con un stop ajustado antes de darte la razón.

## 2. Los grupos: tu intuición acierta en la pregunta, no en la variable

Agrupé por volatilidad medida en **los 60 minutos anteriores a la entrada** — nunca dentro de la ventana, porque elegir el stop sabiendo lo que pasó después es hacer trampa y la regla no se podría aplicar en vivo.

| Grupo | Vol. 1m | Stop óptimo | Esperanza | Llega |
|---|---|---|---|---|
| Muy tranquila | 0,046% | 0,8% | −0,817% | 10,3% |
| Tranquila | 0,087% | 0,8% | −0,937% | 8,8% |
| Movida | 0,132% | 0,8% | −0,846% | 11,3% |
| **Muy volátil** | 0,220% | 0,8% | **−0,595%** | **17,6%** |

**El stop óptimo es 0,8% en los cuatro grupos.** No escala con la volatilidad. La idea de "stop más ancho para monedas volátiles" no aparece en los datos.

Lo que sí cambia mucho es **la tasa de llegada**: las muy volátiles llegan al 3,2% el doble de veces que las tranquilas. La correlación entre volatilidad de una moneda y su tasa de llegar a la meta es **r = +0,37** sobre 74 monedas con 5 o más operaciones.

Otros cortes (mismo patrón: stop óptimo siempre 0,8%, solo cambia la tasa):

| Grupo | Esperanza | Llega | n |
|---|---|---|---|
| **Viene cayendo (−1% la hora previa)** | **−0,577%** | **18,1%** | 94 |
| Plana | −0,848% | 10,6% | 517 |
| Viene subiendo | −0,771% | 12,8% | 164 |
| TOCÓ_FONDO | −0,710% | 13,8% | 109 |
| SUBIENDO | −0,819% | 11,5% | 598 |
| Score 80-100 | −0,706% | 14,3% | 161 |
| Score 0-69 | −0,823% | 12,9% | 202 |

"Viene cayendo" es el mejor grupo — coherente con lo que ya sabías de que la caída previa sí predice. El score discrimina, pero poco: 14,3% contra 12,9% entre el mejor y el peor tramo.

**Ninguno de los grupos cruza a positivo.** Los mejores pierden menos.

### Arquetipos de moneda

Las 74 monedas con ≥5 operaciones se separan con mucha claridad:

**Las que llegan:** COTI (100%, 6 ops), NEAR (100%, 8), MET (86%, 7), ETHFI (86%, 7), PUMP (80%, 10), SAHARA (78%, 9), STRK (70%, 10).

**Las que nunca:** ETH, SOL, LTC, BCH, XLM, AAVE, TIA, CHZ, FLOKI, SUSHI — **todas al 0%**.

El patrón es limpio: **las grandes no viajan un 3,2% en un día**. ETH con 665M de volumen, SOL con 232M, LTC con 38M: 0 de 6, 0 de 6, 0 de 8. No es que el sistema falle en ellas — es que ese objetivo no existe en esos gráficos. Con n=5-10 por moneda las cifras individuales son ruidosas; lo sólido es el patrón de conjunto.

## 3. La causa de fondo

Aquí está lo que creo que importa de verdad. Midiendo lo que cada grupo **se mueve de hecho** en 24h desde la entrada:

| Grupo | Sube (mediana) | Sube (p75) | **Baja (mediana)** | Llega a 3,2% |
|---|---|---|---|---|
| Muy tranquila | 1,23% | 2,75% | **−3,48%** | 23,7% |
| Tranquila | 1,38% | 3,16% | **−4,41%** | 24,7% |
| Movida | 1,81% | 3,74% | **−4,92%** | 30,9% |
| Muy volátil | 2,49% | 6,00% | **−6,06%** | 41,5% |

Dos cosas, y las dos son anteriores a cualquier decisión de stop:

1. **En ningún grupo la señal mediana llega al 3,2%.** Ni siquiera las muy volátiles (2,49%). El objetivo está fuera del alcance de la mitad de lo que el sistema emite, en todos los grupos.
2. **En todos los grupos la caída máxima mediana es más profunda que la subida máxima mediana.** −3,48% contra +1,23% en las tranquilas. La asimetría va en tu contra antes de que elijas nada.

Eso no es un problema de gestión de riesgo. Es que **la señal mediana no va a donde tiene que ir**.

## Qué haría yo

**Lo que no haría:** buscar el stop. No está ahí. Cualquier número que eligiera sería elegir cuánto perder, no si ganar.

**Lo que sí, por orden:**

1. **Objetivo por grupo, no fijo.** El 3,2% es el mismo para ETH que para PUMP, y eso no tiene sentido con estos datos. Un objetivo escalado a lo que la moneda se mueve de verdad — mediana de subida de su grupo, o un múltiplo de su volatilidad — es la primera corrección. Esto cambia `trade_levels`, no un umbral.

2. **Filtrar por lo que ya discrimina.** "Viene cayendo" y "muy volátil" son los dos cortes que más separan (18,1% y 17,6% contra 8,8% del peor). Cruzarlos y medir ese subconjunto es barato y se puede hacer en sombra sin tocar la emisión.

3. **Quitar del universo lo que no puede llegar.** Si ETH, SOL y LTC no hacen 3,2% en un día, emitir señales sobre ellas con ese objetivo es ruido garantizado. Eso sí es un filtro de universo.

4. **La entrada en el hoyo tiene el respaldo teórico correcto** — si el 52,2% de las ganadoras baja antes de subir, entrar abajo es la respuesta a ese patrón. Pero **no lo puedo confirmar con estos datos**: solo 99 de 2.197 filas cerradas tienen medición del hoyo (las columnas son recientes), y esas 99 están seleccionadas por haber bajado cerca del stop, o sea casi todas perdedoras. La comparación honesta sale de la cohorte nueva, donde el 49,3% ya está bajando al hoyo y las columnas se llenan bien.

## Límites de esto

- El barrido fino usa **775** operaciones de los últimos 3 días, que fueron peores que la media (30,2% llegan contra 43,0% de los 6 días). En una racha mejor los números serían menos malos; el **signo** no cambia, porque haría falta duplicar la tasa de llegada.
- Todo es en **largo** y sobre las señales que el sistema emitió: no dice qué habría pasado con otras reglas de entrada.
- Las operaciones que no tocan stop ni objetivo se cierran al precio real de mercado a las 24h.
- El coste de 0,5 puntos es el configurado, no comisiones medidas de tu cuenta.
- Esto es un análisis de los datos de tu sistema, no una recomendación de inversión.

## Reproducir

```bash
backend/venv/Scripts/python.exe audit/2026-09-11/stop_optimo.py
backend/venv/Scripts/python.exe audit/2026-09-11/objetivo_alcanzable.py
```

Salidas en [stop_optimo.txt](stop_optimo.txt) y [objetivo_alcanzable.txt](objetivo_alcanzable.txt).
