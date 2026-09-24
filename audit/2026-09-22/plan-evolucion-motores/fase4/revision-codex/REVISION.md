# Revisión local y servidor: fases 1 a 4

**Actualización del 22-sep, 07:55 UTC:** R2, R3 y R4 ya fueron corregidos y comprobados de nuevo en local y servidor. Ver [cierre y evidencia actual](CIERRE_R2_R3_R4.md). El informe siguiente conserva el estado histórico anterior a esas correcciones.

22 de septiembre de 2026. Revisión solicitada por el usuario, limitada a lo ya implementado. **No se implementó ninguna fase posterior ni se modificó código del producto, configuración o servicio desde esta revisión.** Las escrituras de este trabajo están en esta carpeta de auditoría.

## Conclusión

La fase 4 está subida y activada en sombra, con esquema 19. Hay tres defectos reproducibles pendientes; por eso **no corresponde dar por validada toda la fase 4 ni utilizar sus lecturas como evidencia definitiva de mejora**. El problema del signo de la caída fue identificado en la primera revisión y corregido por el trabajo paralelo mientras se revisaba. Se distingue abajo de los problemas todavía presentes.

El diseño conserva la separación entre planes propuestos, recorridos y operaciones elegidas por el usuario. Los nuevos motores observan y guardan datos; sus veredictos no se utilizan para decidir las emisiones actuales. Esto limita el efecto inmediato de R2/R3 a la calidad de la medición en sombra. No se ha realizado una certificación histórica de igualdad de todas las alertas.

## Estado comprobado

Corte principal: **22-sep-2026 06:39:59 UTC / 00:39:59 Guatemala**. Ver [captura completa](estado-20260922T063959Z.json).

- **Local y archivos del servidor:** 33 archivos comparados, todos idénticos byte a byte: 20 módulos de producto, 12 archivos de pruebas y el índice del frontend compilado. No es una comparación exhaustiva de todo el repositorio ni de todos los recursos del frontend.
- **Servidor:** esquema 19; `/api/status` y `/api/operaciones` respondían HTTP 200; 250 pares.
- **Fase 1:** 406 alertas desde el inicio del registro, todas con `plan_id` y `episode_id`. 309 no tienen `signal_id`, pero sí su identidad propia. 188 episodios; ningún plan huérfano de episodio.
- **Fase 2:** los 406 planes tienen `plan_recorrido`. 88 ya tenían desenlace, pero **ninguna ventana completa de 12 horas**. Dos planes notificados resueltos coincidían entre el seguimiento anterior y el nuevo; esa muestra no permite validar todos los casos.
- **Fase 3:** diario disponible y vacío: cero operaciones y eventos. No se creó una operación ficticia en producción. La utilización real por el usuario todavía no está verificada.
- **Fase 4:** 538 lecturas sobre 250 símbolos; el motor de continuación produjo candidatos. Las 269 lecturas del motor de caída eran `SIN_TESIS`, sin transiciones ni estados persistidos todavía. Esto es compatible con el defecto R1 de la primera versión, aunque esos recuentos por sí solos no prueban la causa.
- **Pruebas locales del código actualizado:** 182 de backend, 47 de frontend y comprobación de tipos correctas. Resultados en [pruebas.json](pruebas.json). Las pruebas existentes pasan a pesar de R2/R3/R4: las reproducciones específicas muestran el hueco de cobertura.

Durante la revisión hubo cambios externos. A las 06:31 UTC los archivos estaban copiados, pero el proceso y la DB seguían en fase 3/esquema 18. A las 06:36 UTC ya estaba activo el proceso iniciado a las 06:33:17, con esquema 19. A las 06:38 se corrigieron y subieron `caida.py` y sus pruebas. A las **06:40:30 UTC** se observó otro arranque, PID 3409501, posterior a esa corrección. Ninguno de esos despliegues o reinicios lo realizó esta revisión.

## Hallazgos pendientes

### R2 · P2 · La confirmación del rebote omite el filtro real de volumen

Ubicación: `backend/src/motores/caida.py:235`, condición de transición de `RECUPERACION` a `REBOTE_CONFIRMADO`.

Se consulta `base_rebote.rompio` como si significara «ruptura válida con volumen». El detector `backend/src/analysis/base_rebote.py` asigna ese campo cuando el máximo supera el techo, **antes** de comprobar el volumen. Puede devolver `rompio=True`, `detected=False` y el motivo «rompe sin volumen».

Reproducción con los detectores reales y velas sintéticas: volumen de ruptura **0,5×**, mínimo configurado **2×**; la base es rechazada por volumen y el retroceso sí confirma un rebote. Partiendo de `RECUPERACION`, el motor devuelve **`REBOTE_CONFIRMADO` / `CANDIDATO`**, cuando debería seguir esperando bajo el contrato declarado. Este escenario se prueba partiendo de un estado de recuperación para aislarlo del error de apertura R1.

Corrección propuesta, sin implementar: definir un disparador explícito con los campos y umbrales de volumen necesarios y su disponibilidad; no equiparar el toque del techo con la validación completa. Añadir una prueba que conecte el detector real con el motor, incluyendo una ruptura con poco volumen y otra con mecha que no sostiene el techo.

### R3 · P2 · El límite de escritura pierde eventos y su identidad

Ubicación: `backend/src/motores/servicio.py:196`, y la rotación de muestra en el mismo archivo.

Al alcanzar el límite se descarta la llamada sin conservar la lectura ni su `origen`, `alerta_id`, `plan_id` y `episode_id`. Una llamada normal del minuto siguiente guarda una observación nueva como `TRANSICION`; no recupera la foto ni el enlace de la alerta original. No marcar la lectura como vista evita perder algunos estados estables, pero **no equivale a reintentar el evento original**. La muestra también avanza su cursor y cuenta pares procesados aunque no se hayan guardado filas.

Reproducción: límite reducido a dos filas para representar la saturación; se llena con el primer par, se procesa una alerta del segundo y se vuelve a procesar este al minuto siguiente. Aparecen filas `TRANSICION` sin identificadores y **cero lecturas para la alerta 777**, en vez de las dos esperadas.

Comprobación en producción a las **06:40:32 UTC**: entre la primera y la última lectura almacenadas había **43 alertas; 26 carecían de lectura vinculada en cada motor**. El conteo confirma el faltante, no atribuye por sí solo todas las ausencias a una única causa. La reproducción prueba una ruta concreta que lo produce.

Corrección propuesta, sin implementar: conservar una cola acotada con la observación y las identidades originales, o reservar capacidad para eventos de alerta/veto y para la muestra. Registrar descartes explícitos si el límite es inevitable; no presentar la muestra como completa o independiente de los eventos cuando se perdió por saturación. Probar la integración de ráfaga, alertas y muestreo.

### R4 · P2 · El evaluador ignora el coste congelado del plan

Ubicación: `backend/src/evaluacion/almacen.py:152` y la selección de planes pendientes en la línea 184.

`planes` conserva `coste_pct`, pero el evaluador descuenta `self.coste_pct`, procedente de la configuración actual. Además, la consulta de pendientes no recupera el coste de cada plan. Si cambia la configuración y se vuelve a evaluar un plan con ventana abierta, su resultado neto puede reescribirse con otros costes.

Reproducción en SQLite en memoria: entrada 100, objetivo 105 y coste del plan 0,5 %. El desenlace da **+4,5 % neto**. Reanudar el evaluador con coste global 0,8 % cambia ese mismo resultado a **+4,2 %**, aunque el plan conserva 0,5 %. No se cambió ningún coste real en producción para probarlo.

Corrección propuesta, sin implementar: seleccionar y aplicar el coste propio de cada plan. Los escenarios de costes alternativos deben identificarse por separado, sin sobrescribir el resultado de la política original. Añadir regresión de reinicio/cambio de configuración.

## R1 · Corrección observada durante la revisión

La primera versión de `caida.py` comparaba `retroceso.caida_pct >= 2.0`. El detector real entrega una caída del 4 % como **−4,0 %**, por lo que la reproducción devolvía `SIN_CAIDA` / `SIN_TESIS`. Los ejemplos iniciales de las pruebas usaban magnitudes positivas y reproducían la misma confusión.

El trabajo paralelo cambió la comparación a `abs(caida_pct)` y añadió dos pruebas. La reproducción local posterior devuelve correctamente `CAIDA_ACTIVA` / `ESPERAR`. Los archivos corregidos coinciden con el servidor. El arranque de las 06:40:30 es posterior a la subida; comprobar su actividad posterior se registra en la adenda de cierre, sin atribuir a esta revisión la corrección o el reinicio.

## Otros límites que quedan registrados

- `FASE4.md` y partes de `CONTINUIDAD.md` todavía describían la fase 4 como no desplegada al leerse. No deben usarse como única prueba del estado real. No se reescribieron esos documentos porque están siendo modificados en paralelo.
- `motor_lecturas` guarda `version=motores-v1`, pero no una configuración o huella de código por lectura. La corrección R1 ya separa dos comportamientos bajo la misma etiqueta. Conservar el corte de cada despliegue y la huella antes de agregar resultados. Esto es una limitación de procedencia, adicional a los tres defectos reproducidos pendientes.
- `ServicioMotores.observar()` no rellena `Observacion.confluencia`; `conf_confirmadas` queda ausente aunque el documento dice que se conserva para medirla. No se usa como peso, por lo que no cambia el candidato actual, pero limita la investigación posterior.
- Las muestras nuevas son demasiado jóvenes para concluir una mejora de rentabilidad o para cambiar el objetivo a 4,2 %. Esta revisión verifica implementación y despliegue, no vuelve a optimizar objetivos.

## Evidencia y reproducción

- [inspeccionar.py](inspeccionar.py): conexión SSH, consultas SQLite `mode=ro` y `query_only`, lectura de estado del servicio, API y hashes; guarda capturas nuevas con fecha. No importa el módulo de persistencia remoto ni ejecuta migraciones.
- [reproducir.py](reproducir.py): detectores reales con velas sintéticas y bases `:memory:`. Guarda resultados y huellas de las fuentes usadas. No llama a Telegram ni al servidor.
- [pruebas.json](pruebas.json), `backend.log`, `frontend.log`, `tipos.log`: pruebas y resultados de la revisión.
- `estado-*.json`: capturas sucesivas durante el despliegue paralelo.
- `reproducciones-*.json`: estado de los cuatro casos, con R1 ya corregido localmente.

Ejecutar desde la raíz local con el Python del entorno del backend y la opción `-B`. Los scripts solo escriben resultados en esta carpeta. La inspección consulta el servidor; las reproducciones son exclusivamente locales.

**Punto de parada:** revisión hasta fase 4. No se inicia la fase 5, no se modifica la emisión y no se aplican automáticamente las correcciones propuestas.

## Adenda de cierre: 06:42:19 UTC / 00:42:19 Guatemala

La [última captura](estado-20260922T064218Z.json) confirma el servicio activo tras el arranque de las 06:40:30 (PID 3409501), ambas consultas API con HTTP 200, 250 pares y esquema 19. Los 33 archivos siguen coincidiendo. Hay **408 planes y 408 recorridos**, todas las 408 alertas nuevas con identidad, y **672 lecturas de motores**. El diario continúa vacío.

La corrección del signo ya está en los archivos comparados y el proceso nuevo arrancó después de su subida. La reproducción local pasa; aún no hay transiciones de caída en este corte muy temprano, por lo que no se afirma haber visto en vivo una secuencia completa de caída y rebote después de corregirla. **R2, R3 y R4 permanecen reproducibles y no fueron modificados.** No quedan acciones de despliegue iniciadas por esta revisión ni una monitorización programada.
