# Despliegue de la fase 3 · 22-sep-2026, 03:27 UTC

Diario de operaciones en producción. **Nace vacío y solo lo llena el usuario.**

Autorizado por el usuario. Mismo procedimiento que las fases 1 y 2.

## Qué se instaló

| Archivo | Estado |
|---|---|
| `backend/src/operaciones/diario.py` | nuevo — el diario y sus reglas |
| `backend/src/operaciones/__init__.py` | nuevo |
| `backend/src/persistence/db.py` | esquema v18, `diario_operaciones()` |
| `backend/src/api/routes.py` | `GET/POST /api/operaciones…` (listado, resumen, alta, cierre, parcial, cancelación y nota) |
| `backend/src/state/active_alert.py` | la alerta viva lleva `plan_id` y `episode_id` |
| `backend/src/state/engine.py` | los pone al registrar la identidad |
| `frontend` | «Tomé esta entrada» en el detalle del par y la sección «Mis operaciones» |
| `backend/tests/test_operaciones.py` | nuevo, 12 pruebas |
| `frontend/tests/operaciones.test.ts` | nuevo, 5 pruebas |

Los cuatro archivos de backend modificados se compararon contra la copia del servidor antes de sustituirlos: solo cambiaba lo de esta fase. Tras subirlos, los seis coinciden en `md5sum`.

## Pasos y resultados

**1 · Copia de seguridad** en `/home/flox/.cache/sacbinance-diario-deploy/20260922T032505Z/`: base de 904 MB en 9,9 s con el servicio escribiendo, `integrity_check = ok`, esquema v17, recuento de las 18 tablas, los cuatro archivos con su SHA-256 y el `dist` anterior completo.

**2 · Ensayo sobre la copia de 904 MB:** migración v17 → v18 en **24 ms**, integridad `ok`, **ninguna fila cambiada**, dos tablas nuevas. Y una operación completa sobre un plan real de la copia (plan 75, SUPERUSDT): apertura, no realizado +0,50 %, cierre en el objetivo con **+7,65 % neto**, objetivo copiado del plan y eventos `APERTURA` → `CIERRE`.

**3 · Pruebas en el servidor:** **113, 0 fallos, 0 errores**.

**4 · Reinicio** por `kill -TERM`. La API tardó ~80 s en responder (hidratación más backfill de calentamiento):

```
[2026-09-22 03:27:28.001] Migracion v17->18: diario de operaciones del usuario (vacio; solo se llena con lo que el declare)
[2026-09-22 03:27:28.001] Esquema de la DB en version 18
```

## Comprobación en vivo, sin ensuciar el diario

No se creó ninguna operación de prueba en producción: el diario existe justo para responder qué tomó el usuario, y una fila inventada lo estropearía. Se comprobó el circuito por sus rechazos:

| Comprobación | Resultado |
|---|---|
| `GET /api/operaciones` | `{"operaciones": [], "resumen": {…, "abiertas": 0}}` |
| `POST` con precio 0 | **422** — no llega ni al diario |
| `POST` con `plan_id` inexistente | **400** `"el plan 999999 no existe"` — el mensaje es del diario |
| `GET /api/operaciones/999` | **404** |
| El diario después de todo eso | sigue vacío |
| Errores en el log | ninguno |

En la interfaz real: el panel «Mis operaciones» dice *«Todavía no has registrado ninguna. Se registran desde el detalle de un par, con “Tomé esta entrada”»*, y el detalle de un par muestra la sección «Mi operación» con su explicación y el botón.

## Cómo revertir

1. Restaurar los cuatro archivos desde la copia y borrar `src/operaciones/`. Con el código v17 y la base en v18 no hay migración hacia atrás: las tablas quedan huérfanas sin molestar, y lo que el usuario hubiera registrado sigue ahí.
2. La base solo se restaura ante un problema de integridad; perdería lo ingerido desde las 03:25 UTC.

No hay interruptor de apagado como en las fases 1 y 2, y es deliberado: el diario no hace nada por su cuenta. Sin una acción explícita del usuario, no escribe una sola fila.

## Lo que queda por comprobar

- **Que el usuario registre su primera operación de verdad** y el no realizado se mueva con el precio.
- El caso de la alerta rehidratada tras un reinicio, que llega sin `plan_id`: la operación se registra igual y los niveles viajan desde el plan mostrado, pero conviene verlo en vivo una vez.
