# Fase 6 — presentación unificada · 22-sep-2026

**Desplegada en producción** (22-sep, 22:07 UTC). **298 pruebas de backend y 53 de frontend en verde**, typecheck limpio. Sin migración: esta fase no añade tablas, saca a la superficie las que ya existían.

## 1 · El mismo número hacía dos trabajos

El defecto que esta fase cierra no era cosmético.

| dónde | qué era | tipo |
|---|---|---|
| `objetivo_operador_pct = 3.2` | lo que quieres embolsarte | **neto** |
| `outcome_tracker.OBJETIVO = 3.2` | excursión de precio para medir el recorrido | **bruto** |

Iguales por historia, no por definición. Con 0,5 de coste, tu objetivo de **+3,2 % neto** necesita **+3,7 % brutos**, y el hito de **+3,2 % bruto** solo deja **+2,7 % netos**. Media vuelta de diferencia, con la misma etiqueta en pantalla.

**Medido sobre 502 recorridos completos de producción: 37 señales —el 15,5 % de las que el tablero daba por meta cumplida— nunca llegaron al objetivo real.**

Y había un error de umbral, no solo de texto: `PairDetail` comparaba el TP **bruto** contra el objetivo **neto**, así que avisaba tarde.

Ahora todo sale de `GET /api/contrato`. Un `Porcentaje` sabe su tipo, sabe convertirse al otro y sabe escribirse; ningún porcentaje viaja sin decir qué es. Si el objetivo se mueve a +4,2 % neto, los quince textos se mueven con él — hay una prueba que lo verifica.

## 2 · La vista «Oportunidades»

Con 10 USDT y una posición se toman **dos de cada diecisiete** avisos: el 88 % pasa de largo. El cuello de botella no es qué objetivo poner, es **cuál tomar** — y los datos para decidirlo vivían solo dentro de la base.

`GET /api/oportunidades` reúne por alerta viva:

- si es la **1.ª de su episodio** o la n.º 5 (fase 1)
- qué ven **los dos motores** y qué les falta para disparar (fase 4)
- si los **marcos se contradicen**
- si hay un **techo** entre la entrada y el TP
- si el **ancla de 1h** tiene ruptura alcista — lo único que batió a su control
- cuánto se **desvió el precio** de la entrada del plan

**No ordena por calidad, a propósito.** La puntuación no ordena resultados (AUC 0,535); presentarla como ranking sería volver al problema de origen. Van por hora de emisión, con los hechos al lado.

Y **ningún aviso dice qué hacer**. Hay una prueba que lo comprueba: ninguno contiene «no entres» ni «evita». Este proyecto ya midió que casi todos sus vetos automáticos no distinguen nada.

Las alertas rehidratadas tras un reinicio no traen episodio ni recompensa neta, porque se reconstruyen desde `outcomes`. No se rellenan con datos de hoy —mezclar un plan congelado con estructura actual es lo que este sistema evita— pero la vista **lo dice** en vez de enseñar un hueco.

## 3 · Telegram con identidad de plan

Antes: `Plan #4871`, un identificador de base de datos.

Ahora: `Plan #4871 · episodio 42 · primera oportunidad · disparado en 1h`.

Y la distinción que el plan pedía explícitamente, que faltaba entera:

> ⚠️ **Afecta a tu operación abierta** en este par.

o

> Solo describe una oportunidad: no tienes ninguna operación registrada en este par.

Sin eso, todos los avisos piden la misma atención y acaban sin pedir ninguna. El dato salía del diario de la fase 3 y nunca se había usado.

## 4 · Resultados por población

`GET /api/resultados`. «¿Cuánto acierta el sistema?» no tiene una respuesta: tiene cuatro, y la que se elegía en silencio era la más grande.

Medido al desplegar:

| población | planes | pares | acierto | media | abiertas |
|---|---|---|---|---|---|
| todos los planes | 1.619 | 296 | 38,02 % | −0,170 % | 960 |
| primera de cada episodio | 639 | 296 | 36,99 % | −0,585 % | 403 |
| avisados por Telegram | 44 | 42 | 31,25 % | −0,516 % | 26 |
| **avisados Y primeros del episodio** | **13** | **13** | **16,67 %** | **−2,558 %** | **8** |

**21 puntos de diferencia entre la primera fila y la última.** Ninguna mejora que se discuta en este proyecto es de ese tamaño. Elegir población en silencio decidía la respuesta.

La última tiene **n = 13, con 6 resueltas**: no significa nada todavía, y por eso la prueba prospectiva de la fase 5 no puede cerrar su puerta del dinero antes del 17-oct.

Dos reglas que la tabla hace cumplir:

- **Las vencidas no cuentan como fallos.** Es el hallazgo F14 de la auditoría del 10-sep: incluirlas en el denominador contaba 207 cierres positivos como fracasos. Se ven aparte.
- **Las ventanas abiertas no entran en ninguna media.** Es como se fabricó el +0,25 % que se evaporó en septiembre.

Y cada número viaja con su **horizonte** y su **modelo de coste**: sin esas dos cosas, dos porcentajes no se pueden comparar.

## Criterios de aceptación del plan

| | criterio | estado |
|---|---|---|
| ✅ | Identificar qué entrada se está siguiendo y cuál fue la primera | episodio y ordinal en la vista, en la tarjeta y en Telegram |
| ✅ | Qué actualización llegó y si afecta a lo tomado | la línea de alcance en Telegram, desde el diario |
| ✅ | Qué ganancia es simulada o real | ya separado en la fase 3; el diario nunca las suma |
| ✅ | Ningún porcentaje bruto aparece como neto | el contrato de lectura, con su prueba |
| ✅ | Métricas filtrables por población, con horizonte y coste | `/api/resultados`, las cuatro a la vez |
| ✅ | Los consumidores antiguos siguen funcionando | ningún endpoint ni contrato existente cambió |
| ✅ | Vistas «Mercado», «Oportunidades», «Mi operación», «Resultados» | las cuatro en la misma navegación |

## 5 · «Mi operación», donde toca

Estaba desde la fase 3, pero **dentro de la pestaña de mercado, debajo de la rejilla de pares, el historial, el análisis por marcos y la calculadora** — y plegada. Una operación abierta es lo único que exige atención ahora mismo; tenerla en la sexta posición de otra pantalla la convertía en un dato de archivo.

Ahora es una de las cuatro vistas, y con una sola posición a la vez la posición abierta va **arriba del todo**, con lo que se mira para decidir si se aguanta o se sale:

```
PYTHUSDT     Ejecución declarada · desde 13:42
entrada 0.06396   ahora 0.06510   +1.28 % no realizado   al TP +2.25 %   al SL -3.21 %
```

Las distancias a las dos barreras salen de los niveles que la operación **copió al abrirse**, no de los del plan de hoy: un plan posterior no mueve lo que ya tomaste.

## Un aviso para quien siga

**`npx tsc --noEmit` no comprueba nada** en este repo: el `tsconfig.json` raíz tiene `files: []` y solo referencia proyectos. Hay que usar `tsconfig.app.json`. Estuve a punto de dar por bueno un typecheck vacío.

## Corrección del 24-sep-2026 — el suelo de cobertura

La tabla de arriba se publicó **sin suelo de cobertura**, y eso la infla.

`plan_recorrido` marca `completa = 1` cuando la ventana de 12 h **vence**, sin mirar cuántas velas llegó a ver. Y las que faltan no se pierden al azar:

> Una vela ausente borra la barrera que más se toca, y la que más se toca es **la más cercana**. En estos planes la más cercana es el stop. **Faltar datos fabrica objetivos.**

Medido sobre 1.681 recorridos resueltos, la habilidad aparente cae de forma monótona conforme sube la cobertura: **+26,67 pp** entre 0,75 y 0,90 · **+14,61 pp** entre 0,90 y 0,99 · **+2,49 pp** por encima de 0,99.

Sobre la población «todas», medido el 24-sep:

| | acierto | n |
|---|---|---|
| sin suelo (lo que se publicaba) | **33,22 %** | 2.366 |
| cobertura ≥ 0,90 | 32,68 % | 2.231 |
| **cobertura ≥ 0,99** | **31,62 %** | 2.084 |

**Qué cambia:** `GET /api/resultados` aplica ahora `presentacion_cobertura_minima = 0,99`. Las mal observadas **se cuentan aparte**, como las vencidas — desaparecerlas sería tan engañoso como promediarlas — y salen en la tabla con su propia columna.

**Por qué 0,99 y no 0,90** (el suelo de la fase 5): aquí el suelo sí muerde. La fase 5 mide casi solo recorridos completos —33 de sus 14.642 medidas bajan de 0,99, y las 33 resolvieron en STOP, la dirección contraria al sesgo— así que su suelo nunca llega a actuar y **su registro congelado no se toca**. `plan_recorrido` lo incluye todo.

**Y una cuarta cosa que ahora viaja con el número.** La fase 6 estableció que un porcentaje necesita su población, su horizonte y su modelo de coste. Faltaba el **suelo de cobertura**: dos tasas medidas con suelos distintos no son comparables, y hasta hoy el suelo era cero sin que nada lo dijera. Va en la respuesta y en el tablero.

Cómo se descubrió: al puntuar los motores de la fase 4, el grupo que declaraba **«me falta el dato de 1h»** salía como el que mejor predecía (+45,91 pp). Algo que dice no saber nada no puede ser lo que más acierta — tirar de ese hilo destapó el sesgo. Está en [fase7/PUNTUACION_MOTORES.md](../fase7/PUNTUACION_MOTORES.md).
