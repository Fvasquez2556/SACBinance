# Despliegue de la fase 2 · 22-sep-2026, 02:57 UTC

Evaluador común de recorridos, en producción. **En sombra: mide en paralelo a los cuatro trackers existentes y no sustituye a ninguno.**

Autorizado por el usuario. Mismo procedimiento que la [fase 1](DESPLIEGUE_FASE1.md): comparar, copiar, ensayar, probar, reiniciar, verificar.

## Qué se instaló

| Archivo | Estado |
|---|---|
| `backend/src/evaluacion/recorrido.py` | nuevo — el núcleo puro |
| `backend/src/evaluacion/adaptadores.py` | nuevo — streaming y replay sobre la misma función |
| `backend/src/evaluacion/almacen.py` | nuevo — esquema v17, replay incremental y comparación en sombra |
| `backend/src/evaluacion/__init__.py` | nuevo |
| `backend/src/persistence/db.py` | esquema v17, `almacen_recorridos()` |
| `backend/src/state/engine.py` | `self._recorridos` junto al resto de colaboradores de la base |
| `backend/main.py` | pasada del evaluador en el bucle de mantenimiento |
| `backend/src/config/settings.py` | `evaluador_recorridos_enabled`, `evaluador_max_planes_por_pasada` (60) |
| `backend/tests/test_recorrido.py` | nuevo, 18 pruebas |

Los cuatro archivos modificados se compararon contra la copia del servidor antes de sustituirlos: la única diferencia era el trabajo de esta fase. Tras subirlos, los nueve archivos coinciden en `md5sum` a los dos lados.

## La validación previa, sobre datos reales

Antes de tocar nada se pasó el evaluador nuevo, **en solo lectura**, por los **190 planes notificados ya resueltos** de producción:

| | |
|---|---|
| Reproducen la etiqueta del sistema | **190 de 190 — 100 %** |
| Discrepancias que explicar | ninguna |
| Velas ambiguas (objetivo y stop en el mismo minuto) | 0 |
| Huecos de precio detectados | 1, ejecutado en la apertura |
| Planes con cobertura por debajo del 90 % | 0 |

Esa era la condición que el plan ponía para la fase 2. No quedó ninguna diferencia pendiente de explicar.

## Pasos y resultados

**1 · Copia de seguridad** en `/home/flox/.cache/sacbinance-evaluador-deploy/20260922T025548Z/`: 901 MB en 3,3 s con el servicio escribiendo, `integrity_check = ok`, esquema v16, recuento de las 16 tablas guardado (ya incluye `episodios` y `planes` de la fase 1), más los cuatro archivos a sustituir con su SHA-256.

**2 · Ensayo sobre la copia de 901 MB:** migración v16 → v17 en **14 ms**, integridad `ok`, **ninguna fila cambiada**, dos tablas nuevas. Y una pasada completa del evaluador sobre los 47 planes existentes: **30 ms**.

**3 · Pruebas en el servidor:** **97 pruebas, 0 fallos, 0 errores**.

**4 · Reinicio** por `kill -TERM` con `Restart=always`, como en la fase 1. El log confirma el cierre limpio (`DB cerrada limpiamente`) y el arranque:

```
[2026-09-22 02:57:48.533] Migracion v16->17: recorrido por plan y horizontes (en sombra; no sustituye a ningun tracker)
[2026-09-22 02:57:48.533] Esquema de la DB en version 17
```

## Primera comprobación en vivo (02:59 UTC, +1,2 min)

| | |
|---|---|
| Esquema | 17 |
| Recorridos evaluados | 47 |
| Filas de horizonte | 329 |
| Con desenlace | 3, todos `STOP`, resultado medio **−1,653 %** neto |
| Cobertura media / mínima | 0,942 / 0,80 |
| Velas ambiguas / huecos | 0 / 0 |
| Alertas nuevas con identidad | 2 de 2 |
| Episodios cerrados | 1, por `DESENLACE:SL` |
| Planes en ordinal 2 | 2 — la ventana de 12 h ya está agrupando repeticiones |
| `GET /api/status` | 200, 248 pares |
| Errores en el log atribuibles al cambio | ninguno |

El único `[ERROR` del log es de las 02:49, anterior al despliegue: un fallo de resolución DNS en la reconexión del WebSocket, del que el gestor se recuperó solo.

**La cobertura mínima de 0,80 es información, no un fallo:** son planes abiertos justo antes del reinicio, que perdieron unos minutos de velas mientras el proceso rearrancaba e hidrataba. Es exactamente lo que el campo existe para decir — antes esa pérdida no se veía en ningún sitio.

## Cómo revertir

1. `evaluador_recorridos_enabled=false` en `.env` y reiniciar: el evaluador deja de correr y las tablas se quedan quietas.
2. Restaurar los cuatro archivos desde `/home/flox/.cache/sacbinance-evaluador-deploy/20260922T025548Z/backend/` y borrar `src/evaluacion/`. Con el código v16 y la base en v17 no hay migración hacia atrás: las tablas nuevas quedan huérfanas sin molestar.
3. Restaurar la base desde la copia de 901 MB, solo ante un problema de integridad. Perdería lo ingerido desde las 02:55 UTC.

## Lo que queda por comprobar

- **24 h de emisión sin cambios**, ahora con dos reinicios de por medio (02:22 y 02:57): cada uno produce una pasada completa del universo con una alerta por par, así que la comparación de ritmo hay que hacerla sobre una ventana posterior, no sobre la primera hora.
- **El reparto de cierres de episodio** cuando pasen las primeras 12 h: si `ANCLA` dispara mucho más que `SILENCIO`, la tolerancia del 2,5 % necesita revisión.
- **La comparación en sombra en vivo**, en cuanto haya planes notificados resueltos después del despliegue: `AlmacenRecorridos.comparar_con_notificaciones()` la calcula sola.

---

## Corrección del 22-sep, 03:40 UTC: el evaluador dejaba planes sin turno

Con 192 planes vivos, `plan_recorrido` se quedó clavado en 60. `evaluar_pendientes()` pedía los pendientes **ordenados por fecha del plan** con un límite de 60 por pasada; como todos tenían la ventana abierta, devolvía siempre los mismos 60 más viejos y **los 132 restantes no se habrían evaluado hasta que aquellos vencieran, hasta 12 h después**.

El límite no era el problema —está para no competir con el ciclo de velas—, lo era el orden. Ahora se ordena por **antigüedad de la última evaluación**, con los que nunca se evaluaron primero (`COALESCE(r.ts_evaluado, 0)`), así que cada plan entra por turno.

Con su prueba: tres planes, límite de dos por pasada, dos pasadas, los tres evaluados. **114 pruebas en verde.**

Comprobado en producción tras el reinicio: **195 planes y 195 recorridos**, 11 con desenlace, 0 errores. El atasco desapareció en una sola ronda.
