# Las rupturas por marco, medidas con barreras homogéneas en R · 22-sep-2026

El plan dejaba esto abierto antes de la fase 4: *«reevaluar las 49.648 rupturas por marco con el evaluador de la fase 2 (barreras homogéneas en R)»*. Hecho sobre **50.938 rupturas**, de las cuales **43.500 están maduras** (12 h cumplidas) y con cobertura ≥ 90 % de las velas. Solo lectura sobre producción.

## Por qué no valía la medición anterior

`rupturas_tf` guarda el desenlace contra el plan que se habría publicado, y ese plan tiene un stop distinto en cada fila: `risk_pct` va del 0,5 % al 2,5 %. Decir «5m acierta más que 1h» con esas barreras compara **anchos de stop**, no detectores. Es el mismo error que el análisis del 21-sep ya había desarmado en las señales de Telegram.

Aquí la barrera es la misma para todos en unidades del ruido del propio par:

```
R = ATR(%) del marco en el momento de detectar
simétrica:  +1R antes que −1R      (azar ≈ 50 %)
plan:       +2R antes que −1R      (azar ≈ 33 %, la geometría real)
ventana:    12 h
```

Y **cada ruptura tiene su propio control**: una entrada al azar en el mismo par, el mismo periodo y la misma R. La comparación es pareada, así que mide lo único que importa — si el detector elige *el momento* — y no si el par se movía así de todos modos.

## Lo que sale

### 1 · A 5m y 15m el detector es peor que entrar al azar

| Dirección | Marco | Detector | Control | Diferencia (95 %) |
|---|---|---|---|---|
| Alcista | **5m** | 48,7 % | 53,0 % | **−4,32 pp** [−5,40; −3,24] |
| Alcista | 15m | 54,6 % | 55,6 % | −1,04 pp [−2,96; +0,88] |
| Alcista | **1h** | 64,5 % | 56,0 % | **+8,46 pp** [+4,23; +12,69] |
| Alcista | 4h | 61,8 % | 42,2 % | +19,61 pp [+10,6; +28,7] |
| Bajista | 5m | 45,4 % | 47,1 % | −1,72 pp [−2,85; −0,59] |
| Bajista | 1h | 32,3 % | 37,0 % | −4,73 pp [−9,55; +0,09] |

El marco de 5m es el **72 %** de todas las rupturas: 4.398 al día. Ese caudal no solo no aporta, resta. Con la geometría del plan (+2R/−1R) el resultado es el mismo: −3,35 pp a 5m.

### 2 · Las rupturas alcistas de 1h sí baten al control, y aguantan el corte

Es el primer resultado de todo este proyecto que sobrevive a partir la muestra por la mitad:

| | n | Detector | Control | Diferencia |
|---|---|---|---|---|
| Primera mitad (hasta 20-sep 11:00 UTC) | 503 | 63,2 % | 56,3 % | **+6,96 pp** ±5,85 |
| Segunda mitad | 513 | 65,7 % | 55,8 % | **+9,94 pp** ±6,12 |

Día a día: 18-sep +19,5 pp, 19-sep −6,4, 20-sep +4,3, 21-sep +16,7. Tres de cuatro a favor, el día en contra no es significativo.

Y **cabe en la jornada**: mediana 76 min hasta el desenlace, p90 312 min, solo el 2,4 % sigue sin resolverse a las 12 h. Hay 261 rupturas alcistas de 1h al día sobre 319 pares — de sobra para un sistema que toma una o dos entradas.

**4h no sirve para esto** aunque su número sea el más alto: 0,00 pp en la primera mitad y +41 en la segunda con n≈100, y el **23 % no se resuelve dentro de las 12 h**. Un objetivo que no se cobra en la jornada no es un objetivo de este sistema.

### 3 · Una ruptura bajista no significa que la caída siga

Es lo contrario de lo que el nombre sugiere: solo el 44,1 % de las rupturas bajistas llega a −1R antes que a +1R, y una entrada al azar en el mismo par llega el 45,8 % de las veces. A 1h, 32,3 % contra 37,0 %.

Y el peor caso es justo el que la regla popular llama confirmación — **romper a la baja con volumen alto**:

| Volumen relativo | Detector | Control | Diferencia |
|---|---|---|---|
| **≥ 2×** | 35,8 % | 45,0 % | **−9,26 pp** ±4,98 |
| 1–2× | 40,0 % | 42,2 % | −2,21 pp ±3,71 |
| < 1× | 42,3 % | 42,5 % | −0,22 pp ±2,42 |

Consistente en las dos mitades (−5,3 y −13,2), significativo en la segunda. No está establecido, pero apunta a la familia que el plan ya listaba: **barrida de un nivel y recuperación posterior**.

### 4 · Nada ordena

AUC de todas las columnas guardadas contra «llega a +1R antes que a −1R»:

```
atr_pct 0,519   vol_ratio 0,525   toques_nivel 0,480   rsi14 0,508
conf_confirmadas 0,506   conf_en_conflicto 0,487   confirmada 0,500
```

`confirmada` da **0,500 exacto**: el campo que decide si la ruptura está confirmada no distingue absolutamente nada. Y la confluencia entre los cuatro marcos —la variable que el propio módulo declaraba como «la que hay que medir, si no separa el resultado la función entera es adorno»— tampoco: 0,506 y 0,487.

Ninguna celda de confluencia bate a su control. Las que parecían buenas (4 marcos confirmados: 56,7 %) tienen un control de 53,3 %: la diferencia es +3,3 pp ±6,9.

### 5 · Un detalle de geometría que importa

MFE mediana **+7,08 R**, MAE mediana **−3,33 R**, y el desenlace llega en 10 minutos de mediana. Con 1 ATR la barrera está *dentro* del ruido: el precio la cruza por respirar. Eso explica por qué a 5m casi todo se resuelve en minutos y por qué el detector no puede añadir nada ahí — no hay nada que detectar en esa escala.

El 11–13 % de los stops se ejecuta con **hueco**, por debajo del nivel. No es un detalle contable: es peor precio del que el nivel promete.

## Qué decide esto sobre la fase 4

1. **El motor de continuación se ancla en 1h.** Es el único marco con ventaja medida frente a su control, estable en las dos mitades y con desenlace dentro de la jornada. Los marcos rápidos entran como contexto, no como disparador.
2. **El motor de caída no puede asumir que una caída sigue.** Los datos dicen lo contrario. Su trabajo es describir el estado y esperar el disparador de recuperación declarado, nunca anticipar el suelo.
3. **La confluencia no se usa como confianza.** Se sigue guardando —es barata y puede cambiar con más régimen—, pero no pondera nada.
4. **La unidad de riesgo tiene que ser más ancha que 1 ATR** para que la barrera signifique algo. Los planes actuales (0,5 %–2,5 %) ya lo son; lo que no sirve es medirlos con 1 ATR y creer la tasa que sale.

## Salvedades

4,4 días, un solo régimen, 319 pares. La ventaja de 1h es de **1.016 casos** y la del volumen bajista de **713**. Es suficiente para orientar el diseño de una fase en sombra; no es suficiente para cambiar la emisión, y esta fase no la cambia.

## Reproducir

```bash
ssh sac '/home/flox/sacbinance/backend/venv/bin/python -' < reeval_rupturas_remote.py > reeval.json.gz
python analizar_reeval.py && python analizar_reeval2.py && python analizar_reeval3.py
```
