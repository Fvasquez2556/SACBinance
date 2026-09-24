# El soporte, el techo y el desvío de entrada · 22-sep-2026, 06:00 UTC

Desplegado. Tres cosas: los dos niveles del plan visibles en los tres sitios, el aviso de desvío de entrada, y el arreglo del volumen que faltaba en la sombra por marcos. **Sin migración.**

## 1 · Los dos niveles que se calculaban y se tiraban

`calcular_niveles()` conocía desde siempre el soporte estructural que ancla el stop y la resistencia más cercana, pero solo publicaba `sl_basis` como texto. El operador veía `SL 0.211382` sin saber sobre qué se apoya, y un TP sin saber si había algo en medio.

Ahora se publican (`soporte`, `toques_soporte`, `toques_resistencia`), **se congelan con la alerta** junto al resto del plan, y llegan a:

- **Telegram** — `soporte que sostiene el SL 0.211382 (−5,51 %) · 4 toques · soporte estructural` y `techo que debe romper 0.2402 (+7,37 %) · 3 toques — está entre la entrada y el TP`. Si el techo queda por encima del TP se dice sin alarma; si no hay niveles, no se inventan líneas.
- **Tarjetas del tablero** — dos líneas bajo el plan, en ámbar solo cuando el techo estorba de verdad.
- **Análisis por par** — los dos niveles por marco, con sus toques, la base del stop y el volumen de la ruptura.

En el informe por marcos, `calcular_plan_direccional()` expone ahora `nivel_apoyo` y `toques_apoyo`, que tampoco salían.

**Las alertas rehidratadas tras un reinicio no traen estos niveles**, porque se reconstruyen desde `outcomes`, que no los guarda. No se rellenan con los niveles de hoy: mezclar un plan congelado con estructura actual es exactamente lo que este sistema evita. Aparecen en cuanto la alerta se sustituye.

## 2 · El aviso de desvío de entrada

Sale de un caso real. Plan de PYTHUSDT: entrada 0,06307, TP 0,065397, SL 0,061907 — arriesgar 1,84 % para ganar 3,69 %, **R:R 2,0**. La entrada se hizo en 0,06396, un 1,41 % más arriba. Desde ese precio se arriesga **3,21 %** para ganar **2,25 %**: **R:R 0,70**. La misma operación, al revés, y nada lo decía.

`desvioDeEntrada()` compara tu precio con el del plan mientras lo escribes, en «Tomé esta entrada», y sobre la operación ya abierta. El aviso no mira el porcentaje de desvío —que por sí solo no significa nada— sino lo que queda a cada lado: **por debajo de R:R 1 arriesgas más de lo que puedes ganar**, y ahí el aviso se pone en ámbar. Si el precio cae fuera del plan (en el stop o pasado el TP) lo dice en vez de puntuarlo.

Los dos porcentajes se miden sobre **tu** precio, que es el capital que pones. Medir el riesgo sobre el stop y el recorrido sobre la entrada da un cociente distinto del R:R real — un error que cometí al explicarlo la primera vez, y que la prueba con los números de PYTH ahora fija.

## 3 · El volumen que faltaba

`leer_tf()` solo tenía `vol_ratio` cuando el marco traía `IndSnap`, y eso solo pasa en los marcos «en vivo»: **14.496 de 19.565 rupturas guardadas no lo traían**. Ahora se calcula de las velas cuando falta —última contra la media de 20—, con la misma definición que el indicador.

Comprobado tras el despliegue: **64 de 64** rupturas por marco de los primeros 20 minutos llevan volumen. Antes era el 26 %.

## Lo que la medición dice sobre la hipótesis del rango

Medido sobre 5.564 operaciones cerradas con `pos_en_rango`, entrar abajo del rango lee **peor**: 29,8 % de aciertos y −0,494 R en el suelo (0–20 %) frente a 37,5 % y −0,106 R arriba (60–80 %). En el caso concreto de «tendencia bajando + precio en el suelo» (`TOCÓ_FONDO`) es el peor cuadrante: 28,3 % y −0,446 R sobre 658 casos.

Lo que sí aparece es el matiz del margen: pegado al soporte (<0,5 %) el stop mediano es de **0,86 %** y el resultado −0,849 R; con 1–2 % de margen el stop es 1,66 % y el resultado −0,147 R. **No es la cercanía al soporte: es el ancho del stop.** Es la misma conclusión que el análisis del 21-sep y la rejilla de objetivos — los stops estrechos pierden.

## Despliegue

Copia previa en `/home/flox/.cache/sacbinance-niveles-deploy/20260922T055811Z/` (cinco archivos de backend y el `dist` anterior). **139 pruebas en verde en el servidor** (12 nuevas de backend, 8 de frontend). Reinicio limpio, API arriba en ~60 s, **0 errores**.
