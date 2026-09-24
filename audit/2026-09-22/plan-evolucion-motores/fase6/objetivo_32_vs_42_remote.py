"""
¿+3,2 % neto o +4,2 % neto? La pregunta con la vuelta que faltaba.

Lo medido hasta ahora comparaba ESPERANZA POR OPERACION, y con esa vara las
dos son indistinguibles: +0,33 % contra +0,51 %, con el intervalo del 95 % de
la actual en [-0,04 %, +0,99 %].

Pero eso responde a "¿cuanto deja cada señal?", y con **una sola posicion** esa
no es la pregunta del operador. La suya es "¿cuanto deja mi capital al mes?", y
ahi entra una variable que nadie habia medido: **cuanto tiempo ocupa cada
objetivo la unica posicion que hay**.

Un objetivo mas lejano tarda mas en cobrarse. Mientras tanto, la posicion esta
ocupada y todas las demas oportunidades pasan de largo. Con 10 USDT y una
moneda a la vez, la vara correcta no es esperanza por operacion: es **esperanza
por hora de posicion ocupada**.

Esto se mide sobre los recorridos YA guardados (anteriores al congelado de la
fase 5), asi que es retrospectivo: es de donde sale la pregunta, no el
veredicto. El veredicto lo da la prueba prospectiva, y no antes del 17-oct.

Solo lectura.
"""
import json
import sqlite3

DB = 'file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
COSTE = 0.5
HORIZONTE_H = 12

db = sqlite3.connect(DB, uri=True)
db.execute('PRAGMA query_only=ON')

# Los recorridos completos guardan los hitos BRUTOS con su minuto de llegada,
# y el desenlace del plan. Con eso se reconstruye cualquier objetivo fijo sin
# volver a recorrer velas.
filas = [dict(zip(('plan_id', 'symbol', 'hitos', 'ms_stop', 'ms_objetivo',
                   'desenlace', 'cierre_pct', 'entrada', 'stop'), r))
         for r in db.execute(
    """SELECT r.plan_id, r.symbol, r.hitos, r.ms_stop, r.ms_objetivo,
              r.desenlace, r.cierre_pct, r.entrada, r.stop
       FROM plan_recorrido r
       WHERE r.completa = 1 AND r.hitos IS NOT NULL AND r.hitos != '{}'""")]

# La poblacion que el operador recibe de verdad: avisada por Telegram.
avisados = {r[0] for r in db.execute(
    """SELECT p.plan_id FROM planes p
       JOIN alertas_emitidas a ON a.id = p.legacy_alerta_id
       WHERE a.telegram = 'enviado'""")}
import sys
SOLO_TG = '--telegram' in sys.argv
if SOLO_TG:
    filas = [f for f in filas if f['plan_id'] in avisados]
print(f"recorridos completos: {len(filas)}" + (' (solo avisados a Telegram)' if SOLO_TG else ' (universo entero)'))

OBJETIVOS = {'+2,7 % neto': 3.2, '+3,2 % neto': 3.7, '+4,2 % neto': 4.7}


def desenlace_de(f, bruto):
    """
    ¿Llego al objetivo antes que al stop, y en cuanto tiempo?

    Devuelve (resultado_neto_pct, minutos_ocupados). Si no resuelve, ocupa la
    ventana entera: es lo que de verdad le pasa a la unica posicion.
    """
    hitos = json.loads(f['hitos'] or '{}')
    ms_obj = hitos.get(f'{bruto:g}')
    ms_stop = f['ms_stop']
    horizonte_ms = HORIZONTE_H * 3600_000
    if ms_obj is not None and (ms_stop is None or ms_obj < ms_stop):
        return bruto - COSTE, ms_obj / 60000.0
    if ms_stop is not None:
        perdida = (f['stop'] / f['entrada'] - 1) * 100 - COSTE
        return perdida, ms_stop / 60000.0
    return (f['cierre_pct'] or 0.0) - COSTE, horizonte_ms / 60000.0


print()
print(f'{"objetivo":<14} {"acierta":>8} {"esperanza":>11} {"min. medianos":>14} '
      f'{"por hora ocupada":>18}  {"op./dia":>8}')
print('-' * 80)
resumen = {}
for nombre, bruto in OBJETIVOS.items():
    res = [desenlace_de(f, bruto) for f in filas]
    n = len(res)
    aciertos = sum(1 for r, _ in res if r > 0)
    esperanza = sum(r for r, _ in res) / n
    minutos = sorted(m for _, m in res)
    mediana = minutos[len(minutos) // 2]
    horas_medias = sum(m for _, m in res) / n / 60.0
    por_hora = esperanza / horas_medias if horas_medias else 0
    # Con UNA posicion: cuantas operaciones caben en un dia.
    op_dia = 24.0 / horas_medias if horas_medias else 0
    resumen[nombre] = (esperanza, horas_medias, por_hora, op_dia)
    print(f'{nombre:<14} {100*aciertos/n:>7.1f}% {esperanza:>+10.3f}% '
          f'{mediana:>13.0f} {por_hora:>+17.4f}% {op_dia:>8.2f}')

print()
print('Lo que le pasa a 10 USDT en 30 dias, con una posicion y reinvirtiendo:')
print(f'{"objetivo":<14} {"op./dia":>8} {"%/dia":>9} {"30 dias":>10} {"60 dias":>10}')
print('-' * 55)
for nombre, (esp, horas, por_hora, op_dia) in resumen.items():
    diario = (1 + esp / 100) ** op_dia
    print(f'{nombre:<14} {op_dia:>8.2f} {(diario-1)*100:>8.2f}% '
          f'{10*diario**30:>9.2f} {10*diario**60:>9.2f}')

print()
print('AVISO: retrospectivo sobre datos anteriores al congelado de la fase 5.')
print('Es de donde sale la pregunta, no el veredicto. El veredicto lo da la')
print('prueba prospectiva, y su puerta del dinero no se puede cerrar antes del')
print('17-oct. Ademas son 502 recorridos de un solo regimen de cuatro dias.')
db.close()
