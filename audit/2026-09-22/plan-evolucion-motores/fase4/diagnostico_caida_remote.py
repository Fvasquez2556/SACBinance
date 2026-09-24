"""Por que el motor de caida no abrio en ninguna de las 8 caidas reales."""
import sqlite3
import sys

sys.path.insert(0, '/home/flox/sacbinance/backend')

from src.analysis.retroceso import detectar_retroceso              # noqa: E402
from src.state.symbol_state import Candle                          # noqa: E402

db = sqlite3.connect('file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro', uri=True)
db.execute('PRAGMA query_only=ON')
ahora = db.execute("SELECT MAX(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
desde = ahora - 72 * 3600_000

SYM = 'ONEUSDT'
filas = db.execute("SELECT open_time,o,h,l,c,v FROM klines WHERE symbol=? AND tf='1m' "
                   "AND open_time>=? ORDER BY open_time", (SYM, desde)).fetchall()
velas = [Candle(t=f[0], o=f[1], h=f[2], l=f[3], c=f[4], v=f[5]) for f in filas]
cierres = [v.c for v in velas]

peor, i0 = 0.0, None
for i in range(60, len(cierres)):
    pico = max(cierres[i - 60:i])
    caida = (cierres[i] / pico - 1.0) * 100
    if caida < peor:
        peor, i0 = caida, i
print(f'{SYM}: peor caida de 60 min = {peor:.2f} % en el minuto {i0}\n')
print(f'{"min":>5} {"precio":>12} {"r5%":>7} {"dd30%":>8} {"retro?":>7} {"caida_pct":>10} {"rebote":>8}')
for i in range(i0 - 20, min(len(velas), i0 + 120), 5):
    ventana = velas[max(0, i - 400):i + 1]
    r = detectar_retroceso(ventana)
    c = [v.c for v in velas[max(0, i - 5):i + 1]]
    r5 = (c[-1] / c[0] - 1) * 100 if len(c) > 1 else 0.0
    pico30 = max(v.h for v in velas[max(0, i - 30):i + 1])
    dd = (velas[i].c / pico30 - 1) * 100
    print(f'{i:>5} {velas[i].c:>12.8f} {r5:>7.2f} {dd:>8.2f} '
          f'{str(r.detectado):>7} {str(r.caida_pct):>10} {str(r.rebote_pct):>8}')

print('\nDiagnostico: ¿coinciden alguna vez "esta cayendo" y "caida_pct >= 2"?')
coinciden = solo_cayendo = solo_caida_pct = 0
for i in range(max(400, i0 - 200), min(len(velas), i0 + 400)):
    ventana = velas[max(0, i - 400):i + 1]
    r = detectar_retroceso(ventana)
    c = [v.c for v in velas[max(0, i - 5):i + 1]]
    cayendo = len(c) > 1 and (c[-1] / c[0] - 1) * 100 <= -0.8
    tiene = r.caida_pct is not None and r.caida_pct >= 2.0
    if cayendo and tiene:
        coinciden += 1
    elif cayendo:
        solo_cayendo += 1
    elif tiene:
        solo_caida_pct += 1
print(f'  minutos con las dos a la vez (lo que el motor exige): {coinciden}')
print(f'  minutos solo "cayendo"  : {solo_cayendo}')
print(f'  minutos solo "caida_pct": {solo_caida_pct}')
db.close()
