"""Generate the Spanish report and self-contained Canvas from verified local results."""
import json
from pathlib import Path

P = Path(__file__).resolve().parent
r = json.loads((P / 'results.json').read_text(encoding='utf-8'))
c = json.loads((P / 'comparison.json').read_text(encoding='utf-8'))
v = json.loads((P / 'verification.json').read_text(encoding='utf-8'))
g = json.loads((P / 'gap-diagnostics.json').read_text(encoding='utf-8'))
q, old, new = r['clean_current'], c['previous_cut'], c['newly_eligible']
early, recent = r['early'], r['recent']
ci = r['change_cluster_bootstrap']
quality = r['quality_by_version']['f82bcff']
rupt = c['ruptures']
low_tp_pct = 100 * q['plan_tp_below32_n'] / q['n']
no_id_pct = 100 * r['integrity']['alert_no_id_total'] / r['counts']['alerts']

report = f'''# ¿Mejoraron los datos y las señales?

**La medición ha mejorado respecto al histórico antiguo y hay un pequeño repunte en los resultados acumulados. Todavía no se demuestra una mejora rentable de las señales.** Además, aparecieron nuevos huecos de velas que impiden considerar resuelta la calidad de datos.

Corte principal: **17 de septiembre de 2026, 13:36 Guatemala / 19:36 UTC**. Extracción de solo lectura de `sacbinance.db`: **{r['counts']['outcomes']:,} recorridos, {r['counts']['signals']:,} planes y {r['counts']['alerts']:,} avisos**. Respecto al corte del 16-sep se añadieron {c['counts_delta']['outcomes']} recorridos, {c['counts_delta']['signals']} planes y {c['counts_delta']['alerts']} avisos. No se modificó producción.

## Qué cambió desde el corte anterior

La muestra comparable pasó de **{old['n']} a {q['n']:,} señales emitidas**, con 24 horas completadas, cobertura registrada ≥98% y tiempos válidos. Hay {q['symbols']} símbolos. Las entradas incluidas van del 11-sep 23:04 al 16-sep 18:48 UTC.

- +3.2% antes del SL en 24h: **{old['goal_before_sl_pct']:.1f}% → {q['goal_before_sl_pct']:.1f}%**.
- Resultado medio bruto registrado del plan: **{old['signal_gross_mean']:+.3f}% → {q['signal_gross_mean']:+.3f}%**.
- Cierres registrados de al menos +3.2% bruto: **{old['signal_close32_pct']:.1f}% → {q['signal_close32_pct']:.1f}%**.

Son cortes acumulados que comparten 903 señales, no muestras independientes ni una prueba del efecto de una corrección. Ninguna de las señales incluidas antes salió de la muestra o cambió su etiqueta principal.

Las **{new['n']} señales recién incorporadas a la muestra evaluable** tuvieron {new['goal_before_sl_n']} casos de +3.2% antes del SL (**{new['goal_before_sl_pct']:.1f}%**) y un promedio bruto de **{new['signal_gross_mean']:+.3f}%**. Al restar un coste hipotético uniforme de 0.50 puntos porcentuales, el promedio queda en **{new['signal_net_scenario_mean']:+.3f}%**. Este pequeño repunte no basta para confirmar rentabilidad. Otras 49 señales emitidas que maduraron desde el corte anterior no superaron el filtro de cobertura; la disponibilidad de datos puede sesgar esta comparación.

## Tres resultados que no deben confundirse

En las mismas **{q['n']:,} señales**:

- **{q['touch32_n']} ({q['touch32_pct']:.1f}%)** tocaron +3.2% en algún momento dentro de 24h.
- **{q['goal_after_sl_n']}** lo hicieron después de tocar el SL: no son éxitos de entrada con ese stop.
- **{q['goal_before_sl_n']} ({q['goal_before_sl_pct']:.1f}%)** alcanzaron +3.2% antes del SL observado. Entre ellas, **{q['goal_after_short_tp_n']}** ya habían tocado primero un TP del plan menor: seguir el plan habría supuesto salir antes.
- Solo **{q['signal_close32_n']} ({q['signal_close32_pct']:.1f}%)** registraron un cierre del plan de al menos +3.2% bruto en `signals`.

El promedio de cierre de todos esos planes es **{q['signal_gross_mean']:+.3f}% bruto**, o **{q['signal_net_scenario_mean']:+.3f}%** al descontar el escenario de 0.50 puntos. Son resultados del seguimiento/simulación; no fills acreditados en Binance ni rentabilidad de una cartera. Las señales se solapan y repiten pares.

## No hay una mejora estadística concluyente

Con periodos sin solaparse, las entradas anteriores al 14-sep UTC (n={early['n']}) obtienen **{early['goal_before_sl_pct']:.1f}%** de +3.2% antes del SL. Las posteriores, ya maduras (n={recent['n']}), obtienen **{recent['goal_before_sl_pct']:.1f}%**. La diferencia de **{ci['delta_pp']:+.1f} puntos** tiene un intervalo bootstrap del 95% por símbolo de **{ci['p025_pp']:+.1f} a {ci['p975_pp']:+.1f} puntos**: los datos son compatibles tanto con una caída como con una mejora.

El resultado bruto medio empeora entre esos periodos: **{early['signal_gross_mean']:+.3f}% → {recent['signal_gross_mean']:+.3f}%**. Además cambia el régimen BTC y la mezcla de volatilidad; no se puede atribuir el movimiento al código.

La configuración `7ebc818e36e9` aporta 695 señales: 20.0% de +3.2% antes del SL y −0.109% bruto medio. La posterior `3dff943e60b0` aporta 328: 17.1% y −0.488%. La configuración más nueva, `fc1c5ef3ce25`, tiene solo **{g['new_config_n']} recorridos** en la extracción, ninguno maduro. **Las modificaciones del 17-sep todavía no pueden evaluarse con estos resultados.** La revisión de UI no demuestra por sí misma una mejora del motor.

## El TP sigue sin ajustarse al objetivo y falta muestra por perfil

**{q['plan_tp_below32_n']}/{q['n']} planes ({low_tp_pct:.1f}%) ofrecen un TP inferior a +3.2% bruto.** La mediana es +{q['tp_median']:.3f}%. El sistema puede acertar su propio TP y aun así no cumplir la meta del usuario. Antes de optimizar entradas, hace falta una política de salida coherente con esa meta y declarar si el 3.2% es antes o después de costes.

Las frecuencias de alcanzar +3.2% antes del SL son **{q['goal_before_sl_by_horizon_pct']['240']:.1f}% a 4h**, **{q['goal_before_sl_by_horizon_pct']['360']:.1f}% a 6h** y **{q['goal_before_sl_by_horizon_pct']['480']:.1f}% a 8h**. Son estadísticas históricas de la muestra; no una probabilidad calibrada para la próxima señal.

Los grupos muy tranquilos, tranquilos, movidos y muy volátiles obtienen respectivamente **11.0%, 17.4%, 25.4% y 33.0%** de +3.2% antes del SL en 24h. Sin embargo, el grupo muy volátil tiene el peor resultado bruto medio: **−0.504%**. Más recorrido favorable no significa mejor resultado con las salidas actuales.

En la taxonomía principal hay **946 NEUTRAL, 62 TENDENCIA y solo 2 BASE_POST_CAIDA**. Esto no permite comparar de manera representativa el rebote tras capitulación con la subida sostenida que se quiere detectar. En una prueba con umbral de rango fijado usando únicamente datos anteriores, el grupo seleccionado llega más veces a +3.2% (28.7% frente a 14.6%), pero tiene peor promedio bruto (−0.486% frente a −0.238%). El rango detecta movimiento; por sí solo no demuestra rentabilidad.

## Calidad de datos: progreso real, con una regresión reciente

En versiones antiguas identificadas, 58/280 recorridos maduros superaban el 98% de cobertura registrada (**20.7%**). En `f82bcff` son **{quality['cov98']:,}/{quality['mature']:,} ({100*quality['cov98']/quality['mature']:.1f}%)**, incluyendo recorridos en sombra. Esto mejora mucho el histórico, pero baja desde el **89.7% del corte anterior**.

En las ventanas que comenzaron el 16-sep, **79 de 278 maduras** tienen cobertura <98%. De los 1,191 recorridos emitidos reconstruidos con velas de 1m, 147 tienen algún hueco: 92 comparten el primer hueco del **14-sep 20:28 UTC**, 49 el del **17-sep 06:22 UTC** y 6 el del 12-sep 05:08 UTC. Esta coincidencia justifica investigar interrupciones del colector; no identifica por sí sola su causa.

La reconstrucción independiente valida los **{q['goal_before_sl_n']} casos positivos antes de cualquier primer hueco** y no cambia ninguna de las {q['n']:,} etiquetas principales. {v['analysis_complete_raw_paths']:,} de esas {q['n']:,} ventanas tienen ahora todas las velas esperadas. Otros **{v['tracker_lowcoverage_but_raw_complete']} recorridos** excluidos por cobertura del tracker sí tienen ahora todas las velas: reparar precios no recalcula automáticamente el resultado guardado.

La retención de 1m creció de 7.81 a **{r['retention_1m_days']:.2f} días**. No hay señales abiertas más allá de 12h ni outcomes pendientes más allá de 24h. Todas las señales tienen outcome y todos los outcomes emitidos enlazan a una señal. En los recorridos actuales hay versión, configuración, volatilidad, drawdown, ATR y volumen; faltan RSI/MACD de 15m en 53 de 2,291 filas.

Persisten **{r['integrity']['alert_no_id_total']}/{r['counts']['alerts']} avisos ({no_id_pct:.1f}%) sin `signal_id`**, frente a 39.4% en el corte anterior. No son necesariamente operaciones perdidas: pueden ser avisos de estado o actualizaciones. Para evaluar toda la experiencia de la UI hay que distinguir esos avisos de una entrada operable y enlazar esta última con su resultado. No se encontraron niveles de entrada/TP/SL divergentes en los avisos que sí están enlazados.

## El nuevo seguimiento de rupturas está funcionando, pero aún es inmaduro

La consulta de ejecución de las 19:37 UTC encuentra la tabla `rupturas` y el servicio activo desde las 19:09:16 UTC. Hay **{rupt['n']} eventos: 25 alcistas y 31 bajistas**, con una antigüedad máxima de **{rupt['oldest_minutes']:.1f} minutos**. Existen retornos de 5m en 39 y de 15m en 19; todavía ninguno de 30m, 1h, 4h o 24h, y ninguno cerrado.

`backend/src/analysis/rupture_tracker.py` registra máximos, mínimos, MFE/MAE direccionales y retornos de 5m, 15m, 30m, 1h, 4h y 24h. La nueva tabla no guarda entrada/TP/SL estructural de un plan, TP-before-SL, cobertura o versión de configuración. Tampoco tiene horizontes propios de 2h, 6h y 8h. Es un avance para medir movimientos de mercado, pero aún no responde por sí sola a la pregunta de ganar +3.2% antes del stop. No debe confundirse con la evaluación de planes de `outcomes`.

## Prioridad recomendada

1. **Recuperar y reconciliar los huecos**, guardando cobertura, versión del cálculo y evidencia original. Investigar el tramo común que comienza el 17-sep 06:22 UTC.
2. **Alinear el plan con la meta de +3.2%**, incluyendo costes y riesgo. Subir el TP sin validar su alcanzabilidad no resuelve la entrada ni la esperanza del resultado.
3. **Enlazar detecciones operables, planes y recorridos**, reutilizando `outcomes` para el orden TP/SL. Conservar aparte las rupturas informativas que no ofrecen una operación.
4. **Evaluar cambios en datos posteriores completos**, separando rebote y tendencia sostenida, volatilidad y régimen BTC. Medir el promedio neto, pérdidas, MFE/MAE y tiempos; no seleccionar solo por frecuencia de tocar una meta.

## Reproducibilidad y límites

`export_readonly.py` produjo `snapshot.json.gz` en una transacción SQLite de solo lectura. `analyze.py` reproduce `results.json`; `verify_and_compare.py` compara ambos cortes, reconstruye las velas conservadas usando `verify_paths.py` y comprueba los totales con una consulta SQL independiente. La verificación está en `verification.json`, el detalle de velas en `path-check.json`, y la comparación en `comparison.json`.

Los planes de `signals` vencen a 12h; las excursiones de `outcomes` se observan hasta 24h. No son métricas intercambiables. Los cruces tienen resolución de un minuto; un empate de barreras en la misma vela no permite establecer el orden. Se excluyen 168 recorridos emitidos maduros de `f82bcff` por cobertura <98%; las ventanas inmaduras no se cuentan como fallos. Los promedios brutos siguen negativos usando umbrales de cobertura de 95%, 98%, 99% y 99.5%. Con 100% quedan solo 59 casos, cuyo +0.043% bruto pasa a −0.457% bajo el escenario de coste; esa selección pequeña tampoco valida una ventaja.

El bootstrap usa 3,000 repeticiones por símbolo; no elimina la dependencia de mercado entre pares. El código del servidor tiene cambios sin commit, por lo que `strategy_version` no identifica por sí sola todo lo ejecutado. Los hallazgos son descriptivos y no prueban causalidad. No se corrigió ni desplegó código en esta revisión.
'''
(P / 'ANALISIS.md').write_text(report, encoding='utf-8')

data = {'current': q, 'old': old, 'new': new, 'early': early, 'recent': recent,
        'quality': quality, 'verification': v, 'counts': r['counts'],
        'volatility': r['by_volatility'], 'bootstrap': ci}
canvas = r'''import { BarChart, Callout, Divider, Grid, H1, H2, Stack, Stat, Table, Text, useHostTheme } from "cursor/canvas";

const data = __DATA__;
const q = data.current;
const pct = (x: number, decimals = 1) => `${x.toFixed(decimals)}%`;
const signed = (x: number, decimals = 3) => `${x > 0 ? "+" : ""}${x.toFixed(decimals)}%`;

export default function EvolucionSenales17Septiembre() {
  const theme = useHostTheme();
  return <Stack gap={24} style={{ maxWidth: 1120, margin: "0 auto", padding: 24, color: theme.text.primary }}>
    <Stack gap={8}>
      <H1>Un pequeño repunte; rentabilidad aún sin demostrar</H1>
      <Text>La medición mejoró frente al histórico antiguo. Las señales evaluables llegan algo más a la meta, pero el resultado medio sigue siendo negativo y hay nuevos huecos de velas.</Text>
      <Text tone="secondary">Fuente: sacbinance.db · 17-sep-2026, 19:36 UTC / 13:36 Guatemala. Muestra principal: 1,023 señales emitidas, 234 símbolos, 24h completas, cobertura registrada ≥98% y tiempos válidos. Entradas del 11 al 16 de septiembre UTC.</Text>
    </Stack>
    <Grid columns="repeat(auto-fit,minmax(190px,1fr))" gap={16}>
      <Stat value="5,363" label="Recorridos recolectados · todas las versiones" />
      <Stat value="1,023" label="Señales evaluables · muestra principal" />
      <Stat value={pct(q.goal_before_sl_pct)} label="+3.2% antes del SL · hasta 24h" />
      <Stat value={signed(q.signal_gross_mean)} label="Promedio bruto del plan registrado" tone="danger" />
    </Grid>
    <Callout tone="warning" title="Tocar una meta, alcanzarla antes del stop y cerrar con ganancia son resultados diferentes">
      307 señales tocaron +3.2%; 112 lo hicieron después del SL. De las 195 que llegaron antes del SL, 82 ya habían tocado un TP menor. Solo 62 planes (6.1%) registraron un cierre de al menos +3.2% bruto. Son resultados simulados, no fills de Binance.
    </Callout>
    <Stack gap={10}>
      <H2>Qué cambió desde el corte anterior</H2>
      <Table headers={["Métrica", "Corte 16-sep · n=903", "Corte 17-sep · n=1,023", "120 incorporadas"]} rows={[
        ["+3.2% antes del SL · 24h", ...[data.old,q,data.new].map(x => pct(x.goal_before_sl_pct))],
        ["Promedio bruto del plan", ...[data.old,q,data.new].map(x => signed(x.signal_gross_mean))],
        ["Tras coste hipotético de 0.50 puntos", ...[data.old,q,data.new].map(x => signed(x.signal_net_scenario_mean))],
        ["Cierre del plan ≥+3.2% bruto", ...[data.old,q,data.new].map(x => pct(x.signal_close32_pct))],
      ]} />
      <Text tone="secondary">Los cortes acumulados comparten 903 señales. Las 120 incorporadas completaron su ventana y cumplen los filtros; otras 49 que maduraron no superaron el de cobertura. No es una prueba independiente del efecto del código.</Text>
      <Text>En periodos separados, anteriores y posteriores al 14-sep UTC, la frecuencia sube de 17.2% a 20.3%. El intervalo del cambio va de −2.2 a +8.1 puntos: aún admite empeoramiento o mejora. El promedio bruto pasa de −0.071% a −0.338%.</Text>
    </Stack>
    <Divider />
    <Stack gap={10}>
      <H2>La meta sigue por encima de la mayoría de los TP</H2>
      <Text>703 de 1,023 planes (68.7%) ofrecen un TP inferior a +3.2% bruto. Mediana del TP: +2.383%. Acertar ese TP no equivale a cumplir la meta del usuario.</Text>
      <Text tone="secondary">Eje horizontal: tiempo desde la entrada. Eje vertical: porcentaje de las mismas 1,023 señales que alcanzó +3.2% antes del SL observado.</Text>
      <BarChart categories={["15m","30m","1h","2h","4h","6h","8h","24h"]}
        series={[{name:"+3.2% antes del SL",data:Object.values(q.goal_before_sl_by_horizon_pct),tone:"info"}]}
        yMin={0} yMax={25} height={240} showValues valueSuffix="%" />
      <Text tone="secondary">Fuente: outcomes, muestra principal al 17-sep. Cruces con resolución de un minuto. Incluye metas posteriores a un TP menor del plan. Son frecuencias históricas, no probabilidades calibradas de la próxima señal.</Text>
    </Stack>
    <Stack gap={10}>
      <H2>Más volatilidad trae más recorrido; no mejores cierres</H2>
      <Table headers={["Volatilidad al abrir", "Señales", "+3.2% antes del SL · 24h", "Promedio bruto"]}
        rows={([
          ["MUY_TRANQUILA","Muy tranquila"], ["TRANQUILA","Tranquila"],
          ["MOVIDA","Movida"], ["MUY_VOLATIL","Muy volátil"]
        ] as const).map(([key,label]) => {
          const x = data.volatility[key];
          return [label,x.n,pct(x.goal_before_sl_pct),signed(x.signal_gross_mean)];
        })} />
      <Text tone="secondary">946 señales están etiquetadas NEUTRAL; 62 TENDENCIA y solo 2 BASE_POST_CAIDA. Falta muestra representativa para comparar rebote tras capitulación frente a subida sostenida.</Text>
    </Stack>
    <Stack gap={10}>
      <H2>La cobertura mejoró frente al histórico, pero retrocedió en el último corte</H2>
      <Text tone="secondary">Eje horizontal: versión y corte. Eje vertical: recorridos maduros cuya cobertura registrada supera o iguala 98% (%). Incluye sombra; los dos cortes actuales se solapan.</Text>
      <BarChart categories={["Versiones previas · 280", "f82bcff / 16-sep · 1,619", "f82bcff / 17-sep · 1,965"]}
        series={[{name:"Ventanas con cobertura ≥98%",data:[100*58/280,100*1452/1619,100*1719/1965],tone:"info"}]}
        yMin={0} yMax={100} height={240} showValues valueSuffix="%" />
      <Text tone="secondary">Fuente: outcomes en ambos snapshots. Se excluyen las 2,792 filas antiguas sin versión. Retención actual de velas 1m: 8.86 días. Ninguna señal sigue abierta fuera de 12h ni outcome fuera de 24h.</Text>
      <Callout tone="warning" title="Dos limitaciones siguen afectando a la evaluación">
        79 de las 278 ventanas maduras iniciadas el 16-sep tienen cobertura inferior al 98%. Además, 912 de 2,441 avisos (37.4%) carecen de signal_id: hay que distinguir avisos de estado de entradas operables y enlazar estas últimas con su resultado.
      </Callout>
      <Text>La reconstrucción independiente revisó 1,191 recorridos: 1,044 tienen todas las velas. Dentro de la muestra principal, 1,021 de 1,023 están completos y los 195 casos positivos se confirman antes de cualquier hueco. Ninguna etiqueta principal cambia.</Text>
      <Text>49 recorridos incompletos comparten su primer hueco el 17-sep a las 06:22 UTC. Otros 23 tienen ahora todas las velas, pero el tracker aún los marca con baja cobertura. Hay que reconciliar precios y resultados conservando la evidencia original.</Text>
    </Stack>
    <Stack gap={10}>
      <H2>El seguimiento de rupturas ya recolecta; aún no puede evaluarse a varias horas</H2>
      <Text>La consulta de ejecución de las 19:37 UTC contiene 56 eventos: 25 alcistas y 31 bajistas, con un máximo de 26.1 minutos de antigüedad. Hay 39 retornos de 5m y 19 de 15m; ninguno de 30m o más, y ninguno cerrado.</Text>
      <Text>El tracker registra extremos y MFE/MAE direccionales. Su tabla todavía no vincula un TP/SL estructural ni calcula TP-before-SL; tampoco ofrece horizontes propios de 2h, 6h y 8h. Debe conectarse con la evaluación de planes antes de atribuirle una probabilidad de ganar.</Text>
      <Callout tone="info" title="Los cambios de hoy aún no tienen una muestra madura">
        La nueva configuración fc1c5ef3ce25 aporta dos recorridos en la extracción, ambos sin completar 24h. Los resultados anteriores no permiten juzgar esas modificaciones.
      </Callout>
    </Stack>
    <Divider />
    <Stack gap={10}>
      <H2>Qué priorizar con esta evidencia</H2>
      <Table headers={["Orden", "Acción", "Qué permite comprobar"]} rows={[
        [1,"Investigar huecos y reconciliar resultados con versión del cálculo","Que un stop o una meta no se pierdan por minutos ausentes."],
        [2,"Definir planes coherentes con +3.2%, costes y riesgo","Que acertar el plan cumpla el objetivo del usuario."],
        [3,"Enlazar detección operable → plan → outcome","Medir cada perfil sin duplicar motores de TP/SL."],
        [4,"Validar por perfil y régimen en datos posteriores","Si mejora el resultado neto y el riesgo, además de los toques."],
      ]} />
    </Stack>
    <details>
      <summary style={{cursor:"pointer",color:theme.text.link}}>Método, límites y evidencia reproducible</summary>
      <Stack gap={10} style={{paddingTop:12}}>
        <Text>Extracción SQLite en una transacción de solo lectura. Muestra principal: strategy_version f82bcff, sin sombra, ventanas maduras de 24h, cobertura registrada ≥98% y cinco tiempos de cruce/extremos válidos. Se excluyen 168 recorridos emitidos maduros por cobertura. Los inmaduros no se consideran fracasos.</Text>
        <Text>signals.result_pct corresponde al plan que vence a 12h; outcomes observa excursiones a 24h. El coste de 0.50 puntos es un escenario, no comisiones o fills medidos. El promedio por señal no es rentabilidad de cartera. Un empate de barreras en una vela no demuestra cuál ocurrió primero.</Text>
        <Text>Bootstrap descriptivo: 3,000 repeticiones por símbolo; no elimina la dependencia de mercado entre pares. Cambian regímenes, configuraciones y composición. El código del servidor tiene cambios sin commit; no se atribuye causalidad a una versión.</Text>
        <Text>Fuentes: audit/2026-09-17/data-review/snapshot.json.gz, results.json, comparison.json, path-check.json, verification.json y runtime.json. Scripts: export_readonly.py, analyze.py, verify_paths.py, verify_and_compare.py y build_artifacts.py. Consulta de producción en solo lectura; esta revisión no desplegó cambios.</Text>
      </Stack>
    </details>
  </Stack>;
}
'''.replace('__DATA__', json.dumps(data, ensure_ascii=False, separators=(',', ':')))
canvas_path = Path('C:/Users/felix/.cursor/projects/1776288848687/canvases/evolucion-senales-17-septiembre.canvas.tsx')
assert canvas_path.parent.is_dir()
canvas_path.write_text(canvas, encoding='utf-8')
print(P / 'ANALISIS.md')
print(canvas_path)
