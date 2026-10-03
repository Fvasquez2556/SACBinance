# moderadas_sombra

Observador en sombra de las señales **MODERADA**, con **FUERTE** como comparación (`moderadas-sombra-v1`). Mide qué hace el precio desde R después de cada señal, cuántas llegan a +2,67 % y qué habría dado comprar en R o en R − 0,3 / 0,5 / 0,7 / 1 %. No cambia señales, TP, SL, Telegram ni el tablero.

- **Reglas congeladas** en `core.py`, definidas en `audit/2026-10-02/moderadas/REGLAS.md`. Cualquier cambio exige una versión y una base nuevas.
- **Referencia histórica** en `referencia.json`: del 11-sep al 2-oct, generada con el mismo `core.py` en el servidor. Resumen para leer en `audit/2026-10-02/moderadas/RESUMEN.md`. La variante que se sigue está en `PRINCIPAL.json`.
- **Qué registra:** cada señal MODERADA o FUERTE posterior a la instalación, unos 90 s después de emitirse, con sus rasgos de la hora previa. La vuelve a medir al cerrar cada ventana (1, 3, 6 y 12 h) y mide una vez el control (un minuto al azar de la misma moneda).
- **Seguridad:** la base de producción se abre en `mode=ro` con `query_only` y un autorizador que solo permite SELECT. Solo escribe en `datos/moderadas_sombra.db`.
- **Programación:** `deploy/ejecutar_moderadas_sombra.sh` se ejecuta cada minuto desde el crontab del usuario, con `flock`, `nice 15` y un límite de 55 s. Lo instala `deploy/instalar_moderadas_sombra.py`.
- **Informe:** `python3 -m moderadas_sombra informe`. Pone histórico → nuevo, día a día en hora de Guatemala. Solo cuentan las señales registradas al emitirse.
