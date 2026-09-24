"""
Replay del motor de caida sobre caidas REALES de produccion.

Al desplegar no habia una sola moneda cayendo (0 en DROPPING, 0 en taxonomia
CAIDA), asi que el motor se quedaba —correctamente— en SIN_TESIS. Eso no
demuestra que funcione: demuestra que no habia trabajo.

Esto busca las caidas mas fuertes de los ultimos dias en las velas guardadas,
reconstruye la observacion minuto a minuto con los mismos detectores que usa
el engine, y pasa la secuencia por `avanzar_caida`. Solo lectura.
"""
import sqlite3
import sys

sys.path.insert(0, '/home/flox/sacbinance/backend')

from src.analysis.base_rebote import detectar_base_rebote          # noqa: E402
from src.analysis.retroceso import detectar_retroceso              # noqa: E402
from src.motores.caida import EstadoCaida, avanzar_caida           # noqa: E402
from src.motores.contrato import Observacion                       # noqa: E402
from src.state.symbol_state import Candle                          # noqa: E402

DB = 'file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
db = sqlite3.connect(DB, uri=True)
db.execute('PRAGMA query_only=ON')

# --- Buscar las caidas mas fuertes de las ultimas 72 h -----------------------
ahora = db.execute("SELECT MAX(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
desde = ahora - 72 * 3600_000

candidatos = []
for (sym,) in db.execute(
        "SELECT DISTINCT symbol FROM klines WHERE tf='1m' AND open_time >= ?", (desde,)):
    filas = db.execute(
        "SELECT open_time,o,h,l,c,v FROM klines WHERE symbol=? AND tf='1m' "
        "AND open_time>=? ORDER BY open_time", (sym, desde)).fetchall()
    if len(filas) < 600:
        continue
    # La peor caida de 60 minutos de la ventana
    peor, peor_i = 0.0, None
    cierres = [f[4] for f in filas]
    for i in range(60, len(cierres)):
        pico = max(cierres[i - 60:i])
        if pico > 0:
            caida = (cierres[i] / pico - 1.0) * 100
            if caida < peor:
                peor, peor_i = caida, i
    if peor_i is not None and peor <= -4.0:
        candidatos.append((peor, sym, peor_i, filas))

candidatos.sort()
print(f'{len(candidatos)} pares con una caida de 60 min de al menos -4 % en 72 h\n')

TENDENCIAS = {'5m': 'BAJISTA', '15m': 'BAJISTA', '1h': 'NEUTRAL', '4h': 'NEUTRAL'}


def fsm_aproximado(velas, i):
    """
    Estado 1m aproximado desde las velas. No es la FSM del engine (que lleva
    estadistica adaptativa), pero basta para saber si el motor recorre sus
    fases: lo que se prueba aqui es la maquina de estados, no el detector.
    """
    c = [v.c for v in velas[max(0, i - 10):i + 1]]
    if len(c) < 5:
        return 'NEUTRAL', 'NEUTRAL'
    r5 = (c[-1] / c[-5] - 1) * 100
    r10 = (c[-1] / c[0] - 1) * 100
    if r5 <= -0.8:
        return 'DROPPING', 'CAYENDO'
    if r5 >= 0.8:
        return 'RISING', 'SUBIENDO'
    if r10 <= -1.0:
        return 'BOTTOMING', 'TOCÓ_FONDO'
    return 'VALLEY', 'CONSOLIDANDO'


revisados = 0
for peor, sym, i0, filas in candidatos[:8]:
    velas = [Candle(t=f[0], o=f[1], h=f[2], l=f[3], c=f[4], v=f[5]) for f in filas]
    inicio = max(120, i0 - 90)
    fin = min(len(velas), i0 + 420)
    est = EstadoCaida(symbol=sym)
    historia = []
    candidatos_compra = 0
    for i in range(inicio, fin):
        ventana = velas[max(0, i - 400):i + 1]
        fsm, display = fsm_aproximado(velas, i)
        retro = detectar_retroceso(ventana).to_dict()
        base = detectar_base_rebote(ventana).to_dict()
        obs = Observacion(
            symbol=sym, ts_ms=velas[i].t, precio=velas[i].c, velas_1m=len(ventana),
            fsm_state=fsm, display_state=display, tendencias=dict(TENDENCIAS),
            taxonomia={'estado': 'CAIDA' if fsm == 'DROPPING' else 'NEUTRAL'},
            retroceso=retro, base_rebote=base,
            plan={'valid': True, 'entry': velas[i].c,
                  'take_profit': velas[i].c * 1.05, 'stop_loss': velas[i].c * 0.975},
            ancla={'direccion': 'RUPTURA_BAJISTA', 'tendencia': 'BAJISTA'},
            ancla_edad_min=5.0)
        est, lec, motivo = avanzar_caida(est, obs)
        if motivo:
            historia.append((velas[i].t, motivo, est.estado, round(velas[i].c, 8)))
        if lec.veredicto == 'CANDIDATO':
            candidatos_compra += 1
    revisados += 1
    print(f'{sym}  caida de 60 min: {peor:.2f} %')
    if not historia:
        print('   el motor no abrio nada')
    for t, motivo, estado, precio in historia[:12]:
        print(f'   {motivo:<12} -> {estado:<18} precio {precio}')
    print(f'   minutos marcados como CANDIDATO: {candidatos_compra}\n')

db.close()
print(f'{revisados} caidas reales recorridas')
