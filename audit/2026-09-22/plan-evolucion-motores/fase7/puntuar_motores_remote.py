"""
¿Aciertan los dos motores de la fase 4? El pendiente que quedaba de esa fase.

Los motores llevan desde el 22-sep 06:41 UTC escribiendo lecturas en sombra y
NUNCA se ha puntuado ninguna. Mientras eso siga asi, no hay nada que activar en
la fase 7: la fase 5 mide OBJETIVOS DE SALIDA, y la seleccion —cual de las
diecisiete tomar, que con una posicion es la palanca real— depende de estos
motores.

Como se mide, y por que asi
---------------------------
Un plan no se compara con otro plan: cada uno tiene sus propias barreras, y un
objetivo cercano acierta mas por pura geometria. La vara es la misma que usa la
fase 5:

    base geometrica  P(+A antes que -B) = B / (A + B)
    habilidad        (acerto - base) x 100, en puntos porcentuales

Un motor que solo eligiera planes de objetivo cercano subiria su tasa de acierto
sin saber nada. La habilidad descuenta eso.

El intervalo sale de un bootstrap AGRUPADO POR PAR, igual que en la fase 5: las
lecturas del mismo simbolo no son independientes (ICC 0,114, efecto de diseño
x1,53) y tratarlas como si lo fueran estrecharia el intervalo a la mitad.

Y la pregunta que de verdad importa para la fase 7: **¿ordena?** Si el motor no
separa las buenas de las malas, no sirve como filtro de seleccion por mucho que
su tasa global se vea bien. AUC 0,5 es no saber nada.

Solo lectura. No escribe una sola fila.
"""
import json
import math
import random
import sqlite3
import sys
import time

DB = 'file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
SEMILLA = 20260923
N_BOOT = 2000

# Suelo de cobertura. NO es un detalle: medido el 23-sep sobre 1.681 recorridos,
# la habilidad aparente cae de forma monotona segun sube la cobertura —
# +26,7 pp entre 0,75 y 0,90, +14,6 pp entre 0,90 y 0,99, y +2,5 pp por encima
# de 0,99. El mecanismo es que una vela que falta borra la barrera que mas se
# toca, y la que mas se toca es la mas cercana: el stop. Faltar datos FABRICA
# objetivos. `plan_recorrido` marca completa=1 sin mirar la cobertura, asi que
# sin este suelo cualquier numero de aqui estaria inflado.
COBERTURA_MINIMA = float(sys.argv[1]) if len(sys.argv) > 1 else 0.99

db = sqlite3.connect(DB, uri=True)
db.execute('PRAGMA query_only=ON')

# =============================================================================
#  La poblacion: lecturas atadas a un plan cuyo recorrido ya termino
# =============================================================================
FILAS = """
SELECT l.motor, l.veredicto, l.familia, l.estado, l.datos, l.ts_ms,
       p.plan_id, r.symbol, r.entrada, r.objetivo, r.stop, r.desenlace,
       r.resultado_pct, p.ts_creado, p.ordinal_episodio,
       COALESCE(a.telegram,'') AS telegram
FROM motor_lecturas l
JOIN planes p          ON p.legacy_alerta_id = l.alerta_id
JOIN plan_recorrido r  ON r.plan_id = p.plan_id
LEFT JOIN alertas_emitidas a ON a.id = p.legacy_alerta_id
WHERE l.alerta_id IS NOT NULL
  AND r.completa = 1
  AND r.desenlace IN ('OBJETIVO','STOP')
  AND r.cobertura >= :cob
"""

cols = ('motor', 'veredicto', 'familia', 'estado', 'datos', 'ts_ms', 'plan_id',
        'symbol', 'entrada', 'objetivo', 'stop', 'desenlace', 'resultado_pct',
        'ts_creado', 'ordinal', 'telegram')
filas = [dict(zip(cols, r)) for r in db.execute(FILAS, {'cob': COBERTURA_MINIMA})]

# Causalidad: la lectura tiene que existir ANTES de que el recorrido termine.
# Se escribe justo despues de emitir, asi que deberia cumplirse siempre; si no,
# el motor estaria mirando el futuro y todo lo demas sobra.
tarde = [f for f in filas if f['ts_ms'] > f['ts_creado'] + 5 * 60_000]
print(f"suelo de cobertura aplicado: {COBERTURA_MINIMA:.2f}")
print(f"lecturas con desenlace: {len(filas)}")
print(f"   escritas mas de 5 min despues de crearse el plan: {len(tarde)}"
      + ("  <-- REVISAR" if tarde else "  (ninguna: causalidad limpia)"))
print(f"   planes distintos: {len({f['plan_id'] for f in filas})}")
print(f"   pares distintos: {len({f['symbol'] for f in filas})}")
print()


def base_geometrica(entrada, objetivo, stop):
    """P(+A antes que -B) para un paseo sin deriva. La unica vara honesta."""
    a = (objetivo - entrada) / entrada
    b = (entrada - stop) / entrada
    if a <= 0 or b <= 0:
        return None
    return b / (a + b)


def bootstrap_por_par(por_par, n=N_BOOT, semilla=SEMILLA):
    """
    Remuestrea PARES, no filas. Las lecturas del mismo simbolo se mueven
    juntas; remuestrear filas daria un intervalo la mitad de ancho del real.
    """
    claves = list(por_par)
    if not claves:
        return {'media': None, 'ic_bajo': None, 'ic_alto': None, 'n': 0, 'pares': 0}
    todos = [v for vs in por_par.values() for v in vs]
    media = sum(todos) / len(todos)
    rnd = random.Random(semilla)
    muestras = []
    for _ in range(n):
        vals = []
        for _ in range(len(claves)):
            vals.extend(por_par[claves[rnd.randrange(len(claves))]])
        if vals:
            muestras.append(sum(vals) / len(vals))
    muestras.sort()

    def q(p):
        if not muestras:
            return None
        return muestras[min(len(muestras) - 1, max(0, int(p * len(muestras))))]
    return {'media': media, 'ic_bajo': q(0.025), 'ic_alto': q(0.975),
            'n': len(todos), 'pares': len(claves)}


def resumen(grupo):
    """Tasa de acierto, base geometrica y habilidad con su intervalo."""
    hab, ace = {}, {}
    for f in grupo:
        base = base_geometrica(f['entrada'], f['objetivo'], f['stop'])
        if base is None:
            continue
        acierto = 1.0 if f['desenlace'] == 'OBJETIVO' else 0.0
        hab.setdefault(f['symbol'], []).append((acierto - base) * 100.0)
        ace.setdefault(f['symbol'], []).append(acierto * 100.0)
    h = bootstrap_por_par(hab)
    a = bootstrap_por_par(ace)
    return {'n': h['n'], 'pares': h['pares'], 'acierto': a['media'],
            'habilidad': h['media'], 'ic_bajo': h['ic_bajo'],
            'ic_alto': h['ic_alto']}


def linea(etiqueta, r):
    if not r['n']:
        print(f"  {etiqueta:<28} {'-':>6}")
        return
    print(f"  {etiqueta:<28} {r['n']:>6} {r['pares']:>6} "
          f"{r['acierto']:>8.1f}% {r['habilidad']:>+9.2f} pp "
          f"[{r['ic_bajo']:>+6.2f}, {r['ic_alto']:>+6.2f}]")


def cabecera(titulo):
    print(titulo)
    print(f"  {'':<28} {'n':>6} {'pares':>6} {'acierta':>9} {'habilidad':>12} "
          f"{'IC 95 %':>18}")
    print('  ' + '-' * 84)


def auc(pos, neg):
    """
    Probabilidad de que un acierto puntue por encima de un fallo.

    0,5 es no saber nada. Se calcula por rangos, con empates a la mitad, que es
    lo correcto cuando la mayoria de las lecturas comparten veredicto.
    """
    if not pos or not neg:
        return None
    todos = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rangos, i = {}, 0
    while i < len(todos):
        j = i
        while j < len(todos) and todos[j][0] == todos[i][0]:
            j += 1
        r = (i + j + 1) / 2.0
        for k in range(i, j):
            rangos.setdefault(k, r)
        i = j
    suma = sum(rangos[k] for k, (_, y) in enumerate(todos) if y == 1)
    n1, n0 = len(pos), len(neg)
    return (suma - n1 * (n1 + 1) / 2.0) / (n1 * n0)


# =============================================================================
#  1 · El motor de continuacion
# =============================================================================
cont = [f for f in filas if f['motor'] == 'continuacion']
print('=' * 88)
print(f'1 · MOTOR DE CONTINUACION  ({len(cont)} lecturas con desenlace)')
print('=' * 88)

cabecera('\nPor veredicto:')
todos_c = resumen(cont)
linea('TODAS (referencia)', todos_c)
for v in ('CANDIDATO', 'ESPERAR', 'CONFLICTO', 'SIN_TESIS', 'DATOS_INSUFICIENTES'):
    linea(v, resumen([f for f in cont if f['veredicto'] == v]))

cabecera('\nPor familia:')
familias = sorted({f['familia'] for f in cont if f['familia']})
for fam in familias:
    linea(fam, resumen([f for f in cont if f['familia'] == fam]))

# La pregunta de la fase 7: ¿el veredicto SEPARA?
cand = [f for f in cont if f['veredicto'] == 'CANDIDATO']
resto = [f for f in cont if f['veredicto'] != 'CANDIDATO']
print()
if cand and resto:
    rc, rr = resumen(cand), resumen(resto)
    dif = rc['habilidad'] - rr['habilidad']
    print(f"  CANDIDATO contra el resto: {dif:+.2f} pp de habilidad "
          f"(n={rc['n']} contra {rr['n']})")
    pos = [1.0 if f['veredicto'] == 'CANDIDATO' else 0.0 for f in cont
           if f['desenlace'] == 'OBJETIVO']
    neg = [1.0 if f['veredicto'] == 'CANDIDATO' else 0.0 for f in cont
           if f['desenlace'] == 'STOP']
    a = auc(pos, neg)
    print(f"  AUC del veredicto como ordenador: {a:.3f}"
          if a is not None else "  AUC: sin datos")
    print("     (0,5 = no ordena nada; es la vara que tumbo a la puntuacion "
          "antigua)")

# =============================================================================
#  2 · El ancla de 1h — el unico hallazgo de la fase 4 que batio a su control
# =============================================================================
print()
print('=' * 88)
print('2 · EL ANCLA DE 1h')
print('=' * 88)
print('  La fase 4 midio +8,46 pp para la ruptura alcista de 1h contra su')
print('  control pareado, y aguanto al partir la muestra. Es lo unico que')
print('  sobrevivio. ¿Se reproduce sobre los planes reales?')


def dato(f, clave):
    try:
        return json.loads(f['datos'] or '{}').get(clave)
    except Exception:
        return None


cabecera('\nPor direccion del ancla:')
dirs = sorted({dato(f, 'ancla_direccion') for f in cont} - {None})
for d in dirs:
    linea(str(d), resumen([f for f in cont if dato(f, 'ancla_direccion') == d]))
linea('sin lectura de ancla',
      resumen([f for f in cont if dato(f, 'ancla_direccion') is None]))

alc = [f for f in cont if dato(f, 'ancla_direccion') == 'RUPTURA_ALCISTA']
otros = [f for f in cont if dato(f, 'ancla_direccion') not in (None, 'RUPTURA_ALCISTA')]
if alc and otros:
    ra, ro = resumen(alc), resumen(otros)
    print()
    print(f"  ruptura alcista de 1h contra el resto: "
          f"{ra['habilidad'] - ro['habilidad']:+.2f} pp "
          f"(n={ra['n']} contra {ro['n']})")

# =============================================================================
#  3 · El motor de caida
# =============================================================================
caida = [f for f in filas if f['motor'] == 'caida']
print()
print('=' * 88)
print(f'3 · MOTOR DE CAIDA  ({len(caida)} lecturas con desenlace)')
print('=' * 88)
cabecera('\nPor estado:')
for e in sorted({f['estado'] for f in caida if f['estado']}):
    linea(e, resumen([f for f in caida if f['estado'] == e]))
n_cand_caida = sum(1 for f in caida if f['veredicto'] == 'CANDIDATO')
print()
print(f"  candidatos de compra emitidos por este motor: {n_cand_caida}")
if n_cand_caida < 20:
    print("  Con esta n no se puede decir nada de su acierto, y decirlo seria")
    print("  inventar. Lo unico medible hoy es que **casi no dispara** — que")
    print("  es exactamente lo que se le pidio: no anticipar suelos.")

# =============================================================================
#  4 · Sobre la poblacion que el operador recibe de verdad
# =============================================================================
print()
print('=' * 88)
print('4 · SOLO LO AVISADO POR TELEGRAM')
print('=' * 88)
tg = [f for f in cont if f['telegram'] == 'enviado']
cabecera('')
linea('todas las avisadas', resumen(tg))
for v in ('CANDIDATO', 'ESPERAR', 'SIN_TESIS'):
    linea(v, resumen([f for f in tg if f['veredicto'] == v]))
print()
print('  AVISO: esta es la poblacion que decide, y es la mas pequeña. Un')
print('  veredicto economico sobre estas n no vale; la lectura programada de')
print('  la fase 5 es la que manda.')

print()
print('=' * 88)
print('SALVEDADES')
print('=' * 88)
print('  · Retrospectivo sobre lecturas ya guardadas: es de donde sale la')
print('    pregunta, no el veredicto.')
print('  · Un solo regimen, desde el 22-sep 06:41 UTC.')
print('  · La habilidad descuenta la geometria del plan, no el regimen: la')
print('    tasa base de este sistema se movio 15 puntos en una semana.')
print('  · Ningun numero de aqui autoriza a activar nada. La fase 7a esta')
print('    congelada y apagada, y su puerta 1 es el informe de la fase 5.')
db.close()
