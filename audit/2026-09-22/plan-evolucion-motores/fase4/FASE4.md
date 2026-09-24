# Fase 4 — los dos motores en sombra · 22-sep-2026

**Estado: desplegado en producción, en sombra** (22-sep, último despliegue 07:41 UTC). Esquema v19, aditivo. **202 pruebas en verde** en local y en el servidor. Ninguna línea de este trabajo puede cambiar una emisión, un nivel o un mensaje de Telegram.

Antes del código se cerró la medición que el plan dejaba abierta: [las rupturas por marco con barreras homogéneas en R](MEDICION_RUPTURAS_EN_R.md). Ese resultado no es un apéndice — **es lo que decide el diseño de los dos motores**, y por eso va primero.

## Lo que la medición obligó a cambiar

| Lo que el plan proponía | Lo que salió medido | Lo que se hizo |
|---|---|---|
| Familias de continuación sobre la detección actual | A 5m el detector da **−4,32 pp** frente a entrar al azar en el mismo par; a 1h da **+8,46 pp**, estable en las dos mitades | El disparador se **ancla en 1h**. Los marcos rápidos son contexto, nunca motivo |
| «Caída que continúa: evitar anticipar el suelo» | Una ruptura bajista **no** anticipa que la caída siga: 44,1 % contra 45,8 % del control. Con volumen ≥2× baja a 35,8 % contra 45,0 % | El motor de caída **no tiene ninguna familia que prediga continuación**. Solo describe el estado y espera el disparador |
| Confluencia entre marcos como evidencia | AUC 0,506. Ninguna celda de confluencia bate a su control | Se guarda el dato, **no pondera nada** |
| Puntuación / confianza | El score no ordena (AUC 0,535 reciente) | Los motores **no puntúan**. Dan veredicto y razones |

## Los dos motores

### Contrato común (`src/motores/contrato.py`)

Cinco veredictos, y el constructor hace cumplir tres reglas que hasta ahora eran solo intención:

```
CANDIDATO   exige disparador declarado == True    → si no, ValueError
ESPERAR     la tesis existe y aún no ha disparado
CONFLICTO   los marcos se contradicen — no se promedia, se dice
DATOS_INSUFICIENTES   con la lista de lo que falta → si está vacía, ValueError
SIN_TESIS   no hay nada que seguir
```

Y: **solo un candidato puede llevar entrada, objetivo y stop**. Una lectura que no es candidata con niveles dentro lanza excepción. Así no existe la ruta por la que un «podría rebotar» acaba pintado como plan en una pantalla.

### Motor A — continuación (`continuacion.py`)

Cinco familias, resueltas en este orden:

1. **EXTENDIDO** — agotamiento. Va primero por seguridad: si la subida ya está gastada, no puede clasificarse como ruptura sostenida aunque el detector dispare. **Nunca produce candidato.**
2. **RUPTURA_RETEST** — el precio volvió al nivel roto de 1h y lo respetó. Dispara con el rebote confirmado (≥1 % desde el suelo).
3. **RUPTURA_SOSTENIDA** — el ancla de 1h rompió. Dispara con: confirmada + impulso ACELERANDO/SOSTENIDA + volumen ≥1× + el 1m subiendo.
4. **PULLBACK_TENDENCIA** — tendencia de 1h viva y retroceso detectado. Dispara con `retroceso.confirmado`, que es la versión **medida** (24,4 % de acierto cobrable frente a 19,5 % sin esperar).
5. **EXPANSION_COMPRESION** — dispara solo cuando el precio rompe el pivote con volumen. La compresión dice *cuándo* habrá movimiento, no *hacia dónde*.

Si el ancla de 1h falta o tiene más de 4 horas, el veredicto es `DATOS_INSUFICIENTES` con el motivo. **No hay fallback silencioso a un marco más rápido** — que es justo lo que la medición dice que empeoraría el resultado.

### Motor B — caída y recuperación (`caida.py`)

```
SIN_CAIDA → CAIDA_ACTIVA → DESACELERACION → BASE_EN_FORMACION → RECUPERACION → REBOTE_CONFIRMADO
```

Con cuatro salidas explícitas y persistidas: `NUEVA_CAIDA` (pierde el mínimo), `INVALIDADO` (el rebote pierde el piso de **su base**, aunque el mínimo absoluto aguante), `CADUCADO` (12 h, la misma ventana del episodio) y `DATOS_INSUFICIENTES`.

**Solo `REBOTE_CONFIRMADO` puede producir un candidato**, y exige las dos condiciones a la vez: que el precio haya roto el techo de la base con volumen *y* que el rebote desde el suelo pase del 1 %. Las dos vienen de detectores que ya existían y que confirman después del hecho; ninguno anticipa el suelo.

El estado vive en la tabla `motor_estado`, no en memoria: reiniciar no reabre una caída ya cerrada ni reinicia su reloj.

## La población, que es el punto

Guardar solo lo que pasó el filtro comprador es evaluar el filtro con sus propios elegidos. Por eso cada fila dice **por qué** se guardó:

| origen | qué es |
|---|---|
| `TRANSICION` | el veredicto o el estado cambió |
| `ALERTA` | en ese instante el sistema emitió una alerta |
| `VETO` | en ese instante un candidato quedó bloqueado |
| `MUESTRA` | el par cayó en la muestra rotatoria del universo, **mire lo que mire** |

La muestra es la única que no depende de que haya ocurrido nada, y es la referencia contra la que se medirán las otras tres. Rota 12 pares cada 5 minutos sobre la lista ordenada, así que en unas horas pasan todos y ninguno queda sistemáticamente fuera.

## Criterios de aceptación del plan

| | Criterio | Estado |
|---|---|---|
| ✅ | La ruta de caída detecta y sigue mercados donde no hay compra | probado: `CAIDA_ACTIVA` devuelve `ESPERAR` con «no se compra aquí — se sigue», y sin niveles |
| ✅ | Un rebote potencial no se marca como compra hasta el disparador declarado | probado en el contrato (`ValueError`) y en la secuencia completa: romper la base sin el rebote confirmado sigue siendo `ESPERAR` |
| ✅ | Existen «esperar», «conflicto» y «datos insuficientes» | los tres son veredictos de primera clase, con pruebas propias |
| ✅ | Los dos motores no modifican la emisión | corren después de que la emisión ya está decidida; cualquier excepción se traga; interruptor `motores_enabled`. Probado con un almacén que revienta |
| ✅ | No depender solo de candidatos que ya pasaron el filtro | los cuatro orígenes, con la muestra del universo |
| ✅ | Comparar primero reglas actuales y referencias sencillas | hecho y documentado en [MEDICION_RUPTURAS_EN_R.md](MEDICION_RUPTURAS_EN_R.md), con control pareado |
| ⏳ | Persistir predicciones en sombra sobre datos nuevos | empieza al desplegar |

## Coste

Los dos motores sobre 250 pares: **11,2 ms por ráfaga del minuto**. El ancla de 1h se relee solo cuando cierra una vela de 1h — releerla en cada vela de 1m de cada par sería el mayor gasto del minuto y no cambiaría nada.

Escritura acotada: deduplicación por cambio de veredicto, enfriamiento de 5 min por par y motor (que un candidato o un conflicto se saltan), y tope de 120 filas por pasada. **El tope no marca la lectura como vista**, así que una fila que no entra se reintenta al minuto siguiente en vez de perderse en silencio.

## Dos fallos que la suite no vio y sí vieron los datos reales

Los dos salieron de pasar el motor de caída por **caídas reales de producción** —ocho pares que cayeron entre −18 % y −45 % en 72 h— en vez de por datos de ejemplo.

### 1. El motor de caída no podía abrir. Nunca.

`retroceso.caida_pct` llega **con signo**: una caída del 26 % es `-26.0`. Yo comparaba `caida_pct >= 2.0`. Ningún valor negativo pasa nunca esa condición, así que el motor cuyo primer trabajo es reconocer una caída era incapaz de reconocer ninguna.

Las 41 pruebas pasaban porque **sus datos de ejemplo tenían el mismo error de signo que el código**. Ese es el fallo más caro de este tipo: la prueba y el código salen de la misma cabeza equivocada y se confirman mutuamente. Lo cazó el replay: ocho caídas reales, cero aperturas.

Corregido comparando en magnitud, con una prueba de regresión que usa los valores reales (−2, −4, −18,79 y −44,92) y exige apertura en los cuatro.

### 2. Una compra cada minuto en vez de una compra

Ya arreglado el signo, el replay marcaba **entre 161 y 340 minutos como `CANDIDATO` en un solo par**. Una vez en `REBOTE_CONFIRMADO`, cada minuto siguiente volvía a decir «compra».

Un disparador es un instante, no un estado. Un rebote confirmado hace tres horas no es una compra nueva ahora: el plan que nació de aquel disparo sigue su propio reloj, y reemitirlo es contar diez veces el mismo movimiento — justo lo que la identidad por episodio existe para evitar.

Ahora `CANDIDATO` solo sale en el minuto de la transición; después el estado sigue siendo `REBOTE_CONFIRMADO` pero el veredicto es `ESPERAR` con «el disparador ya ocurrió». El replay pasó de 161–340 a **0–3 candidatos por caída**.

### 3. `EXTENDIDO` etiquetaba medio universo

Salió de mirar el reparto de familias en vivo: `EXTENDIDO` se llevaba **443 de 490** lecturas (90 %). El dato que no cuadraba: `consumido_pct` mediano de **0,74 %**, muy por debajo del umbral de 3,5 %, y **238 de ellas sin ninguna ruptura en 1h**.

La causa está en `impulse._clasificar_fase`: devuelve `FASE_AGOTADA` en cuanto el precio está bajo la EMA7 en dos marcos, que es casi cualquier moneda parada o cayendo. No eran movimientos extendidos, eran monedas quietas.

Y algo peor: **un pullback es, por definición, precio por debajo de su EMA corta**. `EXTENDIDO` se estaba tragando justo la familia que el plan quiere medir — `PULLBACK_TENDENCIA` no aparecía ni una vez.

Corregido con dos condiciones: tiene que existir una tesis alcista (ruptura del ancla o tendencia de 1h viva) para que pueda estar gastada, y un retroceso detectado no cuenta como agotamiento.

Medido 20 minutos después del arreglo:

| | antes | después |
|---|---|---|
| EXTENDIDO | 443 (90 % de las familias) | 75 (71 %) |
| RUPTURA_SOSTENIDA | 19 | 20 *(en 20 min)* |
| RUPTURA_RETEST | 28 | 9 |
| **PULLBACK_TENDENCIA** | **0** | **2** |
| SIN_TESIS | 463 | 280 |

Que `EXTENDIDO` siga siendo el 71 % ya no es un defecto: ahora sí son pares en tendencia alcista de 1h con el impulso gastado. Es una observación sobre el mercado —y sobre por qué este sistema avisa tarde— no un error de etiquetado.

## Lo que encontró la revisión externa, y cómo quedó

Una revisión independiente (`revision-codex/REVISION.md`) reprodujo tres defectos más. Los tres se comprobaron contra el código antes de tocar nada, y los tres eran ciertos. Cada corrección lleva una prueba que **falla con el código anterior** — se verificó una por una.

### R2 · El disparador del rebote se saltaba el filtro de volumen

`base_rebote.rompio` se asigna en cuanto el máximo de la vela pasa el techo, **antes** de mirar el volumen. El detector puede devolver `rompio=True` con `detected=False` y motivo «rompe sin volumen». El motor lo trataba como «rompió con volumen» —así lo decía hasta su propio docstring— y confirmaba rebotes que el detector rechaza. Lo mismo con una ruptura vieja: `rompio` sigue en `True` cuando el precio ya está muy por encima del techo.

Ahora hay una función `ruptura_valida()` que exige las tres cosas por separado, sin heredar el `score` del detector: rompió el techo, con volumen ≥ mínimo, y sin llegar tarde. Si el volumen no se puede medir, no dispara.

La prueba conecta **el detector real** con el motor: unas velas cuya ruptura sale con 0,5× de volumen dan `rompio=True` / `detected=False` / «rompe sin volumen», y el motor se queda en `ESPERAR`. Con 15× de volumen, confirma.

### R3 · El tope de escritura perdía alertas y su identidad

El tope por pasada descartaba cualquier fila, incluidas las que llevan `alerta_id`, `plan_id` y `episode_id`. Ese enlace no se recupera: la fila del minuto siguiente es otra observación, sin la alerta detrás.

Medido en producción con mis propios números: de **100 alertas emitidas, solo 64 tenían lectura vinculada — 36 se perdieron**.

Ahora el tope se aplica **solo a las transiciones**, que son la única fuente sin límite propio. Las alertas y los vetos ya están acotados por el ritmo de emisión, y la muestra por su configuración; además son las únicas filas con identidad, y la muestra es la población de referencia de toda la fase.

### R4 · El evaluador reescribía el resultado con el coste de hoy

`planes.coste_pct` se guarda congelado con el plan, pero el evaluador de la fase 2 descontaba el de la configuración actual — y la consulta de pendientes ni siquiera lo seleccionaba. Cambiar el ajuste reescribía el resultado neto de toda ventana todavía abierta.

Reproducido: entrada 100, objetivo 105, coste del plan 0,5 % → **+4,5 % neto**. Reanudar con coste global 0,8 % lo cambiaba a **+4,2 %** sobre el mismo plan. Ahora usa el coste que el plan congeló; los planes anteriores al campo caen al global, y se nota porque la fila no trae el valor.

### Y un hueco mío que la revisión apuntó como limitación

`ServicioMotores.observar()` nunca rellenaba `Observacion.confluencia`, así que `conf_confirmadas` salía vacío en todas las lecturas aunque el contrato lo declarara. No cambiaba ningún candidato —la confluencia no pondera nada— pero dejaba sin dato justo la variable que se quería poder medir después. Ahora se compone de las lecturas por marco cacheadas, que se refrescan al cerrar cada vela de su marco.

### Comprobado en producción 10 minutos después

| | antes | después |
|---|---|---|
| Alertas con lectura vinculada | 64 de 100 (**36 perdidas**) | **29 de 29** |
| Lecturas con `conf_confirmadas` | 0 | **316 de 316** |

R4 no se comprueba en producción a propósito: exigiría cambiar el coste real para verlo. Queda cubierto por la regresión, que da 4,2 % con el código viejo y 4,5 % con el nuevo.

## El motor de caída, recorriendo una caída real

`TKOUSDT`, que cayó un 18,79 % en una hora:

```
ABRE         -> CAIDA_ACTIVA       0.0556
AVANZA       -> DESACELERACION     0.0554
AVANZA       -> BASE_EN_FORMACION  0.0552
AVANZA       -> RECUPERACION       0.0558
NUEVA_CAIDA  -> CAIDA_ACTIVA       0.0549     ← pierde el suelo, se invalida
AVANZA       -> DESACELERACION     0.0547
AVANZA       -> BASE_EN_FORMACION  0.0548
AVANZA       -> RECUPERACION       0.0546
AVANZA       -> REBOTE_CONFIRMADO  0.0568     ← el único candidato
```

`GUSDT`, que cayó un 44,92 % y no se recuperó dentro de la ventana, produce **cero candidatos**. Eso es lo que se le pide: seguir un mercado donde no hay compra sin inventarse una.

## En vivo, 20 minutos después del último despliegue

- **Motor de caída trabajando**: 103 transiciones, y ahora mismo 2 pares en `CAIDA_ACTIVA`, 3 en `DESACELERACION` y 12 en `RECUPERACION`, sin marcar compra en ninguno. `NUEVA_CAIDA` disparó 5 veces: rebotes que perdieron su suelo y se invalidaron en vez de quedarse esperando.
- **Motor de continuación**: 3 candidatos, todos coincidiendo con alertas reales del sistema.
- **Los cuatro orígenes escribiendo**, con 72 pares distintos en la muestra del universo.
- **Emisión intacta**: la hora 07:00 UTC de hoy lleva 42 alertas a mitad de hora, frente a 40–58 en la hora completa de los cuatro días anteriores. Ningún efecto sobre lo que sale.
- **0 errores** desde el primer arranque.

## Migración ensayada

Sobre una copia de la base **real** de producción: 916 MB copiados en 13,4 s con el servicio escribiendo, salto **v18 → v19 en 19 ms**, integridad `ok`, **ninguna fila cambiada** en las 16 tablas existentes, tres tablas nuevas vacías.

## Despliegue

Copia previa en `/home/flox/.cache/sacbinance-f4-deploy/20260922T062934Z/`: los cuatro archivos de backend que se modifican y la base entera (916 MB, copiada en 6,7 s con el servicio escribiendo, **v18 sin tablas `motor_*`**).

Migración v18→19 aplicada en el arranque de las 06:33 UTC. Verificada contra esa copia previa: **integridad `ok`, ninguna fila perdida** en las 14 tablas existentes, todas creciendo con normalidad. Segundo reinicio a las 06:41 con los dos arreglos de arriba. **0 errores** en el log, API respondiendo 200, 182 pruebas en verde en el servidor.

## Reversión

`motores_enabled=false` apaga los dos motores sin tocar nada más. Las tablas nuevas se quedan con lo que hubieran escrito; ningún otro componente las lee.

## Lo que esta fase NO hace, a propósito

- No cambia ninguna emisión, ningún nivel, ningún mensaje de Telegram.
- No entrena nada. La medición dice que no hay columna que ordene; meter un modelo encima de eso sería ajustar ruido.
- No aparece en el tablero. La presentación es la fase 6, y enseñar un veredicto antes de medirlo en datos nuevos es como se fabrica una confianza sin respaldo.
- No toca los cuatro trackers existentes.
