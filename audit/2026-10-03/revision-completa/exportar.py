"""Exporta, en solo lectura, las velas de 1 minuto y los avisos con sus rasgos.

Se ejecuta en el servidor:  ssh sac 'nice -n 19 ionice -c3 python3 -' < exportar.py > fuente.pkl.gz
Salida: pickle gzip con {meta, velas: {symbol: (t_min int32, o,h,l,c,v float32)}, avisos: [...]}
"""
import gzip, hashlib, io, pickle, sqlite3, sys, time
import numpy as np

DB = "file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro"
t0 = time.time()
con = sqlite3.connect(DB, uri=True)
con.execute("PRAGMA query_only=ON")
def solo_lectura(op, *a):
    return sqlite3.SQLITE_OK if op in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_PRAGMA) else sqlite3.SQLITE_DENY
con.set_authorizer(solo_lectura)

simbolos = [r[0] for r in con.execute("select distinct symbol from klines where tf='1m'")]
velas = {}
n = 0
for s in simbolos:
    filas = con.execute("select open_time,o,h,l,c,v from klines where tf='1m' and symbol=? order by open_time", (s,)).fetchall()
    if not filas:
        continue
    a = np.array(filas, dtype=np.float64)
    velas[s] = ((a[:, 0] // 60000).astype(np.int32),) + tuple(a[:, i].astype(np.float32) for i in range(1, 6))
    n += len(filas)

cols_o = [r[1] for r in con.execute("pragma table_info(outcomes)")]
avisos_cols = ["id", "ts_ms", "symbol", "signal_id", "entry", "take_profit", "stop_loss", "tp_pct", "sl_pct",
               "tier", "score", "display_state", "senal_n", "telegram", "config_hash", "episode_id"]
avisos = [dict(zip(avisos_cols, r)) for r in con.execute(
    "select " + ",".join(avisos_cols) + " from alertas_emitidas order by id")]
oc = ["signal_id", "macro", "btc_regime", "macro_gate_mult", "z_rise", "z_drop", "velocity", "vol_ratio",
      "buy_ratio_30s", "flow_trades_30s", "flow_disponible", "rsi5", "rsi14", "rsi14_15m", "pos_en_rango",
      "rango_1h_pct", "consumido_pct", "fase_impulso", "fuerza_impulso", "taxonomia", "sigma_pct", "atr_pct",
      "score_trend", "es_fakeout", "dist_resistencia_pct", "dist_soporte_pct", "bb_position_15m", "sombra"]
oc = [c for c in oc if c in cols_o]
outc = {r[0]: dict(zip(oc, r)) for r in con.execute("select " + ",".join(oc) + " from outcomes")}
for a in avisos:
    o = outc.get(a["signal_id"])
    if o:
        a.update({("o_" + k): v for k, v in o.items() if k != "signal_id"})

meta = {"creado_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "simbolos": len(velas), "velas": n,
        "avisos": len(avisos), "outcomes": len(outc), "segundos": round(time.time() - t0, 1)}
buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as g:
    pickle.dump({"meta": meta, "velas": velas, "avisos": avisos}, g, protocol=4)
sys.stdout.buffer.write(buf.getvalue())
print(meta, file=sys.stderr)
