"""Observador en sombra de moderadas-sombra-v1.

Lee la base del sistema con una conexión de solo lectura (mode=ro, query_only y un
autorizador que solo permite SELECT). Solo escribe en su propia base. No importa el
backend, no usa red, no envía Telegram y no toca señales, planes ni el tablero.

Prospectivo: registra las señales MODERADA y FUERTE emitidas después de instalarse,
unos 90 s después de cada una, y las vuelve a medir al cerrar cada ventana (1, 3, 6
y 12 h). El control al azar de la misma moneda se mide una vez: su ventana ya pasó.
"""
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import zlib

from . import core as K

MAX_INT = 9223372036854775807
FRESCA_MS = 90_000            # espera a que cierre la vela de la señal
ESPERA_RASGOS_MS = 600_000    # si faltan las velas previas, reintenta hasta 10 min
PROSPECTIVO_MS = 300_000      # registrada a más de 5 min de la señal = captura tardía
HUECO_REINTENTO_MS = 3_600_000
HUECO_LIMITE_MS = 6 * 3_600_000


def ahora_ms():
    return int(time.time() * 1000)


def comprimir(obj):
    return zlib.compress(json.dumps(obj, separators=(",", ":"), allow_nan=False).encode(), 6)


def descomprimir(blob):
    return json.loads(zlib.decompress(blob)) if blob is not None else None


class Fuente:
    def __init__(self, ruta):
        ruta = Path(ruta).resolve(strict=True)
        self.db = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True, timeout=2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA query_only=ON")
        self.db.execute("PRAGMA busy_timeout=2000")
        permitido = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        self.db.set_authorizer(lambda a, *_: sqlite3.SQLITE_OK if a in permitido else sqlite3.SQLITE_DENY)

    def close(self):
        self.db.close()

    def max_id(self):
        return self.db.execute("SELECT coalesce(max(id),0) FROM alertas_emitidas").fetchone()[0]

    def senales_tras(self, despues, limite=500):
        return [dict(r) for r in self.db.execute(
            "SELECT id,ts_ms,symbol,entry,stop_loss,tier,score,display_state,senal_n,tp_pct,sl_pct,telegram,"
            "episode_id FROM alertas_emitidas WHERE id>? ORDER BY id LIMIT ?", (despues, limite)).fetchall()]

    def velas(self, symbol, desde, hasta_excl):
        return [tuple(r) for r in self.db.execute(
            "SELECT open_time,o,h,l,c,v FROM klines WHERE symbol=? AND tf='1m' AND open_time>=? "
            "AND open_time<? ORDER BY open_time", (symbol, desde, hasta_excl)).fetchall()]


# v2 escribe en su propia base: la de v1 se conserva y no se mezcla.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS senales(
 alerta_id INTEGER PRIMARY KEY, ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL, tier TEXT NOT NULL,
 telegram TEXT, episode_id INTEGER, R REAL NOT NULL, stop REAL, start_ms INTEGER NOT NULL,
 first_seen_ms INTEGER NOT NULL, origen TEXT NOT NULL, alerta_json TEXT NOT NULL, feat_json TEXT,
 estado TEXT NOT NULL, next_check_ms INTEGER NOT NULL, velas INTEGER NOT NULL DEFAULT 0,
 o0_pct REAL, evaluado_ms INTEGER, eval_z BLOB, ctrl_z BLOB, ctrl_inicio_ms INTEGER, last_error TEXT);
CREATE INDEX IF NOT EXISTS senales_pendientes ON senales(next_check_ms);
CREATE TABLE IF NOT EXISTS ciclos(
 id INTEGER PRIMARY KEY, started_ms INTEGER NOT NULL, finished_ms INTEGER, vistas INTEGER NOT NULL DEFAULT 0,
 registradas INTEGER NOT NULL DEFAULT 0, evaluadas INTEGER NOT NULL DEFAULT 0,
 errores INTEGER NOT NULL DEFAULT 0, error TEXT);
"""


def _contiguas(filas, inicio):
    n = 0
    while n < len(filas) and filas[n][0] == inicio + n * K.MIN:
        n += 1
    return filas[:n]


def _siguiente_hito(inicio, velas):
    """La próxima ventana que aún no está completa, más 2 minutos de margen."""
    for W in K.VENTANAS:
        if velas < W:
            return inicio + (W + 2) * K.MIN
    return MAX_INT


class Almacen:
    def __init__(self, ruta, stamp):
        self.ruta = Path(ruta).resolve()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.ruta, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(ESQUEMA)
        config = json.dumps(K.CONFIG, sort_keys=True)
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('instalacion_ms',?)", (str(stamp),))
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('config',?)", (config,))
        if self.get("config") != config:
            self.db.close()
            raise ValueError("Reglas distintas: usa una base nueva para otra versión")
        self.db.commit()

    def close(self):
        self.db.close()

    def get(self, key, default=None):
        r = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, str(value)))

    def descubrir(self, fuente, stamp):
        if self.get("cola") is None:
            # Solo señales posteriores a la instalación: nada retrospectivo en esta base.
            self.put("cola", fuente.max_id())
            self.db.commit()
            return 0, 0
        cola, vistas, registradas = int(self.get("cola")), 0, 0
        for a in fuente.senales_tras(cola):
            if a["ts_ms"] > stamp - FRESCA_MS:
                break
            R = a["entry"]
            if a["tier"] in K.NIVELES and isinstance(R, (int, float)) and math.isfinite(R) and R > 0:
                ultima = (a["ts_ms"] - K.MIN) // K.MIN * K.MIN
                filas = fuente.velas(a["symbol"], ultima - (K.PREVIAS - 1) * K.MIN, ultima + K.MIN)
                T = [f[0] for f in filas]
                idx = {t: i for i, t in enumerate(T)}
                O, H, L, C, V = ([f[k] for f in filas] for k in range(1, 6))
                V = [v or 0.0 for v in V]
                feat = K.features(T, O, H, L, C, V, a["ts_ms"], idx.get) if filas else None
                if feat is None and stamp - a["ts_ms"] < ESPERA_RASGOS_MS:
                    break  # las velas previas aún pueden llegar; se reintenta en el próximo ciclo
                inicio = (a["ts_ms"] + K.MIN - 1) // K.MIN * K.MIN
                origen = "PROSPECTIVO" if stamp - a["ts_ms"] <= PROSPECTIVO_MS else "CAPTURA_TARDIA"
                alerta = {k: a[k] for k in ("score", "display_state", "senal_n", "tp_pct", "sl_pct", "telegram")}
                self.db.execute(
                    "INSERT OR IGNORE INTO senales(alerta_id,ts_ms,symbol,tier,telegram,episode_id,R,stop,start_ms,"
                    "first_seen_ms,origen,alerta_json,feat_json,estado,next_check_ms) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (a["id"], a["ts_ms"], a["symbol"], a["tier"], a["telegram"], a["episode_id"], R,
                     a["stop_loss"], inicio, stamp, origen, json.dumps(alerta), json.dumps(feat) if feat else None,
                     "ABIERTO", inicio + (K.VENTANAS[0] + 2) * K.MIN))
                registradas += 1
            vistas += 1
            self.put("cola", a["id"])
        self.db.commit()
        return vistas, registradas

    def evaluar(self, fuente, s, stamp):
        inicio, R, stop = s["start_ms"], s["R"], s["stop"]
        ultima_cerrada = (stamp - 5000) // K.MIN * K.MIN - K.MIN
        fin = min(inicio + (K.SPAN - 1) * K.MIN, ultima_cerrada)
        filas = _contiguas(fuente.velas(s["symbol"], inicio, fin + K.MIN), inicio) if fin >= inicio else []
        esperadas = (fin - inicio) // K.MIN + 1 if fin >= inicio else 0
        o, h, l, c = ([f[k] for f in filas] for k in range(1, 5))
        ev = K.evaluar(o, h, l, c, R, stop)
        if len(filas) == K.SPAN:
            estado, nxt = "COMPLETO", MAX_INT
        elif len(filas) >= esperadas - 2:
            estado, nxt = "ABIERTO", _siguiente_hito(inicio, len(filas))
        else:
            final = stamp > inicio + K.SPAN * K.MIN + HUECO_LIMITE_MS
            estado, nxt = "HUECOS", (MAX_INT if final else stamp + HUECO_REINTENTO_MS)
        ctrl_z, ctrl_inicio = s["ctrl_z"], s["ctrl_inicio_ms"]
        if ctrl_z is None:
            ci = K.inicio_control(s["alerta_id"], s["ts_ms"])
            cf = _contiguas(fuente.velas(s["symbol"], ci, ci + K.SPAN * K.MIN), ci)
            if len(cf) == K.SPAN and cf[0][1] > 0:
                Rc = cf[0][1]
                sc = Rc * stop / R if isinstance(stop, (int, float)) and stop > 0 else None
                ctrl_z, ctrl_inicio = comprimir(K.evaluar(*([f[k] for f in cf] for k in range(1, 5)), Rc, sc)), ci
        o0 = round((filas[0][1] / R - 1) * 100, 4) if filas else None
        self.db.execute("UPDATE senales SET estado=?,next_check_ms=?,velas=?,o0_pct=?,evaluado_ms=?,eval_z=?,"
                        "ctrl_z=?,ctrl_inicio_ms=?,last_error=NULL WHERE alerta_id=?",
                        (estado, nxt, len(filas), o0, stamp, comprimir(ev), ctrl_z, ctrl_inicio, s["alerta_id"]))
        self.db.commit()


def ciclo(ruta_fuente, ruta_db, stamp=None, max_senales=400, presupuesto_s=40):
    ruta_fuente, ruta_db = Path(ruta_fuente).resolve(), Path(ruta_db).resolve()
    if ruta_fuente == ruta_db or (ruta_db.exists() and ruta_fuente.samefile(ruta_db)):
        raise ValueError("La base de sombra debe ser distinta de la de producción")
    stamp = stamp or ahora_ms()
    limite = time.monotonic() + presupuesto_s
    with closing(Fuente(ruta_fuente)) as fuente, closing(Almacen(ruta_db, stamp)) as alm:
        cid = alm.db.execute("INSERT INTO ciclos(started_ms) VALUES(?)", (stamp,)).lastrowid
        alm.db.commit()
        vistas = registradas = evaluadas = errores = 0
        fallo = None
        try:
            vistas, registradas = alm.descubrir(fuente, stamp)
            pendientes = alm.db.execute("SELECT * FROM senales WHERE next_check_ms<=? ORDER BY next_check_ms LIMIT ?",
                                        (stamp, max_senales)).fetchall()
            for s in pendientes:
                if time.monotonic() >= limite:
                    break
                try:
                    alm.evaluar(fuente, s, stamp)
                    evaluadas += 1
                except Exception as exc:
                    alm.db.rollback()
                    errores += 1
                    alm.db.execute("UPDATE senales SET last_error=?,next_check_ms=? WHERE alerta_id=?",
                                   (str(exc)[:500], stamp + K.MIN, s["alerta_id"]))
                    alm.db.commit()
        except Exception as exc:
            fallo = str(exc)[:500]
            errores += 1
        fin = ahora_ms()
        alm.db.execute("UPDATE ciclos SET finished_ms=?,vistas=?,registradas=?,evaluadas=?,errores=?,error=? WHERE id=?",
                       (fin, vistas, registradas, evaluadas, errores, fallo, cid))
        alm.put("ultimo_ciclo_ms", fin)
        if not errores:
            alm.put("ultimo_exito_ms", fin)
        alm.db.commit()
        return {"started_ms": stamp, "finished_ms": fin, "vistas": vistas, "registradas": registradas,
                "evaluadas": evaluadas, "errores": errores, "error": fallo}


def registros(ruta_db, solo_prospectivas=True):
    """Las señales de la base de sombra con la misma forma que los registros del histórico."""
    with closing(sqlite3.connect(Path(ruta_db).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        filas = db.execute("SELECT * FROM senales").fetchall()
        meta = dict(db.execute("SELECT key,value FROM metadata").fetchall())
        ciclos = [dict(r) for r in db.execute("SELECT * FROM ciclos ORDER BY id DESC LIMIT 3")]
    out = []
    for f in filas:
        if solo_prospectivas and f["origen"] != "PROSPECTIVO":
            continue
        out.append({"id": f["alerta_id"], "ts": f["ts_ms"], "symbol": f["symbol"], "tier": f["tier"],
                    "telegram": f["telegram"], "R": f["R"], "stop": f["stop"], "estado": f["estado"],
                    "o0_pct": f["o0_pct"], "alerta": json.loads(f["alerta_json"]),
                    "feat": json.loads(f["feat_json"]) if f["feat_json"] else None,
                    "eval": descomprimir(f["eval_z"]), "ctrl": descomprimir(f["ctrl_z"])})
    return out, meta, ciclos


def huella(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()
