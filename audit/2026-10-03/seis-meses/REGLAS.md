# Estudio de 7 meses: reglas fijadas antes de ver resultados

**Escrito el 3-oct-2026 (UTC), antes de procesar ningún resultado.** Lo pidió Felix: "sí a todo, haz los pasos 1 y 2". La pregunta es si alguna regla sencilla, vista *antes* de entrar, lleva a +2,67 % de forma sostenida en varios meses distintos.

## Datos

- **Origen:** velas oficiales de 1 minuto de Binance (`data.binance.vision`), cada archivo verificado contra su `.CHECKSUM` sha256.
- **Monedas:** 150 más BTCUSDT, elegidas en `monedas.json`: las de mayor volumen mediano en el universo de SAC del 8-sep al 2-oct, sin estables, oro ni envoltorios.
  - *Sesgo conocido:* son líquidas **hoy**. Alguna pudo no existir o ser chica en marzo.
- **Periodo:** del 1-mar al 1-oct de 2026. Marzo–agosto en archivos mensuales; septiembre y el 1-oct en diarios, porque el mensual de septiembre aún no está publicado.
- **Volumen y flujo:** se usa el volumen en USDT y el volumen **comprador agresor** (`taker_buy_quote`), que es lo que SAC llama flujo.
- **Marcas de tiempo:** desde 2025 Binance las publica en microsegundos. Se convierten a minutos.

## Momentos, operación y coste

- **Momentos:** cada 10 minutos de reloj, por moneda, con 24 h de historia previa y 12 h de futuro, y como máximo un 5 % de minutos faltantes en cada lado.
- **Operación:** entra al cierre del minuto. Sale en la meta, en el stop o al vencer el plazo. Si una vela toca las dos, gana el stop. Igual que en `revision-completa/hipotesis.py`.
- **Unidad principal:** una entrada por moneda cada 12 h (sin solapes).
- **Coste principal: 0,4 puntos por operación.** Felix dice pagar "0,2 % la compra y la venta". También se informa con 0,2 (por si es 0,1 % por lado, la comisión normal de Binance sin BNB), 0,3 y 0,5.

## Ideas (las mismas de la revisión, más tres nuevas)

**Las de la revisión:**
- **Largos:** L0–L7.
- **Cortos:** S0–S6.

Las definiciones son las de `revision-completa/hipotesis.py`, sin cambios.

**Nuevas:**
- **L8 — "como SAC"**, que imita el disparo de SUBIENDO con flujo. Se cumplen las cuatro condiciones a la vez:
  - la subida de 3 min, medida en sigmas, llega a 2 o más. La sigma es una EWMA con alfa 0,05 y mínimo 0,08 %, igual que `adaptive.py`;
  - la pendiente de 5 min es positiva;
  - el volumen comprador es el 58 % o más en el último minuto y el 54 % o más en los últimos 2 minutos;
  - la moneda sube como máximo +3,5 % desde el mínimo de 60 min.
- **L9:** lo mismo que L8, pero sin la condición de flujo.
- **L10:** BTC está por encima de su media de 7 días y la moneda sube en 24 h.

**Geometrías:**

| meta / stop | +2,67 / −1,8 | +2,67 / −3 | +2,67 / −5 | +2,67 / −8 | +1,5 / −1,5 | +5 / −2,67 |
|---|---|---|---|---|---|---|

Cada una se prueba a 3 h y a 12 h.

## Partición en el tiempo

- **Exploración:** de marzo a junio.
- **Comprobación:** de julio al 1-oct.
- **Estabilidad:** además, cada mes por separado.

**Modelo combinado.** Es una regresión logística sobre décimos de cada rasgo, igual que en la revisión, con los rasgos de flujo agregados: proporción compradora a 15 y 60 min y cantidad de operaciones relativa. Se entrena **solo** con la exploración y se evalúa su mejor 1, 2, 5, 10 y 20 % en la comprobación.

## Criterio para llamar "candidata" a una regla

Una regla solo es candidata si cumple **todo** lo siguiente, con el coste principal de 0,4:

1. Neto medio > 0 en la exploración **y** en la comprobación.
2. Neto medio > 0 en al menos 5 de los 7 meses.
3. En la comprobación, el límite inferior del IC 95 % (remuestreando días enteros) es > −0,10. Con > 0 se llama "sólida".
4. Al menos 300 entradas y 50 monedas en la comprobación.

Se prueban unas 200 combinaciones. Por eso una candidata **no es una recomendación**: pasa a medirse hacia adelante, con reglas congeladas.

## Comprobación de datos

Para las monedas y minutos que están en las dos fuentes (del 8-sep al 1-oct), se comparan las velas de Binance con las de la base de SAC:
- cuántos minutos faltan en SAC;
- si los cierres coinciden.

Eso mide los huecos del error E4 contra la fuente oficial.
