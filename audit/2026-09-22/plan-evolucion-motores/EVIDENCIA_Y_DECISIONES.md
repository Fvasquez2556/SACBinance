# Evidencia y decisiones para la próxima actualización

Estado: análisis realizado; recomendaciones de diseño, todavía sin implementación del producto.

Captura: **22-sep-2026 01:02:26 UTC / 21-sep-2026 19:02:26 Guatemala**. Fuente: base de producción, transacción SQLite en solo lectura. La captura local queda congelada en [datos/snapshot.json.gz](datos/snapshot.json.gz), con huella en [manifest.json](datos/manifest.json).

## 1. Respuesta sobre +4,2 % netos

**+4,2 % netos es un candidato razonable para probar; los datos no justifican bajarlo por defecto, pero tampoco acreditan todavía que sustituya al TP actual.** La mejora histórica frente al TP variable vigente es pequeña. Una salida fija de +4,2 % netos gana menos veces que una de +3,2 % netos y necesita más tiempo; en esta muestra produce mayor resultado medio.

Hay tres conceptos diferentes:

- **Meta deseada:** cuánto se quiere ganar en una operación exitosa.
- **Resultado medio neto:** media de ganancias, pérdidas y cierres al vencer. Este es el rendimiento medio simulado por aviso.
- **Máximo recorrido favorable:** cuánto llegó a subir el precio dentro de la ventana, incluso después de un stop. No equivale a una ganancia cobrada.

En la configuración más reciente, el máximo favorable de 12 h es **+5,48 % bruto de media y +3,96 % de mediana**. La media supera la mediana por los movimientos grandes. No sería correcto convertir ese +5,48 % en un TP recomendado o descontarle el coste y llamarlo beneficio obtenido.

### Comparación principal: misma configuración, entradas, stops y ventana

Se usan **176 avisos de Telegram**, configuración `a870caf2dc2d`, 18–21 sep UTC, 111 símbolos y cuatro días. Todas sus ventanas de 12 h están completas y contienen el 100 % de los minutos enteros esperados. Se mantiene el stop original de cada aviso. Coste aditivo supuesto: 0,5 puntos porcentuales por operación.

| Política de salida | Barrera bruta | Objetivo antes del SL | Media neta por aviso | Mediana neta | Tiempo mediano al objetivo, solo aciertos |
| --- | --- | --- | --- | --- | --- |
| TP variable original | La del plan | 45/176 · 25,6 % | +0,895 % | +0,472 % | 4,87 h |
| Fija +1,2 % neto | +1,7 % | 132/176 · 75,0 % | +0,314 % | +1,200 % | 1,91 h |
| Fija +2,2 % neto | +2,7 % | 105/176 · 59,7 % | +0,603 % | +2,200 % | 2,76 h |
| Fija +2,7 % neto | +3,2 % | 99/176 · 56,3 % | +0,724 % | +2,700 % | 3,26 h |
| Fija +3,2 % neto | +3,7 % | 87/176 · 49,4 % | +0,699 % | +2,392 % | 4,74 h |
| **Fija +4,2 % neto** | **+4,7 %** | **73/176 · 41,5 %** | **+0,942 %** | **+1,072 %** | **5,66 h** |
| Fija +5,2 % neto | +5,7 % | 53/176 · 30,1 % | +0,943 % | +0,720 % | 5,76 h |

La tabla mide siete políticas hipotéticas, no siete operaciones reales por aviso. Si el objetivo y el stop no se alcanzan, se valora una salida al último cierre entero de la ventana; se descuentan costes en todos los desenlaces. Los tiempos son condicionales a alcanzar el objetivo, no tiempos esperados de todas las operaciones.

Interpretación:

1. Bajar el objetivo mejora la frecuencia de cobro, pero aquí no mejora automáticamente la media. +1,2 % neto acierta el 75 % y deja una media muy inferior al plan actual.
2. +4,2 % neto mejora la media frente a +3,2 % neto en **0,243 puntos por aviso**, mientras la mediana baja. No es una mejora de todos los aspectos del resultado.
3. Frente al **TP variable actual**, +4,2 % solo mejora **0,047 puntos por aviso**. El intervalo exploratorio de la diferencia, remuestreando por día, es **[−0,066; +0,234]**. No demuestra superioridad.
4. +5,2 % neto aporta casi la misma media que +4,2 %, con menos aciertos. La muestra sugiere estudiar +4,2 % antes que perseguir objetivos aún mayores. No establece un óptimo universal.
5. Con coste realizado supuesto de 0,8 %, manteniendo las barreras originales de la simulación, la media de +4,2 % baja a +0,642 %. No se promete que ese coste cubra cualquier spread, salto de precio o ejecución.

Los intervalos por día son exploratorios: solo hay cuatro días en la configuración principal, los símbolos se repiten y puede haber dependencia entre días. No son una prueba fuera de muestra ni corrigen haber inspeccionado varias alternativas.

### Subir el filtro no es cambiar la salida

Actualmente `objetivo_operador_pct` participa en `candidate_reason()`: exige que el **TP ya calculado** ofrezca al menos esa rentabilidad neta. El TP continúa saliendo de la estructura/ruido del stop y de `rr_target`.

Por eso, poner `objetivo_operador_pct=4.2` **no hace que el sistema cobre a +4,2 % netos**: cambia qué candidatos pasan el filtro. De los 176 avisos maduros actuales, 40 no pasarían ese mínimo según su TP original. Este recuento retrospectivo no simula qué candidatos descartados habrían ocupado sus lugares en el lote de avisos.

La futura configuración debe distinguir:

- `operator_goal_net_pct`: aspiración del operador.
- `min_offered_net_pct`: mínimo para admitir un plan.
- `exit_policy`: TP estructural, fijo neto o política experimental.
- `milestone_net_pct`: aviso informativo, sin implicar venta ni cierre del plan.
- `cost_model_id`: versión del cálculo de costes.

No cambiar conjuntamente filtro, entrada, stop y salida en la primera prueba: impediría identificar qué produjo el resultado.

### El horizonte también es parte de la estrategia

La comparación se hizo además a 1, 4 y 24 h. Las cohortes tienen distinta madurez y tamaño: **no deben compararse como si fueran las mismas operaciones**. En particular, el buen resultado a 12 h no acredita una estrategia para cobrar +4,2 % en pocos minutos. Antes de elegir otro horizonte, repetir todos los horizontes sobre una cohorte común madura a 24 h y reconstruir la ocupación de capital.

## 2. Qué datos existen y cuáles sirven para cada pregunta

Inventario de producción al corte:

- 6.231 registros en `signals`.
- 8.364 en `outcomes`, incluidos seguimientos en sombra e históricos de otras configuraciones.
- 8.839 en `alertas_emitidas`; el export contiene 8.827 desde el primer aviso enviado retenido.
- **258 avisos enviados a Telegram**: del 10-sep 23:49 UTC al 22-sep 00:17 UTC.
- 218 planes en `notificacion_planes`, todos con niveles coincidentes con su alerta en los casos enlazados.
- 17.670 rupturas cortas: 8.317 alcistas y 9.353 bajistas.
- 48.240 rupturas por marco, repartidas entre 5m, 15m, 1h y 4h y ambas direcciones.
- Esquema real **15**, leído en `schema_meta`. `PRAGMA user_version` es cero y no representa la versión de este proyecto.

Para la comparación completa de 12 h:

- Se excluyen 31 avisos con ventana abierta y cuatro con cobertura inferior al 98 %.
- Quedan **223 avisos** de todas las configuraciones; 176 pertenecen a la más reciente.
- La media neta del plan original sobre los 223 es +0,509 %; con +4,2 % neto fijo es +0,536 %. Esa diferencia tampoco demuestra una mejora.

Las 65.910 rupturas de ambos registros no son 65.910 oportunidades independientes. Varios marcos y señales sucesivas pueden describir el mismo movimiento. Su cantidad demuestra capacidad de observación, no precisión predictiva ni rentabilidad.

### Falta una identidad completa por plan

**137 de 258 avisos enviados (53,1 %) no tienen `signal_id`.** En la configuración más reciente son 127 de 207 avisos enviados (61,4 %). Los 207 incluyen ventanas aún abiertas; no son el denominador de la tabla de 176.

Consecuencias:

- Se puede reconstruir el resultado desde `alertas_emitidas`, porque conserva entrada, TP, SL y reloj propios.
- No se puede exigir un enlace a `outcomes` sin excluir muchos avisos efectivamente recibidos.
- Falta contexto persistido en buena parte de la cohorte: entre los 176 maduros, 105 no tienen `btc_regime` recuperable mediante ese enlace. De los 71 conocidos, 70 son alcistas y uno neutral. **No hay una comparación fiable de regímenes bajistas en esta cohorte.**
- No hay tabla de operaciones reales del usuario. Un envío confirmado por Telegram no acredita que el usuario haya comprado.

El código explica una vía concreta para esta separación: `abrir_senal()` puede devolver `None` si ya existe una señal OPEN para el par; la emisión de una nueva alerta con niveles propios puede continuar. No debe forzarse esa alerta a heredar el resultado de la señal anterior.

### La primera señal todavía no tiene una identidad de episodio suficiente

Existe `senal_n` y el motor guarda una primera entrada aproximada por par, con reinicio tras una ventana sin nuevas señales. Esto ayuda a la lectura, pero no constituye un contrato persistente completo que enlace todas las señales de un mismo movimiento, sus marcos y la operación elegida.

Como comprobación acotada se simuló tomar el primer aviso disponible por par y no tomar otro hasta cerrar esa posición hipotética. Con el plan original solo se excluye uno de los 223 avisos; con salida +4,2 % se excluyen tres. **La nueva política de Telegram ya reduce el solapamiento.** Eso no resuelve la mezcla de las métricas globales, las lecturas de diferentes marcos ni las entradas manuales del usuario.

No confundir esta simulación con «primera señal del episodio»: sin identificador de episodio, solo describe una política cronológica de una posición por símbolo.

## 3. Qué hace hoy el sistema

### Datos e indicadores

El motor recibe velas cerradas de 1m y marcos superiores, calcula indicadores y contexto macro, y limita el flujo de `aggTrade` a una shortlist. REST y WebSocket usan volumen cotizado. La retención configurada en el código es de 30 días para 1m/5m/15m y 400 días para marcos mayores; eso no recupera velas ya purgadas anteriormente ni prueba por sí solo cobertura efectiva.

### Lectura direccional

- `ruptures.py` clasifica rupturas cortas desde el estado actual. Es una lectura observada, no un modelo entrenado de rentabilidad.
- `tf_rupture.py` analiza ruptura, confirmación y conflicto por marco.
- `tf_rupture_tracker.py` registra el cambio de dirección por símbolo/marco y mide el recorrido.
- `pair_report.py` presenta lecturas y planes distintos por marco. Su resumen usa el marco confirmado más largo como dominante, con advertencia cuando hay conflicto; no hay prueba aquí de que ese criterio sea el mejor predictor.
- `trade_levels.py` también calcula un plan direccional vendedor cuando la ruptura es bajista. Esa aritmética no corresponde a una compra de rebote en spot. La actualización debe distinguir ambas cosas.

### Selección, planes y Telegram

La política actual selecciona lotes cada 30 segundos, como máximo tres oportunidades nuevas por hora, con cooldown y un plan notificado abierto por par. Congela los niveles, edita el mensaje y mantiene los eventos terminales. El hito +3,2 % sigue siendo bruto y no cierra un plan cuyo TP sea mayor.

Los planes de Telegram y las alertas visuales ya tienen ciclos independientes: la alerta visual puede dejar de ser accionable al alcanzar +3,2 % o por un cambio de estado, mientras el plan notificado sigue abierto. Esa diferencia es intencional, pero puede confundir al usuario que está siguiendo su entrada original.

### Medición y presentación

- `signals`: resultado simulado hasta TP/SL/vencimiento, normalmente a 12 h.
- `outcomes`: recorrido durante 24 h, incluidos hechos posteriores al stop.
- `rupturas` y `rupturas_tf`: excursiones direccionales y retornos por horizonte; no son el registro de una compra real de rebote.
- `notificacion_planes`: plan efectivamente notificado con niveles propios.
- `/api/signals/stats`: agrega `signals` de diferentes versiones; no es la métrica de Telegram ni la del usuario.
- La UI ya avisa que son resultados brutos y que se mezclan versiones. Falta permitir elegir de forma inequívoca la población y política de evaluación.
- La probabilidad histórica de `retroceso.py` responde al alcance de una meta según distancia y edad, no al resultado neto de la próxima operación antes del SL. No se debe reutilizar con otra etiqueta.

## 4. Decisiones recomendadas

1. **Primero identidad y evaluación; después selección más sofisticada.** Sin un plan trazable para cada aviso, mejorar un modelo puede optimizar una muestra que no representa lo que recibe el usuario.
2. **Evolucionar a dos rutas especializadas en una infraestructura común:** continuación alcista y caída/recuperación en spot. No duplicar ingestión, indicadores, almacenamiento y cálculo de resultados.
3. **Mantener dos preguntas separadas:** si el mercado ofrece una compra ahora y cómo evoluciona una operación ya tomada. Una nueva señal no sustituye automáticamente la operación original.
4. **Probar +4,2 % netos como política rival del TP vigente**, manteniendo entrada y stop inicialmente. +3,2 % netos y +2,7 % netos pueden ser comparadores, sin promover un ganador sobre la misma muestra usada para escogerlo.
5. **No ampliar stops automáticamente después de una pérdida.** Estudiar el ruido y la invalidación antes de entrar; después de un SL ejecutado, cualquier rebote es una nueva oportunidad potencial, con otra entrada y otro riesgo.
6. **Guardar las entradas manuales fuera del sistema como población propia.** El relato del usuario sobre entrar en los mayores ganadores es una hipótesis útil de compra tardía, pero no permite atribuir sus pérdidas al motor de Telegram ni recomendar esperar cualquier recuperación.

## 5. Calidad de la comprobación y límites

Se preservó un único export con hash. No se reutilizaron los 229 casos del informe anterior como si fueran una nueva muestra madura: cambian el corte, el reloj de activación, la exigencia de ventana completa y la cobertura.

El reloj principal es `ts_activado` cuando existe, y en avisos antiguos se usa el reloj de creación de la alerta. La demora mediana hasta la activación en la política reciente es de unos 30,1 segundos, coherente con el lote. Activación no es recepción confirmada ni entrada del usuario. Se excluye la vela parcial anterior al reloj de evaluación.

Las salidas se simulan por primer toque. Los empates intravela se separan como ambiguos y se valoran conservadoramente como stop; no hay empates en las comparaciones principales. No se modelan órdenes reales, liquidez individual, saltos que atraviesen el stop ni ejecución parcial.

Las cuentas de los siete objetivos en los 176 avisos se recalcularon con un segundo script independiente leyendo las velas. Coinciden las tasas y las medias. Se verificaron exclusividad de desenlaces, orden temporal, unicidad de velas, cobertura y monotonía del alcance al aumentar el objetivo.

Se compararon 18 archivos locales/remotos del circuito revisado. Catorce coinciden byte a byte y cuatro difieren solo en CRLF/LF: **no se encontró divergencia de contenido entre esos 18 archivos**. Esto no es una comparación completa de todo el repositorio ni una certificación de qué código tiene cargado cada proceso. HEAD local `193e113` y remoto `f82bcff` no representan todos los cambios sin commit.

Comprobaciones de la base local: **62 pruebas de backend, 25 de frontend y comprobación de tipos del frontend, todas correctas**. No se ejecutó despliegue ni se reinició el servicio. Estas pruebas no demuestran rentabilidad y no sustituyen la validación de las futuras migraciones.

## 6. Relación con el trabajo previo y fuentes

Este paquete incorpora el propósito de [continuación y caída del 14-sep](../../2026-09-14/HANDOFF_MODELO_CONTINUACION_Y_CAIDA.md), pero no adopta sus modelos como ganadores. La [comparación posterior](../../2026-09-14/COMPARACION_MODELOS.md) ya mostró que mayor acierto podía acompañarse de peor esperanza. Se conserva ese requisito al diseñar la nueva versión.

También integra la [política de notificaciones](../../2026-09-17/notification-policy/IMPLEMENTACION.md), ahora observada en una base con esquema 15. El estado «pendiente de reiniciar» de ese documento era histórico; en esta captura el servicio está activo desde el 18-sep 04:43:34 UTC.

Referencias metodológicas externas utilizadas:

- [Validación temporal y separación entre ajuste y evaluación, scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html): las políticas elegidas sobre este pasado requieren evaluación posterior separada.
- [Calibración de probabilidades, scikit-learn](https://scikit-learn.org/stable/modules/calibration.html): comprobar las probabilidades con resultados observados y datos distintos de los usados para ajustar el modelo. Una mejora de Brier por sí sola no acredita calibración perfecta.
- [Velas y datos de mercado, documentación oficial de Binance](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market): referencia para conservar la semántica de las velas y sus relojes. Los resultados numéricos del documento proceden del export local, no de esta página.

Reproducción: `python analizar.py` y después `python verificar_analisis.py`, desde esta carpeta o usando su ruta completa. No hace falta contactar el servidor. El detalle legible por máquinas está en [resultados.json](datos/resultados.json); la verificación independiente, en [verification.json](datos/verification.json).
