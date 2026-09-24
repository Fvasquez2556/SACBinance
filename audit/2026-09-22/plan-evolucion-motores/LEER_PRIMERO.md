# Evolución de SACBinance: motores direccionales y medición por operación

**Estado: análisis y planificación completados. Implementación del producto pendiente.**

Captura de referencia: 22-sep-2026 01:02:26 UTC, equivalente al 21-sep 19:02:26 en Guatemala.

## Orden de lectura

0. [ADENDA_EPISODIO_Y_CONFIANZA.md](ADENDA_EPISODIO_Y_CONFIANZA.md): lo medido el 21-sep y las dos reglas que el plan dejaba abiertas. Las decisiones de aquí ya están incorporadas al plan.
1. [PLAN.md](PLAN.md): arquitectura, prioridades, fases y criterios de aceptación.
2. [EVIDENCIA_Y_DECISIONES.md](EVIDENCIA_Y_DECISIONES.md): respuesta sobre +4,2 % netos y diagnóstico del sistema actual.
3. [CONTRATOS_Y_METRICAS.md](CONTRATOS_Y_METRICAS.md): identidad, episodios, operación elegida, evaluación y contratos propuestos.
4. [CONTINUIDAD.md](CONTINUIDAD.md): estado exacto y protocolo para continuar con Cloud/Claude u otro colaborador.

## Decisiones tomadas el 21-sep-2026

- **El sistema es intradía.** Entrar y salir en horas, dentro del mismo día. El horizonte de 12 h no se alarga y un objetivo solo vale si se cobra dentro de la sesión.
- **La ventana del episodio queda en 12 h**, con cierre por desenlace, ancla, silencio o caducidad. Decisión del usuario, sobre la medición de la adenda.
- **La fase 1 está implementada en local y sin desplegar**: esquema v16, `src/episodios/`, integración en sombra y 79 pruebas en verde.
- **La puntuación no se publica como confianza.** No ordena (AUC 0,50–0,58) y lo que parecía ordenar era volatilidad. Lo que sí determina la probabilidad es la geometría del objetivo y el régimen.
- **La primera señal del episodio no es mejor que las siguientes** en los datos actuales. Sigue siendo unidad de conteo, no criterio de calidad.

## Decisiones principales

- Probar +4,2 % netos en sombra es razonable. Con 176 avisos maduros de la configuración reciente, su media simulada es +0,942 % por aviso frente a +0,895 % del TP variable vigente. La diferencia aún no demuestra superioridad. Subir el filtro mínimo a 4,2 % es una modificación distinta de fijar la salida en ese nivel.
- Evolucionar dos rutas sobre una base común: continuación alcista y caída/recuperación en spot.
- Dar identidad persistente al episodio y a cada plan. En la captura, 137/258 avisos enviados carecen de `signal_id`; la nueva medición no puede depender de ese enlace.
- Registrar explícitamente qué plan tomó el usuario. Las señales siguientes no cambian sus niveles ni su resultado.
- Primero identidad y evaluador; después motores en sombra, validación prospectiva y activación gradual.

## Alcance acordado

- Revisar el sistema actual y la evidencia recolectada antes de construir la actualización.
- Evaluar si un objetivo de +4,2 % neto se sostiene frente a objetivos inferiores, descontando costes y respetando el orden temporal de TP/SL.
- Evolucionar la lectura alcista y bajista existente. El usuario confirmó que la ruta bajista es para caídas y rebotes en SPOT, no posiciones cortas.
- Separar señales repetidas, episodios de mercado y operaciones tomadas por el usuario. Congelar la entrada y los niveles del plan elegido.
- Entregar documentación y continuidad para unificar el trabajo con Cloud/Claude y otros colaboradores.
- En esta fase se autorizó analizar y planificar. La implementación del sistema corresponde a una fase posterior.

## Continuidad

Leer `CONTINUIDAD.md` para conocer el estado comprobado y el próximo paso. No interpretar hipótesis o tareas pendientes como funciones ya implementadas.

Se encontraron modificaciones locales previas, incluidas las clasificaciones por ruptura y las notificaciones. No sobrescribirlas ni reconstruir el proyecto únicamente desde HEAD.

## Qué contiene la carpeta

Los cuatro documentos anteriores constituyen el paquete de planificación. Los scripts y `datos/` son el respaldo reproducible del análisis; no forman parte del servicio ni se importan desde él.

Para verificar el análisis sin conectarse al servidor:

```powershell
python audit/2026-09-22/plan-evolucion-motores/analizar.py
python audit/2026-09-22/plan-evolucion-motores/verificar_analisis.py
```

Se verificaron 62 pruebas de backend, 25 de frontend y los tipos del frontend. No se reinició ni desplegó el sistema durante esta planificación. La carpeta se puede entregar completa al colaborador; no se envió a ningún servicio externo.
