# Despliegue de la fase 1 · 22-sep-2026, 02:22 UTC

Identidad por episodio y por plan, en producción. **En sombra: no cambia ninguna decisión de emisión, ningún nivel y ninguna política de Telegram.**

Autorizado por el usuario el 21-sep-2026 («sí, despliégalo»).

## Qué se instaló

| Archivo | Estado |
|---|---|
| `backend/src/episodios/__init__.py` | nuevo |
| `backend/src/episodios/registro.py` | nuevo |
| `backend/main.py` | +9 líneas: barrido de episodios en el bucle de mantenimiento |
| `backend/src/persistence/db.py` | esquema v16, `registro_episodios()`, `anotar_identidad_alerta()` |
| `backend/src/state/engine.py` | `_registrar_identidad()`, llamado después de emitir y registrar la alerta |
| `backend/src/config/settings.py` | `episodio_registro_enabled`, `episodio_silencio_horas` (12), `episodio_ancla_tolerancia_pct` (2,5) |
| `backend/tests/test_episodios.py` | nuevo, 17 pruebas |

Los cuatro archivos modificados se compararon contra la copia del servidor **antes** de sustituirlos: la única diferencia era el trabajo de esta fase. No viajó ningún cambio local ajeno. Tras subirlos, los siete archivos coinciden en `md5sum` a los dos lados.

## Pasos, en orden, con lo que devolvió cada uno

**1 · Comprobaciones previas.** Servicio activo desde el 18-sep 04:43 UTC (PID 2012823), 813 GB libres, Python 3.12.13, SQLite 3.46.1 en el servidor.

**2 · Copia de seguridad,** en `/home/flox/.cache/sacbinance-episodios-deploy/20260922T021752Z/`:

- Base completa por la API de backup de SQLite, con el servicio escribiendo: **898 MB en 4,5 s**, `integrity_check = ok`, esquema v15, con el recuento de las 14 tablas guardado (6.056.035 velas, 8.929 alertas, 8.410 outcomes, 6.262 señales).
- Los cuatro archivos que se iban a sustituir, con su SHA-256.

**3 · Ensayo de la migración sobre la copia de 898 MB** — el criterio que quedaba pendiente de la fase 1:

| | |
|---|---|
| Duración del salto v15 → v16 | **28 ms** |
| Integridad después | `ok` |
| `foreign_key_check` | sin filas |
| Filas que cambiaron | **ninguna** |
| Tablas nuevas | `episodios`, `planes` |
| Columnas nuevas en `alertas_emitidas` | `episode_id`, `plan_id` (NULL en las 8.929 filas antiguas) |

Además se dio de alta un plan de prueba **sobre una alerta real** de la copia: episodio 1, plan 1, ordinal 1. La copia queda como respaldo; no se reutiliza.

**4 · Pruebas en el servidor, con el código ya subido:** **79 pruebas, 0 fallos, 0 errores** (`venv/bin/python`, 0,9 s). Es la primera vez que la suite corre en el servidor.

**5 · Reinicio.** El usuario `flox` no tiene `sudo` sin contraseña, así que el reinicio se hizo por la vía que la propia unidad contempla: `kill -TERM` al PID, con `Restart=always` y `RestartSec=10`. SIGTERM entra por el `shutdown` de FastAPI, que vuelca la DB antes de cerrar — el log lo confirma: `DB cerrada limpiamente (0 velas volcadas)`. Proceso nuevo a los ~12 s (PID 3343146, `NRestarts=1`).

**6 · Arranque y migración en vivo:**

```
[2026-09-22 02:22:41.138] Migracion v15->16: episodios y planes con identidad propia (en sombra; no cambia ninguna emision)
[2026-09-22 02:22:41.138] Esquema de la DB en version 16
[2026-09-22 02:23:38.893] Hidratacion completa: 250 pares en 56s | 15427 velas REST + 363388 velas del cache | errores=0
```

`GET /api/status` → 200, 250 pares. Sin errores en el log.

## Primera comprobación en vivo (02:24 UTC, +2 min)

| | |
|---|---|
| Esquema | 16 |
| Alertas emitidas desde el reinicio | 2 |
| **Con `plan_id` y `episode_id`** | **2 (100 %)** |
| De ellas, sin `signal_id` | 2 — el caso que antes quedaba sin nada que lo evaluara |
| Episodios abiertos | 2, ambos ordinal 1, `r_multiplo` 2,0 |
| Errores de identidad en el log | ninguno |

## Cómo revertir

Por orden de menor a mayor intervención:

1. **Apagar el registro sin tocar código:** `episodio_registro_enabled=false` en `.env` y reiniciar. Las tablas se quedan donde están y la emisión no las mira.
2. **Volver al código anterior:** restaurar los cuatro archivos desde `/home/flox/.cache/sacbinance-episodios-deploy/20260922T021752Z/backend/` y borrar `src/episodios/`. Ojo: con el código v15 y una base ya en v16, `_migrate()` no reintenta nada — la versión guardada es mayor que `SCHEMA_VERSION`, así que no hay migración hacia atrás y las tablas nuevas quedan huérfanas, sin molestar.
3. **Restaurar la base** desde la copia de 898 MB solo si apareciera un problema de integridad. Perdería lo ingerido desde las 02:17 UTC, así que es el último recurso, no el primero.

## Lo que queda por comprobar

- **24 h de emisión sin cambios:** mismo ritmo de alertas y de avisos que antes del despliegue (referencia previa: 2.098 alertas y 62 avisos en 24 h; 65 alertas en la última hora).
- **El reparto de cierres de episodio.** Si `ANCLA` dispara mucho más que `SILENCIO`, la tolerancia del 2,5 % necesita revisión antes de construir nada encima.
- **Cuántos planes caen en ordinal ≥ 2**, que es lo que dirá si la ventana de 12 h agrupa como se midió.
