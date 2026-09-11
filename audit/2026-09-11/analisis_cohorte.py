# -*- coding: utf-8 -*-
"""Analisis de la cohorte de b8a3d64 sobre el snapshot del 10-sep 23:19."""
import sqlite3, pathlib, datetime as dt, statistics as st

P = pathlib.Path('audit/2026-09-10/verification/snapshot.db').resolve()
C = sqlite3.connect(f'file:{P.as_posix()}?mode=ro', uri=True)
C.row_factory = sqlite3.Row
VER = 'b8a3d64'
ARRANQUE = 1789080842000   # 10-sep 22:54:02 UTC = 16:54:02 Guatemala
import json
_prov = json.loads(pathlib.Path('audit/2026-09-10/verification/provenance.json').read_text())
CORTE = int(dt.datetime.fromisoformat(_prov['finished_utc']).timestamp() * 1000)


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000) - dt.timedelta(hours=6)).strftime('%d/%m %H:%M')


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "-"


def h(t):
    print(f"\n{'='*72}\n{t}\n{'='*72}")


filas = [dict(r) for r in C.execute(
    "select * from outcomes where strategy_version=? order by ts_open", (VER,))]
reales = [r for r in filas if not r['sombra']]
sombras = [r for r in filas if r['sombra']]
alertas = [dict(r) for r in C.execute(
    "select * from alertas_emitidas where strategy_version=? order by ts_ms", (VER,))]

h("1 · PERIMETRO")
horas = (CORTE - filas[0]['ts_open']) / 3600_000
print(f"Version        {VER} (esquema v11), config_hash {filas[0]['config_hash']}")
print(f"Primera fila   {gt(filas[0]['ts_open'])}")
print(f"Ultima fila    {gt(CORTE)}   (fin del snapshot)")
print(f"Ventana        {horas:.2f} horas")
print(f"Outcomes       {len(filas)}  =  {len(reales)} reales + {len(sombras)} en sombra")
print(f"Alertas        {len(alertas)}")
print(f"\nNINGUNA ventana de 24h ha vencido: la primera cierra el 11/09 a las 16:55.")

h("2 · PRODUCCION: cuanto y de que tipo")
print(f"Ritmo          {len(reales)/horas:.1f} outcomes reales/hora  "
      f"({len(reales)/horas*24:.0f}/dia al ritmo actual)")
print(f"               {len(alertas)/horas:.1f} alertas/hora")
pares = {r['symbol'] for r in reales}
print(f"Pares distintos {len(pares)} de 224 en el universo")
for campo, tit in (('tier', 'Tier'), ('display_state', 'Estado'), ('taxonomia', 'Taxonomia')):
    cuenta = {}
    for r in reales:
        cuenta[r[campo] or '(vacio)'] = cuenta.get(r[campo] or '(vacio)', 0) + 1
    linea = '  '.join(f"{k}={v}" for k, v in sorted(cuenta.items(), key=lambda x: -x[1]))
    print(f"{tit:14} {linea}")
motivos = {}
for r in sombras:
    m = (r['sombra_motivo'] or '(sin motivo)')[:45]
    motivos[m] = motivos.get(m, 0) + 1
print(f"\nVetadas y medidas en sombra ({len(sombras)}):")
for m, n in sorted(motivos.items(), key=lambda x: -x[1]):
    print(f"   {n:3}  {m}")

h("3 · LOS ARREGLOS DE v11: se notan en las filas?")
def nulos(campo, rows):
    return sum(1 for r in rows if r[campo] is None)
print("F07 · indicadores que antes NUNCA llegaban a la base")
for campo in ('rsi14_1m', 'rsi14_15m', 'macd_hist_15m', 'bb_position_15m'):
    n = nulos(campo, filas)
    print(f"   {campo:18} {len(filas)-n:3}/{len(filas)} guardados   "
          f"{'' if n==0 else f'({n} NULL)'}")
print("\nF08 · disponibilidad de flujo")
disp = [r for r in filas if r['flow_disponible']]
print(f"   flow_disponible=1   {len(disp)}/{len(filas)} ({pct(len(disp),len(filas))})")
cero = [r for r in disp if (r['flow_trades_30s'] or 0) == 0]
print(f"   de esos, con 0 trades: {len(cero)}  <- suscrito pero sin compradores")
nodisp = len(filas) - len(disp)
print(f"   sin suscripcion:     {nodisp}  <- su 0 de trades NO significa nada")
print("\nF12 · procedencia")
print(f"   con strategy_version {len(filas)}/{len(filas)}")
print(f"   con config_hash      {sum(1 for r in filas if r['config_hash'])}/{len(filas)}")
print("\nF01 · cobertura de velas (solo se escribe al cerrar)")
conc = [r for r in filas if r['cobertura_velas'] is not None]
print(f"   filas con cobertura registrada: {len(conc)}/{len(filas)}  "
      f"(ninguna ha cerrado todavia)")
falta = [((CORTE - r['ts_open']) // 60000) - (r['n_velas'] or 0) for r in filas]
sobra = sum(1 for f in falta if f < 0)
print(f"   minutos sin vela por fila (contra el cierre real del snapshot):")
print(f"      mediana {st.median(falta):.0f}   minimo {min(falta)}   maximo {max(falta)}")
print(f"      filas sin NINGUN minuto perdido: {sum(1 for f in falta if f<=0)}/{len(falta)}")
print(f"      filas con MAS velas que minutos: {sobra}  "
      f"(un sobreconteo seria imposible sin duplicados)")
print(f"   Las tres filas mas antiguas pierden 12 minutos de 384 (3.1%).")

h("4 · LOS NIVELES QUE SE OFRECIERON")
print("El objetivo del operador son 3.2%. El TP que ofrece el sistema es BRUTO;")
print("el coste configurado (comision + deslizamiento) es 0.5 puntos.\n")
for nom, rows in (("ALERTAS (lo que te llego)", alertas),
                  ("OUTCOMES reales", reales)):
    if not rows:
        continue
    tp = [r['tp_pct'] for r in rows if r['tp_pct'] is not None]
    neto = [r['reward_neto_pct'] for r in rows if r['reward_neto_pct'] is not None]
    # alertas_emitidas guarda el riesgo como magnitud positiva; outcomes con
    # signo. Se normaliza a magnitud para poder compararlos.
    sl = [abs(r['sl_pct']) for r in rows if r['sl_pct'] is not None]
    bajo_b = sum(1 for x in tp if x < 3.2)
    bajo_n = sum(1 for x in neto if x < 3.2)
    alc = sum(1 for r in rows if r['objetivo_alcanzable'])
    print(f"{nom}  (n={len(rows)})")
    print(f"   TP bruto   mediana {st.median(tp):+.2f}%   rango {min(tp):+.2f} a {max(tp):+.2f}")
    print(f"   TP neto    mediana {st.median(neto):+.2f}%   rango {min(neto):+.2f} a {max(neto):+.2f}")
    print(f"   Riesgo(SL) mediana  {st.median(sl):.2f}%   rango {min(sl):.2f} a {max(sl):.2f}")
    print(f"   NO llegan a 3.2% en bruto: {bajo_b}/{len(tp)} ({pct(bajo_b,len(tp))})")
    print(f"   NO llegan a 3.2% en neto:  {bajo_n}/{len(neto)} ({pct(bajo_n,len(neto))})")
    print(f"   marcadas objetivo_alcanzable: {alc}/{len(rows)} ({pct(alc,len(rows))})\n")

h("4b · POR QUE EL TP NO LLEGA A LA META: sale del SL")
import collections
r2 = [(abs(a['sl_pct']), a['tp_pct']) for a in alertas
      if a['sl_pct'] and a['tp_pct']]
ratios = [t/s_ for s_, t in r2]
print(f"TP / riesgo en las 46 alertas: mediana {st.median(ratios):.2f}  "
      f"(rr_target = 2.0)")
print(f"   identicos a 2.00: {sum(1 for x in ratios if abs(x-2)<0.01)}/{len(ratios)}")
print()
print("El TP no se elige: es el riesgo multiplicado por 2. Asi que para ofrecer")
print("3.2% BRUTO hace falta un stop de 1.60%, y para 3.2% NETO uno de 1.85%.")
umbral_b = sum(1 for s_, t in r2 if s_ < 1.60)
umbral_n = sum(1 for s_, t in r2 if s_ < 1.85)
print(f"   alertas con stop < 1.60%: {umbral_b}/{len(r2)} ({pct(umbral_b,len(r2))})"
      f"  -> no pueden llegar ni en bruto")
print(f"   alertas con stop < 1.85%: {umbral_n}/{len(r2)} ({pct(umbral_n,len(r2))})"
      f"  -> no pueden llegar en neto")
print()
print("Esa es la eleccion de fondo, y no la resuelve un umbral: o se aceptan")
print("stops mas anchos (mas riesgo por operacion), o se sube el rr_target (TP")
print("mas lejos sobre el mismo stop, que se toca menos veces), o se acepta que")
print("mas de la mitad de lo que emite el sistema no apunta a tu objetivo.")

h("5 · CAMINO RECORRIDO HASTA EL CORTE (inmaduro)")
print("Nada de esto es un resultado: son ventanas abiertas de entre "
      f"{(CORTE-filas[-1]['ts_open'])/3600000:.1f} y {horas:.1f} horas")
print("sobre una ventana nominal de 24. Un SL tocado ya es definitivo; un TP")
print("no tocado todavia puede tocarse manana.\n")
esc = [('ms_up_1', '+1%'), ('ms_up_2', '+2%'), ('ms_up_32', '+3.2% (meta)'),
       ('ms_up_42', '+4.2%'), ('ms_up_5', '+5%'), ('ms_up_10', '+10%')]
print(f"{'ESCALON':16} {'alcanzado':>12}   mediana de tiempo")
for campo, et in esc:
    hits = [r[campo] for r in reales if r[campo] is not None]
    t = f"{st.median(hits)/60000:.0f} min" if hits else "-"
    print(f"{et:16} {len(hits):3}/{len(reales)} {pct(len(hits),len(reales)):>7}   {t}")
print()
for campo, et in (('ms_dn_1', '-1%'), ('ms_dn_2', '-2%'), ('ms_dn_32', '-3.2%')):
    hits = [r[campo] for r in reales if r[campo] is not None]
    print(f"{et:16} {len(hits):3}/{len(reales)} {pct(len(hits),len(reales)):>7}")
tp_h = sum(1 for r in reales if r['ms_tp'] is not None)
sl_h = sum(1 for r in reales if r['ms_sl'] is not None)
ambos = sum(1 for r in reales if r['ms_tp'] is not None and r['ms_sl'] is not None)
print(f"\nTP propio tocado   {tp_h}/{len(reales)} ({pct(tp_h,len(reales))})")
print(f"SL propio tocado   {sl_h}/{len(reales)} ({pct(sl_h,len(reales))})")
print(f"   los dos          {ambos}   <- el orden dentro del minuto no se sabe")
mfe = [r['mfe_pct'] for r in reales]
mae = [r['mae_pct'] for r in reales]
print(f"\nMFE (lo mas que subio)  mediana {st.median(mfe):+.2f}%   mejor {max(mfe):+.2f}%")
print(f"MAE (lo mas que bajo)   mediana {st.median(mae):+.2f}%   peor  {min(mae):+.2f}%")
vivo = [((r['precio_ultimo'] or r['entry']) - r['entry']) / r['entry'] * 100 for r in reales]
pos = sum(1 for x in vivo if x > 0)
print(f"\nA precio de corte: {pos}/{len(vivo)} en positivo ({pct(pos,len(vivo))}), "
      f"mediana {st.median(vivo):+.2f}%")

h("6 · LA REGLA DEL HOYO (entrar abajo, en sombra)")
entraron = [r for r in filas if r['ms_hoyo'] is not None]
print(f"El precio bajo al nivel de entrada en {len(entraron)}/{len(filas)} "
      f"({pct(len(entraron),len(filas))})")
amb = sum(1 for r in entraron if r['hoyo_ambiguo'])
print(f"   de esos, {amb} con vela ambigua (no se concede el TP en esa vela)")
for regla in ('a', 'c2', 'c3'):
    res = {}
    for r in entraron:
        k = r[f'hoyo_{regla}'] or 'ABIERTA'
        res[k] = res.get(k, 0) + 1
    print(f"   regla {regla.upper():3} " + '  '.join(f"{k}={v}" for k, v in sorted(res.items())))

h("7 · TELEGRAM")
tel = {}
for r in alertas:
    k = r['telegram'] or '(sin marcar)'
    tel[k] = tel.get(k, 0) + 1
for k, v in sorted(tel.items(), key=lambda x: -x[1]):
    print(f"   {v:3}  {k}")
sin = [r for r in alertas if r['signal_id'] is None]
print(f"\nAlertas sin signal_id (sin outcome propio que mida SUS niveles): "
      f"{len(sin)}/{len(alertas)} ({pct(len(sin),len(alertas))})")

h("8 · CONTRA EL HISTORICO (con cuidado)")
print("Las 2.792 filas sin firma mezclan seis dias y varias versiones. Sirve")
print("para ver si el ritmo y la forma de las senales cambiaron, no para")
print("atribuir mejoras a esta version.\n")
viejas = [dict(r) for r in C.execute(
    "select * from outcomes where strategy_version is null and sombra=0")]
for nom, rows in (("historico sin firma", viejas), (f"{VER}", reales)):
    tp = [r['tp_pct'] for r in rows if r['tp_pct'] is not None]
    # alertas_emitidas guarda el riesgo como magnitud positiva; outcomes con
    # signo. Se normaliza a magnitud para poder compararlos.
    sl = [abs(r['sl_pct']) for r in rows if r['sl_pct'] is not None]
    sc = [r['score'] for r in rows if r['score'] is not None]
    print(f"{nom:22} n={len(rows):5}  TP med {st.median(tp):+.2f}%  "
          f"riesgo med {st.median(sl):.2f}%  score med {st.median(sc):.0f}")
cerradas = [dict(r) for r in C.execute(
    "select * from outcomes where cerrado=1 and strategy_version is null and sombra=0")]
llego = sum(1 for r in cerradas if r['ms_up_32'] is not None)
print(f"\nReferencia historica (ventanas de 24h ya cerradas, sin firma, n={len(cerradas)}):")
print(f"   llegaron a +3.2% en bruto: {llego} ({pct(llego,len(cerradas))})")
print(f"   ese es el numero que esta cohorte tendra que batir manana.")
