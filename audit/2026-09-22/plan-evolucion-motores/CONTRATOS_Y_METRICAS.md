# Contratos de datos y medición propuestos

Estado: **especificación para implementar**, no esquema existente. Complementa [PLAN.md](PLAN.md). La migración concreta se diseñará sobre la base elegida al iniciar la fase 1; no ejecutar este documento como SQL.

## 1. Unidades que no deben confundirse

### Observación de mercado

Un hecho producido por un detector en un símbolo, marco y momento: ruptura, caída activa, pérdida de nivel, desaceleración o recuperación. Puede existir sin plan de compra y sin Telegram.

Conservar `source_kind` y `source_id` para las tablas existentes `rupturas`, `rupturas_tf`, `signals` y `alertas_emitidas`. No copiar miles de filas antiguas atribuyéndoles identidades o versiones que no tenían.

### Episodio

Una tesis de mercado identificada desde el momento de detección, con símbolo, ancla estructural y reloj. Tiene una primera observación y puede incluir varias señales, cambios de fase y planes alternativos. Un episodio no es una operación y no tiene una ganancia real por sí solo.

Campos mínimos propuestos:

- `episode_id`: identificador persistente e independiente del proceso.
- `symbol`, `anchor_tf`, `anchor_kind`, `anchor_price`, `opened_at`.
- `initial_direction`, `current_phase`, `episode_rule_version`.
- `first_observation_id`, `first_eligible_plan_id`, `last_observed_at`.
- `closed_at`, `close_reason`, `parent_episode_id` opcional.
- `context_snapshot_id`, procedencia de código y configuración.

Reglas:

1. Asociación solo con información disponible al recibir el evento. No definir el episodio por el mínimo o máximo futuro.
2. La primera oportunidad elegible se fija al aparecer y no cambia porque una posterior gane más.
3. Un cambio material de ancla o invalidación crea una tesis nueva enlazada a la anterior. Un simple cambio de score no crea automáticamente otro episodio.
4. El silencio o la caducidad cierran según una regla versionada y específica del horizonte, no según un contador global que se reinicia al reiniciar el servicio.
5. Puede haber contextos mayores y movimientos menores relacionados. La relación padre/hijo no afirma que sus resultados sean independientes ni exige que tengan la misma dirección.

**Regla congelada el 21-sep-2026 (`episodio-v1`), implementada en `backend/src/episodios/registro.py`.** Un episodio se cierra por lo primero que ocurra: `DESENLACE` (el plan tocó objetivo o stop), `ANCLA` (el candidato nuevo se apoya en un nivel estructural que difiere más del 2,5 %), `SILENCIO` (12 h sin candidato nuevo del mismo símbolo y dirección) o `CADUCIDAD` (12 h desde la apertura sin resolución). Los dos números salen de medir, no de elegir: la mediana entre dos avisos del mismo par es de 21 h y el 82 % de las repeticiones tarda más de 12 h; dentro de esas 12 h el stop estructural se mueve 0,20 % de mediana y el 90 % no pasa del 2,62 %. El agrupamiento no se ajusta con el resultado posterior de las operaciones, y la versión de la regla va en cada fila (`regla_version`) para que un cambio futuro no reescriba el pasado.

Las tablas reales de la fase 1 son `episodios` y `planes` (esquema v16, aditivo). Los campos propuestos más abajo que todavía no existen —`context_snapshot_id`, `first_observation_id`, `anchor_kind` normalizado— se añaden en las fases siguientes; hoy el contexto va serializado en `planes.snapshot` y el enlace a las fuentes antiguas en `legacy_alerta_id` / `legacy_signal_id`.

### Señal o evento candidato

Una propuesta o actualización concreta con `event_id`, `episode_id`, `engine_id`, `trigger_tf`, `observed_at`, `available_at`, `kind`, `reason_codes`, `snapshot_id` y enlaces a su fuente original. Cada señal conserva su identidad aunque no se notifique.

Clases iniciales: `CANDIDATE`, `CONFIRMATION`, `CONTEXT_UPDATE`, `INVALIDATION`, `REENTRY_CANDIDATE`. Son tipos de evento, no resultados.

### Plan de evaluación

La unidad básica para medir una entrada propuesta. Debe existir para **cada aviso con niveles**, tenga o no `signal_id`.

Campos:

- `plan_id`, `episode_id`, `candidate_event_id`, `parent_plan_id` opcional.
- `revision`, `created_at`, `decision_at`, `valid_from`, `expires_at`.
- `market_type=SPOT`, `side=BUY`, `engine_id`, `trigger_tf`, `context_tfs`.
- `entry_policy`, `entry_reference`, `entry_min`, `entry_max`, `max_entry_deviation_pct`.
- `stop_price`, `stop_basis`, `target_price`, `target_net_pct`, `target_basis`.
- `wait_timeout_ms`, `holding_horizon_ms`, `observation_horizon_ms`.
- `cost_model_id`, `risk_policy_id`, `exit_policy_id`, `snapshot_id`.
- `code_id`, `config_hash`, `policy_version`, `feature_schema_version`.
- `legacy_alerta_id`, `legacy_signal_id` y `source_quality` cuando corresponda.

Invariantes:

- Un plan BUY válido requiere `stop_price < entry_reference < target_price`; las bandas deben ser coherentes.
- Los niveles, costes asumidos y reglas de salida de una versión son inmutables.
- Modificar un plan crea una nueva versión con momento de vigencia. La versión nueva no hereda los máximos o resultados de la anterior.
- `signal_id` puede seguir siendo nulo por compatibilidad. `plan_id` no puede faltar en los planes nuevos.
- Los IDs de sombras, señales, notificaciones y operaciones pertenecen a espacios separados. No usar un entero negativo ambiguo como identidad universal.

### Oportunidad seleccionada y notificación

La oportunidad es la decisión de presentar un plan para una acción posible. Puede representarse inicialmente con el plan elegido y un evento de selección, sin crear otra tabla si no aporta información distinta.

Persistir `selection_policy_id`, `selected_plan_id`, `selected_at`, `eligibility_reason`, `capacity_reason`, posición en el lote y estado de entrega. La elegibilidad, el cupo y el transporte deben tener razones separadas.

Relojes diferentes:

- Detección del candidato.
- Selección/activación del plan.
- Inicio del envío.
- Confirmación del proveedor.
- Entrada declarada/real del usuario.

No convertir una confirmación del envío en hora de lectura del usuario ni en fill. La selección reciente tiene una demora mediana de aproximadamente 30 segundos hasta activación; esa diferencia ya puede importar en un mercado rápido.

### Operación del usuario

Campos:

- `trade_id`, `selected_plan_id`, `episode_id`, `symbol`.
- `origin`: `TELEGRAM`, `DASHBOARD`, `MANUAL_EXTERNAL`, `IMPORTED`.
- `evidence_type`: `SIMULATED`, `USER_REPORTED`, `EXCHANGE_CONFIRMED`.
- `entry_at`, `entry_price`, `quantity`, moneda de referencia y comisiones.
- `initial_stop`, `initial_target`, `cost_model_id` cuando sea simulación.
- `status`, `closed_at`, `exit_price`, `realized_net_quote`, `realized_net_pct`.
- `recorded_at`, referencias de ejecución disponibles y revisión del registro.

Eventos anexos: entrada, ampliación, reducción, cierre parcial, cierre total, cambio de stop/TP y corrección declarada. Un cambio de gestión del usuario es un hecho nuevo con hora propia; no modifica el plan original con el que se evaluó la estrategia.

Si la cantidad o ejecución no están disponibles, el sistema puede seguir porcentajes hipotéticos, pero no declarar ganancias reales en dinero. No rellenar comisiones ausentes con cero. Una importación futura requiere conciliar cantidades, moneda de la comisión y duplicados; queda fuera de la primera implementación.

## 2. Snapshot y procedencia

El snapshot se guarda al producir la decisión. Debe incluir valores y disponibilidad, no solo un JSON del estado actual leído después.

Contenido mínimo:

- Precio de referencia, último cierre disponible y origen del dato.
- Tendencia, ruptura, nivel, confirmación y reloj de cada marco.
- Volatilidad, ATR, rango de 1h, ruido y grupo de volatilidad calculados con datos anteriores.
- Impulso, extensión consumida, caída previa y recuperación observada.
- Volumen, liquidez y edad/disponibilidad del flujo agresor.
- Régimen de BTC y del par con su versión de definición.
- Candidatos y política de selección, incluidos motivos de exclusión.
- Cobertura, huecos conocidos, indicador de datos parciales y momento de disponibilidad.

Procedencia mínima en todos los resultados nuevos:

`code_id + config_hash + feature_schema_version + detector_version + exit_policy_id + evaluator_version + snapshot_id`

Para análisis agregados, añadir `dataset_id`, corte temporal y huella de datos. La versión de esquema de SQLite no sustituye a la versión de las reglas. El código efectivo no queda identificado solo por HEAD si hay cambios sin commit.

Histórico:

- Enlaces exactos: preservar la fuente y sus IDs.
- Reconstrucción causal posible desde velas y snapshots: marcar `RECONSTRUCTED` y guardar método/versión.
- Contexto imposible de recuperar: `UNKNOWN`, sin fabricar régimen, score o identidad de episodio.
- Nunca copiar valores actuales de BTC, liquidez o modelo a una señal antigua.

## 3. Evaluador común

Interfaz conceptual pura:

`evaluate(plan_snapshot, ordered_market_events, evaluation_cutoff, evaluator_version) -> policy_outcome + horizon_observations + quality`

Streaming y replay usan el mismo núcleo. Los adaptadores resuelven almacenamiento, reloj y compatibilidad; no duplican la lógica de primer toque.

### Dos salidas diferentes

**Desenlace de la política:** si hubo entrada, cuál ocurrió primero entre TP, SL y vencimiento, a qué precio estimado/real se salió y qué coste se aplicó.

**Observación del recorrido:** máximo favorable/adverso, recuperación y tiempos a umbrales hasta el final del horizonte de investigación, aunque la operación ya haya terminado.

El resultado de la operación queda terminal. La observación posterior puede seguir creciendo, pero no convierte un SL en TP.

### Relojes y velas

- Usar velas cerradas y ordenar por tiempo de mercado; registrar aparte recepción/procesamiento.
- Contar solo minutos enteros incluidos en la ventana cuando no exista una fuente más fina que resuelva la secuencia.
- Identificar la vela que aporta cada primer toque.
- No contar una misma vela dos veces al reintentar, reconectar o reconstruir.
- Vencimiento por reloj aunque el par salga del universo; precio de cierre próximo al vencimiento, no el precio del día siguiente.
- Un hueco pendiente de reconstruir puede afectar el primer toque. La calidad será explícita, no un flag «cerrado» que sugiera que toda la trayectoria fue observada.

### Fills y entrada diferida

La espera y la operación son ventanas distintas. Un candidato puede vencer sin fill y debe contarse como `NO_FILL`, no como una pérdida ejecutada.

Para una compra límite/retest, la política debe declarar precio, momento de armado, condición de confirmación y tiempo máximo de espera. El horizonte de operación empieza desde el fill según su contrato. No usar un precio inferior descubierto después como si el usuario hubiera colocado allí la orden previamente.

Si en la vela que toca la entrada también aparecen objetivo y stop y no se conoce el orden, registrar ambigüedad. No atribuir al fill el máximo previo de la misma vela. Con datos de 1m, la evaluación conservará un límite conservador y el número de casos sin secuencia conocida. Las pruebas deben cubrir también gaps que atraviesen entrada o stop.

Los campos direccionales antiguos `ms_tp`, `ms_sl` de `rupturas_tf` describen barreras desde la detección y no prueban por sí solos una ejecución válida del retest. Separar `touch_from_detection` de `touch_after_fill`.

### Estados propuestos

Plan/candidato: `WATCHING`, `ELIGIBLE`, `SELECTED`, `SUPERSEDED`, `INVALIDATED`, `EXPIRED`.

Resultado de política: `WAITING_ENTRY`, `OPEN`, `TP`, `SL`, `TIME_EXIT`, `NO_FILL`, `CANCELLED`, `AMBIGUOUS`, `INCOMPLETE`.

Calidad: cobertura, edad, huecos, reloj proxy, tipo de ejecución y versión del evaluador. La calidad no se codifica como una ganancia o pérdida adicional.

## 4. Métricas principales y denominadores

### A. Resultado económico de una política

Resultado neto medio sobre operaciones simuladas cerradas y evaluables bajo la política, más resultado por oportunidad elegible cuando existan NO_FILL/no entrada. Ambos denominadores deben estar visibles.

Para un modelo simple:

`retorno_neto_pct = (precio_salida / precio_entrada - 1) × 100 - coste_total_pct`

Para una operación real: calcular a partir de las cantidades y flujos netos de dinero de los fills, incorporando todas las comisiones convertidas a la misma moneda con una regla registrada. No descontar deslizamiento otra vez si ya está representado por los precios ejecutados.

Desgloses obligatorios: media, mediana, porcentaje positivo neto, resultado en unidades de riesgo y coste supuesto/real. Una suma de porcentajes de señales simultáneas no es rentabilidad de cartera.

### B. Cumplimiento de objetivo antes del stop

`planes que alcanzan objetivo neto antes del stop / planes entrados con horizonte comparable y resultado evaluable`

Publicar también vencidos, abiertos, ambiguos y excluidos. La política del denominador debe ser estable; no excluir vencidos negativos para mejorar la tasa. Para comparar objetivos alternativos en un análisis cerrado, usar una cohorte común cuyo horizonte completo haya madurado, no una cohorte resuelta por el TP de otra política.

Separar siempre:

- TP antes del SL.
- Objetivo neto antes del SL.
- Cierre neto positivo.
- Alcance de una subida en cualquier momento, incluso después del SL.

### C. Fidelidad de la medición

Cobertura de identidad: proporción de planes nuevos con enlaces y snapshot completo.

Cobertura temporal: proporción de minutos observados y suficientes para resolver la pregunta; porcentaje de planes con huecos o ejecución ambigua.

Objetivos de aceptación inicial: 100 % de identidad para planes nuevos y 100 % de conservación de los hechos originales en pruebas de migración. Los históricos desconocidos deben seguir visibles como desconocidos, no ocultarse para alcanzar esos porcentajes.

### Guardias económicas y operativas

- Caída acumulada y pérdida extrema con un presupuesto de riesgo acordado.
- Exposición simultánea por símbolo, episodio y grupos correlacionados.
- Tiempo hasta objetivo, tiempo de ocupación de capital y porcentaje sin fill.
- Retraso del dato, cola de procesamiento y fallos de persistencia/entrega.

Los límites monetarios de cartera requieren información adicional del usuario antes de una activación operativa; no se inventa un tamaño de cuenta ni un porcentaje de riesgo personal en este plan.

## 5. Cómo contar primeras y repetidas

Ofrecer estas vistas, cada una con su denominador:

1. **Todas las señales:** cada plan evaluado, para diagnóstico de detectores. Agrupar la incertidumbre por episodio/símbolo/tiempo.
2. **Primera elegible del episodio:** fijada con información disponible entonces. Una observación no operable de caída no consume la primera compra elegible.
3. **Primera notificada del episodio:** mide lo que el usuario tuvo disponible en Telegram; puede diferir de la primera detectada.
4. **Repetidas:** medir valor incremental desde su propia entrada y el estado que tenía el episodio en ese momento.
5. **Una operación por símbolo mientras está abierta:** simulación cronológica con reglas de cartera; no asumir que coincide con la primera del episodio.
6. **Mis operaciones:** solo eventos explícitos del usuario/importados, con selección original conservada.

No asignar una victoria a un episodio porque cualquiera de sus diez planes ganó. Esa pregunta retrospectiva puede registrarse como capacidad descriptiva de cobertura, pero no representa una política ejecutable.

Las señales repetidas pueden mejorar la información sobre un movimiento sin constituir nuevas entradas. Para medir si una actualización ayuda, comparar una política que actúe sobre ella con otra que mantenga el plan original, sin elegir ex post la acción favorable.

## 6. Datos para los dos motores

### Captura que debe ampliarse

No basta recolectar más compras notificadas. El motor de caída requiere observaciones antes de cualquier rebote, incluidos descensos que nunca recuperan y momentos donde no se emitió una compra.

Capturar cambios de estado y una muestra temporal determinista del universo elegible, con snapshot completo y probabilidad de muestreo si no se conserva todo. Mantener las razones de exclusión del universo y del flujo: la falta de `aggTrade` no es ausencia de compras agresoras.

Si se estudian «mayores ganadores del día», guardar el ranking **como era en el momento de observarlo**, la subida ya consumida, el máximo anterior conocido y la entrada hipotética/real. No seleccionar al final del día los que terminaron ganando ni sustituir el universo original por los supervivientes.

### Etiquetas y modelos

Clasificación de patrón observado y predicción de resultado son cosas distintas. Un nombre como «ruptura confirmada» describe cierres observados, no garantiza continuidad.

Para dirección con dos barreras fijas y un horizonte común puede definirse una etiqueta excluyente: subida primero, caída primero, ninguna o ambigua. Para otras preguntas —continuación a 12 h o recuperación después de una entrada futura— las probabilidades no son complementarias y no tienen por qué sumar 100 %.

Medir por separado:

- Capacidad de anticipar caída antes de la meta.
- Capacidad de reconocer una recuperación válida después de una caída.
- Rentabilidad de una regla de compra posterior, incluidos los candidatos que no se activaron.

Las variables que definen la política, como el ancho del stop, pueden entrar en un modelo condicional de **ese plan** si la pregunta se declara como tal. No usarlas para fingir un predictor de dirección independiente de las barreras; parte de su capacidad sería aritmética.

## 7. Diseño de validación

- Congelar dataset, código, política y objetivos antes de evaluar el siguiente bloque.
- Separar entrenamiento, calibración y prueba por tiempo. Retirar de los bordes las observaciones cuyas ventanas futuras invadan el bloque siguiente; considerar todo el tiempo de espera más tenencia y la dependencia de episodios.
- Mantener un episodio en una sola partición. Añadir comprobaciones por símbolo y régimen.
- Comparar contra la política vigente, un ranking sencillo y controles contemporáneos del mismo símbolo/régimen, con restricciones iguales de entrada y riesgo.
- Remuestrear bloques que respeten dependencia; reportar tamaño efectivo y sensibilidad a periodos/símbolos. No tratar las 48.240 rupturas por marco como ensayos independientes.
- Predefinir qué mejora tiene importancia económica, costes adversos y fechas de revisión. Evitar elegir la celda máxima de una rejilla y anunciarla como validación.
- Evaluar calibración con curvas de fiabilidad y tamaño por banda, además de discriminación y resultado neto. Una AUC alta no garantiza ganancias y una mejora de Brier no explica por sí sola toda la calibración.
- Con muestra insuficiente para un segmento, mostrar «sin estimación fiable» o una referencia más amplia expresamente etiquetada. No cambiar silenciosamente la pregunta mediante un fallback.

## 8. API, eventos y compatibilidad

Contratos propuestos, sujetos a los tipos definitivos de la fase 1:

- `GET /api/vnext/episodes`: episodios con contexto, primera oportunidad y estado.
- `GET /api/vnext/episodes/{id}`: observaciones, planes y relaciones, en orden temporal.
- `GET /api/vnext/plans/{id}`: versión inmutable, procedencia y desenlace de su política.
- `POST /api/vnext/trades`: seguimiento simulado o ejecución declarada, elegidos explícitamente.
- `POST /api/vnext/trades/{id}/events`: fill, salida, ajuste o corrección con idempotencia.
- `GET /api/vnext/trades`: operaciones del usuario y estado de ejecución.
- `GET /api/vnext/metrics`: población, política, fechas, horizonte, motor, régimen, configuración y primera/repetida como filtros explícitos.

Respuesta de métricas: definición, numerador, denominador, unidad, media/mediana, costes, abiertos/excluidos/ambiguos, cobertura y procedencia. No devolver únicamente un campo genérico `win_rate`.

Eventos WebSocket propuestos: `episode_updated`, `plan_selected`, `plan_outcome`, `trade_updated`. Cada uno tendrá `event_id`, entidad, versión y tiempo. Las actualizaciones ordinarias no anuncian una nueva oportunidad.

Los endpoints actuales mantienen su contrato mientras existan consumidores. Migrar las pantallas de forma explícita; no cambiar el significado de `signals/stats` conservando el mismo nombre sin versión ni documentación.

Toda escritura de operaciones exige identificar al usuario autorizado, validar el esquema e idempotencia. El hecho de que el sistema actual sea un lector de mercado no justifica exponer escrituras de un diario de operaciones sin esos controles.

## 9. Migración e implementación mínima

Agrupación propuesta de persistencia:

- Fase 1: episodios, snapshots, planes y enlaces a fuentes.
- Fase 2: resultados de política y observaciones por horizonte.
- Fase 3: operaciones del usuario y sus eventos.
- Fase 4: predicciones/estados de motores, enlazados al snapshot y a la política.

No es obligatorio crear una tabla por cada sustantivo del documento: elegir el esquema mínimo que conserve identidad, restricciones y consultas. Sí es obligatorio evitar usar la misma fila mutable para plan original, revisión, resultado simulado y ejecución real.

Restricciones a ensayar:

- Identificador único por entidad y clave idempotente por evento fuente.
- Versión de plan única dentro de su linaje; enlaces que apuntan al plan correcto.
- Una notificación asociada a la versión seleccionada, preservada tras reinicio.
- Índices por símbolo/tiempo, episodio/tiempo y plan/política/horizonte.
- Ningún `INSERT OR IGNORE` silencioso puede considerarse éxito sin revisar si insertó o si la fila existente es realmente equivalente.
- Migraciones con recuentos de origen/destino, integridad de SQLite y recuperación sobre copia consistente.

## 10. Casos de aceptación imprescindibles

1. Primera señal gana y segunda pierde: la primera operación conserva su ganancia; ambas señales siguen en su cohorte correspondiente.
2. Primera pierde y segunda gana: la primera no se reetiqueta; una reentrada explícita produce otra operación.
3. Misma alerta aparece dos veces por reconexión: mismo evento, sin duplicar denominador ni Telegram.
4. Hay `signal_id=NULL`: el plan nuevo tiene identidad, snapshot y resultado propios.
5. Dos marcos se contradicen: ambos quedan visibles; TP/SL no se promedian.
6. Bajista en spot sin recuperación: ninguna compra se infiere de la caída.
7. Recuperación se confirma después: nueva compra candidata con reloj y niveles propios.
8. TP/SL o fill/TP coinciden en la misma vela: ambigüedad explícita, nunca victoria inventada.
9. Vence la ventana sin nuevas velas: cierre por reloj con calidad verificable; no usar cotización futura.
10. Se cambia el objetivo configurado: los planes previos mantienen su política, y los hitos brutos/netos se muestran correctamente.
11. Reinicio con operación abierta y alerta visual ya cerrada: se recuperan las dos entidades sin perder el plan tomado.
12. El usuario compra desde un ranking externo: origen externo, sin atribuir esa entrada a una señal del sistema.
13. Hay una salida parcial: cantidades y costes concilian; no se suma el mismo beneficio dos veces.
14. Se desactiva la nueva versión: la emisión vuelve a la referencia y los planes/operaciones existentes continúan su seguimiento.
