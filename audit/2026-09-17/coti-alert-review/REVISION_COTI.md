# COTIUSDT: revisión de avisos del 17 de septiembre

Corte: 2026-09-17T14:27:15-06:00. Todas las horas siguientes son de Guatemala (UTC−6). Se asume COTIUSDT por el par de la conversación anterior; las capturas nuevas no muestran su símbolo.

**Sí existen avisos de COTI registrados como enviados. Esto no equivale a confirmar que el usuario vio una notificación en su dispositivo.**

- 05:56:00: alerta 2292, señal 3732, SUBIENDO, entrada 0.01897, TP 0.020106 y SL 0.018402. `telegram=enviado`.
- 08:23:00: la señal 3732 cerró como TP; resultado bruto registrado +5.988%. No es una ejecución real en Binance.
- 13:29:04: evento 39, RUPTURA_ALCISTA, precio 0.02297, «subida continua con impulso acelerando». Figura enviado y conserva el identificador del mensaje inicial; posteriormente se anotó seguimiento de 15m.
- 13:42:01: evento 67, RUPTURA_BAJISTA corta, precio 0.02312, «caída activa detectada por el sistema». También figura enviado. No es una invalidación calculada de la ruptura de 1h: usa el estado corto del tablero.

## Por qué esto no garantiza un aviso de ruptura de 1h

La lectura manual en `pair_report.py` calcula estructura por marco y devuelve un informe. El seguimiento por marco en `tf_rupture_tracker.py` es en sombra. Ninguno de esos dos caminos publica su propio aviso de Telegram. Las rupturas notificadas salen de `ruptures.py` y `_evaluar_ruptura`, basados en el estado corto; las señales con plan pasan por otro filtro de emisión y de Telegram.

Hay eventos de TENDENCIA, BASE e IGNICION en `analysis_log` anteriores a la señal de las 05:56. La ruta de perfiles los publica por WebSocket; no equivale a envío de Telegram. También hay vetos registrados por agotamiento, precio bajo EMA7 y movimiento consumido superior al 3.5%. No todos los movimientos visibles generan un nuevo plan ni un nuevo mensaje.

## Un problema adicional del registro

A las 12:50:00 aparece un log `ALERT MODERADA | SUBIENDO | score=79` sin niveles y sin fila asociada en `alertas_emitidas`. El código registra y publica el evento genérico después del intento de crear una alerta, aunque `AlertManager.emitir` pueda devolver None por falta de entrada. Ese log solo no prueba un envío. Debe distinguirse candidato detectado, plan válido, alerta creada y mensaje confirmado por Telegram.

## Cambio recomendado

Mostrar en cada par una cronología con tipo de evento, marco, niveles congelados, filtros y estado de publicación. Identificar explícitamente «señal con plan», «movimiento corto» y «ruptura de 1h». Registrar por separado el mensaje inicial y los seguimientos; el último seguimiento no debería reemplazar la descripción de la entrega inicial. Un estado bajista corto no debe presentarse como si invalidara automáticamente una estructura alcista de 1h.

La comprobación fue de solo lectura y no envió mensajes. `export_case.py` contiene las consultas y `evidence.json` conserva sus resultados; `sources.json` contiene la proyección acotada para la respuesta. No se pudo corroborar el envío con entradas adicionales de journald: la consulta acotada no devolvió coincidencias. La conclusión de envío se apoya en las tablas y en la semántica inspeccionada del cliente Telegram, que exige respuesta de éxito con identificador de mensaje.
