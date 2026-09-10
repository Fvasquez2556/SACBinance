# Auditoría de SACBinance


## El sistema detecta movimientos, pero todavía no demuestra entradas rentables

La medición actual no justifica afirmar que las señales tengan una ventaja suficiente para ganar **3.2% o más por operación**. El problema combina selección, entrada y evaluación: algunas monedas sí suben, pero el stop ocurre antes, el TP es demasiado pequeño o faltan velas para medir el recorrido.

- Las **2,238 señales evaluadas** por el sistema promedian **−0.107% bruto**; con un coste supuesto de 0.20 puntos porcentuales por ida y vuelta serían aproximadamente **−0.307%**. Son resultados simulados de señales, no movimientos de una cuenta real.
- **61.6% de las 2,307 señales** proponen un TP bruto menor a tu objetivo.
- De **915 outcomes reales cerrados** que registran +3.2%, **349 tocaron antes el SL**. Solo **566 de 2,019 (28.0%)** registran +3.2% antes de su stop; esta frecuencia sigue afectada por defectos de cobertura y tiempo.
- Con velas públicas completas, la muestra de otros pares tampoco demuestra una entrada ganadora: **171 oportunidades**, **−0.215% neto aproximado** al entrar según el plan original de 12h. Su intervalo por remuestreo de pares incluye cero: la evidencia es insuficiente para afirmar una ventaja, y tampoco permite fijar una pérdida futura.


## Qué está bien y conviene conservar

La base SQLite está íntegra. No encontré niveles largos invertidos, señales sin outcome ni outcomes reales huérfanos; los IDs separan las sombras. Las **82,935 velas comunes** entre la base y la muestra pública de Binance tienen OHLC coincidente: el principal fallo de precio investigado es la **ausencia de velas**, no valores inventados.

El uso de volumen quote en REST y WebSocket es coherente. Los niveles congelados, la separación entre una operación y su recorrido posterior, los motivos de veto, el gate macro, el control de riesgo y la medición en sombra son buenas bases. Distinguir continuación de impulso y giro tras una caída también tiene sentido: necesitan entradas y validaciones diferentes.

La investigación existente conserva código y reconoce varios riesgos de sobreajuste. Conviene mantener esa disciplina, añadiendo datasets congelados, versiones y resultados fuera de la muestra usada para elegir reglas.


## Hallazgos priorizados


### F01 · P1 · Faltan velas para medir las operaciones

**Evidencia:** 239/239 pares con velas 1m presentan huecos internos: faltan al menos 47,049 minutos-par entre su primera y última vela. De 1,297 señales reales maduras con alguna vela disponible, ninguna alcanza 98% de cobertura de 24h. Las 82,935 velas coincidentes con la referencia pública tienen OHLC idéntico.

**Impacto:** Los precios guardados son correctos en la muestra, pero faltan trayectos que pueden cambiar qué ocurre primero: SL o TP. Los indicadores por número de velas también dejan de representar minutos reales.

**Corrección propuesta:** Separar aggTrade del stream de velas o cambiar suscripciones sin reconectar las velas. Tras cualquier desconexión, reparar por REST desde el último cierre, deduplicar y comprobar continuidad antes de puntuar. Guardar cobertura y estado de calidad por ventana.

Confianza: Alta. Fuente: [backend/src/data_ingestion/ws_manager.py:199](D:/SACBinance/audit/2026-09-10/production/backend/src/data_ingestion/ws_manager.py:199), [backend/src/state/symbol_state.py:284](D:/SACBinance/audit/2026-09-10/production/backend/src/state/symbol_state.py:284), [replay.py](D:/SACBinance/audit/2026-09-10/replay.py), [reference_summary.py](D:/SACBinance/audit/2026-09-10/reference_summary.py)


### F02 · P1 · Los outcomes aceptan datos fuera de su ventana

**Evidencia:** 33 filas tienen ms_tp, ms_sl o ms_up_32 posteriores a 24h; la mayor duración cerrada es 117.92h. Hay 156 outcomes vencidos sin cerrar. Se reprodujo un TP a las 72h dentro de una ventana nominal de 24h.

**Impacto:** Las frecuencias de subida, MFE y MAE pueden atribuir a una señal movimientos de días posteriores. La salida de un par del universo deja seguimientos colgados.

**Corrección propuesta:** Aplicar el corte temporal antes de actualizar métricas; finalizar por un reloj independiente de nuevas velas; reparar huecos o marcar INCOMPLETE. Mantener seguimiento de posiciones aunque el par salga del universo.

Confianza: Alta. Fuente: [backend/src/analysis/outcome_tracker.py:404](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/outcome_tracker.py:404), [backend/src/analysis/outcome_tracker.py:456](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/outcome_tracker.py:456), [reproduce_defects.py](D:/SACBinance/audit/2026-09-10/reproduce_defects.py)


### F03 · P1 · Entrada, TP y objetivo del operador no están alineados

**Evidencia:** 1,420 de 2,307 señales (61.6%) ofrecen TP bruto inferior a 3.2%. En los 2,019 outcomes reales cerrados, son 1,247 (61.8%). objetivo_alcanzable se calcula, pero no bloquea la emisión ni se muestra en los componentes consultados.

**Impacto:** Cumplir el TP ofrecido frecuentemente no cumple tu meta. Un R:R de 2 tampoco equivale a 3.2% de beneficio ni a probabilidad de éxito.

**Corrección propuesta:** Evaluar recompensa neta desde la entrada realmente propuesta y ejecutada. Si no cabe 3.2% con costes y resistencia, clasificar como observación o esperar una entrada mejor. No ensanchar el SL únicamente para fabricar un TP mayor.

Confianza: Alta. Fuente: [backend/src/analysis/trade_levels.py:185](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/trade_levels.py:185), [backend/src/analysis/trade_levels.py:200](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/trade_levels.py:200), [backend/src/analysis/signal_tracker.py:29](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/signal_tracker.py:29)


### F04 · P1 · Hay alertas con niveles que no tienen su propia señal medible

**Evidencia:** El log registra 5,002 alertas con entry/TP/SL; 2,695 no tienen una nueva fila signals para el mismo par a ±2 segundos. abrir_senal impide una segunda OPEN, mientras AlertManager puede emitir otra con signal_id=None.

**Impacto:** El operador puede recibir niveles nuevos mientras las estadísticas continúan evaluando una entrada anterior. La auditoría de signals no es una auditoría de lo recibido por Telegram.

**Corrección propuesta:** Crear una identidad de candidato, señal, plan y episodio; toda alerta operable debe referenciar un plan persistido. Decidir explícitamente si reemplaza uno anterior. Registrar enviados, rechazados, editados y errores de Telegram por signal_id.

Confianza: Alta. Fuente: [backend/src/state/engine.py:807](D:/SACBinance/audit/2026-09-10/production/backend/src/state/engine.py:807), [backend/src/state/engine.py:838](D:/SACBinance/audit/2026-09-10/production/backend/src/state/engine.py:838), [backend/src/state/active_alert.py:481](D:/SACBinance/audit/2026-09-10/production/backend/src/state/active_alert.py:481), [backend/src/analysis/signal_tracker.py:35](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/signal_tracker.py:35)


### F05 · P1 · Comprar en el hoyo tiene una ambigüedad de ejecución

**Evidencia:** La reproducción determinista abre una compra en 100 y asigna TP=105 con una vela que pudo recorrer 104 → 106 → 99 → 100. En ese recorrido el máximo ocurrió antes del fill. No se observó ese caso concreto en las 218 ventanas completas recuperadas.

**Impacto:** El tracker puede conceder ganancias intravela imposibles de confirmar. El simulador histórico y el tracker vivo también difieren en el precio de fill cuando hay un hueco.

**Corrección propuesta:** No asignar TP en la vela de entrada por límite salvo orden verificable con trades o apertura ya ejecutable. Marcar ambigüedad y dar cotas; conservar fills, caducidad de la orden y costes. Unificar el simulador y el seguimiento vivo.

Confianza: Alta. Fuente: [backend/src/analysis/hoyo.py:133](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/hoyo.py:133), [research/entrada_en_el_hoyo.py:121](D:/SACBinance/audit/2026-09-10/production/research/entrada_en_el_hoyo.py:121), [reproduce_defects.py](D:/SACBinance/audit/2026-09-10/reproduce_defects.py)


### F06 · P1 · La probabilidad mostrada responde a otra pregunta

**Evidencia:** prob_meta es una tabla fija por distancia y edad, ajustada con mínimos acumulados. Estima tocar la meta en 6h. La tabla se construye con muestras repetidas cada 5 minutos, incluye outcomes sombra y no exige ganar antes del SL.

**Impacto:** Su n cuenta observaciones correlacionadas, no operaciones independientes. Una lectura de 80% no significa 80% de probabilidad de obtener 3.2% neto con ese plan.

**Corrección propuesta:** Renombrarla como frecuencia histórica de tocar meta, mostrar horizonte y versión; posteriormente calibrar P(TP neto antes del SL | entrada ejecutada, setup, régimen) en datos cronológicamente separados. Reportar episodios únicos e incertidumbre.

Confianza: Alta. Fuente: [backend/src/analysis/retroceso.py:152](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/retroceso.py:152), [backend/src/analysis/retroceso.py:183](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/retroceso.py:183), [research/tabla_meta.py:98](D:/SACBinance/audit/2026-09-10/production/research/tabla_meta.py:98), [frontend/src/components/PairRow.tsx:368](D:/SACBinance/audit/2026-09-10/production/frontend/src/components/PairRow.tsx:368)


### F07 · P2 · Tres indicadores nunca llegan a la base

**Evidencia:** rsi14, macd_hist y bb_position están NULL en 2,786/2,786 outcomes, incluso en las 672 filas recientes con contexto. _contexto busca claves distintas del snapshot: rsi14_1m y el diccionario por TF ind_htf.

**Impacto:** No se puede evaluar si esos indicadores mejoran la selección. Mezclar 1m y 15m bajo un nombre genérico produciría otra distorsión.

**Corrección propuesta:** Guardar nombres explícitos por TF, incluyendo si la vela está abierta y su timestamp. Añadir un contrato de snapshot y validar cobertura por versión. No rellenar retrospectivamente con indicadores actuales.

Confianza: Alta. Fuente: [backend/src/analysis/outcome_tracker.py:116](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/outcome_tracker.py:116), [backend/src/state/symbol_state.py:386](D:/SACBinance/audit/2026-09-10/production/backend/src/state/symbol_state.py:386), [reproduce_defects.py](D:/SACBinance/audit/2026-09-10/reproduce_defects.py)


### F08 · P2 · No disponer de flujo se mezcla con tener flujo neutro

**Evidencia:** 623 de 672 outcomes recientes (92.7%) tienen flow_trades_30s=0. aggTrade solo cubre una shortlist; además el score se limita cuando falta confirmación de flujo.

**Impacto:** La ausencia de suscripción o de datos puede perjudicar el score como si fuera ausencia real de compradores. Es un problema de cobertura, no una prueba de presión vendedora.

**Corrección propuesta:** Guardar flow_available, subscribed, ventana, edad y número de trades. Separar estado desconocido de señal negativa. Medir el efecto del flujo solo en oportunidades con cobertura comparable.

Confianza: Alta. Fuente: [backend/src/analysis/scoring.py:103](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/scoring.py:103), [backend/src/analysis/scoring.py:124](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/scoring.py:124), [backend/main.py:194](D:/SACBinance/audit/2026-09-10/production/backend/main.py:194)


### F09 · P2 · El universo y su volumen quedan fijados al arranque

**Evidencia:** universe_refresh_seconds está declarado pero no se utiliza. El volumen más reciente de pair_metadata es del 10-sep 05:48:59 UTC, unas 16h antes del corte. Había 200 pares activos y 39 pares con velas históricas sin actualización reciente.

**Impacto:** Un par que entra en volumen, se lista o cambia de liquidez puede no entrar al escáner. Retirar cobertura deja señales antiguas abiertas; 29 señales OPEN ya superaban 12h.

**Corrección propuesta:** Actualizar el universo y la liquidez periódicamente; registrar altas, bajas y motivos con fecha. Mantener una suscripción separada para las operaciones en seguimiento.

Confianza: Alta. Fuente: [backend/main.py:77](D:/SACBinance/audit/2026-09-10/production/backend/main.py:77), [backend/src/config/settings.py:26](D:/SACBinance/audit/2026-09-10/production/backend/src/config/settings.py:26), [backend/src/persistence/db.py:475](D:/SACBinance/audit/2026-09-10/production/backend/src/persistence/db.py:475)


### F10 · P2 · El filtro de apalancados excluye monedas normales

**Evidencia:** La regla any(m in base) marca SUPER, JUP y SYRUP por contener UP. exchangeInfo confirmó sus pares USDT spot activos. El filtro de stablecoins/fiat/oro es una capa separada.

**Impacto:** Reduce el universo por coincidencias de texto y puede ocultar oportunidades sin ninguna justificación de mercado.

**Corrección propuesta:** Usar clasificación explícita del instrumento y una lista exacta de tokens apalancados; mantener pruebas para SUPERUSDT, JUPUSDT y SYRUPUSDT. Versionar la política de exclusión de stablecoins.

Confianza: Alta. Fuente: [backend/src/data_ingestion/universe.py:19](D:/SACBinance/audit/2026-09-10/production/backend/src/data_ingestion/universe.py:19), [backend/src/data_ingestion/universe.py:49](D:/SACBinance/audit/2026-09-10/production/backend/src/data_ingestion/universe.py:49), [deep_checks.py](D:/SACBinance/audit/2026-09-10/deep_checks.py)


### F11 · P2 · Los eventos no tienen una convención temporal única

**Evidencia:** 23 outcomes tienen alguno de ms_up_32, ms_sl, ms_tp o ms_dn_1 negativo. Las muestras observadas rondan fracciones de segundo: se resta la hora de emisión de la apertura de la vela. Procesar dos veces una misma vela incrementa n_velas dos veces.

**Impacto:** Los tiempos dejan de representar duraciones válidas y un replay puede volver a procesar eventos. Los negativos observados, por sí solos, no prueban conocimiento del futuro.

**Corrección propuesta:** Distinguir candle_open_time, candle_close_time, decision_time y received_at. Rechazar velas totalmente anteriores a la decisión; hacer idempotente la actualización por (símbolo, TF, apertura) y conservar la ambigüedad de la vela parcial.

Confianza: Alta. Fuente: [backend/src/data_ingestion/ws_manager.py:135](D:/SACBinance/audit/2026-09-10/production/backend/src/data_ingestion/ws_manager.py:135), [backend/src/analysis/outcome_tracker.py:404](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/outcome_tracker.py:404), [backend/src/state/symbol_state.py:284](D:/SACBinance/audit/2026-09-10/production/backend/src/state/symbol_state.py:284)


### F12 · P2 · Se borran las velas antes que la evidencia que deben explicar

**Evidencia:** Las señales abarcan 5-sep a 10-sep, pero las velas 1m retenidas empiezan el 7-sep. prune_klines elimina 1m/5m/15m a los tres días. 2,114 outcomes carecen del contexto agregado posteriormente y no hay strategy_version/config_hash en la tabla.

**Impacto:** No se puede reconstruir la historia ni separar con precisión qué variante produjo cada resultado. Los cambios de parámetros y condiciones de mercado se mezclan.

**Corrección propuesta:** Archivar las velas y features que sustentan cada experimento, fuera del cache operativo. Guardar hash de configuración, commit, versión de etiqueta, instante de features y procedencia live/replay.

Confianza: Alta. Fuente: [backend/src/persistence/db.py:785](D:/SACBinance/audit/2026-09-10/production/backend/src/persistence/db.py:785), [backend/src/persistence/db.py:48](D:/SACBinance/audit/2026-09-10/production/backend/src/persistence/db.py:48), [provenance.json](D:/SACBinance/audit/2026-09-10/provenance.json)


### F13 · P2 · Algunas rutas evitan el ciclo normal de seguimiento

**Evidencia:** El veto blow-off retorna antes de actualizar AlertManager. Los perfiles de tendencia, ignición y base se emiten por un circuito separado sin abrir su outcome. Los vetos nuevos con motivo VETO todavía tienen cero ventanas cerradas.

**Impacto:** Puede retrasarse el cierre visual de una alerta justo cuando hay agotamiento. Tampoco existe una base comparable para determinar cuál detector agrega valor o qué oportunidades bloquea cada veto.

**Corrección propuesta:** Actualizar siempre posiciones y alertas antes de cualquier return de detección. Registrar todos los candidatos de los detectores y los vetos con el mismo contrato y horizonte.

Confianza: Alta. Fuente: [backend/src/state/engine.py:445](D:/SACBinance/audit/2026-09-10/production/backend/src/state/engine.py:445), [backend/src/state/engine.py:741](D:/SACBinance/audit/2026-09-10/production/backend/src/state/engine.py:741), [backend/src/state/engine.py:874](D:/SACBinance/audit/2026-09-10/production/backend/src/state/engine.py:874)


### F14 · P2 · Las métricas de éxito y los costes necesitan nombres precisos

**Evidencia:** La API llama win_rate a TP/(TP+SL+EXPIRED): 23.9%. Los EXPIRED positivos cuentan como no TP, y el resultado medio es bruto. No existen fills, spread, tickSize ni comisiones de cuenta en signals.

**Impacto:** La tasa de tocar TP, la tasa de ganar dinero y la tasa de ganar al menos 3.2% neto son métricas diferentes. El redondeo decimal por precio tampoco garantiza un nivel válido para Binance.

**Corrección propuesta:** Publicar por separado tasa de fill, TP antes de SL, retorno neto medio/mediano, P(net≥3.2%), vencidos, incompletos y cobertura. Añadir tickSize/stepSize, spread, tamaño ejecutable y costes al plan.

Confianza: Alta. Fuente: [backend/src/persistence/db.py:601](D:/SACBinance/audit/2026-09-10/production/backend/src/persistence/db.py:601), [backend/src/analysis/trade_levels.py:67](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/trade_levels.py:67), [backend/src/analysis/signal_tracker.py:116](D:/SACBinance/audit/2026-09-10/production/backend/src/analysis/signal_tracker.py:116)


## MARSCOIN explica el problema de entrada, pero no valida una regla universal

La señal **#1871**, del **9-sep a las 01:52 de Guatemala (07:52 UTC)**, propuso entrada **0.139000**, SL **0.132539** y TP **0.151921**. Las velas públicas confirman SL en la vela de **02:25 local**, +3.2% en **03:12** y TP en **03:13**. Entrar al precio de la señal pierde aproximadamente **4.65% bruto** antes del rebote.

Esperar **0.133201695** (SL×1.005) y usar un stop nuevo de 2% o 3% habría llegado al TP, con **14.05% bruto** bajo el modelo de velas. Mantener el SL original habría provocado otra salida por stop. Por tanto, tu observación identifica una oportunidad real en ese episodio, pero exige especificar **otro plan de riesgo**, no solo otro punto de compra.

En las nueve señales de MARSCOIN de esta base hubo **1 TP y 8 SL**, con promedio bruto de **−3.17%** siguiendo el plan original. ETHFI y RAY sí muestran ejemplos positivos; IO es más mixto. La comparación inferior usa únicamente señales con 24h de referencia completa, aunque la simulación de salida se corta a 12h: por eso incluye 11 señales de RAY y 8 de IO, frente a 12 y 10 señales registradas respectivamente.


## Qué se puede concluir de las entradas alternativas

Recuperé **225,474 velas** mediante **245 consultas públicas**. Los cuatro ejemplos se analizaron aparte. Los otros 24 símbolos se eligieron por hash del nombre, sin consultar sus rendimientos; 22 tienen señales maduras utilizables, con **171 oportunidades completas**. Son ventanas retrospectivas sobre señales ya emitidas, no un experimento futuro ni una estimación representativa de todos los mercados.

La compra en SL×1.005 se ejecuta en **134 de 171 oportunidades (78.4%)** bajo el modelo usado. Con stop fijo de 2% devuelve **−0.382% neto aproximado por fill**; con stop de 3%, **−0.393%**. Conservar el SL original deja un riesgo de solo ~0.50%: **111 de 134 fills terminan en SL** y el promedio neto es **−0.165%**. Las tres medias netas son negativas y sus intervalos de remuestreo por par cruzan cero. Ninguna de ellas queda validada como mejora.

Los ejemplos elegidos por haber subido dan una impresión distinta: entre ellos, la variante de stop 2% promedia +0.545% neto aproximado, frente a −0.382% en los otros pares. La diferencia ilustra el riesgo de seleccionar ganadores para diseñar la entrada; no prueba una causa.

Las simulaciones usan ventanas por tiempo, solo velas íntegramente posteriores a la emisión, stop primero si TP y SL comparten vela, penalización por apertura por debajo del stop y ninguna concesión de TP ambiguo en la vela del fill. Las órdenes pendientes se cancelan si el objetivo ocurrió antes de la entrada. No modelan spread, latencia, profundidad, cola de órdenes ni fills parciales. El horizonte de 24h se cuenta desde la señal, no desde el fill. Los intervalos por par no capturan toda la dependencia entre días y monedas.


## Cómo mejoraría la precisión de entrada

**Primero definiría una operación completa.** Una oportunidad puede existir sin una entrada ejecutable. El registro debería pasar por DETECTADA → ESPERANDO_ENTRADA → EJECUTADA → TP / SL / VENCIDA, con INCOMPLETA cuando falten datos. La entrada por retroceso debe tener un límite temporal y cancelarse si el precio ya completó el objetivo o invalidó la estructura.

**Para continuación:** medir ruptura y retesteo, espacio hasta la resistencia y cuánto movimiento ya ocurrió; evitar perseguir un tramo agotado. **Para giro:** marcar una zona de soporte y exigir una recuperación observable del nivel tras la caída; comprar automáticamente junto al SL de una señal anterior no demuestra que exista un suelo. **Para una base:** registrar duración, rango, contracción de volumen y recuperación del techo. Estas son hipótesis de reglas a contrastar, no parámetros validados por esta semana.

El SL debe representar la invalidación del setup. El tamaño de posición adapta el riesgo monetario a esa distancia; no se mejora la entrada ampliando el stop para que un R:R fijo produzca el TP deseado. El TP debe ser alcanzable desde el fill, tener espacio estructural y cumplir la meta después de costes.

Con 0.10% supuesto de comisión al comprar y 0.10% al vender, y sin deslizamiento, ganar 3.2% neto exigiría aproximadamente **3.41% de subida bruta**: (1+0.032)×(1+0.001)/(1−0.001)−1. Las tarifas reales dependen de la cuenta y del par; 0.20% total se usa aquí solo como escenario. [Comisiones de Binance](https://developers.binance.com/docs/binance-spot-api-docs/faqs/commission_faq).

Antes de ordenar señales por probabilidad, mediría por separado **P(fill)** y **P(TP neto antes del SL | fill)**, retorno esperado neto y tiempo típico hasta resolución. El score actual es una puntuación de reglas, no una probabilidad calibrada.


## Qué simplificaría

Mantendría separados el **estado del mercado**, el **setup**, el **plan operable** y el **recorrido posterior**, pero cada uno tendría una función y una identidad claras. Hoy signals (12h), AlertManager (6h accionable y 24h de seguimiento) y outcomes (24h) pueden dar desenlaces distintos. Conviene compartir un evaluador de eventos y conservar las vistas específicas, no mantener tres motores independientes de TP/SL.

Centralizaría la meta de 3.2%, hoy repetida en módulos, interfaz, mensajes y estudios; consolidaría la clasificación de tiers, los cooldowns y las reglas de ejecución de los simuladores. Los parámetros universe_refresh_seconds y sl_atr_mult están declarados sin uso. Los perfiles de tendencia, ignición y base necesitan outcomes comparables antes de decidir eliminar alguno.

Los vetos de alerta son mayormente contabilidad: **3,751 por alerta viva y 4,168 por cooldown**, 61.3% de 12,909. Deben distinguirse de rechazos de calidad. No se puede afirmar qué veto mejora el rendimiento comparando grupos seleccionados de forma diferente; las nuevas sombras VETO todavía no tienen ventanas cerradas.


## Orden de corrección y criterios para volver a confiar en las métricas

1. **Reparar medición e identidad.** Continuidad de velas, corte estricto de horizonte, timestamps, procesamiento idempotente, alertas ligadas a un plan y estado INCOMPLETO. Criterio: replay repetido produce el mismo resultado, ningún cruce cae fuera de ventana y toda alerta operable tiene identidad persistida.
2. **Arreglar cobertura y contratos.** Refresco del universo, filtro de instrumentos, suscripción de posiciones, persistencia correcta de indicadores y disponibilidad de flujo. Criterio: campos obligatorios completos por versión, gaps visibles y recuperados, y todos los candidatos registran su motivo de aceptación o rechazo.
3. **Definir planes de entrada comparables.** Entrada inmediata y uno o dos planes de retroceso/reclaim previamente especificados, mismo horizonte, costes y regla de cancelación. Guardar signal_id, episode_id, strategy_version, config_hash, decision_time, features_asof, entry_zone, order_expiry, fill_time/price, SL, TP y costes.
4. **Validar hacia delante.** Congelar reglas y reunir periodos adicionales con distintos regímenes. Usar separación cronológica con purga de ventanas solapadas de hasta 24h, agrupar por par/episodio y evaluar también concentración simultánea de riesgo. No optimizar repetidamente sobre esta semana ni sumar retornos de operaciones solapadas como si fueran una cartera financiable.
5. **Ordenar por utilidad operable.** P(fill), P(≥3.2% neto antes del SL), retorno neto esperado, incertidumbre, tiempo y liquidez. Exigir evidencia fuera de muestra antes de llamar mejor a una nueva versión. No hay respaldo para prometer una precisión o ganancia futura concreta.

La subida del 5-sep domina varios resultados: la muestra externa del plan original pasa de +1.59% neto aproximado ese día a medias negativas los cuatro días siguientes. Esto obliga a separar régimen de mercado, cambios de código y calidad del setup.


## Alcance, límites y trazabilidad

Auditoría de solo lectura del servidor Ubuntu y de una copia consistente de SQLite tomada el **10-sep-2026, 21:57 UTC (15:57 Guatemala)**. Código del servidor: **fbed25ca651a0050222ce57d64a4cf2a4fed831e**, árbol limpio. La versión local original era **358a6fa9273a873bafa42c07eca3a7cd47e7790b**. No se modificó ni desplegó el sistema.

Se inspeccionaron 2,307 señales, 2,786 outcomes (2,307 reales y 479 sombras), 1,178,836 velas de seis temporalidades y 83,139 registros de análisis. Los datos de señales abarcan 5–10 septiembre. Las estadísticas del sistema incluyen versiones históricas; la ausencia de config_hash impide atribuirlas exclusivamente al código actual.

Se separaron abiertas, maduras, sombras y datos incompletos. El promedio general usa únicamente 2,238 señales TP/SL/EXPIRED; excluye 49 OPEN y 20 STALE. La tasa denominada win_rate en la API es tasa de TP, no tasa de beneficio positivo. En los cuatro ejemplos y la muestra pública, el replay coincide en estado con 214 de 218 registros; hay cuatro discrepancias, incluyendo un TP que en la reconstrucción da SL. La cifra no certifica fills reales.

La muestra pública cubre 28 símbolos; no se reconstruyó todo el universo ni se reejecutó el generador histórico de candidatos. No hay órdenes de cuenta, ejecuciones, capital, tamaño de posición ni historial completo de notificaciones que permitan medir P&L realizado o la precisión de Telegram. Los logs de servicio visibles por journal no daban cobertura suficiente: la relación entre reconexiones y gaps se identifica en el código, pero no se cuantifica como causa exclusiva.

Seis reproducciones deterministas comprueban los defectos de ventana, duplicación, contrato de indicadores, orden intravela y filtrado. Los scripts y las consultas acompañan el informe; snapshot.db se conserva separado de reference.db. El backup usa la [API de copia consistente de SQLite](https://www.sqlite.org/backup.html). Las velas públicas se verificaron contra [REST de Binance](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints), y la recomendación de suscripción usa los mecanismos documentados de [WebSocket](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams).
