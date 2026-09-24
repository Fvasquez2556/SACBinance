# Fase 5 · Registro congelado de la prueba prospectiva

**Versión 3 — 22-sep-2026, 21:30 UTC.** Añade el escenario de cartera con los límites reales del operador, que la v2 dejaba explícitamente pendientes. Sigue sin existir ningún resultado bajo ninguna versión.

**Versión 2 — 22-sep-2026, 21:00 UTC.** Corrige la versión 1 del mismo día antes de que existiera un solo resultado bajo ella: nunca se desplegó, así que no hay datos que invalidar. Las correcciones están al final, con su motivo. La versión 1 se conserva en el historial de git.

**Escrito el 22-sep-2026 a las 19:50 UTC, ANTES de calcular un solo resultado.** Ese es todo el punto: si los umbrales se escriben después de mirar, la prueba no vale nada y lo que sale es una historia coherente a posteriori. Este documento no se modifica. Cualquier cambio abre una versión nueva, con su fecha, y la anterior se conserva.

Es la misma disciplina que se fijó el 9-sep para los criterios del sábado, y que ya evitó dos autoengaños en este proyecto: la regla C3 del hoyo (+0,25 % que se evaporó con tres horas más de datos) y el «la primera señal es la buena» (que dejó de reproducirse).

---

## 1 · Qué se prueba, y contra qué

La referencia es **la política vigente**: la entrada, el TP y el SL que el plan congeló, ventana de 12 h, coste de 0,5 puntos. Todo rival se compara **contra ella, pareado sobre el mismo plan** — no contra una salida inferior elegida para quedar bien.

Cuatro ejes, **separados a propósito**. No se prueba la rejilla completa: 5 salidas × 2 entradas × 3 stops × 3 filtros son 90 combinaciones, y con 90 pruebas algo sale bonito por puro azar. Cada eje mueve **una** cosa y deja el resto igual que la referencia.

### Eje A — La salida

Misma entrada, mismo stop, objetivo fijo en vez del TP variable.

| | objetivo neto | bruto (coste 0,5) |
|---|---|---|
| A1 | +2,7 % | +3,2 % |
| A2 | +3,2 % | +3,7 % |
| **A3** | **+4,2 %** | **+4,7 %** ← el rival principal del plan |
| A4 | +4,7 % | +5,2 % |
| A5 | +5,2 % | +5,7 % ← exploración registrada, no candidata |

### Eje B — La entrada diferida

Comprando más abajo, con el **mismo precio objetivo** que la referencia y el **mismo porcentaje de riesgo** medido desde la entrada nueva.

Que el objetivo sea el mismo *precio* y no el mismo *porcentaje* es deliberado: el TP es un nivel estructural —una resistencia—, no una distancia, y es lo que hace un operador de verdad al poner una orden límite más abajo. Es también la variante que midió el estudio del 10-sep, que es el único respaldo previo que tiene este eje.

Si el precio no baja a ese nivel dentro de la ventana, **no hay operación** (`NO_LLENADO`): no cuenta en la media, no se le atribuye un cero, y su proporción se reporta siempre sobre el denominador de oportunidades elegibles.

| | descuento sobre la entrada |
|---|---|
| B1 | −0,5 % |
| B2 | −1,5 % ← el punto medido el 10-sep (+12,8 puntos de habilidad, pero la puerta del dinero ya fallaba en muestra) |

### Eje C — El stop

Misma entrada y mismo objetivo; cambia dónde va el stop. **El tamaño de la posición se escala para que el riesgo monetario sea constante** — sin eso, un stop más ancho solo compra más billetes de lotería y el resultado no es comparable.

| | stop |
|---|---|
| C1 | fijo −2,0 % |
| C2 | fijo −3,0 % |
| C3 | el del plan × 1,5 |

### Eje D — El filtro de selección

No es una política distinta: es **la referencia medida sobre un subconjunto**. No consume evaluación propia, solo una etiqueta.

| | subconjunto |
|---|---|
| D1 | planes cuya ancla de 1h tenía ruptura alcista al crearse ← el hallazgo de la fase 4 |
| D2 | primera oportunidad del episodio |
| D3 | planes que se avisaron por Telegram |

---

## 2 · Las tres puertas. No se mueven

Una política mejora el sistema solo si pasa **las tres**:

**1 · Dinero.** Media neta por operación con **bootstrap agrupado por par**, y el **límite inferior del IC 95 % por encima de +0,30 %**. Ese +0,30 es el deslizamiento no modelado: por debajo, lo que se mide no se cobra. Un intervalo que toca el cero no vale.

**2 · Habilidad.** Ventaja sobre la línea base geométrica `P(+A antes que −B) = B/(A+B)`, **mayor que cero con su intervalo**. Un porcentaje de aciertos sin su base geométrica no dice nada — se fabrica ensanchando el stop, que es exactamente lo que el eje C podría hacer sin esta puerta.

**3 · Terreno nuevo.** Solo planes creados **después del instante de congelación** de este documento. Lo de antes no es prueba: es donde se encontró la idea.

Y dos reglas de lectura que ya costaron un error cada una:

- **Comparación pareada contra la política vigente**, no solo contra una salida inferior.
- **No se reporta una media cuyo aporte venga en su mayoría de operaciones sin desenlace.** El +0,25 % de la regla C3 era eso, y se evaporó. O se espera a que cierren, o se reporta solo el subconjunto resuelto.

---

## 3 · Cuándo se puede cerrar cada puerta, y cuándo no

Una operación tiene una desviación típica de **2,55 %** y las del mismo par están correlacionadas (ICC 0,114 → efecto de diseño ×1,53). De ahí salen las operaciones necesarias para que el IC 95 % se separe de cero:

| para demostrar una media de | operaciones |
|---|---|
| +0,30 % | **424** |
| +0,50 % | 153 |
| +1,00 % | 38 |

Y el ritmo medido hoy:

| población | por día | días hasta 424 |
|---|---|---|
| todos los planes | 1.989 | < 1 |
| primera del episodio | 795 | < 1 |
| avisados a Telegram | 54 | 8 |
| **avisados Y primeros del episodio** | **17** | **25** |

**La población que decide es la última**, porque es la que el usuario recibe y la menos contaminada por repeticiones del mismo movimiento. Los 1.989 planes al día llegan a 424 en horas, pero son 286 pares repitiéndose: el tamaño efectivo es una fracción de eso, y usarlo para cerrar la puerta del dinero sería fabricar un intervalo estrecho que no significa nada.

**Consecuencia, escrita antes de mirar: la puerta 1 no se puede cerrar antes del 17-oct-2026** sobre la población que importa. Lo que sí se puede leer antes:

- **¿Bate al azar?** La brecha contra una entrada al azar es mucho mayor que +0,30 %, así que se distingue con 40-50 operaciones — unos 3 días.
- **¿Va en la dirección predicha?** Las predicciones están abajo.
- **¿Se cayó algo?** Como se cayeron la EMA7, los máximos planos y el hoyo.

### Fechas de revisión, fijadas ahora

| fecha | qué se lee |
|---|---|
| **25-sep-2026** | primera lectura: dirección y control de azar. Sin veredicto económico |
| **29-sep-2026** | segunda lectura, sobre la población de Telegram (≈ 380 operaciones) |
| **17-oct-2026** | la puerta 1 ya es alcanzable sobre avisados + primeros de episodio |

No se detiene la prueba en cuanto salga una cifra favorable. No se añaden políticas nuevas a mitad de camino.

---

## 4 · Mis predicciones, registradas antes de mirar

Si el resultado sale mucho mejor que esto, sospechar del método antes que celebrar.

| | predicción | probabilidad de pasar las tres puertas |
|---|---|---|
| **A3 (+4,2 % neto)** | acierta 1,5-1,7 veces más que el TP actual; esperanza **entre −0,1 y +0,3 puntos** sobre la referencia, con el intervalo cruzando el cero | **15 %** |
| A1 / A2 (objetivos cortos) | más aciertos, menos esperanza; la diferencia contra la referencia dentro del ruido | 10 % |
| A4 / A5 (objetivos largos) | menos aciertos, esperanza parecida; peor para intradía porque tardan más en cobrarse | 8 % |
| **B2 (entrar −1,5 %)** | se llena el 60-70 %; habilidad **claramente positiva** (+8 a +15 puntos), dinero con el límite inferior **cruzando el cero** | **12 %** |
| B1 (entrar −0,5 %) | se llena >90 %, efecto pequeño en ambas puertas | 10 % |
| **C1 / C2 (stops fijos)** | con el riesgo normalizado, **sin diferencia medible** contra el stop del plan | 10 % |
| C3 (stop × 1,5) | más aciertos y menos esperanza por operación; con el riesgo igualado, empate | 10 % |
| **D1 (filtro de ancla 1h)** | es la única con mecanismo medido y control pareado detrás. Espero **+5 a +10 puntos de acierto** sobre no filtrar, y que **reduzca el número de operaciones a menos de la mitad** | **30 %** |

**Por qué A3 solo un 15 %** aunque sea el rival del plan: sobre los 229 avisos maduros dio +0,51 % contra +0,47 % de la referencia, y el intervalo del 95 % de la esperanza actual es [−0,04 %, +0,99 %]. Esa diferencia de 0,04 puntos está entera dentro del ruido. Lo que A3 cambia de verdad no es cuánto se gana: es **cuántas veces se cobra** (39,3 % contra 25,3 %). Eso es una elección del usuario sobre cómo operar, no un resultado estadístico, y este registro no puede convertirlo en uno.

**Por qué D1 es la más probable:** es lo único de todo el proyecto que ha batido a un control pareado y ha aguantado partir la muestra por la mitad (+6,96 pp y +9,94 pp). Aun así, 30 % y no más: son 4 días de un solo régimen, y el efecto se midió sobre rupturas por marco, no sobre planes emitidos. Que sobreviva al cambio de población no está garantizado.

---

## 5 · Lo que esta fase NO hace

- **No cambia la emisión.** Todo corre en sombra, como las fases 1 a 4.
- **No convierte a A3 en el valor por defecto.** El plan lo prohíbe explícitamente hasta pasar las puertas.
- **No toca `objetivo_operador_pct`.** Ese ajuste filtra candidatos; no es una salida fija y cambiarlo no equivale a cobrar a ese objetivo.
- **No cambia cómo se opera.** La cartera de abajo es una simulación sobre datos guardados; no abre ni cierra nada.
- **No entrena ningún modelo.** La medición del 22-sep dice que ninguna columna ordena (AUC 0,47-0,53). Meter un modelo encima de eso sería ajustar ruido.

---

## 5 bis · El escenario de cartera, con los límites reales

Declarados por el operador el 22-sep-2026: **10 USDT, todo en una sola moneda, reinvirtiendo ganancias y pérdidas**, hasta que el monto dé para más.

| | valor |
|---|---|
| capital inicial | 10 USDT |
| posiciones simultáneas | **1** |
| fracción por posición | **100 %** del capital disponible |
| mínimo por orden | 5 USDT (`MIN_NOTIONAL` de Binance en pares USDT) |
| población | avisados por Telegram y primeros de su episodio |

**Por qué esto no se contesta con una media por operación.** Dos motivos, y los dos pesan más aquí que en una cartera grande:

1. **Tomar A significa no tomar B.** Con una posición y un horizonte de hasta 12 h, se pueden abrir como mucho dos operaciones al día. El sistema ve 1.989 planes diarios: se opera el **0,1 %** de lo que detecta. Con ese cuello de botella, *cuál* se toma pesa más que cuánto deja cada una — y eso es justo lo que una media por operación borra.
2. **Reinvertir todo compone.** +10 % y −10 % no dejan el capital igual: lo dejan en 99 %. El orden importa, y una media no tiene orden.

**El suelo del exchange deja de ser teórico.** Por debajo de 5 USDT la orden se rechaza. Con 10 USDT al 100 %, una racha de pérdidas del 3 % aguanta unas 22 seguidas antes de tocar ese suelo; una del 20 %, solo tres. La simulación **se detiene** cuando eso pasa, en vez de seguir contando operaciones imposibles.

Este escenario no se optimiza. Es una descripción de cómo opera el usuario, no una variable a ajustar.

## 6 · Las reglas de método, que también van congeladas

Dos reglas deciden si una operación **existe** y si es **medible**. Cambiarlas cambia el resultado tanto como cambiar una barrera, así que entran en la huella igual que ellas.

**Regla del fill.** Solo cuentan las velas cuyo minuto entero cae dentro de la ventana. En la vela donde se llena una entrada diferida:

- **su stop sí se aplica.** La orden se llenó bajando, así que cualquier precio por debajo del límite es posterior al fill. Si el mínimo perfora el stop, la operación se paró. Eso es conocimiento, no suposición.
- **su objetivo no se concede.** El máximo pudo ocurrir antes de que la orden se llenara. Si además lo tocaba, la fila queda marcada `ambiguo`.

**Regla de cobertura.** Un plan solo es medible con **≥ 90 %** de las velas que su ventana debería haber producido. Por debajo se marca `SIN_DATOS`: no entra en ninguna media, no es una pérdida ni un empate, y **se puede volver a medir** cuando las velas se recuperen. Vencer por reloj no es lo mismo que haber observado el recorrido.

Este umbral se fija aquí, antes de ver qué política gana. Es la misma disciplina que el resto del documento.

## 7 · Correcciones de la versión 1

Una revisión externa reprodujo seis defectos sobre la versión 1, los seis ciertos. Se corrigen aquí, **antes de que exista ningún resultado**, y se anotan en vez de reescribirse en silencio.

| | qué decía la v1 | qué dice la v2 |
|---|---|---|
| **F5-R1** | — | La vela del fill conserva su stop. Antes se descartaba entera: una vela que llenaba a 98,5 y se desplomaba a 95 no dejaba rastro, y la subida siguiente se anotaba como objetivo **+7,11 %** en lugar de **−3,5 %**. El motor fabricaba una ganancia de una pérdida |
| **F5-R2** | — | El fill respeta la ventana. Antes, una vela que *empezaba* al vencer el plazo contaba como compra |
| **F5-R3** | — | Se separa madurez de observación: la regla de cobertura de arriba. Antes, una ventana vencida sin velas quedaba fijada como **−0,5 %** para siempre |
| **F5-R4** | «su proporción se reporta siempre» | El informe enseña el embudo entero por defecto. En la v1 el filtro iba antes de agrupar, así que la columna de no llenadas salía siempre a cero |
| **F5-R5** | «mismo objetivo y mismo stop en porcentaje» | **Mismo precio objetivo**, mismo porcentaje de riesgo. El documento y el código se contradecían; se resuelve a favor de lo que hace un operador y de lo que midió el estudio del 10-sep |
| **F5-R6** | «modificar su contenido cambia la huella» | Ahora es cierto: la huella incluye el sha256 de **este documento**, la versión del método, la del evaluador, las dos reglas de arriba y la población decisoria. Antes solo cubría los números |

## 8 · Procedencia

Todo resultado se guarda con la versión de este registro y su huella de contenido. Si el documento cambia, la huella cambia, y los resultados viejos quedan identificados como de otra versión en lugar de mezclarse en silencio con los nuevos.

Congelado en la tabla `experimento_registro` con su fecha UTC y su huella.
