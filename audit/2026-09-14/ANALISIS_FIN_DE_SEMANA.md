# Análisis del fin de semana · 11–14 sep

**Primera medición con datos que se sostienen.** Tres días completos con el código corregido: 1.184 outcomes nuevos, 658 con su ventana de 24h vencida.

## Antes de nada: el servidor reinició con el reloj mal

El 12-sep a las 07:50 UTC la máquina reinició y arrancó con el reloj en **27 de julio**; NTP lo corrigió segundos después. Hay 54 líneas de log con fecha de julio.

**Los datos están limpios:** cero filas con fecha corrupta en `outcomes`, `signals`, `alertas_emitidas`, `symbol_states` ni `analysis_log`. Las 54 líneas fueron mensajes de arranque, antes de que se escribiera nada. El servicio lleva 2 días y 10 horas sin reiniciar, en `f82bcff`, con **cero tracebacks en todo el fin de semana**.

---

## 1. Las correcciones funcionan, y se nota

### La cobertura de velas: de 1 ventana usable de cada 5, a 19 de cada 20

| Código | n | Mediana | ≥98% |
|---|---|---|---|
| Antes de los arreglos | 280 | 0,9711 | **20,7%** |
| Con los arreglos | 658 | 0,9875 | **96,2%** |

Éste es el resultado más importante del fin de semana, y no por la cifra en sí: **cambia la confianza de todo lo demás**. Antes, cuatro de cada cinco ventanas tenían huecos que podían alterar qué ocurrió primero, si el stop o el objetivo.

### La retención ya acumula

Las velas de 1m abarcan **5,8 días** y subiendo, contra los 3,0 clavados de antes. La base pasó de 168 MB a 354 MB. A este ritmo se estabiliza cerca de 1,5 GB, sobre 815 GB libres.

### El reloj de señales

**De 24 señales colgadas a 0.** La más vieja abierta ahora lleva 10,9 horas, dentro de las 12 de `signal_expiry_hours`.

Aparecen 27 `STALE` en los últimos tres días, pero no son un problema nuevo: se cerraron **todas en el mismo minuto**, las 16:53 del 11-sep, cuando el barrido limpió el atasco histórico. Sus edades iban de 12 a 155,8 horas. Y no tenían precio al vencimiento porque sus pares habían salido del universo y sus velas las había borrado la purga vieja. Desde entonces, ninguna nueva.

---

## 2. La cifra que esperábamos, y por qué la referencia no valía

| Cohorte | n | Llegan a +3,2% |
|---|---|---|
| Código viejo (10–11 sep) | 127 | **69,3%** |
| Código nuevo (11–14 sep) | 401 | **26,9%** |
| *Referencia histórica (4–10 sep)* | *2.197* | *43,0%* |

Esa diferencia **no la produce el código**. Los arreglos cambian cómo se mide, no si el precio sube. El 10–11 de septiembre fue un tramo fuerte y el fin de semana flojo; eso es todo.

Lo interesante aparece al filtrar por cobertura:

| Cohorte | Sin filtrar | Solo cobertura ≥98% | n que sobrevive |
|---|---|---|---|
| Código viejo | 69,3% | **52,0%** | 25 de 127 |
| Código nuevo | 26,9% | **27,8%** | 385 de 401 |

En la cohorte vieja, exigir cobertura decente tumba la tasa 17 puntos y deja solo el 20% de las filas. En la nueva, no mueve casi nada.

**Consecuencia incómoda: el 43,0% que llevo días usando como referencia sale de datos con ese mismo problema de cobertura.** Nunca fue un número sólido. La primera cifra fiable que tenemos es **27,8% sobre 385 ventanas con cobertura ≥98%**, y a partir de ahora ésa es la referencia.

---

## 3. Lo que de verdad importa: qué vetos funcionan

Ésta es la primera vez que podemos juzgar las **decisiones** del sistema, no su medición. Sobre 410 ventanas emitidas (29,3% llegan) contra las vetadas:

| Veto | n | Llegan | z | Lectura |
|---|---|---|---|---|
| **La caída sigue acelerando** (cuchillo cayendo) | 116 | **16,4%** | −3,14 | **acierta** |
| GATE_MACRO | 124 | 34,7% | +1,12 | sin evidencia |
| **Impulso agotado — precio bajo la EMA7** | 31 | **51,6%** | +2,41 | **cuesta dinero** |

**El veto del cuchillo cayendo funciona, y con solidez.** Lo que veta llega a la meta la mitad de veces que lo emitido. Ese filtro se gana su sitio.

**El veto de "impulso agotado bajo la EMA7" está tirando lo mejor.** Lo que rechaza llega el 51,6% de las veces, casi el doble que lo que deja pasar. Con n=31 no es definitivo (z=2,41, en torno al 98% de confianza), pero apunta claro y merece medirse otra semana antes de tocarlo.

**GATE_MACRO no demuestra nada.** Veta 124 señales que llegan al 34,7%, por encima del 29,3% de lo emitido — pero la diferencia cabe dentro del ruido (z=1,12). Lo que sí se puede decir: **no hay ninguna evidencia de que proteja**. Y es el veto que más señales descarta.

---

## 4. El objetivo por grupo: la idea funciona, los cortes no

Con 633 ventanas cerradas y grupo asignado:

| Grupo | n | Objetivo | Llega al suyo | Llega al 3,2% fijo |
|---|---|---|---|---|
| Muy tranquila | 365 | 1,23% | 43,8% | 19,5% |
| Tranquila | 113 | 1,38% | 63,7% | 33,6% |
| Movida | 62 | 1,81% | 62,9% | 37,1% |
| Muy volátil | 93 | 2,49% | 64,5% | 48,4% |
| **Total** | **633** | — | **52,3%** | **28,0%** |

Y llega **antes**: mediana de **4,0 horas** contra 5,9 del objetivo fijo. Para operar intradía, eso importa tanto como la tasa.

**Pero los cortes están mal calibrados.** Se sacaron de una muestra de 775 operaciones repartida en cuartiles; sobre la población real no reparten nada parecido:

| Grupo | Reparto real | Debería ser |
|---|---|---|
| Muy tranquila | **49,3%** | 25% |
| Tranquila | 20,4% | 25% |
| Movida | 14,5% | 25% |
| Muy volátil | 15,7% | 25% |

La mediana real de `vol_previa_pct` es **0,0691%** y el primer corte está en 0,068% — justo encima, así que la mitad de las señales cae en el grupo más tranquilo. Recalibrar los cortes sobre esta distribución es trabajo de media hora, y ahora hay datos para hacerlo bien.

**Y el aviso de siempre:** alcanzar un objetivo más bajo más a menudo no es automáticamente mejor. Cuando lo medí en esperanza neta, el objetivo por grupo mejoraba solo **+0,085 puntos por operación**. Sigue siendo medición en sombra por eso.

---

## 5. Lo que sigue igual

**Telegram: 26 avisos de 1.454 alertas (1,8%).** Los filtros dejan pasar menos del 2%. Cero marcadas como `fallo` — el registro de entrega funciona y no hay envíos perdidos.

**F04 sigue abierto y a peor: 576 de 1.454 alertas (40%) sin `signal_id`.** Cuatro de cada diez alertas que verías no tienen outcome que mida sus niveles concretos. Era el 21% el 11-sep.

**F13 sin tocar:** las alertas de perfil (BASE, TENDENCIA, IGNICIÓN) siguen sin abrir plan ni outcome propio.

---

## Lo que yo haría ahora

1. **Recalibrar los cortes de volatilidad** sobre la distribución real. Barato, y la medición en sombra deja de estar sesgada hacia un grupo.
2. **Vigilar el veto de la EMA7 una semana más.** Si aguanta, quitarlo es la mejora más barata que hay a la vista: 31 señales rescatadas que llegan al 51,6%.
3. **Dejar el cuchillo cayendo como está.** Es lo único que hoy demuestra separar.
4. **F04 antes que el motor de recorridos.** Con el 40% de las alertas sin medir, cualquier estadística sobre lo que recibes está construida sobre el 60%.

Y sobre GATE_MACRO: no hay evidencia de que proteja, pero tampoco de que dañe. Con otra semana de datos habrá n suficiente para decidirlo en vez de opinarlo.

---

## Reproducir

Consultas de solo lectura contra `sacbinance.db` en el servidor. Fuente: PID 1308, `f82bcff`, arrancado el 12-sep 07:50 UTC. Base de 354 MB, 4.256 outcomes, 2.488.582 klines.
