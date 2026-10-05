# Revisión completa de SACBinance

**Fecha:** 2 de octubre de 2026, noche en Guatemala (3-oct UTC).
**Qué se revisó:**
- **El código que corre en el servidor:** se comprobó archivo por archivo que es idéntico al de la copia local.
- **La base de datos (en solo lectura):** 9.968.294 velas de 1 minuto de 419 monedas, del 8-sep al 3-oct, y 31.198 avisos.
- **Todo lo investigado antes:** las carpetas `audit/` e `informes/`.
- **Las pruebas automáticas:** las 367 del backend pasan.

**Actualización del 5-oct:** el estudio de 7 meses con velas oficiales de Binance (150 monedas, marzo a septiembre) confirma lo de este informe. Ninguna de 216 combinaciones cumple el criterio registrado de antemano, y el disparo que imita a SAC rinde igual que comprar al azar. Ver [seis-meses/RESULTADOS.md](../seis-meses/RESULTADOS.md).

**Cómo se midió:** la operación de referencia es la tuya. Compra al precio del aviso, meta **+2,67 %** bruta, stop **−1,8 %** y cierre forzoso a las 12 h. El coste es de 0,5 puntos por operación. Con esa geometría, **para no perder hay que acertar el 51,5 % de las operaciones**; un precio al azar acierta un 40 %.

---

## Lo principal, en seis puntos

1. **Tu sospecha tiene una parte de razón.** La puntuación mide **cuánto está subiendo la moneda ahora mismo**: los últimos 3 minutos y las compras de los últimos 30 segundos. El tablero la recalcula cada minuto, así que durante una subida la moneda pasa a FUERTE o EXTRA **cuando ya va subiendo**. Es un velocímetro, no un pronóstico.
2. **Los avisos que quedan registrados no llegan con 3 % ya consumido.** Al emitirse, la mediana va +1,1 % sobre el mínimo de la última hora, y solo el 2 % de los FUERTE llevaba +3 % o más. El problema no es que lleguen tarde: es que **después no suben más que en cualquier otro momento.**
3. **Hay un error de código grave: FUERTE casi nunca significa lo que dice.** El 97 % de los FUERTE **no tenía confirmación de compras**, que es la condición que el código exige para pasar de 79 puntos. Llegaron a FUERTE porque BTC estaba alcista: el ajuste por BTC multiplica por 1,10 *después* del tope. Así, 79 × 1,10 = 86, y **2 de cada 3 FUERTE tienen exactamente 86 puntos.**
4. **Ningún nivel predice.** En 12 h, la meta llega antes que el stop en estos porcentajes:

   | VIGILANCIA | MODERADA | FUERTE | EXTRA | Telegram |
   |---|---|---|---|---|
   | 39 % | 40 % | 42 % | 44 % | 41 % |

   Todos quedan lejos del 51,5 % que hace falta.
5. **Revisé todas las monedas cada 5 minutos, no solo los avisos:** 1,42 millones de momentos, buscando lo que aparece *antes* de una subida.
   - Lo que funcionó del 9 al 23-sep se dio vuelta del 24-sep al 2-oct.
   - De **15 ideas × 12 combinaciones de meta, stop y plazo (180 pruebas), ninguna gana en las dos mitades** con coste de 0,5 %.
6. **Lo único que se repite en las dos mitades es que lo que sube de golpe devuelve parte.** Después de subir +3 % en 15 min, a las 3 h la mediana está −1,3 % abajo. Sirve para **no comprar** en ese momento. No sirve para ganar en corto: ese mismo plazo de 3 h tiene un recorrido típico de −5 % / +4,5 %, y un stop de 1,8 % salta casi siempre.

---

## 1. ¿El sistema marca FUERTE tarde?

### Por aviso: cuánto había subido antes y qué pasó después

Las cifras son medianas sobre todos los avisos de SUBIENDO o BREAKOUT, con sus 12 h de velas completas.

| nivel | avisos | subió en los 15 min previos | desde el mínimo de 1 h | llevaban +3 % o más | máximo en 12 h | mínimo en 12 h | meta antes que stop |
|---|---|---|---|---|---|---|---|
| VIGILANCIA | 4.021 | +0,46 % | +0,95 % | 1,5 % | +2,15 % | −2,18 % | 39,3 % |
| MODERADA | 7.018 | +0,46 % | +1,04 % | 1,5 % | +2,38 % | −2,25 % | 40,1 % |
| FUERTE | 10.923 | +0,49 % | +1,09 % | 2,2 % | +2,50 % | −2,26 % | 41,8 % |
| EXTRA-FUERTE | 597 | +0,67 % | +1,42 % | 5,5 % | +2,60 % | −2,33 % | 43,9 % |
| enviados a Telegram | 680 | +0,60 % | +1,48 % | 6,9 % | +3,10 % | −2,84 % | 41,1 % |

- **Cuanto más alto el nivel, más había subido ya**, aunque poco: EXTRA va +1,4 % y VIGILANCIA +0,95 %.
- **Después, los cinco grupos se comportan casi igual:** suben unos +2,5 % y bajan unos −2,3 % en 12 h.
- **Los de Telegram se mueven más en las dos direcciones.** El filtro de Telegram exige una meta neta de +3,2 %, y eso elige monedas más volátiles.

### Por subida grande: ¿avisó el sistema, y cuándo?

Busqué todas las subidas de **+5 % o más en 3 h o menos**, contadas desde un mínimo:

- Hubo **5.157 subidas en 391 monedas**, unas 200 por día. La mediana subió +6,7 % en 137 min.
- **El 64 % (3.312) no tuvo ningún aviso**, ni media hora antes del mínimo ni durante la subida. El 79 % no tuvo ningún FUERTE.
- **Cuando hubo aviso,** el primero llegó a los **39 min** del mínimo (mediana), con el **28 %** de la subida ya hecho. Al pico le quedaban +4,25 %, pero eso solo se sabe mirando hacia atrás.
- **El primer FUERTE llegó más tarde:** a los **53 min**, con el **33 %** hecho.

**Conclusión:** el sistema no detecta antes. Cuando detecta, ya pasó un tercio de la subida. Además, emite unos 1.400 avisos al día para unas 200 subidas grandes, y la mayoría de sus avisos no son subidas grandes.

---

## 2. Errores encontrados

### E1. El ajuste por BTC rompe los niveles — `backend/src/state/engine.py:702-707` (grave)

```python
if st.fsm_state == FSM_RISING:
    if btc_reg == "BAJISTA":  val = int(val * 0.55)
    elif btc_reg == "ALCISTA": val = min(100, int(val * 1.10))
    tier = _tier_from_score(val)      # <- recalcula el nivel desde cero
```

`score_and_tier` (`scoring.py`) aplica dos protecciones:
- **Tope de 79 sin compras confirmadas.** Sin confirmación, no se llega a FUERTE.
- **Piso de 75 con mercado NEUTRAL** (y de 85 con mercado BAJISTA). Por debajo, no hay aviso.

Estas tres líneas se saltan las dos. **Comprobado con los avisos reales:**

| | |
|---|---|
| FUERTE **sin** compras confirmadas (menos de 8 operaciones en 30 s) | 3.769 de 3.885 (97 %) |
| FUERTE con BTC alcista | 3.862 de 3.885 (99,4 %) |
| FUERTE con exactamente 86 puntos (= 79 × 1,10) | 2.548 de 3.885 (66 %) |
| FUERTE con 80 a 86 puntos (todas las filas) | 11.484 de 11.930 (96 %) |
| MODERADA con mercado NEUTRAL y menos de 75 (deberían no existir) | 972 |
| VIGILANCIA con mercado NEUTRAL y menos de 75 (deberían no existir) | 2.235 |

*Las tres primeras filas cuentan los 3.885 FUERTE que tienen sus datos de emisión guardados.*

- **Efecto:** FUERTE quiere decir, en la práctica, "MODERADA en un día en que BTC sube". De los 732 avisos enviados a Telegram, 504 son FUERTE.
- **Arreglo:** aplicar el ajuste por BTC *dentro* de `score_and_tier`, antes del tope y del piso, o volver a aplicar ambos después. Es una línea de lógica y una prueba nueva.
- **Ojo:** al corregirlo habrá **muchos menos FUERTE**. Arreglarlo no hará ganar dinero, porque el nivel no predecía nada de todas formas. Pero el nombre volverá a decir la verdad.

### E2. El nivel en vivo del tablero es un velocímetro, y se lee como una calificación (diseño)

El tablero muestra `pair.tier` (`frontend/src/components/PairRow.tsx:37`), recalculado cada minuto. La puntuación de SUBIENDO se arma así:
- 48 puntos de base;
- más lo que subió en 3 minutos (z_rise), hasta 22 puntos;
- más la velocidad, el volumen, la tendencia, el RSI y el MACD;
- más 14 si dominan las compras en los últimos 30 s;
- y se multiplica por la tendencia del mercado y de BTC.

Todo eso describe el pasado inmediato. Por eso una moneda "se pone FUERTE" en medio de la subida. **Ya se había medido** en septiembre (`audit/2026-09-22/.../LEER_PRIMERO.md`: la puntuación no ordena, AUC 0,50–0,58). Aun así, se sigue usando como filtro de Telegram (75 puntos o más).

### E3. La confirmación de compras llega tarde por construcción — `backend/main.py:218`

El flujo de compras (aggTrade) solo se abre para las 40 monedas con mayor |z|, y esa lista se recalcula **cada 180 s**:
1. Una moneda tiene que moverse primero para entrar en la lista.
2. Hasta 3 minutos después se abre su flujo.
3. Hacen falta 8 operaciones en 30 s para que cuente.

EXTRA exige ese flujo en todos los casos (los 244 EXTRA con datos guardados lo tenían). Por eso **EXTRA solo puede llegar después de que la moneda ya se movió.**

### E4. Faltaron muchas velas en septiembre (datos)

| periodo | minutos sin vela, en promedio por día |
|---|---|
| 9 al 25 de septiembre | 12 % a 31 % |
| 26 al 28 de septiembre | 2 % a 4 % |
| 29-sep al 1-oct (apagón y después) | 8 % a 15 % |
| 2 de octubre / hoy | 5,8 % / 0,05 % |

- **Hay 99 monedas con más del 20 % de huecos.** En buena parte son monedas que **entran y salen del universo** por volumen: mientras están fuera, no se guardan velas.
- **Comprobado el 5-oct contra las velas oficiales de Binance,** en las 150 monedas más líquidas y del 8-sep al 1-oct (`seis-meses/comparar_sac.json`):
  - a la base de SAC le falta el **3,4 %** de los minutos;
  - los peores días fueron del 9 al 17-sep, con 6–9 %; del 19 al 25-sep, cerca del 1 %; desde el 26-sep, menos del 1 %;
  - **cuando la vela está, es idéntica** a la oficial: 5 cierres distintos en 4,7 millones.

  El 12–31 % de la tabla mezcla esas faltas con las monedas chicas que entran y salen del universo.
- **La reparación automática funciona desde el 26-sep.**
- **Consecuencia:** el 14 % de las señales MODERADA del histórico no se puede medir, y los resultados de septiembre tienen ese hueco.
- **Detalle menor:** una moneda que sale del universo nunca se borra de la memoria. La reparación la rehidrata cada 5 minutos para siempre (se ve en el registro: "Reparando velas: 1 pares…").

### E5. El servidor no se actualiza con git (riesgo)

- **En el servidor:** el repositorio está en el commit `f82bcff` (de septiembre), con 23 archivos modificados a mano y 39 carpetas o archivos sin registrar.
- **En la copia local:** hay 10 archivos sin commit (de la otra sesión: patrones visibles) que **ya están corriendo en producción**.

Nadie puede saber con certeza qué versión corre, ni volver atrás si algo falla. **Arreglo:** desplegar siempre desde un commit, con un script que copie y verifique sumas, como ya se hace con `ia_sombra`.

---

## 3. Duplicados y complejidad

- **La misma pregunta, "¿tocó primero la meta o el stop?", está programada al menos 13 veces:**
  - 8 en el backend: `signal_tracker`, `outcome_tracker`, `active_alert`, `notify/policy`, `evaluacion/recorrido`, `experimentos/almacen`, `tf_rupture_tracker` y `hoyo`;
  - 5 sombras aparte: `objetivos_sombra`, `rebotes_sombra` (largos y cortos), `moderadas_sombra` v1/v2 e `ia_sombra`.

  Todas usan la misma regla (si una vela toca los dos, gana el stop). Pero cada cambio hay que hacerlo 13 veces, y cada una puede equivocarse distinto.
- **Cuatro maneras de medir "cuánto subió ya":**
  - `consumido_pct` (60 min, en `impulse.py`);
  - `z_rise` (3 min);
  - `rango_1h_pct`;
  - `dmin` de las sombras.
- **Tres familias de avisos que no se miden juntas:** el nivel (VIGILANCIA a EXTRA); los perfiles (tendencia, ignición, base y rebote); y las rupturas por marco.
- **29 tablas en la base (2,4 GB), 43 scripts sueltos en `research/` y 1,1 GB en `audit/`** (copias de la base de septiembre, en su mayoría fuera de git).

Nada de esto rompe el sistema hoy. Pero explica por qué cada idea nueva termina en otra sombra más, y por qué cuesta saber qué está funcionando.

---

## 4. Tus ideas, puestas a prueba con todas las monedas

Unidad: una entrada por moneda cada 12 h, sin solapes. "Neto" es el promedio por operación con 0,5 de coste.

| idea | del 9 al 23-sep | del 24-sep al 2-oct |
|---|---|---|
| Comprar en cualquier momento (referencia) | 43 % de aciertos · −0,34 % | 36 % · −0,61 % |
| Rompe el máximo de 24 h con volumen ×3 | 48 % · −0,19 % | 33 % · −0,77 % |
| Volumen ×3 sin mover el precio ("acumulación") | 43 % · −0,31 % | 33 % · −0,73 % |
| Mercado a favor (60 % de monedas y BTC arriba en 24 h) | 53 % · **+0,03 %** | 33 % · −0,75 % |
| Rebote tras desplome (−3 % en 15 min) | 42 % · −0,42 % | 32 % · −0,85 % |
| Moneda a −10 % o más de su máximo de 24 h | 42 % · −0,45 % | 43 % · −0,39 % |
| **Corto** tras subir +3 % en 15 min | 37 % · −0,66 % | 45 % · −0,28 % |
| **Corto** tras subir +10 % en 1 h | 33 % · −0,81 % | 47 % · −0,21 % |
| **Corto** cerca del máximo de 24 h sin haber subido | 29 % · −0,77 % | 43 % · −0,32 % |

- **"Lo que sube de golpe, baja de golpe":** se cumple en mediana y en las dos mitades.

  | después de… | precio a las 3 h (mediana) |
  |---|---|
  | +3 % en 15 min | −1,34 % y −1,29 % |
  | +10 % en 1 h | −2,6 % y −2,3 % |

  Pero en esas 3 h el recorrido típico es de −5 % / +4,5 %, y un stop de 1,8 % salta antes. **Útil para no comprar ahí, no para vender en corto.**
- **"Cerca del máximo sin haber subido, va a bajar":** depende de la época. En la primera mitad cayó antes de subir el 38 % de las veces, *menos* que el promedio. En la segunda, el 58 %, *más* que el promedio.
- **"Hay patrones que se ven antes de una subida":** junté los 20 rasgos (subidas de 5 min a 24 h, rangos, posición, volumen, mecha, BTC, mercado y hora) en un modelo entrenado con la primera mitad.
  - En la primera mitad, su mejor 1 % acertó el 54 % y ganó +0,10 % por operación.
  - **En la segunda, ese mismo 1 % acertó el 35 % y perdió −0,68 %**, peor que comprar al azar. Lo aprendido no se sostuvo.
- **El mercado pesa más que cualquier patrón.** Comprar al azar dio, *antes del coste*:
  - +0,16 % por operación en la primera mitad;
  - −0,10 % en la segunda.

  Por días, del 17 al 22-sep (casi todo el mercado subiendo) se ganó, y del 10 al 16-sep se perdió.
- **El coste decide mucho.** Con 0,5 %, todo pierde. **Con 0,2 %** (comisión de 0,1 % por lado, sin deslizamiento), una sola combinación sale positiva en las dos mitades: comprar una moneda que está a −10 % o más de su máximo de 24 h, con meta +2,67 % y stop −5 % u −8 % (+0,00 / +0,27 % y +0,17 / +0,44 %).
  - Pero es **1 de 180 pruebas**: puede ser suerte.
  - Además usa un stop de 5 a 8 %, que con margin x5 es perder 25 a 40 % del capital de esa operación.

---

## 5. Propuesta

No encontré nada, con estos 24 días de datos, que dé +2,67 % de forma sostenida. Prometer otra cosa sería mentirte. Sí veo cuatro pasos que cambian de verdad la situación:

### Paso 1. Arreglar lo roto (un día de trabajo; requiere tu permiso para reiniciar SAC)
- **E1:** que FUERTE vuelva a exigir compras confirmadas y que se respete el piso de 75. Incluye su prueba.
- **E5:** desplegar desde git, con verificación de sumas.
- **Tablero:** cambiar el texto del nivel en vivo, por ejemplo "velocidad: alta", para que no se lea como una calificación de la oportunidad.

### Paso 2. Más historia antes de más ideas (lo más importante)
**Todo lo medido en este proyecto sale de 24 días**, con dos tipos de mercado. Con eso, cualquier patrón puede ser casualidad.

- **Qué propongo:** bajar **6 meses de velas de 1 minuto** de las ~150 monedas más líquidas desde los archivos públicos oficiales de Binance (`data.binance.vision`, ~1–2 GB comprimidos). Después, repetir este mismo escaneo, que ya está escrito y probado.
- **Qué responde:** si existe algún patrón que gane en varios meses distintos, incluidos meses alcistas, bajistas y laterales.

### Paso 3. Una sola sombra, en lugar de seis
- **Al terminar el 15-oct:** cerrar las sombras de MODERADA, rebotes y cortos (la de IA da su veredicto ese día).
- **Reemplazarlas por un laboratorio único:** cada noche mide, sobre **todas las monedas**, las 2 o 3 reglas que sobrevivan al paso 2, congeladas con huella.
- **Criterio para aceptar una regla:** que sea positiva con tu coste real en al menos 150 entradas y 8 días.

### Paso 4. Mientras tanto, si sigues operando
- **No compres** una moneda que acaba de subir +3 % en 15 min: en las dos mitades, la mediana devolvió −1,3 % en 3 h.
- **No tomes FUERTE como mejor que MODERADA:** hoy significan casi lo mismo.
- **Con margin x5,** un stop de −1,8 % es −9 % de lo que pusiste en esa operación, y cinco stops seguidos son −45 %.

Esto es medición, no consejo de inversión.

---

## Archivos de esta revisión

Todos están en `audit/2026-10-03/revision-completa/`.

| archivo | qué es |
|---|---|
| `exportar.py` | exporta de la base de producción, en solo lectura |
| `fuente.pkl.gz` | datos congelados (92 MB), sha256 `0977d1cc3eb4e357c6637370bed133041d85fd4cde1a5457351713295e7b15c6` |
| `retraso.py` → `retraso.json` | sección 1 |
| `verificar_btc.py` → `verificar_btc.json` | error E1 |
| `huecos.py` → `huecos.json` | error E4 |
| `escaneo.py` → `escaneo.npz` | 1,42 millones de momentos, todas las monedas |
| `patrones.py` → `patrones.json` | rasgos uno a uno y modelo combinado |
| `hipotesis.py` → `hipotesis.json` | las 15 ideas × 12 combinaciones, y el resultado día por día |
