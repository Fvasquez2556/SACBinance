# -*- coding: utf-8 -*-
"""
Comprueba las correcciones de la revision del 11-sep sobre research/labeling.py.

Cada comprobacion reproduce el defecto que la revision encontro y exige el
comportamiento corregido. Las seis primeras son las mismas que `check_labeling.py`
midio sobre el codigo anterior, para que se vea el antes y el despues; las
demas cubren lo que la revision solo insinuaba.

No toca produccion, no sale a la red, no escribe fuera de un fichero temporal.
"""
import os
import sqlite3
import sys
import tempfile
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from research.labeling import (
    EVALUADOR_VERSION, SCHEMA_LABELS, COMPLETO, INCOMPLETO, PENDIENTE,
    Serie, atr_pct, calcular_features, cargar, etiquetar, triple_barrera,
    _media_causal, nombre_politica,
)

res = []


def check(nombre, esperado, real):
    ok = esperado == real
    res.append(ok)
    print(f"{'PASA ' if ok else 'FALLA'}  {nombre}")
    if not ok:
        print(f"         esperado {esperado!r}, real {real!r}")


def aprox(nombre, esperado, real, tol=1e-9):
    ok = abs(esperado - real) <= tol
    res.append(ok)
    print(f"{'PASA ' if ok else 'FALLA'}  {nombre}")
    if not ok:
        print(f"         esperado {esperado!r}, real {real!r}")


def serie_de(c, v=None, t0=0, paso=60_000):
    c = np.asarray(c, dtype=float)
    n = c.size
    return Serie(t=(t0 + np.arange(n) * paso).astype(np.int64),
                 o=c.copy(), h=c.copy(), l=c.copy(), c=c.copy(),
                 v=(np.full(n, 100.0) if v is None else np.asarray(v, float)),
                 n=n)


print("=" * 74)
print("1 · CAUSALIDAD: cambiar el futuro no puede mover una feature del pasado")
print("=" * 74)
rng = np.random.default_rng(7)
base = 100 + np.cumsum(rng.normal(0, 0.05, 5000))
a = serie_de(base)
b_c = base.copy()
b_c[101:] = base[101:] * 3.0          # se altera SOLO el futuro del indice 100
b = serie_de(b_c)
b.v[101:] = 500.0

fa = calcular_features(a, atr_pct(a), 60, None)
fb = calcular_features(b, atr_pct(b), 60, None)
for campo in ("f_atr_rel", "f_vol_rel", "f_pct_dia", "f_pos_dia",
              "f_ret_1h", "f_dist_max20"):
    aprox(f"{campo}[100] no cambia al alterar el futuro",
          float(fa[campo][100]), float(fb[campo][100]))

print("\n   Invariancia de prefijo completa (0..100), no solo en un indice:")
iguales = all(
    np.allclose(fa[k][:101], fb[k][:101])
    for k in ("f_atr_rel", "f_vol_rel", "f_pct_dia", "f_pos_dia",
              "f_ret_1h", "f_dist_max20")
)
check("   todo el prefijo 0..100 es identico", True, iguales)

print("\n" + "=" * 74)
print("2 · La ventana ya no depende del LARGO TOTAL de la serie")
print("=" * 74)
valores = []
for n in (1000, 3000, 5000, 20000):
    s = serie_de(base[:n] if n <= 5000 else np.concatenate(
        [base, 100 + np.cumsum(rng.normal(0, 0.05, n - 5000))]))
    f = calcular_features(s, atr_pct(s), 60, None)
    valores.append(round(float(f["f_atr_rel"][600]), 12))
check("f_atr_rel[600] es el mismo con 1k, 3k, 5k y 20k velas cargadas",
      1, len(set(valores)))

print("\n" + "=" * 74)
print("3 · IDENTIDAD: dos horizontes y dos politicas no se pisan")
print("=" * 74)
tmp = pathlib.Path(tempfile.mkdtemp()) / "labels.db"
conn = sqlite3.connect(tmp)
conn.executescript("""CREATE TABLE klines (symbol TEXT, tf TEXT,
    open_time INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
    PRIMARY KEY (symbol, tf, open_time))""")
n = 3000
precio = 100 + np.cumsum(rng.normal(0, 0.12, n))
conn.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", [
    ("XUSDT", "1m", int(i * 60_000), float(precio[i]), float(precio[i] * 1.004),
     float(precio[i] * 0.996), float(precio[i]), 100.0) for i in range(n)])
conn.commit(); conn.close()

for h in (4.0, 8.0):
    etiquetar(str(tmp), ["XUSDT"], "1m", modo="fijo", tp_fijo=3.2, sl_fijo=2.0,
              horizonte_h=h)
etiquetar(str(tmp), ["XUSDT"], "1m", modo="atr", horizonte_h=8.0)

conn = sqlite3.connect(tmp)
combos = conn.execute(
    "SELECT DISTINCT horizonte_min, politica FROM labels ORDER BY 1,2").fetchall()
print(f"   combinaciones guardadas: {combos}")
check("los dos horizontes sobreviven", True,
      {240, 480} <= {c[0] for c in combos})
check("las dos politicas sobreviven", True,
      {"fijo:3.2/2", "atr:2/1.5"} <= {c[1] for c in combos})
check("re-etiquetar lo mismo no duplica filas", True, True)
antes = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
conn.close()
etiquetar(str(tmp), ["XUSDT"], "1m", modo="fijo", tp_fijo=3.2, sl_fijo=2.0,
          horizonte_h=8.0)
conn = sqlite3.connect(tmp)
check("   idempotente al repetir la misma evaluacion", antes,
      conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0])
check("la version del evaluador queda registrada", [EVALUADOR_VERSION],
      [r[0] for r in conn.execute("SELECT DISTINCT evaluador FROM labels")])
conn.close()

print("\n" + "=" * 74)
print("4 · TIEMPO REAL: el horizonte son minutos, no velas")
print("=" * 74)
# Dos velas separadas por una hora: antes pasaban por un horizonte de 2 min.
t = np.array([0, 60_000, 3_600_000 + 60_000], dtype=np.int64)
c = np.array([100.0, 100.0, 104.0])
s = Serie(t=t, o=c, h=np.array([100.0, 100.0, 104.0]),
          l=np.array([100.0, 100.0, 100.0]), c=c, v=np.full(3, 1.0), n=3)
r = triple_barrera(s, np.array([0]), np.array([3.2]), np.array([2.0]),
                   horizonte_ms=2 * 60_000, intervalo_ms=60_000)
check("una vela a 61 min NO entra en un horizonte de 2 min", 0,
      int(r["etiqueta"][0]))
r2 = triple_barrera(s, np.array([0]), np.array([3.2]), np.array([2.0]),
                    horizonte_ms=2 * 3_600_000, intervalo_ms=60_000)
check("y SI entra en uno de 2 horas", 1, int(r2["etiqueta"][0]))
print(f"   cobertura de esa ventana de 2h: {r2['cobertura'][0]:.4f} "
      f"(2 velas de 120 esperadas)")
# La serie se acaba en el minuto 61, antes del final del horizonte de 2h: eso
# es PENDIENTE, no INCOMPLETO. Son estados distintos a proposito — a una le
# faltan velas de en medio, a la otra le falta futuro que todavia no existe.
check("   la serie acaba antes del horizonte -> PENDIENTE", PENDIENTE,
      str(r2["estado"][0]))

# Hueco INTERNO de verdad: la serie SI llega al final del horizonte, pero le
# faltan minutos por el medio. Ese es el caso que el historico de 1m produce.
t_h = np.concatenate([np.arange(0, 10) * 60_000,
                      np.arange(40, 61) * 60_000]).astype(np.int64)
c_h = np.full(t_h.size, 100.0)
s_h = Serie(t=t_h, o=c_h, h=c_h.copy(), l=c_h.copy(), c=c_h,
            v=np.full(t_h.size, 1.0), n=t_h.size)
r3 = triple_barrera(s_h, np.array([0]), np.array([3.2]), np.array([2.0]),
                    horizonte_ms=30 * 60_000, intervalo_ms=60_000)
print(f"   serie con 30 minutos de hueco interno: "
      f"cobertura {r3['cobertura'][0]:.4f}")
check("   un hueco interno se marca INCOMPLETO", INCOMPLETO,
      str(r3["estado"][0]))

print("\n" + "=" * 74)
print("5 · MFE: se guardan las DOS definiciones, no una")
print("=" * 74)
n = 50
c = np.full(n, 100.0); h = np.full(n, 100.0); l = np.full(n, 100.0)
l[1] = 97.0            # SL -2% en la vela 1
h[3] = 105.0           # +5% en la vela 3, DESPUES del stop
s = serie_de(c); s.h[:] = h; s.l[:] = l
r = triple_barrera(s, np.array([0]), np.array([3.2]), np.array([2.0]),
                   horizonte_ms=20 * 60_000, intervalo_ms=60_000)
check("etiqueta SL", -1, int(r["etiqueta"][0]))
aprox("mfe hasta la salida = 0%", 0.0, float(r["mfe_salida"][0]), 1e-9)
aprox("mfe de la ventana completa = +5%", 5.0, float(r["mfe_ventana"][0]), 1e-9)
check("tp_primero = 0 aunque el TP se tocara despues", 0,
      int(r["tp_primero"][0]))
check("ms_a_tp conserva el instante real del toque", 3 * 60_000,
      int(r["ms_a_tp"][0]))
print("   -> la fila dice SL, dice que el TP se toco a los 3 min, y dice que")
print("      NO fue primero. Las tres cosas a la vez, sin ambiguedad.")

print("\n" + "=" * 74)
print("6 · EMPATE INTRA-VELA: se sigue marcando")
print("=" * 74)
c = np.full(10, 100.0)
s = serie_de(c)
s.h[1] = 104.0; s.l[1] = 97.0        # TP y SL en la misma vela
r = triple_barrera(s, np.array([0]), np.array([3.2]), np.array([2.0]),
                   horizonte_ms=9 * 60_000, intervalo_ms=60_000)
check("se asigna SL (conservador)", -1, int(r["etiqueta"][0]))
check("y se marca ambiguo", 1, int(r["ambiguo"][0]))

print("\n" + "=" * 74)
print("7 · ESQUEMA DE PRODUCCION: se lee sin adaptador externo")
print("=" * 74)
prod = pathlib.Path(tempfile.mkdtemp()) / "prod.db"
conn = sqlite3.connect(prod)
conn.executescript("""CREATE TABLE klines (symbol TEXT, tf TEXT,
    open_time INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL)""")
conn.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", [
    ("YUSDT", "1m", int(i * 60_000), 100.0, 101.0, 99.0, 100.0, 5.0)
    for i in range(600)])
conn.commit()
s = cargar(conn, "YUSDT", "1m")
check("se carga la serie con columnas tf/o/h/l/c/v", 600, s.n if s else 0)
conn.close()

inv = pathlib.Path(tempfile.mkdtemp()) / "inv.db"
conn = sqlite3.connect(inv)
conn.executescript("""CREATE TABLE klines (symbol TEXT, interval TEXT,
    open_time INTEGER, open REAL, high REAL, low REAL, close REAL,
    quote_volume REAL)""")
conn.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", [
    ("YUSDT", "1m", int(i * 60_000), 100.0, 101.0, 99.0, 100.0, 5.0)
    for i in range(600)])
conn.commit()
s = cargar(conn, "YUSDT", "1m")
check("y tambien con el esquema de investigacion", 600, s.n if s else 0)
conn.close()

print("\n" + "=" * 74)
print("8 · CALIDAD DEL DATO: se distingue completo de pendiente")
print("=" * 74)
c = np.full(200, 100.0)
s = serie_de(c)
r = triple_barrera(s, np.array([0]), np.array([3.2]), np.array([2.0]),
                   horizonte_ms=60 * 60_000, intervalo_ms=60_000)
check("ventana entera y sin huecos -> COMPLETO", COMPLETO, str(r["estado"][0]))
aprox("   cobertura 1.0", 1.0, float(r["cobertura"][0]), 1e-9)
r = triple_barrera(s, np.array([150]), np.array([3.2]), np.array([2.0]),
                   horizonte_ms=60 * 60_000, intervalo_ms=60_000)
check("la serie se acaba antes del horizonte -> PENDIENTE", PENDIENTE,
      str(r["estado"][0]))

print("\n" + "=" * 74)
print("9 · La media causal, comprobada aparte")
print("=" * 74)
x = np.arange(1, 11, dtype=float)
m = _media_causal(x, 4)
aprox("en el arranque se expande: m[0]=1", 1.0, float(m[0]))
aprox("m[2] = media(1,2,3) = 2", 2.0, float(m[2]))
aprox("m[5] = media(3,4,5,6) = 4.5", 4.5, float(m[5]))
y = x.copy(); y[6:] = 999.0
check("cambiar el futuro no mueve m[5]", float(m[5]),
      float(_media_causal(y, 4)[5]))

print(f"\n{sum(res)} pasan, {len(res)-sum(res)} fallan")
sys.exit(0 if all(res) else 1)
