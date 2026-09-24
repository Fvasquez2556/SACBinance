# ¿Han mejorado los datos y las señales?

**La medición mejoró; no hay evidencia de una mejora de rentabilidad.** La última configuración observada tiene resultados peores que la anterior, aunque comparar periodos de mercado distintos no permite atribuir esa diferencia al código.

Corte: **16 de septiembre de 2026, 12:22 Guatemala / 18:22 UTC**. Fuente: extracción consistente de solo lectura de `sacbinance.db` en el servidor. Se consultaron 5,017 recorridos, 3,616 planes y 2,146 registros de avisos. No se modificó producción.

## Lo que sí mejoró

La proporción de recorridos maduros con cobertura registrada de al menos 98% pasó de **58/280 (20.7%)** en las versiones identificadas previas a `f82bcff`, a **1,452/1,619 (89.7%)** en `f82bcff`. Son todos los recorridos, incluidos los medidos en sombra; las 2,792 filas sin versión se mantienen fuera de esa comparación. La cobertura mediana actual es **99.79%**.

En la configuración que comenzó a emitir tras el arranque del 14-sep 20:28 UTC, **369/369 recorridos maduros** superan el 98% de cobertura. Esto no significa que todos tengan el 100% de minutos observados.

El histórico de velas de un minuto abarca **7.81 días**, frente a la retención de unos tres días documentada en la revisión del 11-sep. Actualmente hay 2,420,140 velas de un minuto y 3,395,458 velas entre todas las temporalidades.

No hay señales `OPEN` con más de 12 horas ni outcomes abiertos fuera de su ventana de 24 horas. Los 1,945 outcomes de `f82bcff` tienen versión, configuración, grupo de volatilidad, drawdown, ATR y volumen relativo registrados; 50 aún carecen de RSI/MACD de 15m. Entre sus 1,619 recorridos maduros no hay tiempos inválidos en los cinco campos comprobados: primeros cruces de +3.2%, TP y SL y tiempos de MFE/MAE.

## Qué significa ahora alcanzar +3.2%

La muestra principal usa **903 señales emitidas**, sin registros en sombra, con 24 horas completadas, cobertura registrada ≥98% y tiempos válidos. Corresponden a 227 símbolos, del 11-sep 23:04 al 15-sep 17:46 UTC.

- **253/903 (28.0%)** tocaron +3.2% en algún momento de las 24 horas.
- **87** lo tocaron después del stop. No representan un éxito de entrada con ese SL.
- **166/903 (18.4%)** tocaron +3.2% antes del SL observado.
- Incluso entre estas 166, **75 ya habían alcanzado antes un TP del plan inferior a +3.2%**. No sería correcto atribuirles una salida de +3.2% siguiendo el plan original.
- **50/903 (5.5%)** registraron un cierre del plan de al menos +3.2% bruto en `signals`, incluidos vencimientos. Son resultados simulados/registrados, no transacciones acreditadas en Binance.

El resultado medio registrado de esos 903 planes es **−0.265% bruto**. Restar un coste hipotético uniforme de 0.50 puntos porcentuales por operación produce **−0.765% neto estimado**. Este coste es un escenario coherente con el descuento habitual guardado por el sistema, no una medición de comisiones o fills reales. El promedio no equivale a la rentabilidad de una cartera: hay señales simultáneas y repetidas del mismo par.

## ¿Mejoraron los resultados recientes?

Con las mismas reglas de inclusión, el periodo anterior al 14-sep UTC aporta **413** señales, y el periodo del 14-sep hasta el corte de madurez aporta **490**:

- +3.2% antes del SL: **17.2% → 19.4%**. La diferencia es de +2.2 puntos, con intervalo bootstrap por símbolo de aproximadamente **−3.3 a +7.6 puntos**. No demuestra una mejora clara.
- Resultado medio registrado: **−0.071% → −0.428% bruto**. Con el escenario de coste de 0.50 puntos: **−0.571% → −0.928%**.
- Cierres de al menos +3.2% bruto: **5.3% → 5.7%**.

Además, la composición cambió: el periodo anterior está enteramente etiquetado con régimen BTC bajista, mientras el reciente mezcla bajista, neutral y alcista. La cuota del grupo muy tranquilo también baja de 59.8% a 25.5%. No es una prueba A/B ni permite concluir que el código causó el cambio.

Separando por la configuración registrada al arrancar, la anterior (`7ebc818e36e9`, **695** señales) obtiene **20.0%** de +3.2% antes del SL y **−0.109% bruto medio**. La más reciente (`3dff943e60b0`, **208** señales) obtiene **13.0%** y **−0.786%**. La evidencia reciente no respalda decir que las señales mejoraron; todavía es un periodo corto y con mezcla de mercado distinta.

Los arreglos de UI publicados el 16-sep cambian la interpretación de los datos. No cambiaron el motor ni pueden recibir crédito por estos resultados, correspondientes a entradas anteriores.

## El objetivo y los perfiles siguen desalineados

**624/903 planes (69.1%) ofrecen un TP inferior a +3.2% bruto.** La mediana del TP es **+2.324%** y la del neto estimado que guarda el sistema es **+1.84%**. Si el objetivo del producto sigue siendo obtener al menos +3.2% por operación, la mayoría de estos planes no lo ofrece ni siquiera antes de costes.

La frecuencia observada de tocar +3.2% antes del stop, sobre las mismas 903 señales, es **9.6% dentro de 4h**, **13.7% dentro de 6h** y **14.8% dentro de 8h**. Se calcula con los primeros cruces almacenados, no con un nuevo modelo predictivo. No es una probabilidad calibrada de la próxima señal ni implica seguir el TP original si éste era menor.

Hay diferencias útiles por volatilidad: muy tranquilas **10.2%** (n=372), tranquilas **17.6%** (n=204), movidas **27.1%** (n=166) y muy volátiles **29.2%** (n=161), dentro de 24h. Pero las muy volátiles tienen el peor promedio bruto de los cuatro grupos: **−0.651%**, frente a **−0.116%** en movidas. Más aciertos no compensan necesariamente las pérdidas más amplias.

La etiqueta `TENDENCIA` dispone de solo **55** señales en la muestra principal; `BASE_POST_CAIDA` de **1**. La taxonomía no captura todos los avisos emitidos por cada detector. No hay muestra representativa suficiente para comparar de forma fiable los dos perfiles que se quieren operar.

## La clasificación por rango todavía no resuelve la rentabilidad

Se fijó un umbral con el percentil 80 del rango de una hora de las **413 señales anteriores al 14-sep**: **1.548%**. Se aplicó ese umbral sin reajustarlo a las **490 posteriores**; selecciona 205 porque la distribución de volatilidad cambió. Es una prueba de umbral fijo, distinta del ranking transversal de la UI.

Las seleccionadas alcanzan +3.2% antes del SL el **25.9%**, frente al **14.7%** del resto. Sin embargo, su promedio bruto registrado es **−0.637%**, frente a **−0.278%** del resto. El ranking identifica más movimiento, pero no demuestra mejores resultados económicos con estos planes. No se reentrenó ni se optimizó una regla usando este tramo posterior.

Esto limita la recomendación del informe de comparación del 14-sep: aquella prueba más pequeña encontró un ranking prometedor, pero no estableció rentabilidad positiva. Su aproximación de vencimiento plano y barreras a 24h tampoco es idéntica al resultado registrado por `signals`, que vence a 12h. Aquí se prioriza ese resultado registrado para describir el plan actual.

## Lo que sigue fallando o requiere seguimiento

**846/2,146 registros de avisos (39.4%) no tienen `signal_id`.** No significa que se perdieran 846 transacciones; significa que esos avisos no están enlazados al plan medido. Entre los que sí tienen identificador no hay huérfanos ni diferencias de entrada/TP/SL respecto a `signals`. Todas las señales tienen outcome y todos los outcomes emitidos tienen señal.

La cobertura no es uniforme: **128/561 recorridos abiertos el 14-sep** terminaron con cobertura <98%. El día 15, las **313 ventanas ya maduras** sí superan ese umbral. Persisten 98 recorridos emitidos de la versión actual sin ventana bruta de 1m completa entre los 1,022 comprobados. La existencia de huecos está confirmada; no se atribuye aquí una causa sin investigar el pipeline.

La reconstrucción encontró **22 recorridos** que el tracker marca con cobertura <98%, aunque ahora conservan todas sus velas de un minuto. También hubo diferencias en algunos primeros tiempos de cruce. Reparar velas no garantiza que los outcomes guardados se recalculen: hace falta una reconciliación explícita y versionada, conservando la evidencia original.

En los vetos, la caída que sigue acelerando tiene **10.4%** de +3.2% antes del SL (n=163), frente a **18.4%** de las emitidas. El veto de precio bajo EMA7 conserva **38.1%** (n=42), y el macro **21.1%** (n=313). Son grupos seleccionados y no comparables como experimento; estas diferencias justifican seguir midiendo el veto de EMA7, no retirarlo automáticamente ni prometer ganancias al hacerlo.

## Prioridad recomendada

1. Enlazar cada aviso operable y cada detector de perfil con un plan y su outcome; conservar por separado recordatorios o actualizaciones.
2. Resolver la contradicción entre la meta de +3.2% y los TP ofrecidos. Definir explícitamente si la meta es bruta o neta antes de cambiar la política; no ampliar stops solo para aumentar el porcentaje de aciertos.
3. Reconciliar huecos y outcomes contra velas conservadas, e identificar qué provocó las ventanas incompletas del día 14.
4. Validar las siguientes propuestas con periodos posteriores completos, por perfil y régimen, utilizando resultado neto estimado y riesgo además de frecuencia de aciertos.

## Evidencia y límites

La extracción `snapshot.json.gz` proviene de una única transacción SQLite en modo solo lectura. `export_readonly.py` contiene las consultas. `analyze.py` reproduce los cálculos y guarda `results.json`.

Una comprobación independiente de 1,022 recorridos contra `klines` encontró 924 ventanas completas. De las **903** señales del análisis, **902** tienen ahora todas las velas esperadas; **las 166 positivas están confirmadas antes de cualquier primer hueco**. Ninguna de las 903 cambia de clasificación de +3.2% antes del SL. Los resultados están en `path-check.json` y `verification.json`; la consulta está en `verify_paths.py`.

Las ventanas se delimitan por timestamps reales, usando velas de un minuto enteramente posteriores a la entrada y dentro de 24h. Un empate de TP/SL en una vela no prueba su orden. Las tasas de toque a distintos horizontes se refieren al timestamp de apertura de la vela que contiene el toque, con resolución de un minuto.

La muestra de rendimiento excluye 119 recorridos emitidos maduros de `f82bcff` que no alcanzan 98% de cobertura registrada. El análisis de sensibilidad con umbrales de cobertura 95%, 98%, 99% y 99.5% mantiene el promedio registrado negativo. Esto reduce, pero no elimina, el sesgo de selección por disponibilidad de datos.

El bootstrap agrupa por símbolo para no tratar todas sus señales como independientes. No corrige por sí solo la dependencia común de mercado entre pares ni convierte el antes/después en un efecto causal. El código desplegado contiene modificaciones sin commit; `strategy_version` por sí solo no identifica todo el estado ejecutado. La configuración y el arranque se consideran por separado.
