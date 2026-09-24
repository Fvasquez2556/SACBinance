# Continuidad para Cloud/Claude y próximos colaboradores

**Punto de parada (22-sep-2026): las fases 1, 2 y 3 están desplegadas en producción; la 4 está escrita, probada y pendiente de desplegar.** Esquema v18. Incluye la corrección del turno del evaluador (ver el final de [DESPLIEGUE_FASE2.md](DESPLIEGUE_FASE2.md)): 195 planes con 195 recorridos al día. El registro de identidad escribe con cada alerta y el evaluador común mide los recorridos en paralelo a los trackers existentes, sin sustituir a ninguno. Detalle en [DESPLIEGUE_FASE1.md](DESPLIEGUE_FASE1.md) y [DESPLIEGUE_FASE2.md](DESPLIEGUE_FASE2.md).

**Nota de la fase 1, que sigue vigente:** Esquema v16 migrado en vivo a las 02:22:41 UTC; el registro de identidad escribe con cada alerta nueva y no toca ninguna decisión de emisión. El detalle del despliegue, con la copia de seguridad y la reversión, está en [DESPLIEGUE_FASE1.md](DESPLIEGUE_FASE1.md). El análisis y la planificación siguen vigentes; lo que cambió es que la identidad por episodio y por plan ya es código, con pruebas, en el árbol de trabajo local.

Este archivo permite retomar sin la conversación. No es una instrucción de despliegue ni una afirmación de que las funciones propuestas ya existen.

## 1. Encargo y alcance confirmado

El usuario pidió revisar el sistema actual, evaluar objetivos netos —especialmente +4,2 %—, evolucionar los motores alcista/bajista y resolver el caso de tomar la primera señal mientras aparecen otras con distintos TP/SL. Quiere unificar este plan con trabajo que realiza con Cloud/Claude y conservar continuidad ante un cambio de sesión o límite de tokens.

Confirmación explícita: **el motor bajista será para caídas y rebotes en spot, no cortos**. Primero se planifica y se comparte la base; la implementación corresponde a una fase posterior.

## 2. Leer antes de actuar

1. [LEER_PRIMERO.md](LEER_PRIMERO.md).
2. [PLAN.md](PLAN.md).
3. [CONTRATOS_Y_METRICAS.md](CONTRATOS_Y_METRICAS.md).
4. [EVIDENCIA_Y_DECISIONES.md](EVIDENCIA_Y_DECISIONES.md).
5. Plan previo `audit/2026-09-14/HANDOFF_MODELO_CONTINUACION_Y_CAIDA.md`, junto con `COMPARACION_MODELOS.md`. El primero no debe reutilizarse aislado: la comparación posterior matiza su propuesta de modelo.

La propuesta de Cloud/Claude no estaba disponible en un archivo identificado de este paquete. No se ha afirmado haberla integrado. Unificar sus decisiones con las de aquí, conservando discrepancias explícitas antes de programar los contratos compartidos.

## 3. Qué se hizo y qué queda pendiente

Completado:

- Revisión del circuito datos → indicadores/estados → ruptura → planes → emisión/Telegram → trackers → API/estadísticas/UI, con atención al tiempo, las identidades y los consumidores.
- Snapshot consistente de producción en solo lectura, sin reinicio, despliegue ni envío de mensajes.
- Comparación de salidas netas sobre ventanas maduras, con la cohorte reciente separada por configuración.
- Recálculo independiente de las cuentas principales sobre las velas guardadas.
- Comprobación del enlace entre avisos, planes notificados y outcomes.
- Comparación de 18 archivos locales/remotos del circuito revisado y pruebas base locales.
- Plan por fases, contratos y métricas.

Pendiente de implementación:

- Episodios persistentes, identidad universal por plan, evaluador común y diario de operaciones.
- Nuevos motores especializados, API/UI y validación prospectiva.
- Simulación completa de cartera e importación opcional de operaciones reales.

No se modificaron reglas del motor, TP/SL, filtros ni presupuesto de Telegram. No se entrenó un modelo. No se alteró el plan previo ni los cambios de otros colaboradores. No se hizo commit, push o despliegue, ni se envió esta documentación a Cloud/Claude automáticamente.

## 4. Base técnica comprobada

- Raíz local: `D:/SACBinance`.
- HEAD local observado: `193e113`; hash completo en `datos/manifest.json`.
- HEAD remoto observado: `f82bcffe734c6219fdf4eb5263e07ed96ad78419`.
- Ambos árboles contienen trabajo fuera de esos commits. **No preparar una implementación desde HEAD descartando el árbol de trabajo.**
- Esquema real: 15 en `schema_meta`. `PRAGMA user_version=0` no es el esquema de la aplicación.
- Servicio remoto activo desde 18-sep-2026 04:43:34 UTC, PID observado 2012823. Son datos de la captura, no una garantía del estado actual.
- Snapshot: 22-sep-2026 01:02:26.456 UTC / 21-sep 19:02:26.456 Guatemala.
- Catorce de los 18 archivos revisados coinciden byte a byte; cuatro solo difieren por CRLF/LF. No se detectó diferencia de contenido en ese conjunto.

Los cuatro archivos son `tf_rupture_tracker.py`, `trade_levels.py`, `outcome_tracker.py` y `api/routes.py`. Las copias remotas están en `datos/remoto/`; no reemplazarlos por una diferencia de saltos de línea.

El manifiesto conserva hashes y estado de Git. Compararlos otra vez antes de implementar porque el usuario trabaja en paralelo. Esta comparación es de archivos, no una certificación de los módulos que tiene cargados el proceso.

## 5. Resultados que no deben perderse

- 258 avisos enviados al corte; 223 evaluables en 12 h con cobertura suficiente; 176 maduros de la configuración `a870caf2dc2d`.
- Sobre esos 176: TP variable +0,895 % medio neto; +3,2 % netos fijo +0,699 %; +4,2 % netos fijo +0,942 %.
- +4,2 % netos se alcanza antes del SL en 73/176 casos (41,5 %), mediana de 5,66 h entre los aciertos. Coste supuesto 0,5 puntos: barrera bruta +4,7 %.
- La mejora frente al TP variable es solo +0,047 puntos, con intervalo exploratorio por día que incluye cero. Cuatro días de una configuración no acreditan una política universal.
- `objetivo_operador_pct` es un mínimo de rentabilidad ofrecida para filtrar; cambiarlo no equivale a cobrar a ese objetivo.
- 137/258 avisos no tienen `signal_id`; 127/207 en la configuración reciente. Los denominadores 258/207 incluyen ventanas abiertas y no son 223/176.
- Los 207 avisos de la configuración reciente sí tienen plan notificado. La ausencia de enlace a `signals/outcomes` no significa ausencia de niveles ni de medición reconstruible.
- `signals/stats`, Telegram, observación post-SL y operaciones del usuario son poblaciones diferentes.
- Ya existen detección alcista/bajista y seguimiento por marcos; evolucionarlos, no duplicarlos desde cero.

## 6. Fase 1: lo que ya existe, y el próximo paso real

**Hecho el 21-sep-2026, en local, sin desplegar y sin tocar la emisión.**

| Archivo | Qué es |
|---|---|
| `backend/src/episodios/registro.py` | La regla `episodio-v1` y el alta de planes inmutables. Estado en tabla, no en memoria |
| `backend/src/episodios/__init__.py` | Fachada del paquete |
| `backend/src/persistence/db.py` | Esquema v16 aditivo, `registro_episodios()`, `anotar_identidad_alerta()`, columnas `episode_id`/`plan_id` en `alertas_emitidas` |
| `backend/src/state/engine.py` | `_registrar_identidad()`, llamado **después** de emitir y registrar la alerta |
| `backend/main.py` | Barrido en el bucle de mantenimiento: `sincronizar_desenlaces()` + `barrer()` |
| `backend/src/config/settings.py` | `episodio_registro_enabled`, `episodio_silencio_horas` (12), `episodio_ancla_tolerancia_pct` (2,5) |
| `backend/tests/test_episodios.py` | 17 pruebas: ventana, ancla, idempotencia al reiniciar, plan sin `signal_id`, stop que no se reescribe, reloj, desenlaces y sombra en el motor |
| `audit/2026-09-22/plan-evolucion-motores/ensayo_migracion_v16.py` | Ensayo de la migración sobre una base con la forma de producción |

Resultado de pruebas tras el cambio: **79 de backend en verde** (62 antes + 17 nuevas).

Qué NO se hizo, a propósito: no se desplegó, no se ejecutó la migración v16 contra una copia de producción, no se cambió ninguna decisión de emisión, ningún nivel ni la política de Telegram, y no se tocó `signals`, `outcomes` ni los trackers.

**Próximo paso concreto, por orden:**

1. ~~Ensayar la migración~~ — hecho con `ensayo_migracion_v16.py` sobre una base de 179 MB con la forma de producción: **10 ms**, integridad `ok`, ninguna fila cambiada. Queda por repetirlo sobre una copia de la base real (888 MB); el salto es puro DDL, así que el tamaño no debería cambiar el resultado, pero eso es una expectativa, no una medición.
2. ~~Desplegar~~ — hecho el 22-sep 02:22 UTC. **Queda la comprobación de 24 h**: mismo ritmo de alertas y avisos que antes (referencia: 2.098 alertas y 62 avisos en 24 h) y `episode_id`/`plan_id` en el 100 % de las alertas nuevas con niveles. A los 2 minutos: 2 de 2, ambas sin `signal_id`.
3. Medir la regla en vivo: cuántos episodios se cierran por cada motivo y cuántos planes caen en ordinal ≥ 2. Si `ANCLA` dispara mucho más que `SILENCIO`, la tolerancia del 2,5 % necesita revisión — y se revisa antes de construir nada encima.
4. ~~Empezar la fase 2~~ — **hecha y desplegada el 22-sep 02:57 UTC**: `backend/src/evaluacion/` con el núcleo puro, el almacén (esquema v17) y los dos adaptadores; 18 pruebas nuevas, 97 en total. Validada en solo lectura contra producción: **190 de 190 planes notificados resueltos con la misma etiqueta que el sistema**, sin discrepancias. Falta desplegarla, con el mismo procedimiento de copia + ensayo + reinicio de la fase 1.
5. ~~Fase 3~~ — **hecha y desplegada el 22-sep 03:27 UTC**: `backend/src/operaciones/`, esquema v18, endpoints del diario y el «Tomé esta entrada» del tablero. 113 pruebas de backend y 34 de frontend en verde. El diario nace vacío y solo lo llena el usuario.
6. **Mejora del informe por marcos** (22-sep 04:27 UTC, fuera del plan de fases): las lecturas por marco ya llevan su tasa medida, los dos avisos que los datos contradecían están reescritos con sus números, y cada marco dice si su TP cabe en el horizonte intradía. Ver [MEJORA_INFORME_MARCOS.md](MEJORA_INFORME_MARCOS.md).
7. ~~Cerrar el agujero de `vol_ratio`~~ — hecho el 22-sep 06:00 UTC junto con los niveles visibles: 64 de 64 rupturas nuevas con volumen, antes el 26 %. Ver [NIVELES_Y_DESVIO.md](NIVELES_Y_DESVIO.md).
8. ~~Reevaluar las rupturas por marco con barreras homogéneas en R~~ — hecho el 22-sep sobre 43.500 rupturas maduras con control pareado. Ver [fase4/MEDICION_RUPTURAS_EN_R.md](fase4/MEDICION_RUPTURAS_EN_R.md). **Resultado que condiciona todo lo que se construya encima:** a 5m el detector es peor que entrar al azar (−4,32 pp), a 1h lo bate y aguanta el corte temporal (+8,46 pp), una ruptura bajista no anticipa que la caída siga, y ninguna columna ordena (AUC 0,47–0,53).
9. **Fase 4 — desplegada en producción, en sombra** (22-sep 06:41 UTC). `backend/src/motores/`, esquema v19 aditivo, **182 pruebas en verde** en local y en el servidor, migración aplicada en el arranque y verificada contra la copia previa: integridad `ok`, ninguna fila perdida. Ver [fase4/FASE4.md](fase4/FASE4.md).

   **Dos fallos que la suite no vio y sí vio el replay sobre caídas reales** (ocho pares que cayeron entre −18 % y −45 %):
   - `retroceso.caida_pct` llega **con signo**, y el motor comparaba `>= 2.0` contra un valor negativo: no podía abrir jamás. Las pruebas pasaban porque sus datos de ejemplo tenían el mismo error de signo que el código.
   - Una vez en `REBOTE_CONFIRMADO` emitía `CANDIDATO` **cada minuto**: 161–340 minutos por par. Ahora el disparador es un instante; después el estado sigue pero el veredicto es `ESPERAR`. Bajó a 0–3 por caída.

   **Lección para las fases siguientes: probar los motores contra datos reales de producción, no solo contra datos de ejemplo.** `fase4/replay_caida_remote.py` hace exactamente eso y es reutilizable.

   **Revisión externa** (`fase4/revision-codex/REVISION.md`) reprodujo tres defectos más, los tres ciertos y los tres corregidos el 22-sep 07:41 UTC, cada uno con una regresión que se comprobó que falla con el código anterior:
   - **R2**: `base_rebote.rompio` se asigna antes del filtro de volumen, así que el disparador del rebote confirmaba rupturas que el propio detector rechaza. Ahora `ruptura_valida()` exige techo + volumen + que no llegue tarde, con una prueba que conecta el detector real al motor.
   - **R3**: el tope de escritura descartaba también las filas con identidad. **36 de 100 alertas se quedaron sin lectura vinculada.** Ahora el tope solo se aplica a las transiciones; tras el arreglo, 29 de 29.
   - **R4**: el evaluador de la fase 2 descontaba el coste de la configuración actual en vez del que el plan congeló, reescribiendo el neto de cualquier ventana abierta al cambiar el ajuste.
   - Y un hueco propio: `observar()` nunca rellenaba `confluencia`, así que `conf_confirmadas` salía vacío en todas las lecturas. Ahora 316 de 316.

   Pendiente de la fase 4: medir en vivo cuántos candidatos produce cada motor, cómo se reparten los cuatro orígenes, y comparar la muestra del universo contra las filas de alerta y de veto — que es para lo que existe.
10. **Fase 5 — desplegada y congelada** el 22-sep 21:01:01 UTC, huella `cef2ec54020c46ca`, registro en v3. Primeras medidas a las 09:01 UTC del 23-sep; puerta del dinero no alcanzable antes del **17-oct**. Seis defectos de una revisión externa corregidos antes de congelar (ver `fase5/REGISTRO_CONGELADO.md` §7).
11. **Fase 6 — desplegada** el 22-sep 22:07 UTC (ver [fase6/FASE6.md](fase6/FASE6.md)). Contrato de lectura, vista de oportunidades, Telegram con identidad y resultados por población.
12. **Sobre +3,2 contra +4,2 neto**: medido el 22-sep con una vara nueva —esperanza **por hora de posición ocupada**, que es la que importa con una sola posición—. En el universo entero (n=534) gana 3,2 por poco; en la cohorte de Telegram (**n=15**) gana 4,2. Respuestas opuestas y muestras pequeñas: **no se toca**. Ver [fase6/OBJETIVO_32_VS_42.md](fase6/OBJETIVO_32_VS_42.md).
13. No adelantar el ajuste de +4,2 % sin la prueba prospectiva de la fase 5.

No saltar al entrenamiento ni al ajuste de +4,2 % por parecer más atractivo.

## 7. Reparto de trabajo sin colisiones

No se asignaron tareas ni se enviaron mensajes a otros agentes durante esta planificación. Los responsables se acuerdan al unificar el trabajo.

Divisiones posibles después de fijar el contrato: identidad/persistencia; evaluador/replay; UI/diario; motores en sombra; revisión de aceptación. Debe haber un solo responsable de esquema y migraciones.

No editar simultáneamente `engine.py`, `db.py`, `routes.py` o los tipos compartidos sin coordinar propietario. Mantener cambios pequeños y revisables. Evitar `git add -A`, restauraciones globales o limpieza del árbol con trabajo ajeno. No añadir `.env`, bases activas ni credenciales a un commit.

## 8. Reproducción y comprobaciones

Desde `D:/SACBinance`:

```powershell
python audit/2026-09-22/plan-evolucion-motores/analizar.py
python audit/2026-09-22/plan-evolucion-motores/verificar_analisis.py
python audit/2026-09-22/plan-evolucion-motores/comprobar_base.py
```

Los dos primeros leen el snapshot guardado y escriben resultados derivados dentro de esta carpeta. El tercero ejecuta las pruebas existentes con transportes/DB de prueba y comprueba tipos; sus rutas de runtime son específicas de este equipo y pueden adaptarse en otro.

Resultado base: **62 pruebas de backend, 25 de frontend y tipos frontend correctos**. Siete salidas en 176 avisos recalculadas de forma independiente, con cuentas coincidentes.

Evidencia:

- `datos/manifest.json`: corte, hashes, servicio, comparación local/remota y estado de Git.
- `datos/snapshot.json.gz`: export inmutable. No sobrescribir.
- `datos/resultados.json`: resultados completos y exclusiones.
- `datos/verification.json`: comprobación independiente.
- `datos/baseline-checks.json` y los tres logs de pruebas.
- `remote_export.py`, `adquirir.py`, `analizar.py`, `verificar_analisis.py`, `obtener_fuentes.py`, `comprobar_base.py`: herramientas de investigación, sin integración con el producto.

`adquirir.py` rechaza sobrescribir el snapshot. Para actualizar datos, crear otro corte/paquete y registrar su procedencia. Usar `ssh sac`; no sustituirlo por una IP que omita la identidad SSH configurada.

## 9. Decisiones pendientes de fases posteriores

- Contenido y alcance del plan paralelo de Cloud/Claude.
- Presupuesto de riesgo y exposición de cartera que el usuario quiera evaluar.
- ~~Regla inicial de límites del episodio~~ — **decidida el 21-sep: 12 h, con cierre por desenlace, ancla, silencio o caducidad** (ver la adenda y `PLAN.md` §4).
- Horizonte de espera y tenencia de cada política; no ampliarlo por usar contexto de 4h sin estudiarlo.
- Entrada del diario: simulación, declaración manual e importación posterior opcional.

Son decisiones futuras. No impidieron completar esta planificación ni el análisis del objetivo.

## 10. Actualización obligatoria al terminar cada fase

Registrar fecha UTC, responsable, fase, base de código/configuración, archivos modificados, migraciones/recuentos, pruebas/resultados, estado de sombra/emisión, situación local/remota, decisiones con evidencia, pendientes y próximo paso exacto.

No marcar una fase completa por haber escrito los archivos: verificar sus criterios de aceptación. No indicar «desplegado» si solo se copiaron archivos o falta reiniciar. No afirmar mejora si cambió el denominador, horizonte, coste o población sin comparación válida.

## 11. Texto para retomar

> Revisa `audit/2026-09-22/plan-evolucion-motores/LEER_PRIMERO.md` y los documentos enlazados. La planificación está terminada; el producto aún no se modificó. Unifica este plan con el trabajo paralelo antes de implementar. El alcance es spot: continuación alcista y caída/recuperación, con identidad de episodio/plan y operación elegida. La siguiente fase es identidad en sombra, sin cambiar emisión, TP/SL ni Telegram. Conserva los cambios locales previos, verifica el estado actual y actualiza `CONTINUIDAD.md` con el resultado real de cada fase.
