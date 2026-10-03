

# --- historico.py: se envía por stdin al servidor DESPUÉS de core.py -------------------------
# Solo lectura (mode=ro + query_only + autorizador SELECT). Escribe JSON Lines comprimido en
# stdout: una cabecera, una línea por señal y un cierre. No escribe nada en el servidor.
import gzip as _gzip
import json as _json
import sqlite3 as _sqlite3
import sys as _sys
import time as _time

_DB = "/home/flox/sacbinance/backend/data/sacbinance.db"
_INICIO = 1789084800000          # 2026-09-11 00:00 UTC: velas de 1 min continuas desde aquí

_src = _sqlite3.connect("file:" + _DB + "?mode=ro", uri=True, timeout=5)
_src.execute("PRAGMA query_only=ON")
_permitido = {_sqlite3.SQLITE_SELECT, _sqlite3.SQLITE_READ, _sqlite3.SQLITE_FUNCTION}
_src.set_authorizer(lambda a, *_: _sqlite3.SQLITE_OK if a in _permitido else _sqlite3.SQLITE_DENY)

_started = int(_time.time() * 1000)
_cutoff = (_started // MIN) * MIN - 2 * MIN       # última vela de 1 min seguro cerrada
_salida = _gzip.GzipFile(fileobj=_sys.stdout.buffer, mode="wb", compresslevel=6)


def _linea(obj):
    _salida.write((_json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n").encode())


_alertas = _src.execute(
    "SELECT id, ts_ms, symbol, entry, stop_loss, tier, score, display_state, senal_n, tp_pct, sl_pct, "
    "telegram, episode_id FROM alertas_emitidas WHERE tier IN (?, ?) AND ts_ms >= ? AND ts_ms <= ? "
    "ORDER BY symbol, ts_ms", (NIVELES[0], NIVELES[1], _INICIO, _cutoff - (SPAN + 2) * MIN)).fetchall()
_linea({"tipo": "cabecera", "version": VERSION, "config_hash": CONFIG_HASH, "started_ms": _started,
        "cutoff_ms": _cutoff, "inicio_ms": _INICIO, "alertas": len(_alertas)})

_por_simbolo = {}
for _a in _alertas:
    _por_simbolo.setdefault(_a[2], []).append(_a)

_cuenta = {"evaluadas": 0, "huecos": 0, "sin_entrada_valida": 0, "control_con_huecos": 0}


def _ventana(T, idx, inicio):
    i0 = idx.get(inicio)
    if i0 is None or i0 + SPAN - 1 >= len(T) or T[i0 + SPAN - 1] != inicio + (SPAN - 1) * MIN:
        return None
    return i0


for _sym, _lista in _por_simbolo.items():
    _desde = _lista[0][1] - (CONTROL_MIN[1] + 2 * PREVIAS) * MIN
    _hasta = _lista[-1][1] + (SPAN + 2) * MIN
    _filas = _src.execute("SELECT open_time, o, h, l, c, v FROM klines WHERE symbol=? AND tf='1m' "
                          "AND open_time>=? AND open_time<=? ORDER BY open_time", (_sym, _desde, _hasta)).fetchall()
    T = [f[0] for f in _filas]
    O = [f[1] for f in _filas]
    H = [f[2] for f in _filas]
    L = [f[3] for f in _filas]
    C = [f[4] for f in _filas]
    V = [f[5] or 0.0 for f in _filas]
    _idx = {t: i for i, t in enumerate(T)}
    for (aid, ts, sym, R, stop, tier, score, estado, senal_n, tp_pct, sl_pct, tg, ep) in _lista:
        reg = {"tipo": "senal", "id": aid, "ts": ts, "symbol": sym, "tier": tier, "telegram": tg,
               "episode_id": ep, "R": R, "stop": stop,
               "alerta": {"score": score, "display_state": estado, "senal_n": senal_n,
                          "tp_pct": tp_pct, "sl_pct": sl_pct, "telegram": tg}}
        if not (isinstance(R, (int, float)) and R > 0):
            _cuenta["sin_entrada_valida"] += 1
            continue
        inicio = (ts + MIN - 1) // MIN * MIN
        i0 = _ventana(T, _idx, inicio)
        if i0 is None:
            _cuenta["huecos"] += 1
            reg["estado"] = "HUECOS"
            _linea(reg)
            continue
        reg["estado"] = "COMPLETO"
        reg["o0_pct"] = round((O[i0] / R - 1) * 100, 4)
        reg["feat"] = features(T, O, H, L, C, V, ts, _idx.get)
        s = slice(i0, i0 + SPAN)
        reg["eval"] = evaluar(O[s], H[s], L[s], C[s], R, stop)
        ci = inicio_control(aid, ts)
        j0 = _ventana(T, _idx, ci)
        if j0 is None or not O[j0] > 0:
            _cuenta["control_con_huecos"] += 1
            reg["ctrl"] = None
        else:
            Rc = O[j0]
            sc = slice(j0, j0 + SPAN)
            reg["ctrl"] = evaluar(O[sc], H[sc], L[sc], C[sc], Rc,
                                  Rc * stop / R if isinstance(stop, (int, float)) and stop > 0 else None)
            reg["ctrl_inicio"] = ci
        _cuenta["evaluadas"] += 1
        _linea(reg)

_linea({"tipo": "cierre", "cuenta": _cuenta, "finished_ms": int(_time.time() * 1000)})
_salida.close()
