# Correcciones a la revisión del motor de recorridos

**11-sep-2026.** Verifiqué las afirmaciones de la revisión antes de aplicar nada, corregí los defectos concretos y encontré dos cosas más. **33 comprobaciones nuevas, todas en verde**, y las 23 + 29 anteriores siguen pasando.

## Primero: la auditoría tiene razón

Ejecuté su `check_labeling.py` contra el código anterior y reprodujo sus seis resultados **exactamente**. No es un informe teórico: cada hallazgo venía con su reproducción y todas se sostienen.

## Lo que estaba roto, y por qué importaba

### 1 · Filtración de futuro en las features

`calcular_features()` rellenaba el calentamiento con la media de las **primeras 500 observaciones**:

```python
atr_med[:win] = atr[:win].mean()   # para i=100 con win=500, mira 400 velas del futuro
```

Cambiando solo el futuro, `f_atr_rel[100]` pasaba de 1,0 a **0,294**. Un modelo entrenado con eso aprende del porvenir y parece funcionar hasta que se pone en vivo.

Y hay un agravante que la revisión menciona de pasada y que en mi opinión es peor: el ancho de ventana era `min(500, max(50, n//10))` — **función del largo total de la serie**. Lo medí: la misma vela 600, con el mismo pasado, daba `f_atr_rel` de 1,002391 con 1.000 velas cargadas y 0,996429 con 5.000. Dos corridas del etiquetador sobre rangos distintos producían datasets no comparables, y nada en la salida lo delataba.

El filtro de eventos (`idx > 60`) no cubría ni de lejos la zona contaminada (0..500). Lo comprobé en 1m, 5m y 15m: **en ninguno**.

**Corregido:** ventanas constantes y medias causales por construcción (`_media_causal`), que en el arranque se expanden en vez de rellenarse. Garantía comprobada: si dos series comparten el prefijo 0..i, la feature en i es idéntica aunque el resto difiera — probado sobre las seis features a la vez, no solo en un índice.

### 2 · La identidad borraba trabajo

PK `(symbol, interval, t0)` con `INSERT OR REPLACE`. Etiquetar a 4h y luego a 8h dejaba **solo 8h**; un SL fijo pisaba al de ATR sobre la misma entrada.

**Corregido:** la PK incluye `horizonte_min`, `politica` y `evaluador`. Cada combinación es una fila propia, re-etiquetar lo mismo sigue siendo idempotente, y la versión del evaluador queda registrada para que un cambio de semántica no se confunda con un cambio de mercado.

### 3 · El horizonte se contaba en velas

Con huecos —y el histórico de 1m los tiene— dos velas separadas por una hora pasaban por un horizonte de dos minutos.

**Corregido:** el horizonte es tiempo real en milisegundos. Y cada fila guarda su **cobertura** y su **estado**: `COMPLETO`, `INCOMPLETO` (le faltan velas de en medio) o `PENDIENTE` (la serie no llega al final del horizonte). Son tres cosas distintas y antes eran todas "una etiqueta".

### 4 · MFE medía dos cosas con un nombre

El tracker en vivo mide el recorrido completo de la ventana; el etiquetador medía hasta la vela de salida. Tras un SL en −2% con subida posterior a +5%, una dice +1% y la otra +5%.

**Corregido:** se guardan las dos, `mfe_salida` / `mfe_ventana` (y sus MAE). Comprobado además que `mfe_ventana >= mfe_salida` en todas las filas de una corrida real.

### 5 · `velas_a_tp` mentía por omisión *(esto lo añado yo)*

La revisión lo dejó en su JSON (`bars_until_tp_despite_sl_first: 2`) pero no lo subió a hallazgo. El campo se rellenaba **aunque el SL hubiera ido primero**: la fila decía "SL" y a la vez "llegó al TP en 3 velas". Quien leyera esa columna sin cruzarla con `etiqueta` contaba aciertos que no existieron.

**Corregido:** se conserva —es información real del recorrido— pero ahora es `ms_a_tp` (tiempo real, no velas) y va acompañado de **`tp_primero`**, que es lo único que autoriza a contarlo como acierto.

### 6 · Esquema incompatible

`cargar()` pedía `interval/open/high/low/close/quote_volume`; producción tiene `tf/o/h/l/c/v`. Apuntarlo a la base real fallaba con `no such column: open` — no daba un resultado malo, no daba ninguno.

**Corregido:** detecta el esquema y lee los dos, conservando que `v` es volumen **cotizado** en ambos (mezclarlo con volumen base rompería `vol_rel`, que es un ratio entre ambos).

## Lo que rompí yo y también arreglé

Dos cosas que mis propias correcciones provocaron, y que conviene que consten:

**`frequencies.py` leía las columnas que renombré.** `cargar_labels()` pedía `mfe_pct, mae_pct`. Se habría caído en la primera consulta.

**Y algo peor: habría mezclado evaluaciones.** Al hacer que la tabla contenga varios horizontes y políticas a la vez, un `SELECT ... FROM labels` sin filtro junta horizontes de 4h con los de 8h en la misma frecuencia — exactamente el error que la identidad nueva venía a evitar. Ahora `cargar_labels()` **se niega a leer** si hay más de una evaluación y no se elige cuál, y descarta por defecto las ventanas que no están `COMPLETO`.

## Una corrección de fondo en la estadística

La revisión apunta que `n_min=200` cuenta filas, no muestra independiente. Con etiquetas solapadas eso infla la confianza: mil filas que se pisan casi del todo valen como unas pocas observaciones.

**Corregido:** el umbral se aplica ahora sobre el **tamaño efectivo de muestra de Kish**, `(Σw)² / Σw²` con `w = 1/concurrencia`. En una corrida real de 648 etiquetas, la muestra efectiva es 549,3; y la celda más solapada pasa de **57 filas a 40,0 observaciones independientes**. Esa es la cifra que ahora decide si una celda responde o dice "muestra insuficiente".

## Lo que NO hice, y por qué

La sección «Integración propuesta» de la revisión (A–F) **no son correcciones: es el diseño de un motor nuevo**. Pide `path_evaluator.py` compartido entre streaming y replay, tablas `candidate_episodes` / `evaluation_plans` / `outcome_horizons`, los siete horizontes en producción, captura sistemática de candidatos sin alerta, calibración por perfil y régimen, y una UI que lo muestre.

Eso es una construcción de semanas, cambia la arquitectura de producción y **la revisión misma lo pone como orden recomendado, no como arreglo**. No lo he empezado. Cuando quieras abordarlo, el punto 1 de su orden es el que ya está listo de mi lado y pendiente del tuyo: **desplegar**.

Tampoco he tocado el `prob_meta` del tablero. La revisión tiene razón en que responde otra pregunta (tocar la meta original en 6h, sin exigir que sea antes del SL), pero cambiarlo altera lo que ves en la UI y eso es decisión tuya, no una corrección.

## Estado

| Suite | Resultado |
|---|---|
| Correcciones del etiquetado (nueva) | **33/33** |
| Auditoría del 10-sep | 23/23 |
| Sombra de grupos | 29/29 |
| Backend | importa |

Nada de esto está desplegado: el servidor sigue en `25d03fa`.

## Reproducir

```bash
backend/venv/Scripts/python.exe audit/2026-09-11/path-engine-review/verificar_labeling.py
```

El `check_labeling.py` de la revisión sigue en su sitio y mide el comportamiento **anterior**: sirve para ver el antes y el después.
