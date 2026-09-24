# Revisión de fase 5 — 22 de septiembre de 2026

**Conclusión: existe el evaluador local de experimentos por plan, pero no daría la fase 5 por cerrada.** Reproduje cuatro defectos de medición/informe y una diferencia entre la política escrita y la implementada. Además, la protección de versiones no cubre todo lo que el documento promete y falta implementar la lectura estadística declarada. Los límites de cartera son una decisión pendiente real, pero no son lo único pendiente.

Alcance: revisión del código local, ejecución de pruebas y consulta remota de solo lectura. No se modificó la aplicación, la configuración ni la base de producción; no se desplegó ni se reinició el servicio. Los únicos entregables nuevos de esta revisión están en esta carpeta. El registro congelado se conserva intacto.

## Estado local y del servidor

- **Local:** módulo `src/experimentos`, integración al mantenimiento, migración v19→v20 y 11 políticas: REF, A1–A5, B1–B2 y C1–C3. Las **223 pruebas del backend pasan**, incluidas 21 de experimentos. Esto no cubría los cinco casos adversos de esta revisión.
- **Servidor `sac`, `/home/flox/sacbinance`, a las 20:33:51 UTC / 14:33:51 Guatemala:** servicio activo y API HTTP 200, pero esquema **v19**. No existen las tablas `experimento_registro` y `experimento_resultados`, ni el directorio de módulos `backend/src/experimentos` revisado. Los cuatro archivos de integración difieren de los locales. El proceso sigue arrancado desde las 07:40 UTC.
- Por tanto, **en ese servidor todavía no está desplegada la fase 5**. No hay resultados prospectivos de esta fase allí ni fecha de congelación de producción que permita contar sus 12 horas de maduración. La fecha escrita en el documento no sustituye la fecha efectiva que se registrará en la base.

Evidencia: [inventario remoto final](estado-20260922T203351Z.json), [pruebas existentes](pruebas-backend.txt), [reproducciones y hashes](reproducciones.json). Los inventarios son fotografías del momento de consulta, no una afirmación sobre despliegues posteriores.

## F5-R1 · P1 · Se ignora el stop de la vela de entrada diferida

Ubicación: `backend/src/experimentos/almacen.py:190–200`.

Para evitar atribuir a una orden un máximo anterior a su entrada, `_medir()` descarta **toda** la vela del fill y comienza en la siguiente. También pierde el mínimo y cualquier stop ocurrido después de entrar. El argumento `stop` de `_fill()` no se utiliza, pese a que su comentario promete contar esa parada.

Reproducción con B2: entrada **98,5**, objetivo **106**, stop **95,545**. La primera vela abre a 100, alcanza 100,2 y cae a 95 antes de cerrar a 96; la siguiente sube a 107. Al abrir por encima de entrada y stop, la bajada cruza primero la entrada y después el stop. El resultado esperado es **STOP, −3,5 % neto**. El motor registra **OBJETIVO, +7,1142 % neto**, sin ambigüedad. La muestra incluye las 60 velas: no es un efecto de falta de cobertura.

Corrección requerida: conservar la información de stop y de huecos de la vela de entrada; tratar por separado el TP cuyo orden intravela sea desconocido. No basta con omitir la vela completa. Añadir esta regresión contra el evaluador real.

## F5-R2 · P2 · Se permiten fills fuera de la ventana

Ubicación: `backend/src/experimentos/almacen.py:143–162,179–197`.

La consulta incluye velas cuya apertura llega hasta el final de la ventana, inclusive. El núcleo de recorrido excluye minutos que no caben enteros; `_fill()` no aplica esa regla antes de decidir si se compró.

Reproducción: ninguna de las 60 velas de la ventana llega a 98,5. Solo lo hace la vela que **empieza al vencer**. Se evalúa dos minutos después, cuando esa vela ya puede estar cerrada. B2 se registra con `ms_fill=3600000`, `VENCIDO`, **−0,5 %**, cero velas útiles y `completa=1`. Debería ser `NO_LLENADO`, sin resultado de operación. La siguiente pasada no lo reconsidera.

Corrección requerida: aplicar a la búsqueda del fill la misma regla de elegibilidad temporal que al recorrido, incluidos los límites que no coinciden con un minuto exacto.

## F5-R3 · P2 · Una ventana vencida sin datos se convierte en pérdida definitiva

Ubicación: `backend/src/experimentos/almacen.py:198–223,274–282,295–314`; interacción con `backend/src/evaluacion/recorrido.py:226–242`.

Vencer por reloj no garantiza disponer del recorrido. Con cero velas, REF termina `VENCIDO`, `cobertura=0`, `completa=1`, **−0,5 % neto** y entra en la media como una operación resuelta. Para B1/B2, ausencia de datos también puede confundirse con certeza de que no se llenaron.

Añadí después una vela que habría alcanzado el objetivo y repetí mantenimiento: **cero reevaluaciones**, porque tener cualquier fila de resultado excluye el plan de pendientes. Así, una interrupción o un retraso en recuperar datos puede fijar permanentemente un resultado inventado. No afirmo que haya ocurrido en producción: la fase 5 aún no está allí.

Corrección requerida: separar madurez temporal, calidad de observación y resultado final; mantener retorno desconocido cuando no sea medible y permitir completar/revisar mediciones incompletas con trazabilidad. Definir antes del experimento la regla de cobertura, sin elegirla según qué política gane.

## F5-R4 · P2 · El informe oculta las órdenes no ejecutadas

Ubicación: `backend/src/experimentos/almacen.py:295–314`.

`resumen()` usa por defecto `desenlace != 'NO_LLENADO'` antes de agrupar. Por ello, `SUM(desenlace = 'NO_LLENADO')` siempre vale cero en las políticas que aparezcan; si una política nunca se llenó, desaparece por completo.

Reproducción: con 60 velas y ningún toque del límite, B2 queda correctamente almacenada como `NO_LLENADO`, pero no aparece en el resumen por defecto. El registro exige reportar siempre la proporción de órdenes no llenadas. Existe `solo_resueltas=False`, pero no es el comportamiento por defecto ni separa explícitamente elegibles, llenadas y no llenadas.

Corrección requerida: contar todas las oportunidades elegibles y sus estados, y calcular la media solo sobre operaciones con resultado medible. La tasa de ejecución debe conservar su denominador; no atribuir cero de rentabilidad a una operación que no existió.

## F5-R5 · P2 · B1/B2 no ejecutan exactamente la política documentada

Ubicación: `backend/src/experimentos/registro.py:188–200`; `fase5/REGISTRO_CONGELADO.md:29`.

El documento declara mismo objetivo y stop **en porcentaje**. El código conserva el porcentaje del stop, pero mantiene el **precio absoluto** del objetivo. La prueba existente exige expresamente ese precio absoluto.

Reproducción: referencia 100→106 (+6 % bruto), B2 compra a 98,5. El objetivo porcentual documentado sería **104,41**; el código usa **106** (+7,6142 % bruto desde su entrada).

Ambas variantes se pueden estudiar, pero son experimentos distintos. Se debe fijar una definición coherente en código, pruebas y contrato. Como el documento se declara inmutable, registrar una corrección/versionado explícito; no reescribir el protocolo anterior como si siempre hubiera dicho lo mismo.

## F5-R6 · P2 · La huella no protege todo el protocolo prometido

Ubicación: `backend/src/experimentos/registro.py:118–130`; `fase5/REGISTRO_CONGELADO.md:145–149`.

La huella actual, `3940d2a3a05518b1`, cubre la versión declarada, los campos de las políticas, las puertas y los textos de D1–D3. **No calcula el hash del documento**, ni incluye la versión del evaluador, la regla de fill, la regla de cobertura o la definición explícita de la población decisoria `Telegram Y primera del episodio`.

El documento promete que modificar su contenido cambia la huella. No es así: ese archivo no se lee al calcularla. También puede cambiarse el procedimiento de evaluación manteniendo las mismas constantes, de modo que mediciones con semánticas distintas compartan identificación si no se cambia manualmente la versión.

Corrección requerida: versionar explícitamente el método completo y registrar las definiciones que afectan al resultado, además de las barreras. Vincular el documento aprobado por hash, o corregir la promesa y mantener un manifiesto canónico completo. Una corrección metodológica debe dejar procedencia identificable y no mezclar resultados silenciosamente.

## Alcance que todavía falta, aparte de la cartera

Lo implementado mide cada plan bajo 11 alternativas y resume conteos y medias. Son avances útiles: respeta el coste congelado del plan, espera su horizonte antes de la evaluación ordinaria, excluye planes anteriores a la congelación y escala posiciones al comparar stops.

Sin embargo, los subconjuntos D1–D3 y las puertas estadísticas aparecen **declarados**, no calculados por el módulo. `resumen()` no selecciona la población decisoria, no compara diferencias pareadas contra REF, no calcula intervalos agrupados por par ni la puerta de habilidad. No encontré otro consumidor de estas nuevas tablas que complete esa lectura en el código revisado. Que las puertas estén en un diccionario no significa que se hayan verificado.

La fase 5 de `PLAN.md:383–389` incluye primera oportunidad por episodio y cartera con exposición limitada. Es más preciso describir el estado actual como **evaluador por plan implementado, pendiente de correcciones; informe de decisión y cartera pendientes**, en vez de fase 5 completa o bloqueada únicamente por números del usuario. Todavía no permite decidir que +4,2 % netos sea superior.

## Qué significa la decisión sobre riesgo y exposición

- **Exposición:** cuánto capital está invertido a la vez, en total y por moneda. También limita cuántas oportunidades simultáneas se pueden aceptar.
- **Presupuesto de riesgo:** pérdida prevista si los stops de las posiciones abiertas se ejecutan, tanto por operación como en conjunto. No equivale al dinero invertido.
- **Cartera:** procesa las señales cronológicamente, reserva y libera saldo, dimensiona posiciones y rechaza entradas que superan esos límites. Permite medir retorno de cuenta, rachas y caída de capital. Las medias independientes por plan no contestan eso.

Ejemplo exclusivamente aritmético: una posición de 500 USDT con stop a 2 % tiene exposición de 500 USDT y riesgo teórico de 10 USDT antes de costes y diferencias de ejecución. No son valores elegidos para el usuario. Dos posiciones simultáneas requieren sumar tanto su exposición como su riesgo.

Para configurar una simulación concreta hacen falta capital inicial ficticio, riesgo por operación, riesgo agregado máximo, exposición total/por moneda, máximo de posiciones y reglas de concurrencia. El usuario fija sus restricciones para representar su forma de operar; quien desarrolla el simulador traduce eso a reglas verificables. También pueden compararse escenarios hipotéticos explícitos, sin presentarlos como preferencias personales ya autorizadas.

## Secuencia propuesta para cerrar la revisión

1. Corregir F5-R1 a F5-R4 y cubrir los casos reproducidos.
2. Resolver la discrepancia B1/B2 y congelar una versión coherente del método/protocolo (F5-R5 y R6).
3. Añadir el informe sobre población decisoria, comparación pareada y puertas estadísticas; devolver «inconcluso» cuando corresponda.
4. Validar y desplegar la versión acordada; confirmar archivos, esquema, servicio y congelación real. Conservar los resultados de otras versiones identificados.
5. Incorporar la simulación de cartera cuando sus escenarios/límites estén definidos. No cambiar automáticamente la emisión ni el objetivo a +4,2 % por haber terminado el código del experimento.

Reproducciones: ejecutar desde la raíz `backend/venv/Scripts/python.exe -B audit/2026-09-22/plan-evolucion-motores/fase5/revision-codex/reproducir.py`. Usa exclusivamente SQLite en memoria. Sus cinco `FAIL` describen incumplimientos reproducidos de las invariantes esperadas; no son fallos de arranque del script. La evidencia JSON conserva resultados y hashes de las fuentes revisadas.
