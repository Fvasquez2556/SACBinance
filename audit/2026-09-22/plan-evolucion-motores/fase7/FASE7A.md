# Fase 7a — reglas de activación congeladas · 24-sep-2026

**Desplegada en producción** (24-sep, 16:52 UTC). Esquema v21 aditivo, `backend/src/activacion/` (registro congelado, regla de elección del rival, almacén y reparto), ajuste `activacion_enabled`. **44 pruebas nuevas; 356 en total en verde.** Registro en **v2**, tras una revisión externa que encontró tres discrepancias entre el contrato y el código y un error de ocho veces en mi aritmética — el detalle está en el §11 del [registro congelado](ACTIVACION_CONGELADA.md).

**No activa nada.** Al terminar esta fase el sistema emite exactamente igual que antes: activación apagada, ningún rival atado, emisión idéntica. Lo único que corre es el reparto por episodio, en sombra.

## Por qué ahora y no el día del veredicto

La fase 7 del plan exige una fracción **«definida antes de ver sus resultados»**. El 23-sep ya vi un resultado parcial de la fase 5 sobre el universo entero. Cada día que estas reglas siguieran sin escribirse, la elección quedaría más teñida por lo que voy viendo pasar — y no habría forma de demostrar lo contrario.

El registro completo está en [ACTIVACION_CONGELADA.md](ACTIVACION_CONGELADA.md), con su sha256 dentro de la huella.

## Las cuatro decisiones que quedan cerradas

### 1 · Quién puede ser el rival — la regla, no el nombre

Nombrarlo hoy sería prejuzgar la fase 5. Se congela **cómo se elige**: la política que pase las tres puertas sobre la población decisoria con el mayor límite inferior del dinero.

**Y una condición que la fase 5 no tiene.** Sus tres puertas son **absolutas**: una política puede pasarlas siendo **peor que la referencia** —le basta con ganar algo y acertar más de lo que su geometría predice—. Activar eso sería un retroceso presentado como mejora. El propio plan lo pide en su §8: «comparación pareada frente a la política vigente». La fase 5 calcula ese pareado y lo reporta, pero **no lo mete en su veredicto**.

No se toca su registro congelado —cambiarlo invalidaría la prueba en marcha—, así que la condición se añade aquí, como requisito **adicional** de activación. Es más estricto, no menos, y queda escrito antes de saber quién gana.

**Y una tercera condición, contra coronar a una ganadora por azar:** se examinan hasta diez políticas, y quedarse con el máximo de diez estimaciones infla por construcción. La ganadora tiene que sostener su ventaja pareada **en las dos mitades temporales**, no solo en el agregado. Es la misma vara que tumbó aquí a «la primera señal es la buena» y a la regla C3. Una elección sin ese corte sale marcada `provisional` y **no autoriza a activar**.

### 2 · La fracción: 25 %, y mi aritmética estaba mal

La v1 puso 50 % justificándolo con «≈2 planes decisorios al día». Ese 2 salía de los 2 medibles de las primeras 25 h — **y eran el atasco de la hambruna del evaluador, no la tasa de llegada**. Leí un artefacto de mi propio bug como si fuera un dato del mercado.

Remedido con el atasco drenado, separando generación de maduración:

| | |
|---|---|
| planes decisorios **creados** | **17,6 al día** (32 en 43,5 h) |
| tasa de **maduración** | 68,4 % (13 de 19) |
| **medibles** al día | **≈ 10,5** |

| fracción | días hasta n=50 en el brazo rival | señales afectadas |
|---|---|---|
| 50 % | ≈ 9,5 | la mitad |
| **25 %** | **≈ 19** | **una de cada cuatro** |
| 10 % | ≈ 48 | una de cada diez |

Con la tasa real el 50 % ya no hace falta, y el 10 % ya no es absurdo (48 días, no 250) — se descarta porque 48 días atraviesan varios regímenes y este sistema movió su tasa base 15 puntos en una semana. Y **la fracción sí acota exposición**: la v1 lo negaba y era un error. El cortacircuitos complementa ese límite, no lo sustituye.

### 3 · El reparto: por episodio, determinista, escrito una vez

```
u = primeros 8 bytes de sha256("<huella>:<episode_id>") en [0,1)
brazo = RIVAL si u < FRACCIÓN
```

Sin generador aleatorio: este servicio reinicia, y un `random` con estado rebarajaría en cada arranque. La huella entra en el hash para que una versión nueva rebaraje en vez de heredar la suerte de la anterior. Y `episode_id` es **clave primaria** de la tabla: la regla «se escribe una vez» es esquema, no confianza en que nadie llame dos veces.

La fracción se lee del registro en vez de mirar si el hash es par. Con la paridad, cambiarla en el documento dejaría el reparto clavado en el 50 % y el papel diría una cosa mientras el código hacía otra.

### 4 · Reversión asimétrica

| disparador | umbral |
|---|---|
| daño | > 1,0 punto por operación, n ≥ 15 por brazo |
| cortacircuitos | capital **compuesto** del rival ≤ −10 % **y la referencia por encima de ese suelo** → revierte **ya**, sin esperar a n |
| integridad | cualquier fallo → revierte ya |
| manual | el operador, sin justificar |

**No existe un disparador de «va ganando».** Las revisiones son de calendario (30 y 60 días) y la fracción no sube por un resultado intermedio favorable. Parar —o crecer— al ir ganando es elegir el momento que más favorece: así se fabricó el +0,25 % de la regla C3 que se evaporó con tres horas más de datos. Hay una prueba que se llama `test_winning_never_triggers_a_stop`.

**Y los disparadores se aplican solos**, en el bucle de mantenimiento. En la v1 `evaluar_reversion()` devolvía una decisión y nadie la llamaba: presentar eso como protección era falso. Ahora hay una prueba de extremo a extremo que mete datos, deja correr la vigilancia y comprueba que la activación queda apagada sin intervención.

Revertir es **apagar un interruptor**, no restaurar una copia: los planes ya notificados conservan sus niveles, las operaciones registradas también, y no se toca ninguna base antigua.

**Y lo que revertir NO hace, sin adornos:** corta la exposición **futura**. No cierra ninguna posición abierta, y un stop puesto en el exchange no garantiza el precio de ejecución — con un hueco se ejecuta donde haya liquidez. El −10 % es un umbral de decisión, no un suelo de pérdida.

## La amenaza que esta fase no puede eliminar

El brazo decide **qué se muestra**; quien decide **qué se toma** es el operador, y puede preferir un brazo sistemáticamente. Si eso pasa, la población tomada deja de ser comparable aunque la asignación sea perfecta.

No hay forma de evitarlo sin quitarle la decisión al operador. Así que se declara la lectura: manda la **principal** (todos los planes decisorios emitidos, en sombra, independiente de qué se tomó), y la secundaria —el dinero de verdad— va siempre con la **tasa de toma por brazo** al lado. Y cada mensaje de Telegram dirá a qué brazo pertenece: un experimento que el sujeto no puede auditar es un cambio silencioso.

## Ensayo de migración sobre la base real

Copia de **1.230 MB en 17,8 s** con el servicio escribiendo:

| | |
|---|---|
| v20 → v21 | **23 ms** |
| filas cambiadas en tablas existentes | **ninguna** |
| tablas nuevas | 4, vacías |
| integridad | `ok` |
| reparto sobre **2.006 episodios reales** | 1.484 / 522 → **fracción 0,2602** |
| segunda pasada mueve a alguien | **no** |
| integridad del reparto | limpia |

El ensayo corrió sobre un árbol de staging en `/tmp`, borrado después: no queda un solo fichero nuevo en el directorio de la aplicación mientras el despliegue no esté autorizado.

## Criterios de aceptación del plan

| | criterio | estado |
|---|---|---|
| ✅ | Solo activar una política validada y revisada por el usuario | `activar()` exige `aprobado_por` y el veredicto; probado por sus rechazos |
| ✅ | Fracción acotada definida antes de ver sus resultados | **25 %**, congelada con su aritmética remedida |
| ✅ | Conservando una referencia comparable | brazo REFERENCIA, mismo reparto |
| ✅ | Asignación por episodio | clave primaria; probado que un episodio no cambia de brazo |
| ✅ | No aumentar a la vez avisos o riesgo | congelado en el registro, con prueba |
| ✅ | Reversión que vuelve a la política previa | interruptor, probado |
| ✅ | Mantener planes notificados y operaciones registradas | probado: revertir conserva el reparto y los niveles |
| ✅ | No restaurar ciegamente una base antigua | revertir no toca ninguna tabla existente |
| ✅ | Migración ensayada sobre copia de la base real | 23 ms, ninguna fila cambiada |
| ✅ | Desplegado | 24-sep 16:52 UTC. Migración v20→21, 356 pruebas en verde en el servidor, reparto ejercitado en vivo |
| ⏳ | Fase 7b | cuando la fase 5 llegue a n=50 (**≈27–29 sep** al ritmo actual) **y** exista un rival que cumpla las tres condiciones |

## Lo que la puntuación de los motores cambia en esta fase

Nada de las reglas — y eso es lo correcto. Pero cambia la expectativa: medido el 24-sep ([PUNTUACION_MOTORES.md](PUNTUACION_MOTORES.md)), **el veredicto del motor de continuación no ordena (AUC 0,501)**, así que hoy no hay ningún filtro de selección que activar. Lo que la fase 7b pueda encender saldrá de la fase 5 —los objetivos de salida— y de nada más.


## Despliegue — 24-sep-2026, 16:52 UTC

| paso | resultado |
|---|---|
| diff local contra remoto | 68 líneas en 4 ficheros + 5 nuevos. **Nada más había derivado** |
| copia de seguridad | `pre-v21-20260924-165144.db`, 1.233 MB en 8,6 s, esquema v20 |
| pruebas en el servidor | **356 en verde** (1 omitida: el documento no vive en el servidor) |
| reinicio | `kill -TERM`, `Restart=always` lo levantó |
| migración | v20 → **v21** |
| registro congelado | huella **`060c86b2d35cd99b`**, `fase7a-v2` — la misma del ensayo |
| estado de la activación | **0 filas: apagada, sin rival atado** |
| API | viva a los ~30 s |
| reparto en vivo | los dos primeros planes nuevos recibieron brazo: uno RIVAL, uno REFERENCIA |
| emisión | intacta: 2 de 2 alertas con identidad de episodio |
| fases 2, 4 y 5 | siguen midiendo (1.254 medidas, 440 lecturas, 967 recorridos en los primeros 5 min) |

### Reversión

Esta fase **no cambia ninguna emisión**, así que revertirla es quitar código, no restaurar datos:

1. `activacion_enabled = false` en los ajustes → deja de repartir. Nada más se detiene.
2. Si hiciera falta retirar el código: borrar `src/activacion/`, revertir los 68 renglones de los cuatro ficheros y bajar `SCHEMA_VERSION` a 20. **Las cuatro tablas `activacion_*` pueden quedarse**: nadie más las lee, y borrarlas perdería el reparto ya hecho.
3. **No restaurar la copia de seguridad** salvo corrupción real. La copia es de las 16:51 y desde entonces hay operaciones, desenlaces y lecturas que no tienen nada que ver con esta fase — restaurarla los borraría. Es la misma regla que el propio registro impone para revertir la fase 7b.
