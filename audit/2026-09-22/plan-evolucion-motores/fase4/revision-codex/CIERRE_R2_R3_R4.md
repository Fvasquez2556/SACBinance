# Reverificación de R2, R3 y R4

**Resultado al 22-sep-2026, 07:55:38 UTC / 01:55:38 Guatemala: los tres defectos originales están corregidos en local y en el código desplegado del servidor.** Los mismos casos de la revisión anterior ahora devuelven el resultado esperado. No se modificó el producto, la configuración ni el servicio durante esta comprobación.

## Casos reproducidos nuevamente

- **R2 — volumen insuficiente:** usando el detector real y las mismas velas sintéticas, la ruptura con volumen 0,5× frente al mínimo 2× ya no produce un candidato. Conserva `RECUPERACION` / `ESPERAR`. La nueva función también comprueba que haya volumen medido y que no se supere la distancia máxima sobre el techo. Las pruebas de ruptura tardía y volumen ausente pasan.
- **R3 — escritura saturada:** se llena el límite con otro par y después se registra una alerta. Ahora se conservan **las dos lecturas**, con `origen=ALERTA`, su alerta 777 y su plan 888. El límite solo bloquea lecturas de transición; las pruebas de muestra y alerta durante saturación pasan.
- **R4 — coste congelado:** entrada 100, objetivo 105, coste del plan 0,5 %. El resultado permanece en **+4,5 % neto** después de reanudar el evaluador con coste global 0,8 %. La consulta de pendientes ya recupera `p.coste_pct` y la evaluación usa ese valor. Los planes sin coste propio mantienen el fallback explícito al coste general.
- **R1 — signo de la caída:** se mantiene corregido; el detector real entrega −4 % y el motor abre `CAIDA_ACTIVA` / `ESPERAR`.

Los casos se ejecutaron **tanto localmente como directamente en el servidor**, en un proceso de comprobación separado y con SQLite en memoria. No se insertaron operaciones, alertas ni lecturas ficticias en producción. Ver [resultados en el servidor](reproducciones-servidor-20260922T075458Z.json).

## Despliegue y evidencia nueva en producción

- Los **33 archivos comparados coinciden byte a byte** entre local y servidor. Ver [captura de estado y hashes](estado-20260922T075347Z.json).
- Los tres módulos corregidos se subieron a las 07:39:12 UTC; el proceso activo arrancó después, a las **07:40:00 UTC** (PID 3425098). Esquema 19 y API HTTP 200, con 250 pares.
- En la ventana posterior al arranque y hasta la última lectura almacenada había **30 alertas nuevas: las 30 tienen lectura vinculada en ambos motores**. Cero discrepancias entre sus identificadores de plan/episodio y los de las alertas.
- `observar()` ya rellena la confluencia. En producción, **359 de 359 lecturas nuevas del motor de continuación** contienen `conf_confirmadas`, con valores observados de 0 a 3.
- **Alcance de esa corrección de confluencia:** las 316 lecturas nuevas del motor de caída no guardan `conf_confirmadas` en su propio campo `datos`. La observación común lo recibe, pero `caida.py` no lo incorpora a lo que persiste. Por tanto, el hueco original del motor de continuación está cerrado; no afirmar que la confluencia se conserva en las filas de ambos motores.

Recuentos, ventana y fechas de archivos en [validación en vivo](validacion-vivo-20260922T075537Z.json). Es una ventana inicial de unos 15 minutos, suficiente para comprobar que el flujo ya escribe; no acredita una mejora de rentabilidad ni una prueba de carga prolongada. Los huecos de datos anteriores al despliegue no quedan reconstruidos por esta corrección.

## Pruebas y punto de parada

**202 pruebas de backend correctas, cero fallos y cero omitidas.** Incluye las pruebas que conectan el detector real con el motor; en esta ejecución no se saltaron. Ver [registro de pruebas](backend-reverificacion-20260922T075459Z.log). No se repitieron pruebas de frontend porque estas correcciones no lo modifican.

Se cierran los hallazgos originales **R2, R3 y R4** para la versión comprobada. La verificación sigue limitada a la fase 4; no se inició una fase posterior, no se cambió el objetivo de beneficio y no se programó monitorización.
