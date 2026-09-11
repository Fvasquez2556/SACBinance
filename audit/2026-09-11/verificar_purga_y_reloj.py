# -*- coding: utf-8 -*-
"""
Comprueba los dos arreglos del 11-sep: la purga de velas y el reloj de señales.

Lo que hay que demostrar del reloj no es solo que cierre: es que el precio de
salida sea HONESTO. Calificar una señal de hace seis dias contra el precio de
hoy es lo que inflaba el win rate, y es el motivo de que la edad se mire antes
que TP/SL. Si no se conoce el precio al vencimiento, la señal tiene que quedar
STALE y sin resultado, no con un numero inventado.

No toca produccion ni sale a la red: todo sobre bases temporales.
"""
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['TELEGRAM_ENABLED'] = 'false'

res = []


def check(nombre, esperado, real):
    ok = esperado == real
    res.append(ok)
    print(f"{'PASA ' if ok else 'FALLA'}  {nombre}")
    if not ok:
        print(f"         esperado {esperado!r}, real {real!r}")


MIN = 60_000
HORA = 3_600_000


def base_temporal():
    d = pathlib.Path(tempfile.mkdtemp()) / "t.db"
    os.environ['DB_PATH'] = str(d)
    from src.config.settings import get_settings
    get_settings.cache_clear()
    from src.persistence.db import Database
    return Database()


# =============================================================================
print("=" * 74)
print("1 · PURGA: la retencion sale de la configuracion, no del codigo")
print("=" * 74)
from src.config.settings import Settings

s = Settings(_env_file=None)
check("retencion de 1m/5m/15m por defecto (era 3 clavados)", 30,
      s.klines_1m_retention_days)
check("retencion de 1h/4h/1d", 400, s.klines_htf_retention_days)

db = base_temporal()
ahora = int(time.time() * 1000)
from src.state.symbol_state import Candle

# velas de hace 40, 20 y 1 dias
for dias in (40, 20, 1):
    t = ahora - dias * 86_400_000
    db.save_klines("XUSDT", "1m", [Candle(t=t, o=1, h=1, l=1, c=1, v=1)])
    db.save_klines("XUSDT", "1h", [Candle(t=t, o=1, h=1, l=1, c=1, v=1)])
db.flush()
antes_1m = len(db.get_klines("XUSDT", "1m", 100))
db.prune_klines()
quedan_1m = len(db.get_klines("XUSDT", "1m", 100))
quedan_1h = len(db.get_klines("XUSDT", "1h", 100))
check("de 3 velas de 1m (40d, 20d, 1d) sobreviven las 2 dentro de 30 dias",
      2, quedan_1m)
check("las de 1h sobreviven las 3 (retencion 400 dias)", 3, quedan_1h)
print(f"   antes de purgar habia {antes_1m} velas de 1m")

# Con la retencion vieja de 3 dias, la de 20 dias tambien habria muerto.
os.environ['KLINES_1M_RETENTION_DAYS'] = '3'
from src.config.settings import get_settings
get_settings.cache_clear()
db.prune_klines()
check("bajando la retencion a 3 dias, solo sobrevive la de ayer", 1,
      len(db.get_klines("XUSDT", "1m", 100)))
print("   -> eso es lo que borraba la evidencia antes de tiempo")
del os.environ['KLINES_1M_RETENTION_DAYS']
get_settings.cache_clear()
db.close()

# =============================================================================
print("\n" + "=" * 74)
print("2 · RELOJ DE SEÑALES: cierra sin que lleguen velas")
print("=" * 74)
from src.analysis.signal_tracker import cerrar_vencidas

db = base_temporal()
s = get_settings()
expiry = s.signal_expiry_hours * HORA
ahora = int(time.time() * 1000)


def senal(sym, edad_ms, entry=100.0):
    sid = db.abrir_signal({
        "symbol": sym, "ts_open": ahora - edad_ms, "display_state": "SUBIENDO",
        "tier": "MODERADA", "score": 75, "entry": entry,
        "take_profit": entry * 1.032, "stop_loss": entry * 0.98,
        "risk_reward": 1.6, "macro": "NEUTRAL",
    }) if hasattr(db, "abrir_signal") else None
    return sid


# La API real de apertura:
from src.analysis import signal_tracker as st_mod

def abrir(sym, edad_ms, entry=100.0):
    snap = {"display_state": "SUBIENDO", "tier": "MODERADA", "score": 75,
            "macro_global": "NEUTRAL",
            "trade_levels": {"valid": True, "entry": entry,
                             "take_profit": entry * 1.032,
                             "stop_loss": entry * 0.98, "risk_reward": 1.6}}
    sid = st_mod.abrir_senal(sym, snap, db)
    if sid:
        db._conn.execute("UPDATE signals SET ts_open=? WHERE id=?",
                         (ahora - edad_ms, sid))
        db._conn.commit()
    return sid


# a) caducada, CON vela en el vencimiento -> EXPIRED con ese precio
sid_a = abrir("AUSDT", int(expiry * 1.5))
vence_a = (ahora - int(expiry * 1.5)) + expiry
db.save_klines("AUSDT", "1m", [Candle(t=vence_a - MIN, o=103, h=104, l=102,
                                      c=103.0, v=1)])
# b) caducada, SIN vela cerca del vencimiento -> STALE sin resultado
sid_b = abrir("BUSDT", int(expiry * 1.5))
db.save_klines("BUSDT", "1m", [Candle(t=ahora - 10 * MIN, o=150, h=150, l=150,
                                      c=150.0, v=1)])
# c) todavia viva -> no se toca
sid_c = abrir("CUSDT", int(expiry * 0.5))
# d) tan vieja que el sistema no la siguio -> STALE
sid_d = abrir("DUSDT", int(expiry * 3))
db.save_klines("DUSDT", "1m", [Candle(t=(ahora - int(expiry * 3)) + expiry,
                                      o=90, h=90, l=90, c=90.0, v=1)])
db.flush()

r = cerrar_vencidas(db, ahora)
print(f"   resultado del barrido: {r}")

def fila(sid):
    c = db._conn.execute(
        "SELECT status, result_pct FROM signals WHERE id=?", (sid,)).fetchone()
    return (c[0], c[1])

check("a) con vela en el vencimiento -> EXPIRED", "EXPIRED", fila(sid_a)[0])
check("   y su resultado sale del precio de ENTONCES (+3.0%)", 3.0, fila(sid_a)[1])
check("b) sin vela cerca del vencimiento -> STALE", "STALE", fila(sid_b)[0])
check("   y SIN resultado inventado", None, fila(sid_b)[1])
print("   (el precio de hoy era 150, o sea +50%: no se usa)")
check("c) una señal viva no se toca", "OPEN", fila(sid_c)[0])
check("d) demasiado vieja para haberla seguido -> STALE", "STALE", fila(sid_d)[0])
check("   tampoco inventa resultado", None, fila(sid_d)[1])

# idempotencia
r2 = cerrar_vencidas(db, ahora)
check("repetir el barrido no cierra nada mas", {"expired": 0, "stale": 0}, r2)

# el margen es configurable y se respeta
sid_e = abrir("EUSDT", int(expiry * 1.5))
vence_e = (ahora - int(expiry * 1.5)) + expiry
db.save_klines("EUSDT", "1m", [Candle(t=vence_e - 40 * MIN, o=99, h=99, l=99,
                                      c=99.0, v=1)])
db.flush()
cerrar_vencidas(db, ahora, margen_min=15)
check("una vela a 40 min del vencimiento no vale con margen de 15",
      "STALE", fila(sid_e)[0])

sid_f = abrir("FUSDT", int(expiry * 1.5))
vence_f = (ahora - int(expiry * 1.5)) + expiry
db.save_klines("FUSDT", "1m", [Candle(t=vence_f - 40 * MIN, o=99, h=99, l=99,
                                      c=99.0, v=1)])
db.flush()
cerrar_vencidas(db, ahora, margen_min=60)
check("...y si vale con margen de 60", "EXPIRED", fila(sid_f)[0])

db.close()
print(f"\n{sum(res)} pasan, {len(res)-sum(res)} fallan")
sys.exit(0 if all(res) else 1)
