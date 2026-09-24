# Avisos relevantes de Telegram

Estado al terminar: archivos instalados y verificados en Ubuntu; **pendiente reiniciar el servicio**.
El intento `sudo -n systemctl restart sacbinance` devolvió `sudo: interactive authentication is required`.
La API continúa respondiendo HTTP 200 con el proceso anterior (PID 1891912, esquema 14).
Los cambios empezarán a funcionar al reiniciar; el arranque creará el esquema 15.

Desde PowerShell, en el equipo con el alias SSH configurado:

```powershell
ssh -t sac "sudo systemctl restart sacbinance"
```

La contraseña se introduce directamente en la terminal. No se necesita enviarla al chat.

## Comportamiento implementado

- Máximo de **3 oportunidades nuevas en una hora móvil**, persistido en SQLite.
- Selección en lotes de 30 segundos: relación beneficio/riesgo del plan, luego score y liquidez. Es una regla de selección, no una probabilidad de éxito validada.
- Se exige un plan coherente, TP neto de costes supuestos de al menos 3.2%, riesgo dentro del límite configurado, score mínimo 75 y volumen de 24h mínimo 2M USDT. Se rechazan resistencias antes del TP y falsas rupturas.
- Los rebotes mantienen la confirmación requerida. Las continuaciones necesitan impulso sostenido o acelerando y un movimiento todavía no extendido.
- Antes de enviar se comprueba que el plan siga vigente y el precio no se haya alejado más de 0.5% de la entrada congelada.
- Un plan notificado abierto por par. No se abren avisos repetidos por cada cambio de estado o marco. El cooldown entre nuevas oportunidades del mismo par sigue en 45 minutos.
- La actualización ordinaria se hace editando el mensaje cada 5 minutos, sin generar una notificación nueva.
- Los antiguos seguimientos de rupturas por 15m/1h/4h/24h editan su mensaje original. Las nuevas rupturas cortas permanecen registradas para consulta y medición en la UI; solo los planes seleccionados originan avisos nuevos.
- Avisos relevantes del plan: +3.2% bruto una sola vez, TP, SL y proximidad al SL una sola vez al consumir el 80% del riesgo inicial. Estos eventos no consumen el cupo de oportunidades nuevas.
- TP y +3.2% en una misma vela se combinan. El hito de +3.2% no cierra un plan cuyo TP sea superior. Alcanzar TP o SL termina sus avisos; no se presenta un rebote posterior al SL como ganancia de ese plan.
- Si la misma vela toca SL y TP/meta, el orden es desconocido: se informa esa ambigüedad y no se anuncia éxito.
- Los niveles y los identificadores de mensajes se conservan para no mezclar una entrada con el seguimiento de otra después de un reinicio.
- Los mensajes identifican la señal de 1m y el contexto de 15m/1h/4h; un giro de 1m no se presenta como invalidación de una estructura de 1h.
- Caducidad de 12h conforme al plan existente: actualiza el mensaje en silencio, incluso si ya no llegan velas.

## Alcance y límites

Esta modificación afecta la selección y entrega de notificaciones. Conserva los motores de señales, los análisis multitemporales y las mediciones en sombra. No cambia la estrategia para emitir órdenes y no incorpora avisos de ejecución real de una entrada.

El seguimiento es simulado con velas cerradas de 1m. Excluye la vela que comenzó antes del aviso, cuyo recorrido no puede atribuirse íntegramente al periodo posterior a recibirlo. No reconstruye en este cambio los recorridos perdidos durante una desconexión. El +3.2% del hito es bruto; el mensaje distingue el TP neto bajo el coste supuesto.

Los eventos confirmados por Telegram no se repiten tras un reinicio. Un fallo de red sin confirmación tiene la limitación habitual de entrega incierta; no se promete entrega exactamente una vez. Los envíos iniciales interrumpidos no se reenvían automáticamente como si fueran entradas nuevas.

La reducción efectiva de mensajes y el rendimiento de las oportunidades seleccionadas deben medirse después de la activación; las pruebas no demuestran una mejora de rentabilidad.

## Archivos y comprobaciones

- `backend/src/notify/policy.py`: selección, presupuesto horario, persistencia y eventos del plan.
- `backend/src/notify/service.py`: lotes, comprobación antes de enviar, entrega y mantenimiento.
- `backend/src/notify/telegram.py`: edición por ID y textos del plan y sus eventos.
- `backend/src/state/engine.py`: integración con velas y alertas; supresión de mensajes repetidos de rupturas.
- `backend/src/persistence/db.py`: tablas `notificacion_planes` y `notificacion_eventos`, esquema 15.
- `backend/src/config/settings.py`: parámetros de la política.
- `backend/main.py`: mantenimiento periódico y cierre del servicio de notificaciones.
- `backend/tests/test_notification_policy.py`: regresiones sin conexiones reales a Telegram.

Pasaron **62 pruebas en Ubuntu**, además de la compilación de los ocho archivos instalados. Incluyen deduplicación, concurrencia del cupo, TP/SL, ambigüedad intravela, reinicios, caducidad, fallos de transporte y seguimiento sin mensajes nuevos. Antes de las dos últimas regresiones también habían pasado las 60 pruebas locales.

Se ensayó la migración y recuperación sobre una copia consistente de la base real. `PRAGMA quick_check` devolvió `ok`; los recuentos anteriores y posteriores coincidieron: 4,000 señales, 5,571 outcomes, 2,672 alertas, 4,000,764 velas, 1,092 rupturas y 2,480 rupturas por marco. La prueba recuperó dos planes notificados abiertos y nueve históricos, sin enviar mensajes.

Se comparó el hash de cada archivo remoto con el respaldo inicial antes de reemplazarlo y con el archivo probado después de instalarlo. No se sobrescribieron los demás cambios del repositorio ni el frontend.

Evidencia local: `stage-result.json`, `install-result.json`, `verification.json`, `remote-before.json` y `local-tests.txt` en este directorio.

Respaldo remoto de los archivos anteriores y de la base consistente:

`/home/flox/.cache/sacbinance-notification-deploy/20260918T043955Z/backup`

El directorio superior también contiene la versión probada, su manifiesto y los resultados de pruebas y migración. La fecha remota es UTC del 18 de septiembre; corresponde al 17 de septiembre en Guatemala.

Tras reiniciar puede ejecutarse `verify_notifications.py` desde este directorio para comprobar hashes, servicio, API y esquema 15. Este verificador es de solo lectura y no contacta Telegram.
