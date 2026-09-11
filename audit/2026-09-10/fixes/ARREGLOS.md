# Arreglos sobre la verificación del 10-sep

Las **23 comprobaciones dirigidas** de la verificación pasan ahora contra el código del repositorio: **23 pasan, 0 fallan**. Antes eran 8 y 15. Esto acredita que los defectos concretos que las pruebas describen ya no se reproducen. **No acredita precisión, ni rentabilidad, ni mejora de la entrada**: ninguna ventana de 24h de esta versión existe todavía, y las cifras del informe anterior siguen siendo las últimas medidas.

Nada de esto toca el servicio, la configuración de producción ni la base. La verificación original (`audit/2026-09-10/verification/`) se deja intacta como registro de lo que se midió aquel día.

## Una corrección en la propia prueba de F13

La sonda de F13 parcheaba `_alertas.update`. Ese método no existe: se llama `actualizar`. Poner un lambda con un nombre inventado sobre una instancia de Python no da error — crea el atributo — así que la comprobación no podía pasar por mucho que se arreglara el defecto de fondo. En `verify_fixes.py` se parchea `actualizar`, que es lo que el motor llama de verdad, y se deja dicho en el encabezado. El defecto que describía sí era real y está arreglado.

## Qué se arregló, hallazgo por hallazgo

### F01 · Faltan velas para medir las operaciones

El problema no era descargar el hueco, era que el hueco no se veía y, cuando se descargaba, se tiraba.

- **Detección por secuencia.** `SymbolState.huecos_1m()` cuenta los minutos ausentes ENTRE la primera y la última vela del buffer. El detector anterior miraba solo el último minuto: en cuanto el stream volvía, el hueco dejaba de ser visible para siempre. Los 2.344 minutos-par ausentes eran todos de ese tipo.
- **La reparación repara.** `preload_1m` salía de vacío si el par ya estaba caliente — descargaba el hueco, lo guardaba en la base y lo descartaba antes de llegar al buffer que se analiza. Ahora fusiona por apertura de vela: `SymbolState.fusionar_velas()` inserta lo que falta por el medio y añade lo nuevo por el final, sin duplicar.
- **La descarga llega hasta el hueco.** `_hydrate_tf` dimensionaba la petición por lo vieja que era la ÚLTIMA vela, así que un hueco de hace una hora con el stream restablecido pedía cinco velas de la cola. Ahora `_primer_hueco()` manda sobre ese cálculo.
- **`preload_htf` ya no duplica.** Antes hacía `buf.append(c)` sin mirar: cada reparación volvía a meter las mismas velas de 15m y 1h en un deque acotado, expulsando historia real por copias.
- **Coste acotado.** La reparación de huecos internos usa `reparar_1m()`, un request por par y solo el marco de 1m, con tope de 40 pares por vuelta. Por `hydrate_all` habrían sido ~1.300 peticiones cada cinco minutos, por encima del límite de peso de Binance.
- **Lo que Binance no tiene.** Un minuto sin operaciones no genera vela, así que hay huecos que no se pueden rellenar. El bucle recuerda por par cuántos quedaron sin rellenar y no reintenta hasta que ese número cambia; el log dice cuántos minutos se rellenaron y cuántos no existen.

**Sigue pendiente:** separar la suscripción de trades de la de velas, y reprocesar los outcomes desde la primera vela ausente. Lo segundo necesita releer OHLC de la base más allá del buffer de 320 minutos y es un cambio de otro tamaño. Mientras tanto, `cobertura_velas` es el dato con el que se decide si una fila se puede sostener — y ahora su denominador es correcto (1.439 velas posibles en 24h, no 1.440: antes una cobertura perfecta se leía como 99,93%).

### F02 · Los outcomes aceptaban datos fuera de su ventana

El camino de una señal se mide ahora por **intervalos completos**: una vela cuenta solo si su minuto entero cae dentro de la ventana. La que abría antes del vencimiento y cerraba después tenía su máximo en un instante desconocido, que podía ser posterior al vencimiento, y una prueba le concedía el TP con ese máximo. El cierre pasa a ser del reloj (`cerrar_vencidos`) o de la primera vela que ya cae entera fuera; el cierre dentro del camino de la vela quedó sin alcanzar y se retiró.

**Sigue pendiente:** las 27 signals OPEN de más de 12h. El reloj nuevo cierra outcomes, no signals; darles un reloj común es el punto 2 del orden de cierre y no está hecho.

### F04 · Telegram daba por enviado lo que no salió

`_pedir` se traga el rechazo de la API y el fallo de red y devuelve `None`. Como `avisar` no devolvía nada, el llamante marcaba `enviado` salvo que saltara una excepción — que ahí no salta nunca. Ahora `avisar` y `responder` devuelven si el mensaje llegó, y `_quiza_avisar` registra `fallo` cuando no llegó. Los avisos de seguimiento (stop, TP, hitos, bajadas) pasan por `_responder_aviso`, que distingue en el log lo entregado de lo rechazado.

**Sigue pendiente:** el `plan_id` persistente por alerta operable y el enlace de reemplazos. Las 17 alertas con `signal_id` NULL siguen sin outcome propio.

### F05 · El simulador del hoyo era más optimista que el sistema

`research/entrada_en_el_hoyo.py` usaba `min(apertura, disparo)` como fill y podía conceder el objetivo en la propia vela de entrada, cuyo máximo pudo ocurrir antes de la compra. Ahora aplica la misma regla conservadora que el tracker en vivo: el fill es el disparo, el stop sí se aplica en la vela de entrada y el TP se mira desde la siguiente. La regla queda versionada en el encabezado del estudio como **REGLA DE EJECUCIÓN v2**.

**Importante:** cualquier cifra publicada de ese estudio antes de hoy se midió con la regla v1 y no es comparable. Hay que volver a ejecutarlo contra la base para tener números nuevos.

### F08 · Disponibilidad de flujo contra suscripción real

El motor recibía la shortlist **pedida** mientras el gestor se quedaba con la anterior cuando el cambio no pasaba el freno de churn. Con eso, `flow_disponible` marcaba disponible un par sin stream y su cero de trades se leía como "nadie compró" en vez de "nunca miramos".

El freno existía porque cambiar la shortlist obligaba a tirar WS-A y rehacer los ~500 streams de todos los pares para mover cuatro suscripciones de aggTrade — 126 reconexiones en 6,4 horas en el tramo auditado. Ahora `_WSConnection.aplicar_streams()` manda `SUBSCRIBE` / `UNSUBSCRIBE` sobre la conexión viva, el freno sobra, y `update_shortlist` devuelve **lo que quedó suscrito**, que es lo único que `main.py` le pasa al motor.

**Sigue pendiente:** publicar también la edad del último dato recibido, separada del volumen de compras.

### F09 · El universo se quedaba fijado

`update_symbols` actualizaba `self.symbols` aunque no reconectara, así que la comparación siguiente ya daba por aplicado lo que nunca se suscribió: un par nuevo de cada 100 no entraba jamás. Ahora hay dos variables distintas — universo **deseado** y universo **suscrito** — y la comparación va contra lo suscrito. Un cambio por debajo del umbral se aplaza una vez; si el refresco siguiente vuelve a pedir lo mismo, ya no es un parpadeo del listado y se aplica. Los streams se arman desde lo suscrito.

### F11 · Los eventos no tenían identidad

La vela se identifica por su apertura, en los tres sitios donde se contaba dos veces:

- `OutcomeTracker.on_candle` rechaza la repetida y la atrasada. Contarla dos veces inflaba `n_velas` y con él la cobertura, que es justo el dato con el que se decide si una fila se puede leer; una atrasada hacía retroceder `ts_last`.
- `SymbolState.add_closed_candle` es idempotente. La repetida refresca los valores sin volver a alimentar la EWMA — que es la escala con la que se miden todos los z-scores — ni adelantar `candles_in_fsm`.
- `fusionar_velas` / `fusionar_velas_htf` reconstruyen el buffer por apertura, sin duplicados.

### F12 · El hash de configuración no cubría lo que decide

El hash se construía con una lista de prefijos permitidos, y lo que no empezara por uno de ellos quedaba fuera en silencio: `rr_target`, `coste_operacion_pct`, `exigir_objetivo_operador`, `flow_min_trades` y `rise_z` no lo movían. Ahora entra **todo ajuste declarado** salvo una lista corta y explícita (endpoints, rutas, puerto, nivel de log y credenciales). El error posible cambia de lado a propósito: de más, el hash cambia cuando no hacía falta y se nota; de menos, se pierde la evidencia sin que nadie se entere.

El esquema va dentro del texto que se firma (`v2|...`), así que los hashes nuevos no se pueden confundir con los viejos. **Los outcomes ya guardados con `config_hash=50d5bbbe74aa` siguen etiquetados con un hash que no cubría esos cinco ajustes**: eso no se arregla hacia atrás.

**Sigue pendiente:** la purga sigue reteniendo 3 días de velas cortas, y los 2.484 outcomes cerrados sin cobertura y 2.792 filas sin versión siguen sin marcar. Reconstruirlos o excluirlos toca la base de producción y es tu decisión, no un arreglo de código.

### F13 · Rutas que evitaban el ciclo de seguimiento

El veto de blow-off hacía `return` sin pasar por `AlertManager`. La vela de agotamiento es justo la que suele perforar el stop, así que ese desenlace se perdía hasta la siguiente vela que no fuera blow-off — y si el par seguía agotado, no llegaba nunca. El bloque de refresco se extrajo a `_refrescar_alerta_viva()` y el veto lo llama antes de vetar: **un plan vivo se actualiza siempre antes de vetar nada**.

De paso, la variable `h` del bucle de hitos pisaba el máximo de la vela dentro del mismo ámbito. Ahora se llama `hito`.

**Sigue pendiente:** los perfiles BASE / TENDENCIA / IGNICIÓN siguen sin crear plan ni outcome propio (101, 33 y 5 eventos desde el despliegue).

### F14 · Nombres de las métricas

El encabezado de `signal_tracker.py` llamaba "win rate real" a la frecuencia con que el precio toca el TP antes que el SL, en bruto, sobre una operación simulada que nadie ejecutó. Ahora dice qué es, qué no incluye (fill, spread, deslizamiento, comisión), que las EXPIRED positivas cuentan como fallo — 210 de 416 — y para qué sirve: comparar versiones entre sí con el mismo sesgo, no decir cuánto se gana.

**Sigue pendiente:** separar de verdad tasa de tocar TP, cierre positivo, cumplimiento neto y expectativa por plan y versión, con denominadores explícitos.

## Lo que NO se tocó, y por qué

- **`exigir_objetivo_operador` sigue en `false`.** Activarlo recorta la producción de señales alrededor del 60%. El propio comentario del ajuste dice que eso es una decisión, no un arreglo, y sigue siendo tuya. Con la configuración actual, 26 de 46 alertas no llegaban a 3,2% ni siquiera en bruto. El veto está implementado y probado: es un cambio de una línea cuando lo decidas.
- **El histórico no se reconstruye ni se excluye.** Toca la base de producción.
- **No se desplegó nada.** El servicio sigue con **b8a3d64**.

## Lo que falta para que esto llegue a producción

El `frontend/dist` del servidor es anterior a los cambios: no tiene `FRECUENCIA HISTORICA` ni `reward_neto_pct`, y el backend sirve ese directorio. El `dist` local sí los tiene y la compilación de TypeScript pasa, pero eso no actualiza la copia del servidor — `dist` está en `.gitignore` y se construye allí.

En el servidor:

```bash
cd /home/flox/sacbinance && git pull && bash deploy/deploy.sh && sudo systemctl restart sacbinance
```

Después conviene comprobar dos cosas sobre el recurso realmente servido: que el JavaScript contiene las dos cadenas nuevas, y que el `config_hash` de los outcomes nuevos empieza por un valor distinto de `50d5bbbe74aa`. Hasta que eso ocurra, ninguna de estas correcciones está en el aire.

## Evidencia reproducible

- [verify_fixes.py](verify_fixes.py) — las 23 comprobaciones contra `backend/`
- [fixes_checks.json](fixes_checks.json) — resultado: 23 pasan, 0 fallan

```bash
backend/venv/Scripts/python.exe audit/2026-09-10/fixes/verify_fixes.py
```
