# Adenda al plan: la ventana del episodio y qué puede significar «confianza»

**Escrita el 21-sep-2026, 23:40 UTC**, después de leer [PLAN.md](PLAN.md), [CONTRATOS_Y_METRICAS.md](CONTRATOS_Y_METRICAS.md), [CONTINUIDAD.md](CONTINUIDAD.md) y [LEER_PRIMERO.md](LEER_PRIMERO.md).

No cambia el plan: cierra dos huecos que el propio plan deja abiertos a propósito y que Felix señaló.

- `CONTRATOS_Y_METRICAS.md` §1, regla 4: «el silencio o la caducidad cierran según una regla versionada» — pero **no dice cuál**, y remite a «ensayarse en replay y congelarse en la fase 1».
- `PLAN.md` §4: pide medir «primera oportunidad del episodio» sin fijar **cuándo se cierra ese episodio y empieza el siguiente**.
- `CONTRATOS_Y_METRICAS.md` §7: exige que la probabilidad esté «ligada a un evento y horizonte precisos, con calibración comprobada» — sin decir **si la puntuación actual sirve** para eso.

Todo lo que sigue está medido sobre la base de producción en solo lectura, misma cohorte y método que [el análisis del 21-sep](../../2026-09-21/telegram-signal-review/ANALISIS.md): 229 avisos de Telegram evaluables, 4.513 señales evaluables, ventana de 12 h, velas de 1 minuto.

---

## 1. La ventana del episodio: lo que dicen los datos

### Los avisos de Telegram casi nunca se repiten dentro del mismo movimiento

109 pares de avisos consecutivos del mismo símbolo, 146 símbolos:

| Hueco entre dos avisos del mismo par | Reparto |
|---|---|
| ≤ 1 h | 0 % |
| ≤ 4 h | 4,6 % |
| ≤ 6 h | 8,3 % |
| ≤ 12 h | 18,3 % |
| ≤ 24 h | 54,1 % |
| **Mediana** | **21,0 h** |

En el universo interno pasa lo contrario: sobre las 8.733 alertas con niveles, la mediana entre alertas del mismo par es **2,5 h** y el **69,5 %** de las repeticiones ocurre dentro de 4 h.

**Conclusión operativa:** la regla «un plan notificado abierto por símbolo» + cooldown de 45 min ya convierte casi todos los avisos de Telegram en primeras del episodio. Con una ventana de silencio de 12 h, **212 de 229 avisos (92,6 %) ya son ordinal 1**. El problema de «cuál es la primera» es real, pero **no está en lo que tú recibes: está en la medición del universo interno**, donde sí hay racimos de repeticiones.

### Cuando sí se repite pronto, el primer plan ya había terminado

| Hueco | n | La 2ª entrada difiere de la 1ª (mediana) | El 1º ya había resuelto (TP o SL) | La 2ª entrada cae dentro de los niveles del 1º |
|---|---|---|---|---|
| 1–3 h | 4 | 0,91 % | 75 % | 100 % |
| 3–6 h | 5 | 3,02 % | 100 % | 100 % |
| 6–12 h | 11 | 3,16 % | 100 % | 82 % |
| 12–24 h | 39 | 2,18 % | **41 %** | 82 % |
| > 24 h | 50 | 7,69 % | 52 % | 40 % |

Los repetidos de menos de 12 h llegan **después** de que el primero cerrara: son reintentos, no planes en competencia. Los de 12–24 h son los ambiguos: en el 59 % de los casos el primero seguía vivo o acababa de caducar sin resolver. Ahí es donde una regla de cierre cambia el resultado de la medición.

### La regla concreta que propongo congelar en la fase 1

Un episodio de compra se cierra por **lo primero que ocurra** de estas cuatro:

1. **Desenlace del plan vigente:** toca su objetivo o su stop. El episodio se cierra con ese desenlace; un candidato posterior abre episodio nuevo con `parent_episode_id`.
2. **Invalidación estructural:** se pierde el ancla del episodio (el nivel roto, el soporte de la base). Regla propia de cada motor, persistida con su versión.
3. **Silencio de 12 h** sin candidato nuevo del mismo símbolo y la misma dirección.
4. **Caducidad de 12 h del plan** sin resolución (lo que hoy hace `signal_expiry_hours`), que cierra el episodio como `VENCIDO_SIN_RESOLVER`.

**Por qué 12 h y no otra cosa:** coincide con el horizonte que ya usa el sistema, con el reloj del plan notificado y con el punto donde el 82 % de las repeticiones de Telegram todavía no ha llegado. Bajarlo a 4 o 6 h partiría en dos episodios que hoy son uno solo en el 14 % de los casos, sin ninguna ganancia de medición. Subirlo a 24 h fundiría movimientos claramente distintos: por encima de 24 h la segunda entrada ya difiere un 7,7 % de la primera y solo el 40 % cae dentro de los niveles del primer plan.

**Y una advertencia sobre el número 3:** el silencio de 12 h debe medirse desde el **último candidato del episodio**, no desde el primero, y debe sobrevivir a un reinicio del servicio — es exactamente lo que pide la regla 4 de los contratos.

### Aviso importante: hoy la primera señal no es mejor que las siguientes

El calendario de trabajo anterior (9-sep) daba como «el cambio con más evidencia» que la 1ª señal de un par acierta el 43,1 % y la 7ª en adelante el 28,9 %. **Ese efecto no se reproduce en los datos actuales.** Con ventana de 12 h, sobre 4.513 señales evaluables:

| Ordinal dentro del episodio | n | Toca TP antes que stop | Toca +3,2 % antes que stop |
|---|---|---|---|
| 1ª | 2.214 | 23,7 % | 26,6 % |
| 2ª | 934 | 30,5 % | 28,6 % |
| 5ª o posterior | 494 | 30,2 % | 32,2 % |

En los avisos de Telegram pasa lo mismo, con muestra pequeña: ordinal 1 acierta el 25,9 % y ordinal 2, el 18,8 % (n=16), diferencia que no significa nada con esos números.

No digo que la medición de 9-sep estuviera mal: la población, el periodo y la definición de «acierto» eran otros, y entre medias cambiaron el cooldown, la política de notificación y el evaluador. Lo que digo es que **hoy no hay base para diseñar el sistema alrededor de «la primera es la buena»**. La política de «primera del episodio» sigue siendo necesaria como **unidad de conteo** —evita contar diez veces el mismo movimiento— pero **no como criterio de calidad**. Debe probarse en sombra, como pide `PLAN.md` §5, no asumirse.

---

## 2. Tu forma de operar, contra el reloj medido

Tomas una o dos señales al día y las dejas correr una a seis horas. Esto es lo que ha pasado, hora a hora, en los 229 avisos:

| Han pasado | Llegó al +3,2 % antes que al stop | Llegó a su TP antes que al stop | Tocó el stop | Sigue sin resolver |
|---|---|---|---|---|
| 1 h | 11,4 % | 4,4 % | 4,4 % | 91,3 % |
| 2 h | 19,7 % | 7,0 % | 9,6 % | 83,4 % |
| 3 h | 27,5 % | 10,5 % | 15,7 % | 73,8 % |
| 4 h | 32,3 % | 12,2 % | 20,5 % | 67,2 % |
| **6 h** | **41,9 %** | 16,2 % | 26,2 % | **57,6 %** |
| 8 h | 45,9 % | 19,2 % | 29,3 % | 51,5 % |
| 12 h | 53,3 % | 25,3 % | 32,8 % | 41,9 % |

- De los que **acaban** llegando al +3,2 %, el **73 % lo hace en las primeras 6 h**. De los que acaban tocando el stop, el **78 %** también.
- El máximo del recorrido (MFE) llega, de mediana, a las **6,4 h**.

Tu ventana de una a seis horas captura la mayor parte de lo que va a pasar, pero **a las 6 h el 57,6 % de los planes sigue abierto**. Dos consecuencias para el plan:

1. El horizonte de 12 h está bien elegido para medir; no lo acortes solo porque tú cierres antes.
2. Si tu costumbre es cerrar dentro del día, **el objetivo fijo te encaja mucho mejor que el TP del plan**: a las 6 h el objetivo de +3,2 % ya se ha cobrado 2,6 veces más a menudo que el TP (41,9 % frente a 16,2 %).

---

## 3. Los objetivos netos, medidos con el stop de cada plan

Complementa la decisión de `LEER_PRIMERO.md` sobre +4,2 % netos. Cohorte de Telegram, n=229, coste 0,5 puntos, ventana 12 h:

| Objetivo | Llega antes que el stop | Esperanza por señal |
|---|---|---|
| +3,2 % neto (+3,7 % bruto) | 46,7 % | +0,33 % |
| +3,7 % neto (+4,2 % bruto) | 42,4 % | +0,40 % |
| **+4,2 % neto (+4,7 % bruto)** | **39,3 %** | **+0,51 %** |
| +4,7 % neto (+5,2 % bruto) | 34,9 % | +0,58 % |
| TP actual del plan (mediana +6,72 % bruto) | 25,3 % | +0,47 % |

El +4,2 % neto se sostiene como rival principal: **acierta 1,6 veces más que el TP actual con una esperanza igual o algo mejor**. Pero la diferencia entre todas esas filas está dentro del ruido —el intervalo del 95 % de la esperanza actual es [−0,04 %, +0,99 %] con esta muestra—, así que lo que cambia de verdad al bajar el objetivo **no es cuánto ganas, es cuántas veces cobras**. Eso es una decisión tuya sobre cómo quieres operar, no un resultado que los datos decidan por ti.

---

## 4. La confianza: qué se puede publicar y qué no

### La puntuación actual no sirve como confianza

En los avisos de Telegram, la puntuación **no ordena**:

| Score | n | TP antes que stop | +3,2 % antes que stop |
|---|---|---|---|
| 70–79 | 63 | 27,0 % | 49,2 % |
| 80–84 | 34 | 38,2 % | 64,7 % |
| 85–89 | 119 | 22,7 % | 52,9 % |
| 90–101 | 13 | **7,7 %** | 46,2 % |

Sobre las 4.513 señales, el AUC del score para «llega al +3,2 % antes que al stop» es **0,580**; en el tramo reciente (15–21 sep), **0,535**. Un 0,5 es lanzar una moneda. **La puntuación describe cuántas condiciones se cumplieron, no la probabilidad de que la operación salga bien**, y mostrarla como confianza es prometer algo que no tiene.

### Las columnas que «predicen» están midiendo volatilidad

Ordenando por cada columna disponible en el momento de decidir, para «llega al +3,2 % antes que al stop»:

| Columna | AUC (todas las señales) |
|---|---|
| `atr_pct` | 0,662 |
| `reward_neto_pct` | 0,660 |
| `ruido_1m_pct` | 0,650 |
| `rango_1h_pct` | 0,635 |
| `score` | 0,580 |

Son, todas, medidas de amplitud del movimiento. Y la [comparación de modelos del 14-sep](../../2026-09-14/COMPARACION_MODELOS.md) ya avisó del riesgo: subir la tasa de acierto seleccionando volatilidad no mejora el dinero. **Comprobado ahora fuera de muestra, en los 7 días posteriores a aquel estudio:**

| 15–21 sep (n=2.730, tasa base 37,3 %) | AUC | Top 20 %: acierta | Top 20 %: esperanza | Todas: esperanza |
|---|---|---|---|---|
| `rango_1h_pct` | 0,596 | 46,9 % | +0,08 % | +0,16 % |
| `atr_pct` | 0,635 | 51,6 % | +0,17 % | +0,16 % |
| `score` | 0,535 | 37,7 % | +0,02 % | +0,16 % |

El hallazgo de `rango_1h_pct` **se degrada fuera de muestra** (AUC 0,717 → 0,596) y **su ventaja económica desaparece**: +0,08 % frente a +0,16 % de no filtrar nada. Sube el porcentaje de aciertos y no sube el dinero, porque el objetivo y el stop están en porcentaje fijo y una moneda más ancha alcanza los dos con más facilidad.

### Cuando la pregunta se hace neutral a la volatilidad, no queda nada

Si el objetivo se expresa en múltiplos del riesgo del propio plan (**R = entrada − stop**), la ventaja aritmética desaparece. Y con ella, toda la capacidad de ordenar:

| 1R antes que el stop | AUC de la mejor columna | AUC del score |
|---|---|---|
| hasta 14-sep (n=1.783, base 37,3 %) | 0,558 (`senal_n`) | 0,517 |
| 15–21 sep (n=2.730, base 52,8 %) | 0,541 (`rsi14_15m`) | 0,502 |

Y las columnas que encabezan cada periodo **no son las mismas**: en el primero manda `senal_n`, en el segundo `rsi14_15m`. Eso es el retrato del ruido.

### Lo único que mueve la probabilidad de verdad es la geometría

| Objetivo | Telegram (229) | Todas las señales (4.513) |
|---|---|---|
| 0,50 R | 73,4 % | 64,9 % |
| 0,75 R | 61,6 % | 54,7 % |
| 1,00 R | 52,0 % | 46,7 % |
| 1,50 R | 39,3 % | 34,7 % |
| 2,00 R (≈ el TP actual) | 25,3 % | 27,5 % |

Y el régimen: la tasa base de 1R pasó de **37,3 % a 52,8 %** entre las dos mitades del periodo, sin que cambiara nada del sistema.

### Contrato de confianza que propongo

En vez de un score de 0 a 100, publicar una sola frase con todas sus piezas:

> **«Probabilidad de tocar +X % neto antes que el stop, dentro de 12 h: NN %»**, acompañada de **la muestra en la que se estimó** y **la ventana temporal** de esa estimación.

Reglas para que ese número no mienta:

1. **Se estima como tasa base condicionada**, no como salida de un modelo: celda = (múltiplo de R del objetivo × régimen de BTC × escenario del motor), sobre una ventana móvil reciente. Hoy, ese es el único estimador que los datos respaldan.
2. **Cada objetivo tiene su propio número.** Prohibido reutilizar la cifra calculada para +3,2 % cuando el plan apunta a otra cosa — es el fallback silencioso que `CONTRATOS_Y_METRICAS.md` §7 ya prohíbe.
3. **Si la celda tiene menos de N observaciones, se muestra «sin estimación fiable»**, no una cifra bonita. N se fija antes de mirar; mi propuesta es 50.
4. **Se reestima con ventana móvil y se muestra su fecha.** Con la tasa base moviéndose 15 puntos en una semana, un número calibrado en agosto es desinformación en septiembre.
5. **Una confianza que ordene señales solo puede afirmarse después** de capturar el universo no avisado (lo que ya pide `PLAN.md` §6) y de una validación temporal con episodios enteros en la misma partición. **Hasta entonces, la posición honesta es: no sabemos ordenar señales; sabemos elegir la geometría del objetivo.**

Y una consecuencia incómoda que conviene escribir ahora: puede que ese ordenador no exista. Los datos actuales dicen que, con lo que el sistema mide hoy, **la palanca no es escoger mejor la señal, es escoger el objetivo**.

---

## 5. Qué añadiría a la limpieza de datos que pide el plan

Lo que encontré al reconstruir los recorridos, por si sirve para la fase 0:

- **Cobertura buena donde se mide:** 99,4 % de las velas esperadas en la cohorte de Telegram, y **ninguna** vela de un minuto en la que el precio tocara TP y stop a la vez, así que el orden de los toques nunca es ambiguo en esta muestra. Esa comprobación debería quedar como prueba fija del evaluador común de la fase 2.
- **La purga sigue siendo el agujero grande:** 1.500 de las 6.202 señales no se pueden evaluar porque ya no existen sus velas de 1 minuto — todas las anteriores al 8-sep. Antes de tocar nada más, exportar la evidencia de los experimentos como pide `PLAN.md` §6.
- **La reconstrucción coincide con el sistema:** 46 TP, 46 SL y 88 VENCIDO de `notificacion_planes` sin una sola discrepancia, y 99 % de acuerdo con `signals.status`. Eso significa que el evaluador nuevo tiene una referencia sólida contra la que compararse en sombra.
- **Tres filtros descartan señales tan buenas como las que envían:** «resistencia antes del TP» (50,4 % llega al +3,2 % antes que al stop), el tope de 3 avisos por hora (45,5 %) y «ya hay un plan notificado» (56,5 %, mejor que el 53,3 % de las enviadas). Los dos últimos son límites de capacidad, no de calidad: al medir la política de primera oportunidad del episodio hay que contarlos aparte, o parecerá que el filtro acierta cuando solo estaba lleno.
- **El escenario `TOCÓ_FONDO` rinde la mitad** que `SUBIENDO` (10,0 % contra 26,4 % al TP) con el doble de caída máxima (−4,85 % contra −2,16 %). Es exactamente la rama que el motor B quiere reconstruir: empezar por medir sus avisos actuales como línea base antes de sustituirlos.

---

## 6. Decisiones que siguen siendo tuyas

1. **La ventana de silencio del episodio.** Propongo 12 h por las razones de arriba; si prefieres otra, el criterio debería fijarse antes de medir, no después.
2. **Si el objetivo fijo sustituye al TP variable o solo lo acompaña.** Los datos dicen que cobra más a menudo con esperanza parecida; cuál prefieres depende de cómo quieras operar, y eso no lo decide la tabla.
3. **Aceptar que la confianza sea geometría + régimen** mientras no exista un ordenador validado, en vez de seguir mostrando una puntuación que no discrimina.
4. **Riesgo por operación y tamaño de posición**, que el plan deja pendiente y sin los cuales la comparación de stops no se puede cerrar.

---

### Reproducir

Los scripts están en [`audit/2026-09-21/telegram-signal-review/`](../../2026-09-21/telegram-signal-review/) — `episodios.py`, `confianza.py`, `confianza2.py` y `tiempos.py` producen todas las tablas de esta adenda; los tres pases remotos son de solo lectura (`mode=ro`, `PRAGMA query_only`, transacción revertida).
