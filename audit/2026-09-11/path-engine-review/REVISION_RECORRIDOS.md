# Revisión del análisis de recorridos futuros de SACBinance

**Dictamen: existe una implementación parcial importante, pero todavía no un motor integrado que responda las dos preguntas solicitadas.** El sistema combina detectores de patrones, seguimiento posterior de señales, una probabilidad estática para el tablero y herramientas experimentales de triple barrera. No se limita a señales instantáneas. Faltan la unión de esas piezas, resultados completos por horizonte y probabilidades separadas por comportamiento y volatilidad.

Esta es una revisión previa al cambio de UI. Se inspeccionaron código, tablas y resultados; se ejecutaron reproducciones sintéticas locales. No se modificaron el servicio, sus reglas, la base de producción ni la UI.

**Fuentes y versiones.** Código local `10f990a`; servidor `25d03fa82c147a1c28786c6fd9fb236863557a21`. Servicio con PID 390990, iniciado el 11 de septiembre de 2026 a las 06:06:20 UTC. El servidor tiene una modificación en `frontend/package-lock.json`. Tras la pausa por el límite de uso se tomó una segunda copia para actualizar los datos; se conserva también la primera. La copia consistente más reciente de SQLite terminó el **11 de septiembre de 2026 a las 21:33:30 UTC / 15:33:30 Guatemala**, tiene esquema **v11**, 161.566.720 bytes e `integrity_check=ok`. El código local contempla v12 y cambios que aún no estaban desplegados al comprobarlo. Las referencias de código siguientes apuntan al árbol local, salvo indicación expresa; el archivo de producción permite comparar exactamente ambas versiones.

Evidencia: [procedencia](D:/SACBinance/audit/2026-09-11/path-engine-review/refresh/provenance.json), [resultados SQL](D:/SACBinance/audit/2026-09-11/path-engine-review/refresh/inspection.json), [consultas](D:/SACBinance/audit/2026-09-11/path-engine-review/refresh/queries.json), [reproducciones](D:/SACBinance/audit/2026-09-11/path-engine-review/labeling_checks.json). SHA-256 de la copia: `392a155c6c00daa210faf459a2b2729f83c5663a4be0710c355ae6ae3ea6a7d6`.

## Qué existe y dónde

**1. Caída rápida, mínimo local y rebote: sí, como detección parcial.**

- [retroceso.py](D:/SACBinance/backend/src/analysis/retroceso.py:37): modelo `Retroceso`, función `detectar_retroceso()`. Busca un pico en 40 velas anteriores a una zona de 8 velas de 1 minuto, mide caída hasta el suelo de esa zona y recuperación desde él. Los valores por defecto exigen caída de 2% y rebote de 1% para confirmar. Devuelve `pico_previo`, `suelo`, `caida_pct`, `rebote_pct`, `minutos_desde_suelo`, `detectado` y `confirmado`. Es un mínimo observado, no una garantía de que haya terminado la caída.
- [base_rebote.py](D:/SACBinance/backend/src/analysis/base_rebote.py:44): modelo `BaseRebote`, función `detectar_base_rebote()`. Busca caída, base y ruptura; mide `base_piso`, `base_techo`, duración y amplitud de base, `vol_dryup`, volumen de ruptura y distancia sobre el techo. Ya cubre parte de la estabilización que pides.
- [symbol_state.py](D:/SACBinance/backend/src/state/symbol_state.py:36) y [adaptive.py](D:/SACBinance/backend/src/state/adaptive.py:30): `Metrics`, `SymbolState` y `AdaptiveStats` aportan drawdown, retorno, velocidad, sigma y movimientos normalizados `z_drop`/`z_rise`. La máquina de estados distingue caída, suelo y subida.

**Límite:** no hay un episodio persistente de capitulación con tiempos de pico, mínimo y confirmación, asociado a un régimen y a una entrada evaluada por siete horizontes. `minutos_desde_suelo` cuenta posiciones de velas; con huecos no representa minutos reales. `BaseRebote.caida_velas` es la longitud del segmento previo a la base, no el tiempo exacto entre el swing high y el swing low. La ruptura usa el máximo de la última vela: conviene conservar si fue toque o cierre por encima al definir la confirmación.

**2. Movimiento sostenido durante horas: sí, hay un detector específico.**

- [momentum_profile.py](D:/SACBinance/backend/src/analysis/momentum_profile.py:40): `GrindResult` y `evaluar_grind()` evalúan por defecto 16 velas de 15m, equivalentes a 4 horas nominales. Miden pendiente porcentual por hora, R², retroceso máximo, proporción de cierres sobre EMA25, velas verdes y estabilidad del volumen. Consideran tendencia de 1h, 4h y 1d. Este es el punto natural para tu oportunidad de subida gradual.
- En el mismo módulo, `IgnitionResult` y `evaluar_ignicion()` detectan aceleración explosiva. Ignición no equivale necesariamente a rebote después de una capitulación.
- [taxonomy.py](D:/SACBinance/backend/src/analysis/taxonomy.py:73): `TaxonomyResult` y `clasificar()` combinan estados como `TENDENCIA`, `IGNICION`, `COMPRIMIDA` y `BASE_POST_CAIDA`. Clasifican estructura/patrón; no son por sí solos una clasificación de volatilidad.
- [engine.py](D:/SACBinance/backend/src/state/engine.py:893) emite `alert_tendencia`, `alert_ignicion` y `alert_base_rebote` por una rama independiente del tier clásico.

**Límite:** esa rama emite eventos y logs, pero no abre por sí misma un plan y un outcome para cada detección. Una detección puede coincidir con la rama clásica y tener seguimiento; no existe cobertura sistemática de todas las oportunidades de perfil. En la copia hay 2.589 logs `TENDENCIA`, 1.839 `BASE` y 158 `IGNICION`; son avisos repetibles, no operaciones independientes. Hay 176 outcomes con taxonomía `TENDENCIA`, lo que confirma seguimiento parcial, sin permitir vincular uno a uno todos los avisos.

**3. Indicadores, volatilidad y niveles: gran parte del cálculo ya existe.**

- [calculator.py](D:/SACBinance/backend/src/indicators/calculator.py:24): `IndSnap`, `compute_indicators()` e `indicators_from_candles()` calculan EMA7/25/99, RSI5/14, MACD, Bollinger, ATR y volumen relativo.
- [ma_slopes.py](D:/SACBinance/backend/src/analysis/ma_slopes.py:54): `analizar_tf()` y `tendencia_timeframe()`; [impulse.py](D:/SACBinance/backend/src/analysis/impulse.py:215): `TFImpulse`, `ImpulseResult`, `medir_impulso()`. Reutilizables para tendencia, momentum multitemporal y agotamiento.
- [consolidation.py](D:/SACBinance/backend/src/analysis/consolidation.py:29): `ConsolidationResult`, `detectar_consolidacion()`; [compression.py](D:/SACBinance/backend/src/analysis/compression.py:142): `CompressionResult`, `detectar_compresion()`. Cubren percentil de ATR, convergencia y contracciones. La expansión puede caracterizarse con estas medidas y el impulso, pero no se guarda un régimen conjunto por episodio.
- [levels.py](D:/SACBinance/backend/src/analysis/levels.py:90): `Nivel`, `NivelesResult`, `detectar_niveles()` calculan soportes/resistencias y sus distancias.
- [trade_levels.py](D:/SACBinance/backend/src/analysis/trade_levels.py:107): `TradeLevels`, `calcular_niveles()` propone SL desde soporte o swing low de 15m con margen ATR; aplica riesgo mínimo ligado a ATR/ruido y riesgo máximo. Calcula TP mediante R:R y marca resistencia intermedia. Adapta el riesgo al activo, pero comparte la política general entre perfiles; no consulta una probabilidad condicionada para elegir el plan.

La distancia a medias puede derivarse de precio y EMA en el snapshot; no hay columnas históricas explícitas para todas esas distancias. Parte de los indicadores superiores y del detector grind usa velas en formación. Un replay debe reproducir la información disponible entonces, sin sustituirla por el cierre definitivo de esa vela superior.

**4. Recorrido posterior, MFE/MAE y primer TP/SL: sí, en producción.**

[outcome_tracker.py](D:/SACBinance/backend/src/analysis/outcome_tracker.py:152), clase `OutcomeTracker`: `abrir()`, `abrir_sombra()`, `cargar()`, `backfill()` y `on_candle()`. El engine alimenta el tracker con las velas cerradas de 1 minuto, incluso después del cierre de una señal. La ventana por defecto es **24h**.

La tabla **`outcomes`** guarda:

- Entrada y TP/SL propuestos; estado, tier, score, macro y taxonomía al abrir.
- `mfe_pct`, `mae_pct`, `ms_mfe`, `ms_mae`: extremos del recorrido completo observado durante la ventana.
- Primeros cruces `ms_up_*`/`ms_dn_*` para 1%, 1,2%, 2%, 3,2%, 4,2%, 5% y 10%. No hay escalón exacto de 4%.
- `ms_tp` y `ms_sl` para las barreras del plan; `dip_antes_obj` y `forma` para describir el camino hasta/tras el objetivo.
- Contexto parcial de indicadores mediante `_contexto()`, más versión/configuración y cobertura en las cohortes recientes.

**Se puede derivar** si el +3,2% ocurrió antes del SL comparando `ms_up_32` con `ms_sl`, y si el cruce observado ocurrió antes de un horizonte. Hace falta validar cobertura, madurez y ambigüedad. **No se puede recuperar el MFE/MAE de 4h, 6h u 8h a partir del máximo/mínimo agregado de 24h.** Para ello hacen falta las velas o acumulados guardados en cada frontera.

Los tiempos de cruce se atribuyen al comienzo de la vela que contiene el cruce, no al instante exacto de ejecución. Un máximo y un mínimo en la misma vela no revelan cuál ocurrió primero. El `dip_antes_obj` también puede incluir un mínimo de esa vela posterior al toque del TP.

[hoyo.py](D:/SACBinance/backend/src/analysis/hoyo.py:123), `inicial()`, `actualizar()`, `resultado()`, ya simula otra entrada cerca del SL y conserva fill hipotético, MFE/MAE y desenlaces de reglas A/C2/C3 en columnas `hoyo_*`. Es reutilizable para evaluar entradas alternativas; no sustituye la medición multihorizonte ni acredita una ejecución real en Binance.

**5. Probabilidad visible en el tablero: existe, pero responde otra pregunta.**

[retroceso.py](D:/SACBinance/backend/src/analysis/retroceso.py:207), `prob_llegar_meta(dist_pct, edad_min)`, consulta una tabla histórica incorporada al código. [active_alert.py](D:/SACBinance/backend/src/state/active_alert.py:569) la usa para `prob_meta` y `prob_meta_n`.

Su fuente, [research/tabla_meta.py](D:/SACBinance/research/tabla_meta.py:32), mide **tocar la meta original en las siguientes 6h**, condicionado a distancia actual y edad de la alerta. Muestrea cada 5 minutos la vida de señales. No comprueba primero el SL, no separa perfil ni volatilidad y sus muestras repetidas no son operaciones independientes. Además, la tabla se ajusta a monotonía por distancia y puede usar otra banda de edad si falta muestra.

Por tanto, `prob_meta` **no representa** «probabilidad de ganar al menos 3,2% antes del SL desde una nueva entrada». La meta se ancla a la entrada original; desde el precio actual el rendimiento restante puede ser distinto. Su presencia impide afirmar que no existe ninguna probabilidad, pero no satisface el objetivo nuevo.

**6. Motor experimental muy cercano a lo solicitado: sí, fuera del flujo de producción.**

- [research/labeling.py](D:/SACBinance/research/labeling.py:243): `Serie`, `cargar()`, `calcular_features()`, `eventos_cusum()`, `triple_barrera()` y `etiquetar()`. Evalúa TP, SL o expiración; marca empate intravela; guarda MFE/MAE y variables de volatilidad relativa, volumen, retorno, posición diaria y BTC. Tiene modo fijo +3,2%/−2% y modo proporcional al ATR, con horizonte configurable, por defecto 8h.
- [research/frequencies.py](D:/SACBinance/research/frequencies.py:139): `Consulta`, `TablaFrecuencias.entrenar()` y `.consultar()`. Estima frecuencias condicionales, tasa base, lift, retorno y excursiones. Incluye `split_purgado()` y `brier_descompuesto()`: bases útiles de validación temporal y calibración.
- [research/marea_tranquila.py](D:/SACBinance/research/marea_tranquila.py:102): `futuro()` estudia +3,2% antes de −1,2% en 60/180/360 minutos nominales. Su patrón lateral no equivale al grind alcista que pides.

No se encontraron llamadas del backend a `TablaFrecuencias` ni a `triple_barrera`. El etiquetador espera `research/data/history.db` con columnas `interval/open/high/low/close/quote_volume`; producción usa `tf/o/h/l/c/v`. No está presente ese directorio de datos en el servidor ni esa base en las rutas locales inspeccionadas. No existe tabla **`labels`** en la copia de producción ni en las tres bases locales inspeccionadas. Esto prueba ausencia en esas fuentes, no que el experimento nunca se haya ejecutado en otro equipo.

**7. Grupos de volatilidad: añadidos localmente, todavía ausentes del servidor.**

[backend/src/analysis/grupos.py](D:/SACBinance/backend/src/analysis/grupos.py:72), `volatilidad_previa()`, `grupo()`, `objetivo_de()`, `campos()`, usa el rango medio porcentual de las últimas 60 velas de 1m, con mínimo de 30. Separa `MUY_TRANQUILA`, `TRANQUILA`, `MOVIDA` y `MUY_VOLATIL`; cortes 0,068%, 0,106% y 0,165%. La medición es previa al evento, aunque falta garantizar continuidad temporal de esas velas.

La v12 local añade `vol_previa_pct`, `grupo_vol`, `objetivo_grupo_pct`, `ms_objetivo_grupo` a `outcomes`. Es medición en sombra, sin decidir alertas. **Sus objetivos experimentales, 1,23%, 1,38%, 1,81% y 2,49%, están todos por debajo de tu objetivo de +3,2%.** Pueden servir como comparación, pero no deben convertirse en el objetivo principal de esta integración.

El régimen BTC de `StateEngine._btc_regime()` es dirección macro del mercado, una dimensión distinta de volatilidad del activo. Y [research/grupos.py](D:/SACBinance/research/grupos.py:54) clasifica por resultados futuros MFE/MAE: es una segmentación posterior, inapropiada como predictor al entrar. Son conceptos distintos pese al nombre compartido.

## Tablas y persistencia: qué puede responder hoy

- **`signals`**: 2.433 planes/señales; estado TP/SL/expiración, con ventana de expiración por defecto de 12h. `signal_tracker.abrir_senal()` y `evaluar_senales()`. No contiene un resultado independiente por horizonte ni prueba de fill de una orden real.
- **`outcomes`**: 3.062 recorridos, incluidos registros en sombra. Seguimiento nominal de 24h. Conserva indicadores seleccionados, no el snapshot completo ni los siete horizontes.
- **`klines`**: 1.294.805 velas en varios TF; 847.566 de 1m para 266 símbolos. Fuente para reconstruir caminos donde existe cobertura suficiente.
- **`symbol_states`**: 65.593 estados; guarda estado, FSM, score, tier, macro y precio. No es un histórico completo de features.
- **`analysis_log`** y **`alertas_emitidas`**: registros de diagnóstico/avisos; no reemplazan un episodio con entrada y resultados enlazados.
- **`labels`**: esquema experimental definido en `research/labeling.py`, ausente de las bases inspeccionadas.

`Database.get_historial()` en [db.py](D:/SACBinance/backend/src/persistence/db.py:788) ya compara TP/SL y expone `llego_meta` por separado. `llego_meta` solo significa que se tocó +3,2%; puede ocurrir después del SL. [routes.py](D:/SACBinance/backend/src/api/routes.py:97) sirve ese historial; no existe un endpoint dedicado a probabilidades por perfil/régimen/horizonte.

## Hallazgos que impiden usarlo como el motor solicitado

**Prioridad alta — faltan resultados por horizonte y captura sistemática de candidatos.** No hay filas independientes para 15m, 30m, 1h, 2h, 4h, 6h y 8h. Las alertas de perfil no generan sistemáticamente seguimiento propio. Entrenar solo con señales que pasan el filtro clásico introduce una población diferente de «todos los activos que caen y estabilizan» o «todos los grind moderados».

**Prioridad alta — el etiquetador sobrescribe horizontes/políticas.** La PK de `labels` es `(symbol, interval, t0)` y `etiquetar()` usa `INSERT OR REPLACE`. La prueba de guardar 240 y luego 480 velas conserva solo 480. Tampoco distingue la misma entrada con SL estructural frente a SL fijo o ATR. Hay que corregir la identidad antes de producir el nuevo dataset.

**Prioridad alta — filtración de futuro en el calentamiento de features experimentales.** `calcular_features()` rellena el inicio con la media de las primeras 500 observaciones ATR y hasta 200 de volumen; puede usar observaciones posteriores al evento. En una serie sintética de 5.000 puntos, dejando intacto el pasado hasta el índice 100, cambiar solo el futuro convirtió `f_atr_rel[100]` de 1 a 0,2941 y `f_vol_rel[100]` de 1 a 0,5. El filtro de calentamiento de eventos permite índices mayores que 60 en 1m, por lo que no elimina toda la zona afectada. Las ventanas dependen además del largo total de la serie. Se necesitan ventanas causales estables y pruebas de invariancia del prefijo.

**Prioridad alta — datos faltantes y cohortes históricas incompatibles.** De 3.062 outcomes, 2.792 no tienen versión de estrategia; solo 948 tienen drawdown/ATR/volumen relativo y 248 MACD de 15m. Los 270 con versión están todavía abiertos en esta copia: no validan resultados completos de 24h de la versión reciente. Hay 104 filas cerradas con tiempo de MFE o MAE superior a 24h; pertenecen a registros históricos, no demuestran que el código local actual siga produciéndolas.

Para ventanas de 8h ya transcurridas desde `ts_open`, **ninguno de los 2.985 registros conserva todas las velas completas de 1m esperadas dentro de la ventana**; 1.720 no conservan ninguna. Para 6h tampoco hay ventanas íntegramente reconstruibles entre 3.012 registros maduros. El histórico de 1m solo abarca aproximadamente los últimos tres días y también tiene huecos internos. `Database.prune_klines()` aplica expresamente una retención de tres días a 1m/5m/15m; eso explica la pérdida de historia antigua, aunque no los huecos internos. La comprobación excluye fragmentos de vela en los bordes y cuenta timestamps únicos. Esto limita reconstrucción exacta: no demuestra que ningún trade haya funcionado. Un desenlace probado antes del primer hueco podría rescatarse, aunque su MFE/MAE del horizonte completo siguiera incompleto.

**Prioridad media — semánticas distintas de MFE/MAE y del tiempo.** El tracker online mide todo el recorrido de 24h; `triple_barrera()` mide hasta la vela de salida. La reproducción con SL primero y subida posterior da MFE de +1% hasta salida frente a +5% en la ventana completa. Ambas medidas son útiles, pero no deben mezclarse. El etiquetador usa cantidad de velas: dos velas con un hueco pueden cubrir 60 minutos y calificarse como un horizonte nominal de 2 minutos. Además, entrada al cierre y timestamp de apertura deben alinearse expresamente.

**Prioridad media — probabilidad de toque presentada como si fuera probabilidad operable.** `prob_meta` y `llego_meta` no exigen TP antes del SL. En los valores almacenados hay 1.301 registros que tocaron +3,2%, de los cuales 528 registran SL antes; es una diferencia descriptiva de esta copia mixta, no una tasa validada para operar. El nuevo modelo debe medir el evento correcto y publicar muestra/fecha/calibración. El umbral `n_min=200` de `TablaFrecuencias` cuenta filas, no tamaño efectivo de muestra independiente.

**Cambios locales frente al servidor.** El tracker local ya incorpora exclusión de velas que cierran fuera de ventana, idempotencia y cierre por reloj; el árbol desplegado no contiene esos últimos ajustes. Estos cambios mejoran la medición futura, pero no reparan automáticamente las filas históricas ni integran los siete horizontes. Esta revisión no vuelve a certificar toda la batería de correcciones de la auditoría anterior.

## Integración propuesta reutilizando la arquitectura

**A. Mantener dos perfiles y separar tres dimensiones.**

1. `REBOTE_POST_CAIDA`: reutilizar `detectar_retroceso()` y `detectar_base_rebote()`, con confirmación explícita de estabilización/recuperación. Medir rapidez y profundidad de caída y volatilidad previa; no usar el mínimo definitivo visto a posteriori como entrada histórica.
2. `TENDENCIA_SOSTENIDA`: reutilizar `evaluar_grind()`, slopes y macro multitemporal; distinguir pendiente persistente de aceleración explosiva. Evaluar prioritariamente 4/6/8h sin omitir las ventanas cortas.

En ambos, conservar por separado **perfil**, **régimen de volatilidad del activo** y **régimen de mercado/BTC**. Un rebote no es automáticamente de alta volatilidad y un grind no es automáticamente tranquilo. Reutilizar `grupos.volatilidad_previa()` como primera variable, añadiendo ATR relativo/percentil, compresión/expansión y controles de continuidad. Cortes y versión deben quedar fijados con datos de entrenamiento anteriores, sin recalcularlos usando el periodo de prueba.

**B. Congelar el contexto y el plan cuando se toma la decisión.**

Extender `SymbolState.snapshot()`/`OutcomeTracker._contexto()` y el punto de apertura del engine. Persistir: timestamps de decisión y última información disponible; perfil y sus scores; swing high/low y sus timestamps; caída %, duración real pico→mínimo, tiempo mínimo→confirmación; base y recuperación; volumen relativo; RSI/MACD/ATR con TF; distancias a EMA; compresión/expansión; pendientes multitemporales; soportes, resistencias y espacio hasta resistencia. Mantener los resultados futuros fuera de este contexto.

Guardar precio propuesto, tipo de entrada, condición de confirmación, precio/tiempo de fill si existe, SL estructural y su fundamento, TP, costes y versión de política. La entrada al cierre observado es una hipótesis de ejecución; una orden límite necesita fill o `NO_FILL`. Comparar entradas inmediata, confirmada y en retroceso como planes distintos del mismo episodio. No reubicar retrospectivamente el SL después de conocer el recorrido.

**C. Compartir un solo evaluador de recorridos.**

Extraer un núcleo puro propuesto `analysis/path_evaluator.py` de la lógica existente en `OutcomeTracker.on_candle()` y `triple_barrera()`. Usarlo tanto en streaming como en replay; `hoyo.py` aporta políticas alternativas de entrada y salida, evitando otro cálculo independiente de extremos y barreras. Conservar el tracker como orquestador de persistencia y recuperación.

El núcleo debe actualizar por timestamps reales, sin volver a procesar velas duplicadas, y acumular por horizonte **15/30/60/120/240/360/480 minutos**:

- MFE/MAE de la ventana completa, retorno al final, y tiempo/intervalo de cada extremo.
- MFE/MAE hasta salida, como medidas distintas.
- Primer toque de +3,2%, primer toque del TP ofrecido y primer toque del SL estructural. No confundir el TP del sistema con la meta fija.
- Resultado `TP_FIRST`, `SL_FIRST`, `NEITHER`, `AMBIGUOUS`, además del estado de datos `PENDING`, `COMPLETE`, `INCOMPLETE` o `NO_FILL`.
- Cobertura, huecos, fuente y límites temporales. Los empates intravela se conservan como ambiguos; puede calcularse un escenario conservador que asigne SL, sin presentarlo como orden observado.

Para no inflar certeza, los cruces que solo se conocen dentro de una vela deben conservar su intervalo temporal. No rellenar huecos con precios interpolados: una interpolación inventa cuál barrera se tocó primero. Reutilizar la reparación REST de `hydrator.py` y guardar su procedencia; si no se puede recuperar el dato, conservar el estado incompleto.

**D. Persistencia mínima, sin otra base paralela de producción.**

Propuesta de modelos, todavía no implementados: `CandidateSnapshot`, `EntryPlan`, `HorizonOutcome`.

- Añadir **`candidate_episodes`** para registrar la primera detección, contexto congelado, perfiles coincidentes y motivo de filtrado, incluso sin alerta operable. Deduplicar por episodio; evitar convertir cada minuto en un caso independiente.
- Reutilizar **`signals`** para planes operables y **`outcomes`** para su seguimiento compatible de 24h. Para variantes hipotéticas o candidatos sin señal, añadir **`evaluation_plans`** como extensión enlazada al episodio y opcionalmente al `signal_id`, con identidad de política y fill. No forzar variantes en la restricción actual de una señal abierta por símbolo.
- Añadir una tabla hija **`outcome_horizons`**, con unicidad `(evaluation_plan_id, horizon_min, evaluator_version)`. La versión inmutable del plan identifica entrada, TP/SL y costes. Una fila por horizonte; no siete tablas ni siete copias del detector. Las revisiones por reparación de datos deben conservar trazabilidad.
- Adaptar el lector de investigación al mismo esquema canónico de velas y a estas salidas. El WS guarda volumen cotizado `k["q"]` en `v`, por lo que el adaptador debe conservar esa unidad. Retirar gradualmente los cálculos duplicados de `labels` y simuladores después de comprobar paridad. La retención debe permitir reconstruir features previas y todo el horizonte de evaluación; el archivo analítico puede conservar más historia que el buffer operativo.

**E. Estadística condicionada con el resultado correcto.**

Reutilizar `TablaFrecuencias`, corregida y versionada, como primer estimador interpretable. La consulta principal debe ser:

`P(τ(+3,2%) ≤ H y τ(+3,2%) < τ(SL estructural) | perfil, régimen previo, contexto disponible, política de entrada)`

Para una entrada límite, publicar tanto probabilidad de fill como éxito condicionado al fill; no omitir silenciosamente las órdenes no ejecutadas. Para comparar el recorrido del precio, puede publicarse también `P(MFE_H ≥ 3,2%)`, claramente separada de la probabilidad operable.

Mostrar conteo de episodios, tamaño efectivo de muestra, incertidumbre, periodo, versión, fracción incompleta y comparación con tasa base del mismo régimen/horizonte. Con pocos casos, responder «muestra insuficiente». Validar en bloques temporales posteriores, purgando solapamientos hasta el máximo horizonte usado, agrupando episodios relacionados y midiendo calibración fuera de muestra. Los cuantiles y cortes de régimen se ajustan solo en entrenamiento. Evitar combinar todas las variables en cientos de celdas vacías desde el comienzo.

**F. Mantener explícito tu objetivo de 3,2%.**

La pregunta de recorrido se evalúa con toque de precio **+3,2%** desde cada entrada. Para «ganancia por operación», mostrar además el neto. El código local descuenta un coste configurado por defecto de 0,5 puntos porcentuales: con esa aproximación, un +3,2% bruto deja +2,7% neto, y +3,2% neto requeriría +3,7% bruto. Ese coste es una hipótesis del sistema, no una tarifa de Binance verificada en esta revisión. Guardar ambas políticas y sus costes sin mezclar etiquetas. Los objetivos inferiores de `grupos.py` quedan como comparación experimental.

Si el SL estructural exige demasiado riesgo o no hay espacio razonable hasta resistencia, el plan debe quedar como no apto para el objetivo. No estirar artificialmente el TP ni reducir la meta para hacer pasar la señal.

## Orden recomendado y criterio de aceptación

1. Alinear la versión desplegada con las correcciones de medición ya revisadas y verificar cobertura/recuperación. Cualquier despliegue queda fuera de esta revisión.
2. Corregir causalidad, identidad de evaluación y semántica temporal del etiquetador; unificar el evaluador con fixtures compartidos.
3. Registrar ambos perfiles y contexto completo en sombra; producir los siete horizontes con calidad y ambigüedad explícitas.
4. Reconstruir solo episodios respaldados por historia suficiente y reunir cohortes posteriores; calibrar las probabilidades por perfil/régimen/horizonte.
5. Actualizar la UI cuando pueda mostrar, para una misma oportunidad, objetivo, SL, horizonte, probabilidad de TP antes de SL, muestra y calidad verificables.

La implementación deberá demostrar: paridad streaming/replay; indicadores invariables al cambiar el futuro; conservación simultánea de 4/6/8h; manejo de empate TP/SL, huecos, reinicios y límites de ventana; separación de entrada propuesta y fill; y que una subida posterior al stop nunca se contabilice como éxito operable. Para una entrada a las 23:00, el backend debe poder recuperar resultados distintos a las 23:15, 23:30, 00:00, 01:00, 03:00, 05:00 y 07:00, calculados en UTC y mostrados en la zona elegida. Llegar hasta las 08:00 desde las 23:00 requiere un horizonte adicional de 9h; las siete ventanas solicitadas llegan hasta las 07:00.

**Validación realizada para este dictamen:** inspección de las fuentes locales y del archivo del servidor; consultas de solo lectura sobre la copia; comprobación de schemas en tres bases locales; seis reproducciones sintéticas sobre el módulo real de etiquetado (sobrescritura, causalidad, definición de MFE, empate, horizonte con huecos y esquema incompatible). Los scripts [inspect_paths.py](D:/SACBinance/audit/2026-09-11/path-engine-review/refresh/inspect_paths.py) y [check_labeling.py](D:/SACBinance/audit/2026-09-11/path-engine-review/check_labeling.py) permiten repetirlo. No se entrenó un modelo ni se estimó una probabilidad nueva de operación: la evidencia actual no respalda todavía esa conclusión.
