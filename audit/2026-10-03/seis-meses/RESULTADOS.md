# Estudio de 7 meses: resultados

**Fecha:** 5 de octubre de 2026. **Reglas:** [REGLAS.md](REGLAS.md), registradas en git (commit `c567d59`) antes de procesar los datos. Este documento aplica esas reglas sin cambiarlas.

## Datos

- **Origen:** velas oficiales de 1 minuto de Binance (`data.binance.vision`), del 1-mar al 1-oct de 2026. Cada archivo se verificó contra la suma sha256 que publica Binance.
- **Volumen:** 5.451 archivos (1.225 MB) y 42,7 millones de velas de 150 monedas.
- **Monedas recientes:** 23 tienen menos de 7 meses porque se listaron después de marzo (las acciones tokenizadas, MARSCOIN, 牛来…).
- **Monedas elegidas:** las más líquidas del universo de SAC hoy. Es un sesgo conocido: monedas que ya no cotizan no están.

**Comparación con la base de SAC** (8-sep a 1-oct, mismas monedas y minutos):
- a SAC le falta el **3,4 %** de los minutos. Del 9 al 17-sep faltaba entre 6 y 9 % por día; desde el 26-sep, menos del 1 %;
- **cuando la vela está, es idéntica:** 5 cierres distintos en 4,7 millones.

## La respuesta corta

**Ninguna de las 216 combinaciones cumple el criterio** (18 ideas, 6 metas o stops, 2 plazos). Con el coste principal de 0,4, ninguna gana dinero en los dos periodos.

En 7 meses y 150 monedas, **comprar en cualquier momento** con meta +2,67 %, stop −1,8 % y 12 h da, antes de comisiones:
- −0,01 % por operación de marzo a junio;
- +0,07 % de julio a septiembre.

Es decir, **cero**. Lo que se pierde es la comisión. Ninguna regla se separa de ese cero lo suficiente para pagarla. Con 0,4 de coste, empatar exige acertar el 49,2 % de las operaciones, y todas las reglas aciertan entre el 37 % y el 44 %.

## Lo que te importa, idea por idea

Geometría tuya (+2,67 / −1,8, 12 h). Una entrada por moneda cada 12 h, coste 0,4. "Aciertos" es meta antes que stop, sobre las resueltas.

| idea | mar–jun: entradas · aciertos · neto | jul–sep: entradas · aciertos · neto | meses positivos |
|---|---|---|---|
| Comprar en cualquier momento (referencia) | 31.534 · 38 % · −0,41 % | 27.134 · 41 % · −0,33 % | 0 de 7 |
| **Como SAC:** subida de 3 min ≥ 2 sigmas con compras dominantes | 12.064 · 37 % · −0,47 % | 9.840 · 41 % · −0,34 % | 0 de 7 |
| Lo mismo, sin mirar las compras | 15.938 · 37 % · −0,46 % | 13.193 · 41 % · −0,34 % | 0 de 7 |
| Rebote tras desplome (−3 % en 15 min) | 1.450 · 42 % · −0,31 % | 1.720 · 40 % · −0,41 % | 1 de 7 |
| Moneda a −10 % o más de su máximo de 24 h | 2.990 · 42 % · −0,30 % | 2.883 · 39 % · −0,44 % | 0 de 7 |
| **Corto** tras +3 % en 15 min | 1.638 · 41 % · −0,36 % | 1.868 · 38 % · −0,52 % | 0 de 7 |
| **Corto** tras +5 % en 1 h | 1.442 · 44 % · −0,25 % | 1.736 · 38 % · −0,50 % | 0 de 7 |

- **El disparo de SAC es igual que comprar al azar:** −0,07 % / +0,06 % antes de comisiones, contra −0,01 % / +0,07 % del azar. Agregarle la condición de compras dominantes (el "flujo") no cambia nada. Es la prueba más directa de la idea central del sistema, y con 7 meses sale en cero.
- **"Lo que sube de golpe, baja"** se cumple solo en mediana. Tras +3 % en 15 min, el precio está −0,5 % abajo a las 3 h en los dos periodos; en los 24 días había salido −1,3 %.
  - Comprar ahí con meta y stop **no** fue siempre peor que comprar en cualquier momento: peor de marzo a junio (−0,57 frente a −0,41) y mejor de julio a septiembre (−0,25 frente a −0,33).
  - Vender en corto ahí perdió en los dos periodos.
- **El mercado del día anterior no anticipa el siguiente:**
  - comprar al azar dio, en promedio, +0,03 % por día antes de comisiones (213 días, el 48 % positivos);
  - la relación con cuántas monedas subieron el día anterior es −0,02, y con BTC, −0,005 (cero).

  Por meses, antes de comisiones: marzo +0,10; abril +0,10; mayo +0,02; junio −0,18; julio −0,14; agosto +0,23; septiembre +0,12.
- **El modelo con los 30 rasgos juntos no gana ni siquiera en los meses con los que aprendió.** Su mejor 1 % da −0,18 % por operación de marzo a junio y −0,37 % de julio a septiembre; solo marzo queda positivo.

## ¿Y con comisión de 0,2?

Solo **3 de 216** combinaciones quedan en cero o arriba en los dos periodos. Las tres usan un stop de −8 %, que es casi no tener stop:

| idea | plazo | mar–jun | jul–sep | meses positivos con 0,4 |
|---|---|---|---|---|
| Rebote tras desplome (−3 % en 15 min) | 12 h | +0,08 % | +0,12 % | 3 de 7 |
| Rebote tras desplome | 3 h | +0,19 % | +0,01 % | 2 de 7 |
| Moneda a −10 % de su máximo de 24 h | 3 h | +0,10 % | +0,01 % | 1 de 7 |

- **Las ganancias son de décimas de punto por operación**, con 216 pruebas hechas: entra dentro de lo que la suerte puede dar.
- **Con margin x5, un stop de −8 % es perder el 40 %** de lo puesto en esa operación.
- La idea "moneda a −10 % de su máximo", que en los 24 días parecía prometedora con 0,2, **no se confirma** con 7 meses.

## Qué significa

1. **Lo de los 24 días se confirma con 7 meses.** En las velas de 1 minuto de estas 150 monedas no hay una regla sencilla y estable que lleve a +2,67 % antes de −1,8 % más seguido que el azar. Y por lo tanto no la hay que pague la comisión.
2. **El disparo de SAC no es mejor que el azar,** y el flujo de compras no le suma nada. El problema no es solo el error de FUERTE: es la idea de comprar cuando ya sube rápido.
3. **El coste decide.** Antes de comisiones, casi todo da cero; después, todo da negativo. Si pagas 0,2 % por lado (0,4 en total), pasar a la comisión con BNB (0,075 % por lado) o a órdenes límite te ahorraría unos 0,2 puntos por operación. Eso reduce la pérdida, no crea ganancia.
4. **No sigo minando estas velas.** Ya van unas 400 combinaciones entre los dos estudios. Seguir probando aumenta la probabilidad de encontrar algo que parezca bueno por casualidad.

## Lo que sí queda por probar (otras fuentes, no más de lo mismo)

- **El estudio de IA a ciegas:** da su veredicto el 15-oct.
- **Otro plazo:** tendencias de varios días o semanas. Es lo más documentado en cripto, pero es otro estilo de operar, no scalping. Hacen falta años de velas diarias, que se pueden bajar de la misma fuente oficial.
- **Información que no está en las velas:** profundidad del libro de órdenes, financiación y posiciones abiertas de futuros, listados nuevos y anuncios.

Esto es medición, no consejo de inversión.

## Archivos

| archivo | qué hace |
|---|---|
| `descargar.py` | baja y verifica los archivos de Binance (`descarga.json`, `descarga_reintento.json`) |
| `convertir.py` | pasa los .zip a un .npz por moneda |
| `escaneo7.py` | mide 4,2 millones de momentos |
| `analisis7.py` → `analisis7.json` | aplica el criterio de REGLAS.md |
| `tablas7.py` | arma estas tablas |
| `proteccion7.json` | la regla de no comprar tras un salto |
| `comparar_sac.py` → `comparar_sac.json` | compara la base de SAC con Binance |
| `data/binance_vision/` | las velas y el escaneo (fuera de git, 2,7 GB) |
