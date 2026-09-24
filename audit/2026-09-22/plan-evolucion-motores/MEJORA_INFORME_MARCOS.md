# El informe por marcos, con números detrás · 22-sep-2026, 04:27 UTC

Desplegado. Tres cambios pedidos: la tasa medida al lado de cada lectura, los dos avisos que los datos contradicen, y la coherencia con el horizonte intradía. **Sin migración**: solo lee tablas que ya existían.

## De dónde salen los números

`rupturas_tf` llevaba **49.648 rupturas por marco registradas con su desenlace** mientras el informe decía, en su propio docstring, que ninguna de sus lecturas tenía medición. Ahora las lee: ventana móvil de 14 días, mínimo de 50 observaciones por celda, y la instantánea cacheada 5 minutos porque el informe se pide a mano.

`construir_informe` sigue siendo una **función pura**. Recibe la instantánea ya calculada, igual que recibe los indicadores; quien la busca en la base es `obtener_informe`.

## 1 · La tasa al lado de cada lectura

| Marco | Tocó el TP antes que el stop | Muestra | Llenó la entrada |
|---|---|---|---|
| 5m | 47,9 % | n=13.776 | 90,1 % |
| 15m alcista | 52,3 % | n=4.321 | 82,2 % |
| 15m **bajista** | **18,6 %** | n=3.808 | 94,7 % |
| 1h | 67,5 % | n=826 | 55,1 % |
| 4h | 56,4 % | n=172 | 32,0 % |

La celda bajista de 15m es el mejor argumento para haber hecho esto: el aviso de siempre —«todo lo medido aquí es comprador»— ahora tiene su número al lado.

El resumen cuelga de la **confluencia**, que es lo único monótono de toda la medición: 0 marcos 44,5 % · 1 → 46,0 % · 2 → 51,4 % · 3 → 58,5 % · 4 → 62,4 %.

Reglas, las mismas de la adenda: cada celda con su `n` y su ventana; por debajo del mínimo dice **«sin estimación fiable»** en vez de ensancharse en silencio; y el porcentaje de fill se publica al lado, porque la tasa está condicionada a haber entrado —con ATR alto solo llena el 30 %—.

## 2 · Los dos avisos reescritos

**Conflicto entre marcos.** Antes insinuaba un riesgo. Ahora: *«se enseñan los dos y no se promedian. Medido en los últimos 14 días, el desacuerdo no anticipa peor resultado: 52,4 % de las rupturas en conflicto tocaron su TP antes que el stop (n=5.634) frente al 48,1 % de las que iban de acuerdo (n=13.458)»*. Sin muestra suficiente, dice que no la hay.

**Nivel que estorba antes del TP.** Sigue describiendo el obstáculo, que es real, pero con el dato: *«con un nivel de por medio, 50,0 % (n=15.209); sin él, 46,5 % (n=3.882)»*. Es el tercer sitio donde ese veto apunta al revés de lo que dice — los otros dos son el filtro de Telegram y la rejilla de objetivos.

## 3 · Coherencia intradía

Cada marco lleva ahora cuánto tarda y si cabe en la jornada: **5m → 5,03 h de mediana, el 82,5 % cabe en 12 h; 15m → 6,45 h, 74,0 %; 1h → 10,08 h, 58,1 %; 4h → 10,95 h, 58,1 %**. Por debajo del 70 % sale un aviso con su número, que sustituye al texto anterior sobre «días» y una ventana de 24 h que ya no existe.

## Despliegue

Copia previa en `/home/flox/.cache/sacbinance-tasas-deploy/20260922T042542Z/` (tres archivos de backend y el `dist` anterior). **127 pruebas en verde en el servidor** (14 nuevas). Reinicio limpio, API arriba en ~60 s, **0 errores**.

Comprobado en vivo con BTCUSDT, que además cayó en un caso ideal: marcos en desacuerdo (5m y 4h al alza, 15m a la baja), cada tarjeta con su tasa, el aviso de conflicto con sus dos porcentajes y el de horizonte señalando 4h con su 58,1 %.

## Lo que queda de la propuesta

- **Reevaluar las 49.648 rupturas con el evaluador de la fase 2**, con barreras homogéneas en R, para que los marcos sean comparables entre sí. Hoy cada fila usa el plan que se calculó entonces.
- **Cerrar el agujero de `vol_ratio`**: el 74 % de las filas lo tiene nulo, así que la pregunta de si el volumen en la ruptura sirve —la receta que repite toda la literatura— sigue sin poder responderse con estos datos. Con lo que hay, no aparece: <1× da 52,6 %, 1,5–2× da 56,2 % y 2–3× baja a 50,0 %, sin relación monótona.
