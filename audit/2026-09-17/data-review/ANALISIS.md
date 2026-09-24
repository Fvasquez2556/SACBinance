# ¿Mejoraron los datos y las señales?

**La medición ha mejorado respecto al histórico antiguo y hay un pequeño repunte en los resultados acumulados. Todavía no se demuestra una mejora rentable de las señales.** Además, aparecieron nuevos huecos de velas que impiden considerar resuelta la calidad de datos.

Corte principal: **17 de septiembre de 2026, 13:36 Guatemala / 19:36 UTC**. Extracción de solo lectura de `sacbinance.db`: **5,363 recorridos, 3,845 planes y 2,441 avisos**. Respecto al corte del 16-sep se añadieron 346 recorridos, 229 planes y 295 avisos. No se modificó producción.

## Qué cambió desde el corte anterior

La muestra comparable pasó de **903 a 1,023 señales emitidas**, con 24 horas completadas, cobertura registrada ≥98% y tiempos válidos. Hay 234 símbolos. Las entradas incluidas van del 11-sep 23:04 al 16-sep 18:48 UTC.

- +3.2% antes del SL en 24h: **18.4% → 19.1%**.
- Resultado medio bruto registrado del plan: **-0.265% → -0.230%**.
- Cierres registrados de al menos +3.2% bruto: **5.5% → 6.1%**.

Son cortes acumulados que comparten 903 señales, no muestras independientes ni una prueba del efecto de una corrección. Ninguna de las señales incluidas antes salió de la muestra o cambió su etiqueta principal.

Las **120 señales recién incorporadas a la muestra evaluable** tuvieron 29 casos de +3.2% antes del SL (**24.2%**) y un promedio bruto de **+0.029%**. Al restar un coste hipotético uniforme de 0.50 puntos porcentuales, el promedio queda en **-0.471%**. Este pequeño repunte no basta para confirmar rentabilidad. Otras 49 señales emitidas que maduraron desde el corte anterior no superaron el filtro de cobertura; la disponibilidad de datos puede sesgar esta comparación.

## Tres resultados que no deben confundirse

En las mismas **1,023 señales**:

- **307 (30.0%)** tocaron +3.2% en algún momento dentro de 24h.
- **112** lo hicieron después de tocar el SL: no son éxitos de entrada con ese stop.
- **195 (19.1%)** alcanzaron +3.2% antes del SL observado. Entre ellas, **82** ya habían tocado primero un TP del plan menor: seguir el plan habría supuesto salir antes.
- Solo **62 (6.1%)** registraron un cierre del plan de al menos +3.2% bruto en `signals`.

El promedio de cierre de todos esos planes es **-0.230% bruto**, o **-0.730%** al descontar el escenario de 0.50 puntos. Son resultados del seguimiento/simulación; no fills acreditados en Binance ni rentabilidad de una cartera. Las señales se solapan y repiten pares.

## No hay una mejora estadística concluyente

Con periodos sin solaparse, las entradas anteriores al 14-sep UTC (n=413) obtienen **17.2%** de +3.2% antes del SL. Las posteriores, ya maduras (n=610), obtienen **20.3%**. La diferencia de **+3.1 puntos** tiene un intervalo bootstrap del 95% por símbolo de **-2.2 a +8.1 puntos**: los datos son compatibles tanto con una caída como con una mejora.

El resultado bruto medio empeora entre esos periodos: **-0.071% → -0.338%**. Además cambia el régimen BTC y la mezcla de volatilidad; no se puede atribuir el movimiento al código.

La configuración `7ebc818e36e9` aporta 695 señales: 20.0% de +3.2% antes del SL y −0.109% bruto medio. La posterior `3dff943e60b0` aporta 328: 17.1% y −0.488%. La configuración más nueva, `fc1c5ef3ce25`, tiene solo **2 recorridos** en la extracción, ninguno maduro. **Las modificaciones del 17-sep todavía no pueden evaluarse con estos resultados.** La revisión de UI no demuestra por sí misma una mejora del motor.

## El TP sigue sin ajustarse al objetivo y falta muestra por perfil

**703/1023 planes (68.7%) ofrecen un TP inferior a +3.2% bruto.** La mediana es +2.383%. El sistema puede acertar su propio TP y aun así no cumplir la meta del usuario. Antes de optimizar entradas, hace falta una política de salida coherente con esa meta y declarar si el 3.2% es antes o después de costes.

Las frecuencias de alcanzar +3.2% antes del SL son **9.8% a 4h**, **13.9% a 6h** y **15.2% a 8h**. Son estadísticas históricas de la muestra; no una probabilidad calibrada para la próxima señal.

Los grupos muy tranquilos, tranquilos, movidos y muy volátiles obtienen respectivamente **11.0%, 17.4%, 25.4% y 33.0%** de +3.2% antes del SL en 24h. Sin embargo, el grupo muy volátil tiene el peor resultado bruto medio: **−0.504%**. Más recorrido favorable no significa mejor resultado con las salidas actuales.

En la taxonomía principal hay **946 NEUTRAL, 62 TENDENCIA y solo 2 BASE_POST_CAIDA**. Esto no permite comparar de manera representativa el rebote tras capitulación con la subida sostenida que se quiere detectar. En una prueba con umbral de rango fijado usando únicamente datos anteriores, el grupo seleccionado llega más veces a +3.2% (28.7% frente a 14.6%), pero tiene peor promedio bruto (−0.486% frente a −0.238%). El rango detecta movimiento; por sí solo no demuestra rentabilidad.

## Calidad de datos: progreso real, con una regresión reciente

En versiones antiguas identificadas, 58/280 recorridos maduros superaban el 98% de cobertura registrada (**20.7%**). En `f82bcff` son **1,719/1,965 (87.5%)**, incluyendo recorridos en sombra. Esto mejora mucho el histórico, pero baja desde el **89.7% del corte anterior**.

En las ventanas que comenzaron el 16-sep, **79 de 278 maduras** tienen cobertura <98%. De los 1,191 recorridos emitidos reconstruidos con velas de 1m, 147 tienen algún hueco: 92 comparten el primer hueco del **14-sep 20:28 UTC**, 49 el del **17-sep 06:22 UTC** y 6 el del 12-sep 05:08 UTC. Esta coincidencia justifica investigar interrupciones del colector; no identifica por sí sola su causa.

La reconstrucción independiente valida los **195 casos positivos antes de cualquier primer hueco** y no cambia ninguna de las 1,023 etiquetas principales. 1,021 de esas 1,023 ventanas tienen ahora todas las velas esperadas. Otros **23 recorridos** excluidos por cobertura del tracker sí tienen ahora todas las velas: reparar precios no recalcula automáticamente el resultado guardado.

La retención de 1m creció de 7.81 a **8.86 días**. No hay señales abiertas más allá de 12h ni outcomes pendientes más allá de 24h. Todas las señales tienen outcome y todos los outcomes emitidos enlazan a una señal. En los recorridos actuales hay versión, configuración, volatilidad, drawdown, ATR y volumen; faltan RSI/MACD de 15m en 53 de 2,291 filas.

Persisten **912/2441 avisos (37.4%) sin `signal_id`**, frente a 39.4% en el corte anterior. No son necesariamente operaciones perdidas: pueden ser avisos de estado o actualizaciones. Para evaluar toda la experiencia de la UI hay que distinguir esos avisos de una entrada operable y enlazar esta última con su resultado. No se encontraron niveles de entrada/TP/SL divergentes en los avisos que sí están enlazados.

## El nuevo seguimiento de rupturas está funcionando, pero aún es inmaduro

La consulta de ejecución de las 19:37 UTC encuentra la tabla `rupturas` y el servicio activo desde las 19:09:16 UTC. Hay **56 eventos: 25 alcistas y 31 bajistas**, con una antigüedad máxima de **26.1 minutos**. Existen retornos de 5m en 39 y de 15m en 19; todavía ninguno de 30m, 1h, 4h o 24h, y ninguno cerrado.

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
