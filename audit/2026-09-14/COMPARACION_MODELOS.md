# Comparación de modelos de entrada · 14-sep

**La pregunta:** el sistema lanza una señal. ¿Qué modelo acierta más?

Sobre 393 señales emitidas, cerradas a 24h, cobertura ≥98%, versión `f82bcff`. Entrenamiento con las 235 primeras (11–12 sep), prueba con las 158 siguientes (12–13 sep). Fuera de muestra y en orden cronológico: el modelo nunca ve el tramo con el que se le juzga.

## Primero: el handoff se reproduce

Mi primera ejecución dio AUC 0,47–0,53 contra el 0,736–0,755 que reporta el handoff. **Era un bug mío, no un fallo suyo.**

Lo detecté porque el AUC de *entrenamiento* bajaba a 0,40 al pedir más iteraciones — una regresión logística correcta no puede empeorar sobre sus propios datos. Mi descenso de gradiente divergía: hay features con colas enormes (`vol_24h` va de 1e6 a 6e8) y sin recortar los valores normalizados el optimizador se va. Con el recorte y seguimiento de la pérdida:

| | Mi medición | Handoff |
|---|---|---|
| AUC agrupado por símbolo | **0,727** | 0,736 |
| Solo las 4 features "estables" | **0,770** | — |

El modelo del handoff es real y su AUC se sostiene. El script ahora **lanza excepción si la pérdida sube**, para que ese fallo no pueda repetirse en silencio.

## El resultado: qué modelo acierta más

Operando el **top 20%** de cada ranking, sobre el tramo de prueba:

| Modelo | Opera | Acierta | IC95 | z vs base | **Esperanza neta** |
|---|---|---|---|---|---|
| **M0** · sistema actual (todo) | 158 | 20,3% | [14,0–26,5] | — | −0,682% |
| **M1** · score | 54 | 31,5% | [19,1–43,9] | +1,59 | −0,415% |
| **M2** · continuación (handoff) | 32 | 37,5% | [20,7–54,3] | +1,89 | **−0,881%** |
| **M1b** · `rango_1h_pct` sola | 32 | **43,8%** | [26,6–60,9] | **+2,52** | **−0,312%** |

«Acierta» = llega a +3,2% **antes** del SL, que es lo único cobrable.

### La respuesta a tu pregunta

**Solo M1b es significativo** (z=2,52). Y no es un modelo: es **ordenar por una sola columna, `rango_1h_pct`, que el sistema ya calcula y ya guarda**. Sin entrenamiento, sin artefacto, sin tabla nueva.

Duplica la tasa de acierto del sistema actual: 43,8% contra 20,3%.

### Y la trampa que había que buscar

**M2 acierta más que M1 pero tiene la PEOR esperanza de la tabla — peor que no hacer nada.**

Acierta el 37,5% y aun así pierde −0,881% por operación, contra los −0,682% de operarlo todo. La razón: selecciona señales volátiles, donde el TP y el SL son más anchos. Gana más veces y pierde más grande. La suma sale peor.

Es exactamente el riesgo que había que vigilar: **la tasa de acierto no es la métrica que paga**. Si hubiéramos mirado solo el porcentaje, M2 parecía el ganador.

M1b gana en las dos: más aciertos *y* la mejor esperanza.

## Lo que ningún modelo consigue

**Todas las esperanzas siguen en negativo.** La mejor (M1b) pasa de −0,682% a −0,312%: reduce la pérdida a la mitad, no la cruza.

Esto concuerda con lo que medí el 11-sep por otro camino: con el TP atado al stop por `rr_target`, ningún filtro de entrada arregla la aritmética. Un ranking mejor te da mejores señales dentro del mismo sistema perdedor.

## Sobre la entrada diferida del handoff

El handoff propone entrar 0,5% por debajo en las continuaciones, y **marca él mismo el límite**: el grupo «continuación» se elige *después* de ver el camino.

Lo comprobé: para aplicarla en vivo haría falta seleccionar ese grupo por adelantado. El mejor selector disponible (top 20% de M2) acierta 37,5% con IC95 [20,7–54,3] contra una base de 20,3%. **El intervalo toca la base**, así que todavía no hay a quién aplicar la entrada diferida con confianza.

## El objetivo por grupo (v12), con datos maduros

Sobre el mismo tramo de prueba: alcanza el objetivo de su grupo el **58,9%** [51,2–66,5] contra el 33,5% del 3,2% fijo. Pero el objetivo del grupo es más bajo (1,23%–2,49%), así que acertar más es lo esperable — y medido en esperanza dio solo **+0,085 puntos**. Sigue siendo medición en sombra con razón.

## Qué construiría, y qué no

**El frontend ya compila.** Estaban los tres errores de `PairDetail.tsx:40` que el handoff señalaba: `pair.alerta?.entrada_alt > 0` no estrecha el tipo. Corregido a `pair.alerta != null && pair.alerta.entrada_alt > 0`.

**Lo que la evidencia NO sostiene todavía:** el artefacto de modelo offline, las tablas nuevas, el contrato API/WebSocket y las tres fases de backend que pide el handoff. Todo eso es la infraestructura de M2, y M2 tiene peor esperanza que no hacer nada. Construirlo ahora sería trabajo caro al servicio del modelo que peor sale en la prueba.

**Lo que sí sostiene:** exponer el ranking por volatilidad. `rango_1h_pct` ya está en el snapshot y en `outcomes`. Surfacearlo en el tablero es ordenar por una columna existente — y es el único candidato con mejora significativa.

Mi recomendación: **medir M1b en sombra una semana** con el marcador ya en la fila, y solo entonces decidir si entra en la emisión. Con 32 señales en el tramo alto, el IC95 va de 26,6% a 60,9%: sé que es mejor que la base, no cuánto.

## Deuda que sigue condicionando todo

**F04: el 40% de las alertas emitidas no tiene `signal_id`.** Todo lo de arriba se mide sobre el 60% que sí está enlazado. Antes de tratar cualquier modelo como representativo de lo que ves en el teléfono, hay que cerrar eso.

## Reproducir

```bash
backend/venv/Scripts/python.exe audit/2026-09-14/comparar_modelos.py datos.json
```

El export se genera con la consulta de solo lectura incluida en el script. 393 filas, 184 símbolos.
