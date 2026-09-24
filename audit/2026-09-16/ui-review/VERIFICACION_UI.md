# Corrección de UI — 16 de septiembre de 2026

Publicada y verificada en http://100.96.211.5:8000/. Se conservó el diseño de tarjetas y la clasificación direccional añadidos durante la pausa.

## Cambios entregados

- La puntuación técnica se presenta sobre 100, sin atribuirle una probabilidad de ganar.
- La probabilidad de TP antes del SL por perfil, volatilidad y horizonte aparece como **estimación no disponible**. La referencia histórica de toque a 6 horas queda en un apartado separado: explica el umbral de +3.2%, su posible diferencia respecto al TP del plan, la inclusión de SL previos y la dependencia entre observaciones.
- Las tarjetas distinguen los niveles fijados al emitir una alerta de las propuestas calculadas por el sistema. Los movimientos de precio posteriores no se presentan como ganancias realizadas.
- El historial compara los tiempos de primer toque de TP, SL y +3.2%. Los empates de vela son ambiguos; los datos ausentes o inválidos no se convierten en resultados favorables. Expone cobertura y versión cuando existen.
- El resumen histórico diferencia frecuencia de cierre por TP, cierres positivos, cierres de al menos +3.2% y resultado medio bruto. No atribuye esas frecuencias a la próxima señal.
- La calculadora usa porcentajes manuales y declara sus límites. Se eliminaron afirmaciones fijas sobre mejoras de rentabilidad sin muestra/versionado. Distingue bruto y neto, valida entradas y no ejecuta órdenes.
- Se corrigieron las fechas del historial de estados (`ts_ms`), el filtro de caída, el contraste de etiquetas oscuras y el ancho del detalle móvil. El botón de cierre permanece visible al desplazarse.

## Verificación

- 15 pruebas de dominio superadas: recuperación después de SL, TP anterior, empates, tiempos cero/ausentes/inválidos, seguimiento pendiente, TP inferior o superior a +3.2%, cobertura y niveles congelados.
- ESLint, TypeScript y compilación Vite: correctos.
- Navegador conectado a la API real: filtros, apertura/cierre con Escape, detalle, referencia histórica, historial y calculadora.
- Caso observado en el historial: BOMEUSDT alcanzó +3.2% después del stop y se presentó como **SL primero**, con excursiones provisionales separadas.
- Vista de escritorio y viewport móvil de 390 × 844: tabla con desplazamiento propio; sin desbordamiento global; panel móvil ajustado al ancho disponible. Se restauró el viewport del navegador.
- Producción: HTML y ambos assets devueltos por HTTP coinciden byte a byte con la compilación local; WebSocket conectado; detalle visible; sin errores de consola durante la comprobación.
- La API en ejecución expone `ms_tp`, `ms_sl`, `ms_meta`, `cobertura_velas`, `strategy_version` y `reward_neto_pct`.

## Publicación y reversión

Se actualizaron únicamente archivos bajo `frontend/`, incluyendo fuentes, pruebas y compilación. No se instalaron dependencias ni se modificó `package-lock.json`. Se verificaron los hashes de los fuentes remotos antes de reemplazarlos; los assets anteriores se conservaron y `dist/index.html` se sustituyó al final.

Respaldo remoto: `/home/flox/.cache/sacbinance-ui-backups/20260916T161655332166Z`.

El manifiesto `deployment.json` registra hashes anteriores y nuevos. `http-verification.json` registra la comprobación HTTP. Para volver a la vista anterior basta restaurar el `frontend/dist/index.html` del respaldo: sus assets originales permanecen disponibles. Para revertir fuentes también deben usarse las copias individuales del mismo respaldo; no ejecutar de nuevo `deploy_frontend.py` con el estado anterior.

El servicio `sacbinance` continuó activo con PID **866008**, iniciado el **2026-09-14 20:28:24 UTC**. No se reinició ni se publicaron cambios de backend o de esquema de base de datos.

## Límite de esta entrega

Se corrigió la interpretación de los datos en pantalla. Esta entrega no implementa ni valida estadísticamente el motor de probabilidades condicionado por régimen y horizonte. Los cruces son observaciones con la cobertura disponible, no ejecuciones de órdenes. Tampoco certifica que todas las propuestas del informe de recorridos estén implementadas: la UI muestra expresamente la estimación que aún no está disponible.
