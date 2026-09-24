"""Project the evidence needed to explain COTI notifications; no network calls."""
import datetime as dt
import json
from pathlib import Path

P = Path(__file__).resolve().parent
d = json.loads((P/'evidence.json').read_text(encoding='utf-8'))
tz = dt.timezone(dt.timedelta(hours=-6))
def local(ms):
    return dt.datetime.fromtimestamp(ms/1000,tz).isoformat(timespec='seconds')
cut = local(d['as_of_ms'])
alerts = [r for r in d['alerts'] if r['id']==2292]
signals = [r for r in d['signals'] if r['id']==3732]
rup = [r for r in d['rupturas'] if r['id'] in (39,67)]
assert len(alerts)==1 and alerts[0]['telegram']=='enviado'
assert len(signals)==1 and signals[0]['status']=='TP'
assert len(rup)==2 and all(r['telegram']=='enviado' and r['telegram_message_id'] for r in rup)

items=[{
    'id':'avisos-coti','title':'COTIUSDT tiene avisos registrados como enviados el 17 de septiembre',
    'queries':[
        {'id':'alerta-principal','source':{'label':'sacbinance.db · alertas emitidas',
            'tables':[{'label':'alertas_emitidas'}], 'sql':d['queries']['alerts'],
            'filters':['Parámetro symbol: COTIUSDT'],
            'caveats':['Enviado refleja la confirmación registrada por el servidor; no acredita lectura ni notificación en el teléfono.'],
            'evidenceFlow':[{'kind':'validation','title':'Cruce entre alerta y señal','detail':'La alerta 2292 enlaza a la señal 3732 con entrada 0.01897 y estado de envío enviado.'}]},
         'capturedAt':cut,'reportingPeriod':'17 de septiembre de 2026; horas UTC−6',
         'columns':[{'field':'fecha','label':'Fecha y hora (Guatemala)'},'symbol','entry','take_profit','stop_loss','telegram'],
         'rows':[{'fecha':local(r['ts_ms']),**{k:r[k] for k in ['symbol','entry','take_profit','stop_loss','telegram']}} for r in alerts],
         'preview':{'kind':'partial','note':'Se muestra la alerta 2292 del 17-sep; la consulta original devolvió 19 avisos históricos de COTIUSDT.','totalRows':19}},
        {'id':'avisos-ruptura','source':{'label':'sacbinance.db · rupturas',
            'tables':[{'label':'rupturas'}],'sql':d['queries']['rupturas'],
            'filters':['Parámetro symbol: COTIUSDT'],
            'caveats':['telegram_detail puede reflejar el seguimiento más reciente; ambos eventos conservan el identificador del mensaje inicial.'],
            'evidenceFlow':[{'kind':'validation','title':'Comprobante de mensaje inicial','detail':'Los eventos 39 y 67 conservan telegram_message_id y estado enviado. No se publican los identificadores de Telegram.'}]},
         'capturedAt':cut,'reportingPeriod':'17 de septiembre de 2026; horas UTC−6',
         'columns':[{'field':'fecha','label':'Fecha y hora (Guatemala)'},'direction','price_open','reason','telegram'],
         'rows':[{'fecha':local(r['ts_open']),**{k:r[k] for k in ['direction','price_open','reason','telegram']}} for r in rup]},
    ]
},{
    'id':'resultado-plan','title':'El seguimiento de la señal de las 05:56 registró TP a las 08:23',
    'queries':[{'id':'signal-3732','source':{'label':'sacbinance.db · señales',
        'tables':[{'label':'signals'}],'sql':d['queries']['signals'],
        'filters':['Parámetro symbol: COTIUSDT','Parámetro ts_open mínimo: 1789516800000 (16-sep-2026 00:00 UTC)'],
        'caveats':['Es el resultado registrado por el seguimiento del plan, no una operación ejecutada en Binance.']},
        'capturedAt':cut,'reportingPeriod':'17 de septiembre de 2026; horas UTC−6',
        'columns':['id','apertura','cierre','status','entry','take_profit','stop_loss',{'field':'result_pct','label':'Resultado bruto registrado (%)'}],
        'rows':[{'apertura':local(r['ts_open']),'cierre':local(r['ts_close']),**{k:r[k] for k in ['id','status','entry','take_profit','stop_loss','result_pct']}} for r in signals],
        'preview':{'kind':'partial','note':'Se muestra la señal 3732, enlazada a la alerta enviada; la consulta devolvió dos señales desde el 16-sep UTC.','totalRows':2}}]
},{
    'id':'marcos-sin-envio','title':'La lectura por marcos y las notificaciones usan circuitos distintos',
    'queries':[{'id':'lectura-codigo','source':{'label':'Código del analizador y del motor',
        'files':[{'label':'pair_report.py'},{'label':'tf_rupture_tracker.py'},{'label':'engine.py'},{'label':'telegram.py'}],
        'metricDefinitions':[{'label':'Circuitos de aviso','definition':'La consulta por marcos devuelve una lectura de estructura. TFRuptureShadow registra sus eventos en sombra; las señales y las rupturas cortas tienen sus propias rutas de Telegram.'}],
        'evidenceFlow':[{'kind':'validation','title':'Ruta de publicación','detail':'construir_informe calcula y devuelve datos sin enviar mensajes. TFRuptureShadow.evaluar persiste el evento. El envío de rupturas cortas se realiza mediante _avisar_ruptura y el de señales mediante _quiza_avisar.'}]},
        'reportingPeriod':'Código inspeccionado el 17 de septiembre de 2026'}]
}]
(P/'sources.json').write_text(json.dumps({'schemaVersion':1,'items':items},ensure_ascii=False,indent=2),encoding='utf-8')

report=f'''# COTIUSDT: revisión de avisos del 17 de septiembre

Corte: {cut}. Todas las horas siguientes son de Guatemala (UTC−6). Se asume COTIUSDT por el par de la conversación anterior; las capturas nuevas no muestran su símbolo.

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
'''
(P/'REVISION_COTI.md').write_text(report,encoding='utf-8')
print('Evidence projected; receipt input and case report written.')
