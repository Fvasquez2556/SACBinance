# Fase 5 — Segunda revisión, 22 de septiembre de 2026

Las seis observaciones de la primera revisión tienen corrección y pasan las reproducciones específicas. La fase 5 ya está desplegada. Sin embargo, la revisión del nuevo informe y de la cartera, junto con el reintento de planes sin datos, encuentra **cuatro problemas nuevos que impiden dar la fase por cerrada**.

Esta revisión no modifica la aplicación, la configuración, las operaciones ni el servicio. Las reproducciones usan exclusivamente bases SQLite en memoria. Los ejemplos son pruebas sintéticas, no resultados obtenidos en el mercado.

## Evidencia y despliegue

- Suite local: **275 pruebas correctas**. Registro: [salida de la suite](../revision-codex/pruebas-segunda-revision.txt).
- Reproducciones independientes: seis comprobaciones de las correcciones previas correctas; seis comprobaciones nuevas fallidas, agrupadas en los cuatro hallazgos siguientes. [Resultados y hashes](reproducciones.json), [programa reproducible](reproducir.py).
- Servidor `sac`, `/home/flox/sacbinance`, comprobado a las **21:21:20 UTC / 15:21:20 Guatemala**: servicio activo, API HTTP 200, esquema **v20**. Las dos tablas de experimentos existen.
- **11 archivos coinciden** entre local y servidor, incluidos `almacen.py`, `registro.py`, `informe.py`, `cartera.py`, sus pruebas y la integración. Los dos módulos nuevos estaban presentes antes del arranque del servicio. [Inventario remoto](estado-20260922T212120Z.json).
- Registro activo: `fase5-v3`, método `metodo-v2`, huella **`cef2ec54020c46ca`**, congelada el **22-sep a las 21:01:01 UTC**.
- En la fotografía remota hay **40 planes posteriores a la congelación y cero resultados**. Es esperable: el primer plan vence el **23-sep a las 09:03 UTC / 03:03 de Guatemala**. No hay evidencia de resultados reales de fase 5 afectados por los defectos descritos; sí está desplegado el código que los reproduce.

## Correcciones anteriores verificadas

1. **R1, stop en la vela de entrada:** B2 devuelve STOP **−3,5 %**, en lugar de la ganancia incorrecta de +7,1142 %.
2. **R2, entrada fuera de ventana:** queda `NO_LLENADO`, sin `ms_fill`.
3. **R3, ausencia y recuperación de datos:** queda `SIN_DATOS` con retorno desconocido; al recuperar cobertura, se reevalúa y obtiene el objetivo real del caso sintético. El problema nuevo de turnos de reintento se describe abajo.
4. **R4, órdenes no ejecutadas:** el resumen incluye elegibles, resueltas, no llenadas y sin datos; mantiene el denominador sin añadir ceros ficticios a la rentabilidad.
5. **R5, política B1/B2:** documento, descripción y código ya declaran conservar el **precio absoluto** del objetivo. El ejemplo de entrada 98,5 conserva TP 106.
6. **R6, identificación:** la declaración incorpora método, evaluador, cobertura, población decisoria y hash del documento. El SHA-256 fijado coincide con el archivo local; cambiar la versión del método modifica la huella. Es un hash fijado y comprobado mediante prueba, no lectura automática del documento en cada llamada.

También existen ahora el informe por subconjuntos, la comparación pareada, el remuestreo por par y el simulador de cartera. El escenario configurado es 10 USDT, una posición y reinversión del capital. Esta revisión comprueba ese escenario presente en los archivos, no establece preferencias nuevas del usuario.

## F5-N1 · P1 · Tres planes sin datos pueden bloquear todos los planes posteriores

**Ubicación:** `backend/src/experimentos/almacen.py:353–365`.

La corrección permite volver a seleccionar planes `SIN_DATOS`, pero siempre ordena por su fecha original y toma los primeros `max_por_pasada`. Con el límite configurado de **3**, tres planes antiguos sin cobertura pueden ocupar cada pasada indefinidamente. No hay rotación, espera entre reintentos ni una selección separada para los planes nuevos.

**Reproducción:** cuatro planes maduros; los tres primeros sin velas y el cuarto con cobertura completa y un objetivo alcanzado. Tras **cinco pasadas**, solo existen resultados de los planes 1, 2 y 3; el cuarto nunca recibe turno. Cada pasada vuelve a medir las mismas 33 combinaciones. El defecto no necesita un error de base de datos: basta con tres recorridos que no alcancen la cobertura exigida.

**Corrección requerida:** conservar la posibilidad de recuperación, pero garantizar avance de la cola. Por ejemplo, separar nuevos y reintentos, programar el próximo reintento o rotar según última evaluación. Añadir una prueba donde varios `SIN_DATOS` permanentes no impidan evaluar un plan posterior medible.

## F5-N2 · P1 · La cartera calcula mal cuándo se libera el capital

**Ubicación:** `backend/src/experimentos/cartera.py:143–157`, en relación con `almacen.py:238–251`.

En entradas diferidas, `ms_desenlace` se mide desde el inicio del recorrido que comienza en la vela del fill. La cartera suma ese valor a `ts_creado`, omitiendo el retraso de entrada. Además usa `ms_desenlace or horizonte_ms`, por lo que **cero minutos se interpreta como ausencia de dato**.

**Reproducción principal, con evaluador y cartera reales:**

- A se crea en minuto 0, entra en minuto **10** y alcanza el objetivo en minuto **12**.
- La cartera registra que abre en 10 y **cierra en 2**, antes de abrir.
- B entra en minuto 11 mientras A aún estaría abierta. La cartera acepta ambas pese al límite de una posición, y devuelve **11,4735 USDT** en vez de limitarse a la primera operación, cuyo saldo sería aproximadamente **10,7114**.

**Segundo caso:** un objetivo de REF alcanzado en la primera vela tiene `ms_desenlace=0`; la cartera mantiene ocupada la posición durante toda la ventana de una hora del ejemplo. En producción el horizonte habitual es 12 horas, por lo que el mismo fallback puede descartar oportunidades durante ese plazo.

**Corrección requerida:** definir un reloj inequívoco para entrada y salida, preferiblemente timestamps absolutos, preservar el cero como valor válido y decidir la disponibilidad al cierre de la vela observada según el protocolo. Verificar `cierre >= entrada` y ausencia de solapamientos. La selección de entradas diferidas también debe especificar el tratamiento de órdenes pendientes y reservas de saldo; ordenar avisos por creación no sustituye un procesamiento cronológico de eventos.

## F5-N3 · P1 · La cartera aplica rentabilidades de una posición distinta a la que puede financiar

**Ubicación:** `backend/src/experimentos/cartera.py:105–115,148–156`; `almacen.py:297–300`.

`resultado_pct` ya está multiplicado por `tamano_relativo` para comparar stops a igual riesgo teórico. La cartera lo utiliza directamente como rendimiento de **todo el saldo**, aunque declara invertir únicamente el capital disponible. No consulta ni representa ese tamaño relativo.

**Reproducción:** referencia con stop de 3 % y rival C1 con stop de 2 %. C1 tiene tamaño relativo **1,5**. Un TP de 6 % bruto, menos 0,5 puntos de coste, deja **5,5 % neto** sobre lo efectivamente invertido. Con 10 USDT y una posición spot financiada con esos mismos 10, el saldo sería **10,55**. El simulador devuelve **10,825**: ha aplicado 8,25 % al saldo, equivalente a obtener el resultado de una posición de 15 USDT, aunque registra solo 10 invertidos.

Hay una segunda inconsistencia en la misma actualización del saldo: si se configura `fraccion_por_posicion=0.5`, registra 5 invertidos y 5 sin invertir, pero aplica la ganancia al saldo entero. En REF, +5,5 % produce **10,55** en vez de **10,275**.

**Corrección requerida:** separar retorno por unidad invertida, tamaño normalizado del experimento y resultado monetario de la cartera. Actualizar el saldo con el P&L del importe realmente financiado, manteniendo el efectivo restante. Si se conserva igual riesgo entre políticas, dimensionar posiciones con un presupuesto que respete el capital y las restricciones spot; no convertir el factor de normalización en financiación implícita.

## F5-N4 · P2 · `APROBADA` no considera si la política empeora frente a REF

**Ubicación:** `backend/src/experimentos/informe.py:164,183–190,242–259`.

El informe calcula `pareado_vs_ref`, pero no usa esa comparación en el veredicto ni en la lista `aprobadas`. Solo exige rentabilidad absoluta y ventaja sobre la base geométrica. Por tanto, la aprobación actual no demuestra la mejora económica exigida por `PLAN.md` §8.

**Reproducción:** 50 planes medibles, de 50 pares distintos, todos enviados por Telegram y primeros de su episodio. En cada uno, REF gana **+5,5 %** y A1 **+2,7 %**. La diferencia pareada de A1 es **−2,8 puntos**, con todo su intervalo en −2,8. A pesar de ello el informe devuelve **`APROBADA`** para A1.

No es un fallo del cálculo de la diferencia: la diferencia se informa correctamente y después no interviene en la decisión. Tampoco demuestra que A1 nunca sea útil; una salida más temprana podría merecer otro análisis de cartera. Lo que no puede inferirse de ese sello es que mejora la referencia.

**Corrección requerida:** distinguir «supera las puertas absolutas» de «mejora demostrada frente a REF», y aplicar una regla de comparación preregistrada para el veredicto que se use para promover políticas. Cuando la mejora no esté demostrada, indicarlo expresamente, aunque el rival sea rentable. No seleccionar nuevos umbrales después de ver los resultados.

## Cierre de esta revisión

Las correcciones anteriores están verificadas, pero los nuevos hallazgos afectan precisamente a lo que se quiere medir: qué operaciones son posibles, cuánto capital queda y qué política merece considerarse superior. **No recomiendo cerrar la fase 5 ni usar su ranking para cambiar el objetivo de Telegram todavía.**

El trabajo inmediato es corregir F5-N1 a N4 y repetir estos casos junto a las 275 pruebas existentes. Como el método de selección, los relojes y la contabilización de cartera afectan a la comparación, documentar y versionar cualquier cambio antes de sacar conclusiones prospectivas; conservar identificadas las versiones previas. No se ha desplegado ni corregido código durante esta revisión.

Para reproducir desde la raíz: `backend/venv/Scripts/python.exe -B audit/2026-09-22/plan-evolucion-motores/fase5/revision-codex-2/reproducir.py`. Los `FAIL` del programa son incumplimientos de las invariantes esperadas, no fallos de arranque. La evidencia JSON preserva los hashes de las fuentes usadas.
