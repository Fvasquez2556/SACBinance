# Qué queda pendiente de las auditorías

**Estado a 11-sep-2026, 16:50.** Servidor en `bddb688`, esquema v12.

Las **85 comprobaciones** (23 + 29 + 33) están en verde, pero eso no significa que los informes estén cerrados: esas pruebas miden **defectos concretos**, y las secciones «Para cerrar» de cada hallazgo piden más. Esto es el inventario honesto, comprobado contra la base viva.

---

## ✅ Aplicado y verificado

| | Qué se arregló |
|---|---|
| **F01** | Detección de huecos por secuencia, fusión sin duplicar, descarga que alcanza el hueco, reparación acotada a 40 pares |
| **F02** | La vela cuenta solo si su minuto entero cae en la ventana; cierre por reloj |
| **F05** | El estudio del hoyo comparte la regla conservadora del tracker |
| **F07** | Indicadores con su marco temporal — 69/69 y 65/69 |
| **F08** | El motor recibe la shortlist **suscrita**; SUBSCRIBE en caliente sin reconectar |
| **F09** | Universo deseado vs suscrito, con delta acumulada |
| **F10** | Filtro de apalancados |
| **F11** | Idempotencia de vela en tres sitios |
| **F12** *(parcial)* | Hash de configuración v2: cubre todo lo que decide |
| **F13** *(parcial)* | El plan vivo se actualiza antes del veto de blow-off |
| **F14** *(parcial)* | El encabezado ya no llama "win rate real" a una frecuencia bruta |
| **Recorridos** | Causalidad, identidad, tiempo real, MFE doble, esquema de producción, muestra efectiva de Kish |
| **Despliegue** | Frontend compilado y sirviéndose; backend en `bddb688` |

---

## 🔸 No hecho **a propósito** — son decisiones tuyas, no arreglos

**`exigir_objetivo_operador` sigue en `false`.** Activarlo recorta la producción ~60%. Y como medí después: no arregla nada, solo silencia las que no llegan (de 46 alertas a 17). El veto está implementado y probado.

**`prob_meta` del tablero sigue respondiendo otra pregunta** (tocar la meta original en 6h, sin exigir que sea antes del SL). Cambiarlo altera lo que ves en la UI.

**El histórico no se reconstruye ni se excluye.** Toca la base de producción: 2.792 outcomes sin versión y 2.484 cerrados sin cobertura siguen ahí.

**El TP sale del stop × 2** (`rr_target`). Es la causa aritmética de que más de la mitad no apunte a 3,2%, y cambiarlo mueve todo el sistema.

---

## 🔴 Pendiente de verdad — trabajo real sin hacer

### Alto impacto

**F02 · Signals sin reloj.** El cierre por reloj se aplicó a *outcomes*, no a *signals*. Ahora mismo hay **24 signals OPEN de más de 12h, la más vieja de 155,7 horas** — seis días y medio con `signal_expiry_hours=12`. Es el mismo defecto que el informe describía, en la tabla que no se tocó.

**F13 · Las alertas de perfil no abren plan ni outcome.** **1.846 eventos BASE** en el log y solo 176 outcomes con taxonomía TENDENCIA. Esa rama emite avisos que nadie mide: no se puede saber si esos perfiles aciertan.

**F04 · Alertas sin identidad propia.** **33 de 155 (21%)** con `signal_id` NULL: sus niveles concretos no tienen outcome que los evalúe. Falta el `plan_id` persistente y el enlace de reemplazos.

**F12 · La purga borra antes de tiempo.** Retención de 3 días para velas de 1m. La revisión de recorridos lo midió: de 2.985 registros con ventana de 8h vencida, **ninguno conserva todas sus velas**, y 1.720 no conservan ninguna. Sin OHLC no hay forma de reconstruir nada.

### Medio

**F01 · Reprocesar seguimientos desde la primera vela ausente.** La reparación ya rellena el buffer, pero los outcomes no se recalculan sobre las velas recuperadas.

**F01 · Separar la suscripción de trades de la de velas.** WS-A sigue llevando klines + aggTrade juntos (ahora sin reconectar, así que duele menos).

**F05 · Recalcular los análisis del hoyo.** La regla está corregida; las cifras publicadas se midieron con la anterior y **no se han vuelto a calcular**.

**F07 · Razón de indisponibilidad** en los indicadores NULL, y comprobar calentamiento de 15m.

**F08 · Edad del último dato de flujo**, separada del volumen de compras.

**F14 · Separar las métricas de verdad**: tasa de tocar TP, cierre positivo, cumplimiento neto y expectativa por plan y versión. `pct_sobre_meta` sigue comparando contra 3,2 bruto fijo.

---

## 🔵 El motor de recorridos: sin empezar

La sección «Integración propuesta» (A–F) de la revisión del 11-sep **no es una corrección, es un sistema nuevo**. No se ha tocado:

- `path_evaluator.py` compartido entre streaming y replay
- Tablas `candidate_episodes`, `evaluation_plans`, `outcome_horizons`
- Los **siete horizontes** (15/30/60/120/240/360/480 min) en producción
- Captura sistemática de candidatos sin alerta
- Calibración por perfil y régimen, con validación temporal purgada
- La UI que lo muestre

**La tabla `labels` no existe en producción**: el etiquetador corregido nunca se ha ejecutado contra datos reales. Y con la retención de 3 días no puede producir horizontes de 8h completos — por eso la purga es la pieza que bloquea a las demás.

---

## Lo que no salió de ningún informe, y quizá importa más

Analizando tu operación de DOGS: **+6,34% en 9 horas con −0,47% de drawdown, y el sistema no la vio** — score máximo 45 ese día, umbral 60.

Ningún hallazgo de las auditorías trata eso. Todas miran si el sistema *mide bien* lo que emite. Ninguna mira si *encuentra* lo que debería.

---

## Orden que yo seguiría

1. **La purga** (F12). Bloquea el motor de recorridos y cualquier reconstrucción histórica. Es barato: cambiar la retención.
2. **El reloj de signals** (F02). 155 horas abiertas es un dato roto que contamina cualquier estadística.
3. **Plan y outcome para las alertas de perfil** (F13 + F04). Sin esto, 1.846 eventos BASE son invisibles.
4. Después, el motor de recorridos, con historia suficiente detrás.

---

**Nota sobre desplegar esto:** si commiteas y despliegas solo documentación, `procedencia` firmará las filas nuevas con un commit distinto y la cohorte se parte otra vez sin motivo funcional — como pasó con `b8a3d64` → `25d03fa`. Conviene agrupar los commits de documentación con cambios reales antes de desplegar.
