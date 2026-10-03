# Reglas de `moderadas-sombra-v1`

Escritas el 2026-10-02, **antes de mirar ningún resultado**. Las reglas viven en código en `moderadas_sombra/core.py`. Si cambia cualquier valor, cambia la versión y se usa una base nueva.

## Qué se mide y sobre qué

- **Población:** todas las señales de nivel `MODERADA` de `alertas_emitidas`, con `FUERTE` como comparación. Entran las de Telegram y las que solo salen en el tablero. Se excluyen las que no tienen entrada válida.
- **Precio de entrada (R):** el `entry` de la señal.
- **Velas:** de 1 minuto, cerradas. El recorrido empieza en el primer minuto entero después de la señal.
- **Ventanas:** 1 h, 3 h, 6 h y 12 h.
- **Coste:** 0,5 puntos por operación completa. Se informa siempre en bruto y en neto.

## Por señal y por ventana (en % sobre R)

1. **Máximo:** el high más alto. **Mínimo:** el low más bajo. **Cierre:** el último close.
2. **Escalera:** el minuto en que se toca por primera vez cada nivel: +0,5, +1, +1,5, +2, +2,5, **+2,67**, +3, +3,5, +4 y +5 % brutos.
3. **Mínimo antes de la meta:** el low más bajo hasta el minuto en que se toca +2,5, +2,67 o +3 %, incluida esa vela. Si la meta no se toca, se usa el mínimo de toda la ventana.
4. **Retoques de la entrada:** cuántas veces el precio vuelve a R (low ≤ R) **después de haber subido al menos +0,5 %**. En cada vela se mira primero si toca R (y solo cuenta si ya estaba armado) y después si arma. Volver a armarse exige otra subida de +0,5 %.
5. **Grupo**, con meta +2,67 %, caída −1 % y corte +1 % / −2 %:
   - `SUBE_DIRECTO`: toca la meta sin haber tocado antes −1 %.
   - `BAJA_Y_SUBE`: toca −1 % antes de la meta (o en la misma vela) y después la meta.
   - `SE_QUEDA_CORTA`: no llega a la meta, pero sube al menos +1 %.
   - `CAE`: no llega a la meta, no sube +1 % y baja −2 % o más.
   - `LATERAL`: todo lo demás.

## Simulación de operaciones

- **Entradas:** cinco órdenes límite: en R y a −0,3, −0,5, −0,7 y −1,0 % bajo R. Cada orden se llena cuando el low toca su nivel, siempre dentro de la ventana. La de R también es límite: si al empezar el precio ya está por encima de R, comprar "en R" no habría sido posible. Por eso se anota además a qué distancia de R abrió el primer minuto.
- **Metas, en % brutos sobre el precio de compra:** +2,5 (2,0 neto), **+2,67** (≈ 2,2 neto) y +3,0 (2,5 neto).
- **Stops:**
  - `SISTEMA`: el stop de la propia señal. Si el precio ya lo había roto al llegar a la compra límite, la operación no existe (`PLAN_ROTO`).
  - `SIN_STOP`: se cierra al final de la ventana.
- **Reglas de vela:**
  - Una compra límite no puede cobrar la meta en su misma vela, pero sí tocar el stop.
  - Si meta y stop caen en la misma vela, cuenta como stop.
  - Si una vela abre por debajo del stop, se sale en la apertura.
- **Resultados posibles:** `TP`, `SL`, `TIEMPO` (cierre al final de la ventana), `SIN_ENTRADA`, `PLAN_ROTO`, `ABIERTO`.
- **Métricas:** porcentaje de órdenes llenadas, de TP y de SL; neto por operación; y neto por señal, donde las que no entran cuentan 0.

## Tres maneras de contar las repeticiones

- **TODAS:** cada señal cuenta.
- **PRIMERA_DEL_MOVIMIENTO:** solo la primera de cada moneda y nivel tras 12 h sin señales de ese nivel en esa moneda. Es la regla del proyecto ("episodio = 12 h de silencio") y se aplica igual a todo el periodo, porque el `episode_id` del sistema solo existe desde el 22-sep.
- **UNA_POR_VENTANA:** propuesta de Felix. En cada moneda y nivel, una señal cuenta solo si ya pasó la ventana entera (1, 3, 6 o 12 h) desde la última que contó.

## Control: ¿la señal aporta algo frente al azar?

Para cada señal se mide igual un **minuto al azar de la misma moneda**, elegido entre 36 h y 12 h antes de la señal. La semilla sale del id de la señal. Es la vara del proyecto: sin ella, una tasa alta solo dice que la moneda se movía.

## Patrones antes de la señal (exploratorios)

- **Datos:** las 60 velas de 1 m cerradas antes de la señal. Con ellas se calculan:
  - el retorno a 5, 15 y 60 min;
  - el rango y la posición dentro de ese rango;
  - el volumen de los últimos 5 min frente a los 55 anteriores.
- **Patrones de vela:** sobre las cuatro velas de 15 m que forman esas 60:
  - martillo y estrella fugaz;
  - envolvente alcista y bajista;
  - doji y vela fuerte alcista o bajista;
  - tres velas verdes seguidas.
- **Campos de la señal:** score, escenario, número de señal, TP %, stop %, hora UTC y si fue a Telegram.
- **Cómo se juzgan:** todo esto es **exploratorio**. Un patrón encontrado mirando los datos vale como pista, no como regla. Solo se tiene en cuenta si se sostiene en las dos mitades del histórico **y** en los datos nuevos (del 3 al 15-oct).

## Versión 2 (`moderadas-sombra-v2`, 2026-10-03)

Añadida **a petición de Felix después de ver los resultados de la v1**. Es exploración nueva, no confirmación de la v1.

- **Un solo cambio:** un tercer stop, `FIJO_1.8`, colocado a −1,8 % del **precio de compra** (no de R). Sustituye al stop del sistema en la comparación que pidió Felix. Los otros dos stops, `SISTEMA` y `SIN_STOP`, se siguen midiendo igual.
- **Reglas del stop fijo:**
  - Se puede tocar en la misma vela de la compra.
  - Si una vela posterior abre por debajo del stop, se sale en la apertura.
  - Si meta y stop caen en la misma vela, cuenta como stop.
  - Con una entrada en R − 1 %, el stop queda en R − 2,78 %.
- **Base nueva** (`moderadas_sombra_v2.db`) e **histórico nuevo** en `v2/`. La v1 se conserva tal cual.
- La variante principal se vuelve a elegir con la misma regla de arriba, ahora entre 45 variantes por ventana.

## Qué es exploración y qué es confirmación

- **Exploración:** el histórico, del 11-sep hasta el momento de instalar. De ahí sale la referencia (`referencia.json`).
- **Variante principal:** la combinación de entrada, meta, stop y ventana con **mayor neto por señal en MODERADA**, contando `PRIMERA_DEL_MOVIMIENTO`. Debe tener al menos 100 entradas y ser positiva en las dos mitades del histórico. Se escribe en `PRINCIPAL.json` antes de que haya datos nuevos.
- **Confirmación:** del 3 al 15-oct, solo con señales registradas al emitirse. Que una variante gane en el histórico no la aprueba: tiene que repetir en los datos nuevos.
