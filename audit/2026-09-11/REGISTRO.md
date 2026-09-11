# Registro de la cohorte b8a3d64 · primeras 6,4 horas

**Fecha del corte:** 10-sep-2026 23:19 de Guatemala. **Analizado:** 11-sep-2026.

Esto es un registro de arranque, no un veredicto. Ninguna ventana de 24h ha vencido: **la primera cierra hoy 11-sep a las 16:55**. Todo lo que sigue sobre resultados es un camino a medias.

## A qué hora fue la actualización

No hizo falta recordarlo: las filas están firmadas. Fueron **tres despliegues seguidos aquella tarde**, no uno.

| Versión | Outcomes | Desde | Hasta |
|---|---|---|---|
| *(sin firma)* | 2.792 | 04/09 21:56 | 10/09 **16:34** |
| `e222b70` | 6 | 10/09 **16:37** | 16:43 |
| `c41d477` | 5 | 10/09 **16:45** | 16:54 |
| **`b8a3d64`** | **69** | 10/09 **16:55** | 23:13 (fin del snapshot) |

La que está corriendo es **b8a3d64**, `config_hash` `50d5bbbe74aa`, desde las **16:55**. Las dos anteriores vivieron 6 y 9 minutos: subiste tres veces seguidas mientras ibas cerrando hallazgos.

**Importante:** esto mide b8a3d64 (esquema v11). Los arreglos que commiteé anoche **no están desplegados**.

## Qué produjo

- **69 outcomes** = 29 reales + **40 en sombra** (vetadas y medidas sin emitir)
- **46 alertas**, de las que **2 llegaron a Telegram**
- 29 pares distintos de 224 en el universo
- Ritmo: 4,6 outcomes reales/hora ≈ **110/día**

De las 40 vetadas, **34 lo fueron por GATE_MACRO**: el gate de régimen está descartando más de la mitad de todo lo que el sistema ve. Esas 40 se están midiendo en sombra, así que mañana se podrá comparar lo vetado contra lo emitido — que es exactamente la pregunta que interesa.

## Los arreglos de v11, ¿se ven en las filas?

| | Resultado |
|---|---|
| **F07** indicadores | `rsi14_1m` **69/69**. Los tres de 15m, **65/69** — los 4 NULL son TAO, LUNC y KAITO al arrancar y GPS después: falta de calentamiento, no el error de antes |
| **F12** procedencia | `strategy_version` y `config_hash` en **69/69** |
| **F08** flujo | Solo **4/69** con `flow_disponible=1`. De esas 4, **2 con cero trades** — ésas sí son "nadie compró". Las otras 65 tienen un cero que **no significa nada** |
| **F01** velas | **0/69 filas completas.** Todas pierden minutos: mediana **9**, mínimo 2, máximo 12 |

Sobre F01: comprobé si alguna fila tenía **más** velas que minutos transcurridos — el sobreconteo por duplicados. **Ninguna (0/69)**. El defecto es reproducible en pruebas pero no se ha materializado aquí. Lo que sí es universal es la pérdida: ni una sola ventana está completa, y las tres más viejas pierden 12 minutos de 384 (3,1%).

## El hallazgo que no esperaba: el TP no se elige

De las 46 alertas, **38 tienen TP exactamente igual a 2,00 × el riesgo**. No es una coincidencia: es `rr_target = 2.0`. El take profit no se decide mirando a dónde puede llegar el precio — **sale del stop, multiplicado por dos**.

Eso convierte el problema de F03 en aritmética:

- Para ofrecer **3,2% bruto** hace falta un stop de **1,60%**
- Para ofrecer **3,2% neto** (con el coste de 0,5) hace falta un stop de **1,85%**
- **26 de 46 alertas (56,5%)** tienen el stop por debajo de 1,60% → no podían llegar ni en bruto
- **29 de 46 (63,0%)** por debajo de 1,85% → no podían llegar en neto

El stop mediano de las alertas es **1,29%**. Mientras el TP sea el stop por dos, un stop estrecho es matemáticamente incompatible con tu objetivo. Y esto **no lo arregla activar `exigir_objetivo_operador`**: eso solo silencia las que no llegan — pasarías de 46 alertas a 17. Las opciones reales son tres, y las tres son tuyas:

1. **Stops más anchos** — más riesgo por operación, menos señales sacadas por ruido.
2. **Subir `rr_target`** — el TP se aleja sobre el mismo stop, y se toca menos veces.
3. **Aceptar** que más de la mitad de lo que emite no apunta a 3,2% y tratarlo como observación.

Hay una señal de que el sistema ya se está moviendo en la dirección 1: el riesgo mediano pasó de **1,28% en el histórico a 1,76%** en esta cohorte, y con él el TP de 2,56% a 3,52%. Con n=29 no es una tendencia todavía, pero es lo que hay que vigilar mañana.

## Camino recorrido hasta el corte (inmaduro)

Ventanas de entre 0,1 y 6,4 horas sobre una nominal de 24. Un SL tocado ya es definitivo; un TP no tocado aún puede tocarse hoy.

| Escalón | Alcanzado | Mediana |
|---|---|---|
| +1% | 19/29 (65,5%) | 73 min |
| +2% | 9/29 (31,0%) | 133 min |
| **+3,2% (meta)** | **4/29 (13,8%)** | 127 min |
| +5% | 3/29 (10,3%) | 142 min |
| +10% | 3/29 (10,3%) | 185 min |

Hacia abajo: −1% en 12/29, −2% en 5/29, −3,2% en 2/29.

- **TP propio tocado: 3/29** · **SL propio tocado: 8/29** · los dos en la misma vela: 1 (orden desconocido)
- MFE mediana **+1,23%** (mejor +20,38%) · MAE mediana **−0,49%** (peor −3,40%)
- A precio de corte, **22/29 en positivo (75,9%)**, mediana +0,64%

**La referencia que hay que batir:** en las 2.197 ventanas de 24h ya cerradas del histórico, **el 43,0% llegó a tocar +3,2% en bruto** en algún momento. Ése es el número contra el que se mide esta cohorte cuando maduren sus ventanas — no el 13,8% de arriba, que son ventanas de 6 horas contra ventanas de 24.

## La regla del hoyo

El precio bajó al nivel de entrada en **34 de 69 (49,3%)** — casi la mitad. De esas, ninguna con vela ambigua.

| Regla | Abierta | SL | TP |
|---|---|---|---|
| A (mismo % bajo la nueva entrada) | 22 | 10 | 2 |
| C2 (stop fijo 2%) | 27 | 4 | 3 |
| C3 (stop fijo 3%) | 31 | 0 | 3 |

Con tan pocos desenlaces no se puede concluir nada, pero la forma es la esperable: cuanto más ancho el stop, menos paradas y los mismos TP. **Ojo:** esto se mide con la regla del tracker en vivo, que sí es conservadora. El estudio `research/entrada_en_el_hoyo.py` usaba una regla más optimista hasta anoche; sus cifras anteriores no son comparables con esta tabla.

## Telegram

**44 de 46 alertas: `no_procede`. Solo 2 enviadas.** Los filtros (`aviso_score_min=75`, `aviso_solo_confirmado`, `aviso_vol24h_min`, cooldown) están dejando pasar el 4%. Eso es 0,3 avisos por hora — coherente con lo diseñado, pero conviene saberlo: el teléfono callado de anoche era el sistema funcionando, no roto.

Y **17 de 46 alertas (37%) siguen sin `signal_id`**: sus niveles concretos no tienen outcome propio que los mida. Es F04 y sigue abierto.

## Qué mirar hoy a las 16:55

Cuando cierre la primera ventana:

1. **% que tocó +3,2% en 24h**, contra el **43,0%** histórico.
2. **Lo vetado contra lo emitido**: las 40 sombras, y sobre todo las 34 de GATE_MACRO.
3. **`cobertura_velas`** — se escribe al cerrar. Si las filas vienen con cobertura baja, el resultado no se sostiene.
4. **Riesgo mediano**: ¿se consolida en 1,76% o vuelve a 1,28%?

## Reproducir

```bash
backend/venv/Scripts/python.exe audit/2026-09-11/analisis_cohorte.py
```

Fuente: `audit/2026-09-10/verification/snapshot.db`, SHA-256 `ac87a6db622a8f5bb425713751f54d141197d64cd6ff7ea42ad9458f95cd6a2a`, tomado el 10-sep 23:19:35 de Guatemala. Salida completa en [cohorte_b8a3d64.txt](cohorte_b8a3d64.txt).

**Lo que este registro no cubre:** desde el corte del snapshot hasta ahora han pasado ~1,5 horas más que no están aquí. No tengo acceso SSH al servidor desde esta sesión; para traer una copia fresca:

```bash
backend/venv/Scripts/python.exe audit/2026-09-10/verification/acquire.py
```

---

# Addendum · 11-sep 00:55, con acceso al servidor

Recuperado el acceso SSH (era un fallo mío de invocación, no del servidor), consulté la base viva. Tres correcciones a lo de arriba.

## 1. Sí hubo un reinicio posterior, y tenías razón

El servicio **se reinició el 11-sep a las 00:06 de Guatemala**. Yo había tratado el arranque de las 16:54 como "este reinicio"; tú dijiste que la actualización fue *antes* de un reinicio posterior, y era correcto.

## 2. La cohorte se partió en dos etiquetas, sin motivo funcional

| Versión | `config_hash` | Filas | Desde | Hasta |
|---|---|---|---|---|
| `b8a3d64` | 50d5bbbe74aa | **83** | 10/09 16:55 | 10/09 23:55 |
| `25d03fa` | 50d5bbbe74aa | **11** | 11/09 00:26 | 11/09 00:48 |

El repo del servidor está en **25d03fa**, así que al reiniciar, `procedencia` firmó las filas nuevas con ese commit. Pero **25d03fa no toca ni una línea del backend**: sus 26 ficheros están todos bajo `audit/`. Es el mismo código con otra etiqueta.

**Consecuencia para el análisis de hoy:** `b8a3d64` y `25d03fa` son la misma cohorte y hay que **sumarlas**, no compararlas. Ahora mismo son 94 filas. El `config_hash` idéntico lo confirma: la configuración no cambió.

Esto es un efecto secundario de firmar con el commit de git: un commit que solo añade documentación parte la muestra igual que uno que cambia la estrategia. El `config_hash` es el que distingue de verdad.

## 3. Hay un hueco de 31 minutos

Última fila de `b8a3d64` a las **23:55**, primera de `25d03fa` a las **00:26**. El servicio arrancó a las 00:06, así que 20 de esos minutos son hidratación y calentamiento. Las señales vivas durante ese hueco perdieron seguimiento.

## Estado a las 00:55

- **outcomes** 2.897 · **alertas** 63 · **signals** 2.360
- Cohorte nueva: **94 outcomes** (83 + 11), frente a los 69 del snapshot de las 23:19

## Sobre `acquire.py`

El script de la auditoría tiene la misma trampa en la que caí: invoca `ssh flox@100.96.211.5` con la IP cruda, que **no coincide** con el bloque `Host sac` de `~/.ssh/config` y por tanto no usa la clave `id_ed25519_sac`. Para que funcione desde esta máquina hay que llamarlo con el alias `sac`.

## Cuándo repetir esto

**No merece la pena volver a bajar el snapshot ahora**: serían 94 ventanas inmaduras en vez de 69. El momento es **después de las 16:55 de hoy**, cuando cierren las primeras ventanas de 24h y haya algo que sí sea un resultado contra el 43,0% histórico.
