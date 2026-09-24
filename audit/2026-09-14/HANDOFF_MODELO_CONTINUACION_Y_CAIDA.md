# Handoff tecnico: modelo de continuacion y entrada diferida

## Proposito de este documento

Este documento entrega a la siguiente IA el contexto necesario para convertir
el analisis reciente en **instrumentacion en sombra** para el backend y una
lectura honesta para el frontend. No autoriza cambiar las reglas que emiten
alertas ni enviar ordenes. La evidencia todavia no alcanza para eso.

La hipotesis no es una sola estrategia. Son dos recorridos distintos desde la
misma senal:

1. **Continuacion:** el precio llega a `+3.2%` antes de tocar el stop. La
   entrada candidata es superficial, entre la entrada original y `-0.5%`.
2. **Caida / espera:** el precio cae antes de llegar a `+3.2%`. Una entrada
   diferida podria tener sentido entre `-1.5%` y `-2.5%`, pero aun no hay una
   ventaja estadisticamente confirmada.

Hay un tercer resultado que no se debe esconder: **indeterminado / no operar**.
El inverso de un score de continuacion no es automaticamente una prediccion de
caida. Incluye señales planas, datos insuficientes y rutas que no pertenecen a
ninguna de las dos politicas.

## Actualizacion de implementacion, 14-sep

Se implementaron dos cambios de producto sin convertir los modelos en reglas
de ejecucion:

1. `backend/src/state/active_alert.py` resetea la fase accionable cuando la
   señal alcanza `+3.2%`. Si el TP congelado es menor que esa meta, tocarlo
   abre una observacion de extension de cuatro horas configurables en vez de
   cerrar de inmediato. Si no excede el TP, se resetea con
   `TP_CORTO_SIN_EXTENSION`. La alerta sigue en seguimiento para conservar el
   recorrido de 24 h y permitir una nueva emisión tras el cooldown normal.
2. El tablero ahora usa tarjetas en `frontend/src/components/PairCard.tsx`.
   Muestra el ranking actual de `rango_1h_pct` como lectura de continuación en
   sombra y las bandas de retroceso como medición. El clasificador completo y
   la ruta de caída no se usan para vetar, alertar ni recomendar compras.

Verificado: cinco pruebas del ciclo de vida pasan, `python -m compileall -q
backend` pasa y `frontend/npm run build` pasa. `npm run lint` sigue fallando
por una regla previa en `frontend/src/hooks/useNotifications.ts:37`, no tocada
por esta implementación.

---

## Resumen ejecutivo

- La medicion util se limita a outcomes emitidos, cerrados a 24 h, con
  `cobertura_velas >= 0.98` y `strategy_version = f82bcff`. La referencia
  anterior basada en ventanas incompletas no se debe reutilizar.
- En el snapshot direccional hay 391 senales de 184 simbolos. El 27.9% llego
  a `+3.2%` alguna vez; solo 68 de 346 rutas resueltas lo hicieron **antes**
  del SL. El modelo de ranking de continuacion es prometedor, no calibrado:
  AUC agrupado por simbolo 0.736 y AUC cronologico del 13-sep 0.740.
- En las 279 rutas que tocaron SL antes de `+3.2%`, el SL planeado no describe
  el suelo: mediana `-0.84%`, mientras que el minimo de toda la ventana tiene
  mediana `-2.95%`. No usar el promedio de SL como precio de compra.
- La simulacion condicionada a rutas que cayeron sugiere una zona de espera de
  `-1.5%` a `-2.5%`. El supuesto mejor punto, `-2.5%` con SL nuevo de `-1%`,
  solo da `+0.12%` medio antes de costes con IC95 `[-0.12%, +0.37%]`.
  Es indistinguible de cero y esta seleccionado con informacion futura.
- El backend ya tiene snapshots ricos de la senal y un tracker de outcomes;
  falta un contrato para guardar predicciones y politicas hipoteticas. El
  frontend ya evita presentar una probabilidad falsa, pero actualmente no
  compila por una nulabilidad en `PairDetail.tsx`.

---

## Evidencia y definiciones exactas

### Cohortes

Los scripts leen `sacbinance.db` por SSH en modo SQLite de solo lectura. Las
filas se excluyen si son sombra, no cerraron su ventana de 24 h, tienen una
version diferente o cobertura inferior al 98%.

| Medicion | Cohorte | Resultado |
| --- | ---: | --- |
| Modelo direccional | 391 | 109 llegaron a `+3.2%` alguna vez (27.9%) |
| Ruta operativa | 346 | 68 `+3.2%` antes de SL; 278 SL antes de `+3.2%` |
| Reconstruccion de stops | 298 | 279 SL antes de `+3.2%`; 19 meta antes de SL |
| Grid de entrada diferida | 392 | 279 caidas, 68 continuaciones, 45 neutrales |

Las consultas se ejecutaron contra una base que sigue madurando outcomes. Por
eso hay 391 y 392 en artefactos distintos: una fila termino su ventana entre
consultas. No mezclar esos conteos como si fueran un mismo snapshot congelado.
Cuando se inicie una validacion formal, generar una exportacion con un corte de
tiempo unico y guardar su hash.

### Etiquetas usadas en el analisis

| Etiqueta | Definicion temporal |
| --- | --- |
| `reached_32` | `ms_up_32` no es nulo dentro de 24 h |
| `up32_before_sl` | llega a `+3.2%` y no hay SL previo |
| `sl_before_up32` | toca SL y no hay `+3.2%` previo |
| `continua_limpia` | llega a `+3.2%` y nunca toca SL |
| `neutral` | no toca SL ni llega a `+3.2%` |

Para decidir la direccion se usaron objetivos que no dependen del ancho del
SL. `sl_pct` y `tp_pct` son politica de ejecucion, no caracteristicas
predictivas: incluirlos para pronosticar que se toque SL produciria una fuga
mecanica de la politica hacia el modelo.

### Modelo de continuacion: lo que se sostiene

El analisis usa una regresion logistica L1 fuertemente regularizada con
validacion por grupos de simbolo y una prueba cronologica. No se debe copiar
como "probabilidad" de produccion. Sirve como ranking en sombra.

| Objetivo | AUC por simbolo | AUC cronologico 13-sep | Top 20% | Base |
| --- | ---: | ---: | ---: | ---: |
| Llega a `+3.2%` alguna vez | 0.736 | 0.740 | 53.2% | 27.9% |
| `+3.2%` antes de SL | 0.755 | 0.761 | 40.0% | 19.7% |

Los terminos que conservaron signo en los folds son: `score` alto,
`vol_24h` menor, `ruido_1m_pct` alto, `atr_pct` alto; en la ruta operativa se
suman distancia a soporte y resistencia. Rango de 1 h y volatilidad tambien
separan, pero estan muy correlacionados entre si. No apilar filtros que miden
el mismo regimen de expansion.

Interpretacion: el modelo parece reconocer expansion posterior al retroceso.
No prueba causalidad, no estima aun una probabilidad calibrada por moneda y
solo tiene dos dias materiales. El score de produccion inicial debe llamarse
`continuation_rank_shadow`, no `probabilidad de exito`.

### Rutas que cayeron antes de la meta

La poblacion relevante para una entrada diferida son solo las 279 rutas con
SL antes de `+3.2%`, no las 19 que llegaron a meta primero y tocaron el SL
despues.

| Profundidad desde entrada | Media | p25 | Mediana | p75 | p90 | Maximo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SL planeado | 1.17% | 0.58% | 0.84% | 1.42% | 2.28% | 5.34% |
| Minimo de la primera vela que toca SL | 1.30% | 0.65% | 0.97% | 1.59% | 2.46% | 5.52% |
| Minimo de toda la ventana de 24 h | 3.66% | 2.08% | 2.95% | 4.62% | 6.50% | 17.66% |

El minimo de 24 h puede suceder muchas horas despues de un stop ejecutable;
no es una perdida de una operacion que respeta SL ni una entrada recomendada.
La mediana al primer SL fue 236 minutos. El 54.1% de las rutas no alcanzo ni
`+0.5%` antes de caer al stop.

De los 175 stops cuya primera vela quedo a no mas de 0.10 puntos porcentuales
por debajo del SL planeado, 109 (62.3%) recuperaron al menos la entrada desde
la vela siguiente. Solo 24 (13.7%) llegaron a `+3.2%` despues. Recuperar la
entrada no convierte automaticamente un stop en una oportunidad rentable.

### Simulacion de entradas limite inferiores

La simulacion compra con una orden limite al precio de entrada original menos
el offset. El maximo de la vela de llenado no cuenta como ganancia porque puede
haber ocurrido antes del minimo que llena la orden. El minimo de esa vela si
cuenta como adversidad. Es una convencion conservadora para barras de un
minuto.

#### Rutas que continuaron (`+3.2%` antes de SL, n=68)

| Limite inferior | Se llena | Llega a `+3.2%` tras llenar | `+3.2%` antes de SL nuevo -2% |
| --- | ---: | ---: | ---: |
| -0.25% | 86.8% | 88.1% | 76.3% |
| -0.50% | 77.9% | 83.0% | 69.8% |
| -0.75% | 60.3% | 70.7% | 61.0% |
| -1.00% | 51.5% | 62.9% | 54.3% |

La hipotesis de continuacion para sombra es por tanto **limite entre 0% y
-0.5%**. `+0.5%` no se midio como orden limite: seria una entrada de ruptura
por confirmacion y requiere un experimento separado.

#### Rutas que cayeron (`SL antes de +3.2%`, n=279)

| Limite inferior | Se llena | Llega a `+3.2%` tras llenar | MAE mediano despues del llenado |
| --- | ---: | ---: | ---: |
| -1.50% | 88.9% | 23.4% | 1.66% |
| -2.00% | 76.3% | 24.9% | 1.58% |
| -2.50% | 61.6% | 27.3% | 1.66% |
| -3.00% | 49.1% | 24.8% | 1.72% |

Con un SL hipotetico nuevo de `-1%` desde el llenado, los retornos medios por
llenado fueron `-0.14%`, `-0.03%`, `+0.12%` y `-0.01%` respectivamente. Los
IC95 de esos cuatro resultados abarcan cero. El de `-2.5%` es `[-0.12%,
+0.37%]` antes de comisiones y deslizamiento. No elegir un unico "ganador".
La zona de experimento es `-1.5%` a `-2.5%` y debe contrastarse fuera de
muestra sobre todas las senales futuras.

---

## Decisiones que NO estan justificadas

1. No activar compras reales, alertas automaticas nuevas ni cambios de TP/SL.
2. No declarar que una senal de score bajo "va a caer". El modelo actual solo
   tiene evidencia razonable para rankear continuaciones.
3. No ensanchar el SL global porque algunas senales recuperen despues. La gran
   mayoria de stops no tuvo rebote previo significativo y el 24 h posterior
   puede seguir profundizando.
4. No mostrar `prob_meta` como probabilidad de operacion. La propia UI actual
   advierte correctamente que son observaciones repetidas, pueden incluir SL
   previo y no son operaciones independientes.
5. No entrenar ni validar con filas de cobertura menor de 98%, con version de
   estrategia distinta o con outcomes de sombra mezclados sin etiquetar.
6. No usar `sl_pct`, `tp_pct`, `take_profit`, `stop_loss`, `ms_*`, MFE, MAE
   ni datos posteriores a la emision como entradas del modelo direccional.

---

## Trabajo requerido en backend

### Fase 0: reparar y preservar el estado actual

No revertir los cambios sin commitear de otra IA. Estan en:

- `backend/src/persistence/db.py`
- `frontend/src/components/Dashboard.tsx`
- `frontend/src/components/Historial.tsx`
- `frontend/src/components/PairDetail.tsx`
- `frontend/src/components/PairRow.tsx`
- `frontend/src/components/SignalStats.tsx`
- `frontend/src/types/index.ts`
- `frontend/src/components/ProbabilityContext.tsx` (nuevo)
- `frontend/src/domain/reading.ts` (nuevo)

El backend compila con `python -m compileall -q backend`.

El frontend **no** compila al momento de escribir este documento. `npm run
build` falla con `TS18048` en `frontend/src/components/PairDetail.tsx:40`:
la condicion `pair.alerta?.entrada_alt > 0` no estrecha de forma suficiente
`pair.alerta` ni `entrada_alt` en el JSX posterior. Resolver antes de integrar
cualquier vista nueva, por ejemplo almacenando `const alerta = pair.alerta` y
usando una guarda explicita `alerta?.entrada_alt != null && alerta.entrada_alt
> 0` antes de leer `alerta.entrada_alt` y `alerta.meta`.

Tambien mantener alineado el contrato de historial: `get_historial()` ya envia
`objetivo_alcanzable`, pero `HistoryRow` de `frontend/src/domain/reading.ts`
no lo declara. Hoy no rompe porque no se consume; al usarlo, incorporar el
campo opcional al tipo o dejar de enviarlo. No presentar ausencia historica
como `false`.

### Fase 1: artefacto de inferencia, no entrenamiento en el servidor

Crear un modulo nuevo, por ejemplo:

```
backend/src/analysis/continuation_shadow.py
backend/src/analysis/model_artifacts/continuation_shadow_v1.json
research/train_continuation_shadow.py
```

El entrenamiento es offline. El runtime actual no declara scikit-learn en
`backend/requirements.txt`; no agregar entrenamiento pesado ni dependencia de
scikit-learn al daemon solo para inferir. El entrenador puede usar
scikit-learn y debe exportar un JSON autocontenido con:

```json
{
  "model_version": "continuation-shadow-v1",
  "trained_at": "ISO-8601",
  "source_cutoff_ts": 0,
  "strategy_versions": ["f82bcff"],
  "min_coverage": 0.98,
  "target": "ms_up_32 is present within 24h",
  "feature_schema": ["score", "log1p_vol_24h", "ruido_1m_pct", "atr_pct"],
  "imputation": {},
  "standardization": {},
  "coefficients": {},
  "intercept": 0.0,
  "oof_metrics": {},
  "calibration_bins": []
}
```

Empezar con las cuatro variables estables y disponibles en todas las señales:
`score`, `log1p(vol_24h)`, `ruido_1m_pct`, `atr_pct`. No transportar a
produccion el modelo de 39 variables de exploracion sin una exportacion y un
contrato de imputacion reproducibles.

`continuation_shadow.py` debe:

1. Validar tipos, finitud, version del artefacto y esquema de features.
2. Aplicar exactamente la transformacion, mediana y estandarizacion del JSON.
3. Devolver un ranking `0..100` y, solo si supera validacion de calibracion,
   una probabilidad con etiqueta de que esta en sombra.
4. Devolver `UNKNOWN` con razones si faltan datos; nunca imputar silenciosamente
   con cero para volumen, ATR o ruido.
5. No leer outcomes futuros ni actualizar el artefacto desde el proceso vivo.

Por ahora la salida recomendada es:

```python
{
    "model_version": "continuation-shadow-v1",
    "status": "SHADOW" | "UNKNOWN",
    "continuation_rank": 0.0,          # 0..100; no promesa de exito
    "probability": None,               # null hasta calibracion valida
    "route": "CONTINUATION" | "UNDECIDED",
    "reasons": ["score alto", "ATR alto"],
    "feature_quality": "complete" | "partial" | "invalid"
}
```

El primer umbral de `CONTINUATION` debe seleccionarse con predicciones OOF
congeladas y documentadas, no con el score de la misma fila entrenada. Una
opcion inicial es el quintil superior OOF, pero debe quedar como configuracion
versionada y no como constante magica.

### Fase 2: medir bandas de caida absolutas

No entrenar una etiqueta `toco_sl`; su umbral cambia con ATR. Crear etiquetas
de precio absoluto relativas a la entrada:

```
hit_dn_15   # minimo <= entry * 0.985 dentro de 24 h
hit_dn_20   # minimo <= entry * 0.980
hit_dn_25   # minimo <= entry * 0.975
ms_dn_15, ms_dn_20, ms_dn_25
```

Los nombres pueden seguir la convencion existente de `ms_dn_*`, pero no
sobrescribir los marcadores actuales. El tracker ya persiste velas y sigue
outcomes hasta 24 h en `backend/src/analysis/outcome_tracker.py`; extenderlo
ahi para guardar el primer toque de cada banda desde la misma entrada.

Para evaluar una politica limite de verdad, crear una tabla independiente en
vez de añadir decenas de columnas a `outcomes`:

```sql
CREATE TABLE IF NOT EXISTS shadow_policy_outcomes (
    signal_id INTEGER NOT NULL,
    policy_version TEXT NOT NULL,
    route TEXT NOT NULL,
    entry_offset_pct REAL NOT NULL,
    target_pct REAL NOT NULL,
    post_fill_stop_pct REAL NOT NULL,
    filled INTEGER NOT NULL DEFAULT 0,
    ms_fill INTEGER,
    fill_price REAL,
    ms_target INTEGER,
    ms_stop INTEGER,
    mae_after_fill_pct REAL,
    mfe_after_fill_pct REAL,
    close_return_pct REAL,
    resolved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (signal_id, policy_version, entry_offset_pct, post_fill_stop_pct)
);
CREATE INDEX IF NOT EXISTS idx_shadow_policy_version
    ON shadow_policy_outcomes(policy_version, resolved, signal_id);
```

La semantica debe coincidir con la simulacion:

- Llenar si el minimo de una vela de 1m toca el limite.
- No contar el maximo de esa misma vela como TP, porque su orden intravela es
  desconocido. Si minimo y maximo cruzan en la misma vela, marcar el orden como
  ambiguo o usar la convención conservadora ya usada por el script.
- Desde el llenado, medir TP `+3.2%`, SL nuevo relativo al precio de llenado,
  MFE, MAE y retorno de cierre de ventana.
- Registrar una fila por cada politica versionada; no actualizar los resultados
  de una politica anterior cuando se cambian offsets o stops.

Primera matriz de sombra recomendada:

| Ruta | Offsets | TP | SL nuevo desde llenado |
| --- | --- | --- | --- |
| `CONTINUATION` | `0`, `-0.25`, `-0.5` | `+3.2%` | `-2.0%` |
| `WAIT_PULLBACK` | `-1.5`, `-2.0`, `-2.5` | `+3.2%` | `-1.0`, `-1.5`, `-2.0` |

Todavia no asignar `WAIT_PULLBACK` automaticamente desde el modelo. Durante
la primera fase, medir la matriz para **todas** las senales emitidas y reportar
despues por quantil de `continuation_rank`. Eso permite descubrir si una zona
de entrada funciona realmente en el quintil bajo, sin inventar un clasificador
de caida prematuro.

### Fase 3: persistir prediccion y procedencia

Agregar una tabla separada, por ejemplo:

```sql
CREATE TABLE IF NOT EXISTS signal_model_snapshots (
    signal_id INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    ts_scored INTEGER NOT NULL,
    strategy_version TEXT,
    config_hash TEXT,
    feature_schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    continuation_rank REAL,
    calibrated_probability REAL,
    route TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    feature_quality TEXT NOT NULL,
    PRIMARY KEY (signal_id, model_version)
);
CREATE INDEX IF NOT EXISTS idx_model_snapshot_scored
    ON signal_model_snapshots(ts_scored DESC);
```

No guardar solamente el numero final en `outcomes`: se perderian el modelo,
la version de estrategia, el hash de configuracion y los motivos con los que
se tomo la lectura. La tabla soporta reentrenamientos sin reinterpretar el
pasado.

Incrementar `SCHEMA_VERSION` en `backend/src/persistence/db.py` y seguir el
patron idempotente de `_migrate()`. Crear las tablas por `executescript` y no
hacer una migracion que destruya outcomes existentes.

### Puntos concretos de integracion

| Modulo existente | Cambio requerido |
| --- | --- |
| `backend/src/state/engine.py` | Cuando se construye el `snapshot` y antes de emitir/abrir el outcome, calcular y persistir el snapshot de modelo. Publicarlo en el snapshot vivo. No usarlo en vetos ni en Telegram todavia. |
| `backend/src/analysis/outcome_tracker.py` | Extender el seguimiento de bandas y poblar `shadow_policy_outcomes` hasta cerrar las 24 h. |
| `backend/src/persistence/db.py` | DDL, migracion, insercion idempotente y consultas de snapshots/politicas. Mantener `get_historial()` compatible. |
| `backend/src/state/symbol_state.py` | Incluir `model_context` inmutable o el ultimo snapshot asociado a la alerta en `snapshot()`. |
| `backend/src/api/routes.py` | Exponer el contexto actual por WebSocket/snapshot y un endpoint de analitica agregada. No exponer el JSON interno completo de features por defecto. |
| `backend/src/api/ws_server.py` | Confirmar que la nueva clave de snapshot llega a los clientes sin romper el contrato de mensajes. |

Contrato de API sugerido para una alerta activa:

```json
{
  "model_context": {
    "status": "SHADOW",
    "model_version": "continuation-shadow-v1",
    "continuation_rank": 84.0,
    "calibrated_probability": null,
    "route": "CONTINUATION",
    "entry_zone": {"min_offset_pct": -0.5, "max_offset_pct": 0.0},
    "reasons": ["score alto", "ATR alto"],
    "feature_quality": "complete"
  }
}
```

Para `UNDECIDED`, enviar zona `null`; no mostrar una recomendacion de compra
profunda. Una futura ruta `WAIT_PULLBACK` debe existir solo despues de validar
una probabilidad de tocar bandas absolutas fuera de muestra.

### Pruebas de aceptacion backend

1. Una señal con los cuatro features validos produce siempre el mismo rank
   para el mismo artefacto y snapshot.
2. Una señal con `vol_24h`, `atr_pct` o `ruido_1m_pct` invalidos devuelve
   `UNKNOWN` y conserva la razon; no se cae el engine.
3. Cambiar el modelo crea un nuevo `signal_model_snapshots` y nunca altera el
   snapshot historico anterior.
4. Un limite `-2%` no se llena por una vela cuyo minimo queda por encima del
   limite; se llena cuando lo toca.
5. Una vela que podria contener TP y llenado no acredita TP previo al fill.
6. El resultado de una politica se cierra a 24 h aunque deje de llegar stream
   del simbolo, igual que `OutcomeTracker.cerrar_vencidos()`.
7. Consultas de historial existentes siguen devolviendo las mismas claves y
   los clientes anteriores no fallan por `model_context` adicional.
8. Las pruebas usan cobertura, version de estrategia y `sombra` iguales a las
   definiciones de este documento.

---

## Trabajo requerido en frontend

### Reparacion necesaria antes de la nueva UI

Corregir la nulabilidad de `PairDetail.tsx` descrita en Fase 0. Ejecutar:

```powershell
cd D:\SACBinance\frontend
npm run build
```

El build debe terminar con el chequeo de TypeScript y Vite. No se verifico un
servidor de desarrollo porque el build actual falla antes de poder revisarlo.

### Contrato TypeScript

Agregar tipos opcionales y tolerantes a versiones anteriores en
`frontend/src/types/index.ts`:

```ts
export interface ModelContext {
  status: "SHADOW" | "UNKNOWN";
  model_version?: string | null;
  continuation_rank?: number | null;
  calibrated_probability?: number | null;
  route: "CONTINUATION" | "UNDECIDED" | "WAIT_PULLBACK";
  entry_zone?: { min_offset_pct: number; max_offset_pct: number } | null;
  reasons?: string[];
  feature_quality?: "complete" | "partial" | "invalid";
}
```

Agregar `model_context?: ModelContext | null` a `PairState` y declarar los
campos nuevos de historial como opcionales si se muestran. No convertir `null`
en cero ni asumir que una alerta vieja tiene modelo.

### Lectura en `PairDetail`

Reemplazar el actual bloque fijo de `ProbabilityContext` por una lectura que
distinga tres estados:

| Estado | Lo que se muestra | Lo que nunca se muestra |
| --- | --- | --- |
| `SHADOW` + `CONTINUATION` | "Continuacion en observacion", rank, version, zona `0% a -0.5%`, razones y advertencia de no ejecucion | "Probabilidad de ganar" si no hay calibracion |
| `SHADOW` + `UNDECIDED` | "Sin ruta operativa asignada", calidad de datos y razones | una zona de compra profunda inventada |
| `UNKNOWN` | "Lectura no disponible", motivo de datos/version | 0%, score falso o error silencioso |

Cuando exista calibracion suficiente, la UI puede enseñar una probabilidad
solo con su fecha de corte, n, tasa base, banda de calibracion y texto
"estimacion en sombra". El `prob_meta` actual debe permanecer separado como
referencia historica descriptiva o retirarse; no se debe mezclar con el nuevo
modelo.

La zona no es una orden. Etiquetar la entrada como "zona hipotetica de
observacion" y conservar el plan congelado de la alerta como la unica
referencia del plan emitido. Usar el mismo lenguaje en `PairRow`, `PairDetail`
y `Historial`.

### Vistas agregadas

No crear una pagina de marketing ni tarjetas decorativas. Extender el tablero
operativo con una vista compacta, por ejemplo en `SignalStats.tsx` o un panel
desplegable, que muestre por `model_version` y por `continuation_rank`:

- señales observadas y outcomes maduros;
- fill rate de cada limite;
- `+3.2%` antes de SL nuevo;
- retorno medio **neto** al añadir costes;
- mediana/p75 de MAE tras llenado;
- cobertura y rango de fechas.

No mostrar un ratio para una celda sin n suficiente. La API agregada debe
entregar `n`, conteos, definicion de la politica y cobertura junto a cada tasa.

### Pruebas de aceptacion frontend

1. Una alerta antigua sin `model_context` se renderiza sin excepciones.
2. `SHADOW` no usa estilos de exito/ganancia ni botones de compra.
3. `UNKNOWN` explica que faltan datos o version y no muestra `0%`.
4. La zona `0% a -0.5%` se entiende como offset relativo, no como precio
   absoluto ni como TP/SL actual.
5. El historial conserva la distincion actual entre TP antes de SL, SL antes
   de meta, meta posterior a SL y orden ambiguo.
6. `npm run build` pasa y las cadenas largas no desbordan el panel en desktop
   ni movil.

---

## Riesgo de cobertura de alertas (F04)

Existe una limitacion independiente que la siguiente IA debe mantener visible:
576 de 1,454 alertas emitidas (40%) no tienen `signal_id` en
`alertas_emitidas`. El analisis actual usa `outcomes` emitidos, por lo que no
es todavia una auditoria completa de todo lo que el operador vio por Telegram.

No mezclar alertas sin outcome propio con el entrenamiento hasta resolver el
enlace. Antes de declarar que el modelo mejora la experiencia real del
operador, completar F04: cada alerta emitida con niveles debe abrir o enlazar
un outcome inmutable que pueda seguirse 24 h. Esa correccion es prioritaria
respecto a poner el modelo en decisiones reales.

---

## Artefactos disponibles

Los siguientes archivos se crearon para este analisis. Son de solo lectura
respecto a la base remota; se pueden ejecutar desde PowerShell si existe el
alias SSH `sac` y acceso al host.

| Artefacto | Para que sirve |
| --- | --- |
| `C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se\work\analyze_live_continuations.py` | Extrae la cohorte limpia, perfila variables y valida el ranking de continuacion. |
| `C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se\work\analyze_live_stop_paths.py` | Reconstruye velas de 1 min hasta el primer SL y separa stop antes/depués de la meta. |
| `C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se\work\analyze_live_lower_entry_grid.py` | Simula limites inferiores y SL nuevos; incluye IC95 descriptivo de retorno medio. |
| `C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se\outputs\live_continuations_analysis_2026-09-14.json` | Metricas, validacion, variables y calidad del snapshot de continuacion. |
| `C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se\outputs\live_stop_path_analysis_2026-09-14.json` | Profundidades, tiempo a stop, recuperaciones y arquetipos de las caidas. |
| `C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se\outputs\live_lower_entry_grid_2026-09-14.json` | Grid completo por grupo, offset y SL hipotetico. |
| `audit/2026-09-14/ANALISIS_FIN_DE_SEMANA.md` | Auditoria previa: cobertura, reloj, vetos, objetivo por grupo y F04. |

Comandos de reproduccion:

```powershell
cd C:\Users\felix\Documents\Codex\2026-09-09\grupos-listos-sobre-1-319-se
python work\analyze_live_continuations.py
python work\analyze_live_stop_paths.py
python work\analyze_live_lower_entry_grid.py
```

Los scripts leen la base activa. No sobrescriben `D:\SACBinance`, pero sus
conteos pueden cambiar porque nuevas ventanas de 24 h se cierran continuamente.

---

## Orden recomendado de implementacion

1. Corregir el build de frontend y comprobar que los cambios no commiteados
   actuales siguen intactos.
2. Resolver F04 o, como minimo, impedir que el nuevo informe llame
   "representativa" a una muestra que omite alertas sin outcome.
3. Crear migracion y tablas de snapshots/politicas en sombra.
4. Implementar inferencia determinista del artefacto de continuacion y
   persistirla, sin usarla como veto ni como orden.
5. Medir la matriz de limites para todas las nuevas senales durante al menos
   siete dias y con un corte de datos versionado.
6. Entrenar el modelo de bandas absolutas de caida solo cuando exista muestra
   suficiente, con split cronologico final reservado y costes incluidos.
7. Solo entonces decidir si una tercera ruta `WAIT_PULLBACK` merece aparecer
   como recomendacion operativa.

El criterio de salida no es un AUC bonito. Debe haber retorno neto fuera de
muestra, fill rate, drawdown post-llenado, cobertura, n suficiente y una
ventaja que sobreviva a comisiones y deslizamiento.
