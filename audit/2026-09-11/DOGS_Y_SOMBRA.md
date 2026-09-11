# Tu operación de DOGS, y la medición en sombra

## 1. Tu operación salió mejor de lo que recordabas

Contra las velas reales de Binance:

| | |
|---|---|
| Compra | 10/09 **11:34** a 0,00004514 |
| Venta | 10/09 **20:52** a 0,00004800 |
| Duración | 9,3 horas |
| **Resultado bruto** | **+6,34%** |
| Menos 0,2% de comisión | **+6,14%** |

No fue "poco más de 4%": fue **+6,34%**. 

**Vendiste prácticamente en el pico de tu ventana.** El máximo entre tu compra y tu venta fue 0,00004802 — a las 20:52, el mismo minuto en que vendiste. Dejaste 0,04 puntos sobre la mesa.

**Después de vender siguió subiendo:** llegó a 0,00005000 a las 21:49 (+10,77% sobre tu compra). Pero luego se dio la vuelta: ahora está en 0,00004763, o sea **−0,77% por debajo de tu precio de venta**. Vender a esa hora fue, a día de hoy, mejor que aguantar.

**Tu stop nunca corrió peligro.** La caída máxima que tuviste que aguantar fue **−0,47%**. Con stop del 1,9% o del 2%, ninguno se acercó.

## 2. Dos cosas que corrigen mis análisis anteriores

**DOGS no es "tranquila" por volatilidad de minuto.** Midiendo la hora previa a tu compra: **0,123%**, que cae en el grupo **MOVIDA** (tercer cuartil). Tu percepción de "tranquila" seguramente es la forma del gráfico —subida sostenida sin sustos— y no el ruido minuto a minuto. Son dos cosas distintas, y la segunda es la que yo estaba midiendo.

**El sistema no vio esta operación.** Ese día el score máximo de DOGS fue **45**, con umbral de 60. No emitió señal. Un +6,34% limpio, con −0,47% de drawdown, y el sistema callado.

Históricamente sí emitió 6 señales de DOGS: una al SL (−4,20%) y cinco EXPIRED (+4,76%, +1,97%, +1,35%, +0,40%, −1,21%). Fíjate en la de **+4,76% contada como fallo** por EXPIRED — es justo el problema de nombres del F14.

## 3. Lo intradía cambia el cuadro

Todo mi análisis de ayer medía ventanas de **24h**, porque es la ventana del sistema. Tú operas en **horas**. Medido a horizonte intradía:

| Horizonte | Llega al 3,2% fijo | Llega al objetivo de su grupo |
|---|---|---|
| 3h | 11,5% | **28,0%** |
| 6h | 17,2% | **37,2%** |
| **9h** | **21,8%** | **42,3%** |
| 24h | 30,2% | 49,9% |

Cuando llegan, la mediana es **2,5h al objetivo del grupo** contra **4,8h al 3,2% fijo**. El objetivo por grupo es el doble de compatible con tu estilo.

Y equilibra los grupos, que es lo que debe hacer un objetivo bien calibrado — a 9h: 45,1% / 41,5% / 41,9% / 40,8%. Con el 3,2% fijo va de 15,5% a 32,5%.

## 4. Pero no arregla la ventaja negativa

Aquí está la parte que no quiero que se pierda entre las tablas anteriores. Esperanza neta por operación, horizonte 9h, coste 0,5 puntos:

| Stop | 3,2% fijo | Objetivo por grupo |
|---|---|---|
| 0,8% | −0,752% | **−0,668%** |
| 1,5% | −0,895% | −0,809% |
| 2,0% | −1,003% | −0,925% |

**La mejora es de +0,085 puntos por operación.** Real, medible, y muy pequeña. La tasa de acierto se dobla, pero cada acierto vale proporcionalmente menos y casi se cancela.

Corrijo lo que te dije ayer: puse "objetivo por grupo" como la corrección número 1. Es direccionalmente correcta, pero **no es el arreglo** — vale 0,085 puntos, no los 20+ que faltan. Por eso está bien que vaya en sombra y no en la emisión.

Lo que la operación de DOGS sugiere de verdad: el problema no es el objetivo ni el stop, es que **el sistema no está encontrando los movimientos que importan**. Ese día la oportunidad estaba y el score se quedó en 45.

## 5. Lo que se instrumentó (esquema v12)

Cuatro columnas nuevas en `outcomes`, todas de medición:

- `vol_previa_pct` — volatilidad de la hora anterior, **cruda**, para poder reagrupar el histórico después sin volver a desplegar
- `grupo_vol` — el grupo (MUY_TRANQUILA / TRANQUILA / MOVIDA / MUY_VOLATIL)
- `objetivo_grupo_pct` — el objetivo que le tocaría
- `ms_objetivo_grupo` — cuándo lo alcanza (NULL si no)

Con `ms_objetivo_grupo` se puede filtrar a cualquier horizonte intradía después.

**Garantía de que no toca la emisión** — comprobada, no afirmada: `trade_levels` no menciona los grupos, el engine los usa en **un solo sitio** (el cálculo de la volatilidad previa, dentro del helper que solo alimenta la medición), y el cruce del objetivo no cierra ni veta nada. 29 comprobaciones en `verificar_sombra_grupos.py`, y las 23 de la auditoría siguen en verde.

La migración v11→v12 se probó sobre una copia real de 2.872 filas: todas conservadas, 4 columnas añadidas a NULL, integridad `ok`.

## Límites

- Los cortes de grupo y los objetivos salen de 775 operaciones de 3 días. Son un punto de partida para medir, no una calibración definitiva.
- La comparación de esperanza asume que se entra al precio de la señal y se sale a mercado a las 9h si no se toca nada.
- Análisis de los datos de tu sistema, no una recomendación de inversión.
