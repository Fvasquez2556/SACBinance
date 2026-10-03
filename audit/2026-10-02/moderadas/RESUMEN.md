# Señales MODERADA: qué hace el precio desde la entrada

**Periodo:** del 11-sep al 2-oct de 2026. **Fuente:** `fuente.jsonl.gz`, sha256 `f81b5ac6…`, medida en el servidor en solo lectura (5,5 min, el 3-oct de 04:09 a 04:14 UTC). **Reglas** escritas antes de mirar, en [REGLAS.md](REGLAS.md).

- **10.206 señales MODERADA.** 8.791 tienen sus 12 h de velas completas. Contando solo **la primera de cada movimiento**, quedan **2.984**: es la cifra principal, porque una moneda que repite 20 veces no puede pesar 20 veces.
- **11.729 FUERTE** para comparar.
- Todos los porcentajes están medidos **sobre R**, el precio de entrada de la señal.

## Lo que pediste, en una tabla (MODERADA, primera de cada movimiento)

| | 1 h | 3 h | 6 h | 12 h |
|---|---|---|---|---|
| **Llegan a +2,67 %** | 6,0 % | 16,5 % | 28,5 % | **44,0 %** |
| Se quedan cortas | 94 % | 83,5 % | 71,5 % | 56 % |
| Minutos hasta +2,67 % (mediana, de las que llegan) | 29 | 81 | 153 | 256 |
| Máximo desde R (mediana) | +0,59 % | +1,03 % | +1,49 % | +2,29 % |
| Mínimo desde R (mediana) | −0,60 % | −1,11 % | −1,50 % | −2,11 % |
| Retoques de R tras subir +0,5 % (media) | 0,44 | 1,07 | 1,74 | 2,76 |

**A 12 h:**
- **Las que llegan a +2,67 % (1.313):**
  - Siguen subiendo hasta +4,69 % de mediana.
  - Antes de llegar, la mediana baja −0,83 %. Una de cada diez baja más de −2,74 %.
- **Las que se quedan cortas (1.671):**
  - Suben solo hasta +1,14 % de mediana.
  - Caen hasta −2,81 % de mediana.
- **Retroceso promedio desde R:** −2,74 % de media y −2,11 % de mediana.
- **Extremos:** la que más subió llegó a **+70,2 %**; la que más cayó, a **−22,1 %**.
- **Retoques:** el 75 % de las señales vuelve a tocar R al menos una vez después de haber subido +0,5 %, y el 40 % lo hace 3 veces o más. Volver a la entrada es lo normal, no la excepción.

**Grupos a 12 h:**

| grupo | qué pasó | % |
|---|---|---|
| Sube directo | llega a +2,67 % sin tocar antes −1 % | 24,6 % |
| Baja y sube | toca −1 % y después llega a +2,67 % | 19,4 % |
| Se queda corta | no llega a la meta, pero sube +1 % o más | 31,4 % |
| Lateral | no llega a la meta y se mueve poco | 5,0 % |
| Cae | no llega a la meta, no sube +1 % y cae −2 % o más | 19,6 % |

FUERTE se reparte casi igual: 26,9 / 18,8 / 30,6 / 4,4 / 19,4 %.

## Lo más importante: la señal no le gana al azar

A cada señal se le comparó **un minuto al azar de la misma moneda**, entre 12 y 36 h antes. ¿Quién llega antes a +2,67 %?

| | 1 h | 3 h | 6 h | 12 h |
|---|---|---|---|---|
| MODERADA | 6,2 % | 16,8 % | 28,4 % | 44,1 % |
| minuto al azar | 5,7 % | 18,9 % | 31,0 % | **49,3 %** |
| FUERTE | 7,3 % | 18,4 % | 29,0 % | 45,3 % |
| minuto al azar | 5,3 % | 17,2 % | 29,4 % | 43,8 % |

- **MODERADA** queda **por debajo del azar** de 3 h en adelante, y lo mismo pasa en todos los peldaños de la escalera (+1 %, +2 %, +3 %, +5 %).
- **FUERTE** empata con el azar: solo saca algo de ventaja en la primera hora (7,3 % frente a 5,3 %).

Es lo mismo que el proyecto ya había medido de otras formas: el momento que eligen estas señales no es mejor que cualquier otro momento de la misma moneda.

## Simulación de entradas (MODERADA, primera del movimiento, meta +2,67 %)

El neto por señal resta el coste de 0,5 puntos, y las señales en las que la orden no se llena cuentan 0.

| entrada | se llena (12 h) | TP / SL (12 h, stop del sistema) | neto por señal 3 h | neto por señal 12 h, stop del sistema | 12 h sin stop | 12 h sin stop, minuto al azar |
|---|---|---|---|---|---|---|
| R | 98 % | 33,5 % / 48,9 % | −0,54 % | −0,39 % | −0,28 % | +0,05 % |
| R − 0,3 % | 92 % | 30,9 % / 53,2 % | −0,44 % | −0,35 % | −0,24 % | +0,04 % |
| R − 0,5 % | 86 % | 29,9 % / 55,3 % | −0,37 % | −0,29 % | −0,19 % | +0,04 % |
| R − 0,7 % | 77 % | 28,6 % / 57,0 % | −0,30 % | −0,25 % | −0,18 % | +0,06 % |
| **R − 1,0 %** | 61 % | 27,9 % / 58,5 % | −0,22 % | −0,20 % | −0,15 % | +0,03 % |

- **Ninguna combinación gana dinero.** Probé las cinco entradas, las tres metas (+2,5 / +2,67 / +3 %), los dos stops y las cuatro ventanas, y todas pierden después del coste.
- **Comprar más abajo siempre pierde menos.** Mejora porque la meta queda más cerca del precio de compra y porque hay menos operaciones. Pero cada operación que sí se llena sigue perdiendo entre −0,2 y −0,6 %, según la ventana y el stop.
- **El stop del sistema estorba a 12 h:** la mediana baja −0,83 % antes de cobrar, y el stop saca a más de la mitad.
- **El minuto al azar sale mejor en todas las filas.** Sin stop, a 12 h queda prácticamente en cero.
- **Depende mucho de la época.** Sin stop y a 12 h, la primera mitad (11 al 23-sep) da entre 0 y +0,04 %; la segunda (24-sep al 2-oct), entre −0,34 y −0,57 %.
- **La variante principal** (la que se seguirá del 3 al 15-oct) es la menos mala: **entrada R − 1 %, meta +2,67 %, stop del sistema, 1 h**. Da −0,13 % por señal, con IC 95 % por moneda de [−0,16; −0,12]. **No cumple la regla de ser positiva en las dos mitades**, así que se sigue como referencia, no como recomendación.

## Versión 2: stop fijo a −1,8 % del precio de compra

Pedido por Felix después de ver lo anterior. El histórico es el mismo periodo, medido otra vez con el stop nuevo (`v2/fuente.jsonl.gz`, sha256 `2bac3af1…`). MODERADA, primera del movimiento, meta +2,67 %:

| entrada | se llena (12 h) | TP / SL (12 h) | neto por operación (12 h) | neto por señal 3 h | neto por señal 12 h | 12 h, minuto al azar |
|---|---|---|---|---|---|---|
| R | 98 % | 33,0 % / 50,2 % | −0,46 % | −0,55 % | −0,45 % | −0,25 % |
| R − 0,3 % | 92 % | 32,3 % / 49,2 % | −0,45 % | −0,46 % | −0,41 % | −0,22 % |
| R − 0,5 % | 88 % | 33,0 % / 47,5 % | −0,40 % | −0,40 % | −0,35 % | −0,19 % |
| R − 0,7 % | 82 % | 33,0 % / 46,8 % | −0,38 % | −0,35 % | −0,31 % | −0,15 % |
| R − 1,0 % | 74 % | 32,8 % / 45,4 % | −0,37 % | −0,28 % | −0,27 % | −0,16 % |

- **El stop fijo de 1,8 % sale peor** que el del sistema (−0,20 % por señal en R − 1 % a 12 h) y que ir sin stop (−0,15 %). Con +2,5 o +3 % de meta, a 1 h o a 6 h, y en FUERTE, pasa lo mismo: todo negativo.
- **Por qué no puede salir:**
  - Una operación que gana deja +2,17 % neto y una que pierde, −2,3 %. Para empatar hace falta ganar el 51,5 % de las que se resuelven.
  - Las señales ganan el **40 %** (33,0 / (33,0 + 50,2)).
  - Un precio que se mueve al azar tocaría primero +2,67 % que −1,8 % justamente el 1,8 / (2,67 + 1,8) = **40,3 %** de las veces.
  - La señal acierta lo mismo que el azar con esa geometría: no hay ventaja que cubra el coste.
- **El motivo de fondo está en el recorrido:** antes de llegar a +2,67 %, la mediana baja −0,83 % y una de cada diez baja más de −2,7 %. Un stop de 1,8 % saca a muchas de las que después habrían cobrado.
- **Por épocas:** en la primera mitad (11 al 23-sep) pierde menos, entre −0,13 y −0,29 % por señal a 12 h; en la segunda (24-sep al 2-oct), entre −0,41 y −0,60 %.
- **La variante principal de la v2 sigue siendo la de la v1:** R − 1 %, meta +2,67 %, stop del sistema, 1 h, con −0,135 % por señal. Ninguna con stop fijo la supera. La sombra mide desde el 3-oct a las 04:43 UTC las tres opciones (stop del sistema, sin stop y stop fijo 1,8 %).

## Patrones

- **Velas de 15 min antes de la señal** (martillo, envolventes, doji, vela fuerte, tres verdes): ninguna separa a las que llegan a +2,67 %. Las diferencias son de ±1 a 3 puntos y cambian de signo entre mitades. Las únicas grandes salen de muestras de 16 a 51 señales.
- **Score, número de señal y posición en el rango:** no ordenan. Su AUC está entre 0,48 y 0,51, que es lo mismo que el azar.
- **Lo único que separa es la volatilidad.** El rango de la última hora (AUC 0,67 a 3 h, estable en las dos mitades) y lo ancho del TP y del stop del plan (AUC 0,65).
  - Las del quinto más volátil llegan a +2,67 % en 3 h el 27 % de las veces, frente al 5 % del quinto más tranquilo.
  - Pero también **caen −2 % más a menudo** (42 % frente a 13 %).
  - **El neto es negativo en los cinco quintos**, y en todos el minuto al azar rinde mejor. Elige monedas que se mueven, no monedas que suben.

## Cuidado al leer esto

- **El 14 % de las MODERADA se quedó fuera** por algún minuto sin vela en sus 12 h. Se concentran en el 21–25 de septiembre y en el 29-sep–2-oct; el 29-sep fue el apagón. Si esas monedas son las que salieron del universo de SAC, pueden no parecerse al resto.
- **El coste de 0,5 puntos es un supuesto.** Con margin x5 las pérdidas también se multiplican por 5.
- **Todo esto es exploración del histórico.** La confirmación son las señales nuevas, del 3 al 15-oct.

## Qué sigue

La sombra `moderadas_sombra/` registra cada señal MODERADA y FUERTE nueva al emitirse y la mide igual a 1, 3, 6 y 12 h. Lo compara contra esta referencia con `python3 -m moderadas_sombra informe`, con una tabla día a día hasta el 15-oct.

Esto es medición, no consejo de inversión.
