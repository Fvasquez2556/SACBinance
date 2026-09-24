# Fase 7a · Reglas de activación y reversión, congeladas

**Versión 2 — 24-sep-2026.** Corrige la versión 1 del 23-sep **antes de que existiera un solo resultado bajo ella**: nunca se desplegó, así que no hay datos que invalidar. Los cambios y su motivo están en el §11. La versión 1 se conserva en el historial de git.

**Escrito ANTES de que exista un veredicto de la fase 5.** La fase 7 del plan exige una fracción «definida antes de ver sus resultados», y el 23-sep ya se había visto un resultado parcial del universo entero (A1 aprobada, A3 rechazada por habilidad).

Conviene decirlo con precisión, porque la diferencia importa: esto es **fijado antes del veredicto sobre la población decisoria**, no «ajeno a todo resultado». Lo segundo sería falso y ya no se puede conseguir. Lo primero sí es verificable, y es lo que se afirma aquí.

**Este documento no activa nada.** Al terminar la fase 7a, el sistema emite exactamente igual que antes. Lo único que existe es el candado: quién podrá ser el rival, en qué proporción, cómo se reparte, cuándo puede empezar, cuándo hay que pararlo y qué significa parar.

Es la misma disciplina del [registro congelado de la fase 5](../fase5/REGISTRO_CONGELADO.md), y por la misma razón: en este proyecto ya se evaporaron dos hallazgos que se habían escrito después de mirar.

---

## 1 · Lo que la fase 7 exige, línea por línea

Del [PLAN.md](../PLAN.md), §7, fase 7:

| exigencia del plan | dónde se cumple |
|---|---|
| «Solo activar una política validada y revisada por el usuario» | §4, puertas de entrada |
| «fracción acotada … definida antes de ver sus resultados» | §3 |
| «conservando una referencia comparable» | §3, brazo REFERENCIA |
| «asignación por episodio» | §5 |
| «No aumentar simultáneamente el presupuesto de avisos o riesgo» | §7, congelado |
| «Reversión: desactivar … y volver a la política previa» | §6 |
| «mantener el seguimiento de los planes ya notificados y de las operaciones registradas» | §6 |
| «No restaurar ciegamente una base antigua» | §6 |

## 2 · Quién puede ser el rival — la regla, no el nombre

**No se nombra al rival aquí a propósito.** Nombrarlo hoy sería prejuzgar la fase 5, y ya he visto lo suficiente del universo entero como para que mi elección no fuera limpia.

Lo que se congela es la **regla que lo selecciona**:

> El rival es la política de la fase 5, distinta de `REF` y no marcada como exploración, que cumpla **las tres condiciones** de abajo. De las que las cumplan, la del **mayor límite inferior del intervalo de dinero**.

| | condición | por qué |
|---|---|---|
| a | pasa las tres puertas de la fase 5 sobre la población decisoria | es la vara acordada |
| b | **bate a la referencia en la comparación pareada**, con el límite inferior por encima de cero | las puertas de la fase 5 son **absolutas**: una política puede pasarlas siendo **peor que lo que ya hay** |
| c | **mantiene esa ventaja pareada en las dos mitades temporales** | se examinan hasta diez políticas; quedarse con el máximo de diez estimaciones infla por construcción |

**Sobre (b):** el plan lo pide en su §8 —«comparación pareada frente a la política vigente, no únicamente frente a una salida inferior»— y la fase 5 calcula ese pareado pero **no lo mete en su veredicto**. No se toca su registro congelado; la condición vive aquí, como requisito **adicional**.

**Sobre (c):** es el riesgo de coronar a una ganadora por azar, y la defensa no es un apaño de umbral. Es la que este proyecto ya usa: partir la muestra por la mitad y exigir que aguante. Es lo que tumbó a «la primera señal es la buena» y a la regla C3 del hoyo.

Las cuatro formas de no haber rival, todas igual de válidas:

- **Ninguna pasa las tres puertas.** La fase 5 sigue siendo observacional y se dice así.
- **Ninguna bate a la referencia en pareado.** Pasar puertas absolutas no basta.
- **La ganadora no aguanta el corte por mitades.**
- **La ganadora es `REF`:** no hay nada que cambiar. Es un resultado, no un fracaso.

**Si dos quedan dentro del margen de empate (0,10 pp), NO se bloquea la activación**: dos que baten a la referencia son las dos una mejora, y paralizarse ante el éxito es tan arbitrario como perseguirlo. Pero el desempate **no mira los números** —ahí es donde entra el azar—: se deshace por el orden de ejes que el plan fijó el 22-sep (salida, entrada, stop) y, dentro del eje, por el cambio más pequeño.

La política ganadora se ata en el momento de activar, con su propia fecha y su propia huella. Esta regla no se puede reescribir después para que encaje con quien vaya ganando.

## 3 · La fracción: 25 %

**25 % de los episodios nuevos al brazo RIVAL, 75 % a REFERENCIA.**

### La aritmética de la versión 1 estaba mal por un factor de ocho

La v1 justificaba el 50 % diciendo que llegaban **≈2 planes decisorios al día** y que por tanto el 10 % tardaría 250 días. Ese «2 al día» salía de los 2 medibles que había en las primeras 25 h desde el congelado — **y esos 2 eran el atasco de la hambruna del evaluador, no la tasa de llegada**. Se leyó un artefacto de un bug como si fuera un dato del mercado.

Medido de verdad el 24-sep, con el atasco ya drenado y separando las dos cosas que la v1 mezclaba:

| | |
|---|---|
| **generación** — planes decisorios creados | **17,6 al día** (32 en 43,5 h) |
| **maduración** — de los maduros, cuántos resuelven | **68,4 %** (13 de 19) |
| **medibles** — lo que de verdad cuenta para n | **≈ 10,5 al día** |

| fracción | medibles/día en el brazo rival | días hasta n=50 | señales del operador afectadas |
|---|---|---|---|
| 50 % | ≈ 5,3 | ≈ 9,5 | la mitad |
| **25 %** | **≈ 2,6** | **≈ 19** | **una de cada cuatro** |
| 10 % | ≈ 1,1 | ≈ 48 | una de cada diez |

### Por qué 25 y no 50 ni 10

Con la tasa real, **el 50 % ya no hace falta**: gastar la mitad de las señales para concluir en 9 días en vez de 19 no compra nada que importe, y la fracción **sí** acota exposición — eso la v1 lo negaba y era un error. Cada operación del brazo rival se diferencia en céntimos, pero la exposición acumulada sobre 10 USDT no es despreciable, y el cortacircuitos **complementa** ese límite, no lo sustituye.

Y **el 10 % ya no es absurdo**: 48 días, no 250. Se descarta por otra razón, más honesta que la de la v1: 48 días atraviesan varios regímenes, y este sistema ya midió que su tasa base se movió **15 puntos en una semana**. Eso no invalida un estudio largo —un horizonte operativo de 12 h no impide medir durante meses—, pero obliga a comprobar la estabilidad entre regímenes en vez de darla por hecha. A 19 días esa comprobación es factible con el corte por mitades del §2; a 48 haría falta un diseño por régimen que esta fase no tiene.

### Dos precisiones sobre los días

- **50 observaciones es el mínimo de la puerta, no una garantía de precisión.** «Días hasta n=50» mide cuándo se puede *empezar a mirar*, no cuándo habrá una respuesta nítida. Puede hacer falta bastante más.
- **La proyección se apoya en 1,8 días de base** y los días naturales observados van de 13 a 17 planes creados. Es poco para proyectar semanas. Si la tasa cae, las fechas se mueven solas, y eso se reporta en vez de reinterpretarse.

> **Si el operador prefiere otra fracción, el momento es ahora.** Cambiarla una vez empezada la fase 7b cambia la huella y marca lo anterior como otra versión — que es exactamente lo que debe pasar, y por eso no conviene.

## 4 · Cuándo puede empezar la fase 7b — las cuatro puertas

Las cuatro, simultáneas. Ninguna se puede sustituir por otra.

| | puerta | cómo se comprueba |
|---|---|---|
| 1 | Las tres puertas de la fase 5 pasan sobre la población decisoria, con n ≥ 50 | el informe de la fase 5, con su huella |
| 2 | Existe un rival por la regla del §2 — incluido el pareado **y el corte por mitades** | `puede_activarse()`; una elección sin el corte sale marcada `provisional` y **no autoriza** |
| 3 | **El operador lo ha revisado y aprobado explícitamente** | no hay activación automática, nunca |
| 4 | Integridad: ninguna colisión de asignación, ninguna modificación retroactiva de niveles, ningún plan emitido sin brazo | `verificar_integridad()`, en cada arranque |

La puerta 3 no es burocracia: es el dinero del operador, y la fase 7 del plan la exige con esas palabras.

**La fecha se calcula, no se fija.** La v1 decía «17-oct» y esa fecha salía de la misma tasa equivocada del §3. Con ≈10,5 medibles al día en la población decisoria y 19 ya acumulados el 24-sep, la fase 5 alcanza n=50 **en torno al 27–29 de septiembre**; la fase 7b necesita además n=50 **en el brazo rival**, que al 25 % llega **unas tres semanas después de activar**. Si la tasa baja, las fechas se mueven solas y se dice.

## 5 · El reparto: por episodio, determinista, y escrito una sola vez

```
u = primeros 8 bytes de sha256("<huella>:<episode_id>"), escalados a [0,1)

brazo(episodio) = RIVAL       si u < FRACCIÓN
                  REFERENCIA  si no
```

Se compara contra la fracción declarada en vez de mirar si el hash es par. Con la paridad, cambiar la fracción en el documento dejaría el reparto clavado en el 50 % sin que nada lo delatara: el papel diría una cosa y el código haría otra. Así solo hay una fuente.

Cinco propiedades que importan, y por qué cada una:

- **Por episodio, no por plan.** Es lo que el plan exige. Si la quinta repetición de un movimiento cayera en el brazo contrario a la primera, los dos brazos estarían midiendo el mismo movimiento y la comparación sería falsa.
- **Determinista, sin generador aleatorio.** Un `random` con estado da otro reparto al reiniciar, y este servicio reinicia. Además se puede reproducir años después desde la huella y el `episode_id`.
- **La huella entra en el hash.** Una versión nueva del registro rebaraja en vez de heredar el reparto viejo — que sería llevarse la suerte de una versión a otra.
- **Se escribe una vez y no se recalcula.** Si el episodio ya tiene brazo en la tabla, ese gana, pase lo que pase con la huella. Un episodio vivo no cambia de brazo a mitad.
- **La fracción vive en un solo sitio.** El reparto la lee; no hay un 50 % escrito aparte en el código.

No se busca un 50/50 exacto: con un hash, en muestras pequeñas el reparto se desvía, y forzarlo introduciría dependencia entre episodios. El desequilibrio observado se reporta, no se corrige.

## 6 · Reversión — asimétrica a propósito

### Los disparadores

| | disparador | umbral | actúa |
|---|---|---|---|
| **daño** | el rival va peor que la referencia | > 1,0 punto por operación, con n ≥ 15 en cada brazo | revierte |
| **cortacircuitos** | el brazo rival pierde dinero en términos absolutos | capital **compuesto** del rival ≤ −10 % **y la referencia por encima de ese suelo** | revierte **ya**, sin esperar a n |
| **integridad** | colisión de asignación, nivel modificado retroactivamente, plan emitido sin brazo | cualquiera | revierte **ya** |
| **manual** | el operador | cuando quiera, sin justificar | revierte |

### Y el que no existe

**No se para porque el rival vaya ganando.** Las fechas de revisión son de calendario (§7) y no se adelantan por una cifra favorable. La asimetría es deliberada y está en el plan con estas palabras: «No detener la prueba en cuanto salga una cifra favorable». Parar ante el daño protege el dinero; parar ante el éxito es elegir el momento que más favorece, que es como se fabricó el +0,25 % de la regla C3 que se evaporó con tres horas más de datos.

**El cortacircuitos mide capital compuesto, no la suma de porcentajes.** Con una posición que se reinvierte entera, el capital sigue el producto; sumar los porcentajes hacía saltar la protección con diez operaciones normales. Lo encontró una prueba de extremo a extremo.

**Y exige que la referencia no esté igual de hundida:** si cae todo el mercado, revertir no recupera nada y acabaría el experimento por el motivo equivocado. Con la referencia sana, la pérdida sí es atribuible al rival.

**Los disparadores se comprueban y se aplican solos**, en el bucle de mantenimiento, con la reversión ejecutada y registrada. En la v1 `evaluar_reversion()` devolvía una decisión y **nadie la llamaba**: presentar eso como protección era falso, y lo encontró una revisión externa. Un fallo en la vigilancia no tumba el bucle, pero se registra como error — una vigilancia que falla en silencio es peor que no tenerla.

### Lo que revertir NO hace, dicho sin adornos

**Revertir corta la exposición futura. No es una red bajo lo que ya está en mercado.**

- **No cierra ninguna posición abierta.** Si hay una operación viva con los niveles del rival, revertir no la toca: sigue hasta su TP o su stop.
- **Un stop no garantiza el precio de ejecución.** Con un hueco de precio se ejecuta donde haya liquidez, que puede ser bastante por debajo. El −10 % es un umbral de decisión, no un suelo de pérdida.
- Lo que esto protege es **el siguiente plan**, no el que ya está en curso.

### Qué hace revertir, y qué no

Revertir es **apagar un interruptor**, no restaurar una copia.

- ✅ Los episodios nuevos pasan todos a REFERENCIA.
- ✅ **Los planes ya notificados conservan sus niveles.** Un plan que salió con el TP del rival muere con el TP del rival, y se sigue evaluando contra él.
- ✅ **Las operaciones registradas conservan los suyos.** Es la regla de la fase 3 y no se toca: un plan posterior no mueve lo que ya se tomó.
- ❌ **No se restaura ninguna base de datos.** Una base antigua borraría los eventos posteriores —operaciones del usuario, desenlaces, lecturas— que no tienen nada que ver con el experimento.

## 7 · La rampa: por calendario, no por resultados

| momento | fracción | qué se hace |
|---|---|---|
| activación | 50 % | empieza |
| +30 días | 50 % | **primera revisión**. No sube |
| +60 días | 50 % | segunda revisión. Decisión de promover, revertir o seguir |

La fracción **no sube por un resultado intermedio favorable**. Subirla al ver que va bien es la misma trampa que parar al ver que va bien, y convierte un experimento en una apuesta creciente sobre ruido.

Congelado junto a la fracción, y por exigencia expresa del plan:

- El **presupuesto de avisos** no cambia durante la fase 7b.
- El **tamaño de posición** no cambia durante la fase 7b.
- La **regla de un plan notificado abierto por símbolo** no cambia.

Mover cualquiera de las tres a la vez que el objetivo haría imposible saber cuál movió el resultado.

## 8 · La amenaza que esta fase no puede eliminar, y cómo se reporta

El brazo decide **qué se muestra**. Quien decide **qué se toma** es el operador, y puede preferir sistemáticamente un brazo —por ejemplo, porque el TP del rival se ve más apetecible. Si eso pasa, la población *tomada* deja de ser comparable entre brazos, aunque la asignación fuera perfecta.

No hay forma de evitarlo sin quitarle la decisión al operador, que no es lo que se está construyendo. Así que se declara cómo se lee:

- **Lectura principal:** todos los planes decisorios emitidos, evaluados en sombra. No depende de qué tomó el operador.
- **Lectura secundaria:** las operaciones realmente tomadas. Es el dinero de verdad, y va **siempre acompañada de la tasa de toma por brazo**, para que se vea si el operador eligió distinto en cada uno.

Si las dos lecturas discrepan, **manda la principal** para el veredicto y la secundaria se reporta como lo que es.

Cada mensaje de Telegram dirá a qué brazo pertenece. Sin eso el operador no puede llevar su propia cuenta, y un experimento que el sujeto no puede auditar no es un experimento, es un cambio silencioso.

## 9 · Qué entra en la huella

Todo lo que cambia un resultado:

- la regla de selección del rival, con sus tres condiciones
- la regla de desempate
- la fracción y la regla de asignación
- las cuatro puertas de entrada
- los umbrales de reversión y el cortacircuitos
- el calendario de la rampa
- las tres cosas que quedan congeladas (avisos, posición, un plan por símbolo)
- la versión del registro de la fase 5 con el que se acopla
- **el sha256 de este documento**

Si cualquiera cambia, la huella cambia, y lo medido bajo la anterior queda identificado como de otra versión en vez de mezclarse en silencio. Congelado en la tabla `activacion_registro` con su fecha UTC.

## 10 · Estado al terminar la fase 7a

| | |
|---|---|
| activación | **apagada** (`activacion_enabled = False`) |
| rival atado | **ninguno** |
| episodios asignados | los que hayan pasado por el registro, **sin efecto sobre la emisión** |
| emisión | **idéntica** a antes de esta fase |

La asignación corre desde ya **en sombra**: cada episodio nuevo recibe su brazo y se guarda. Así, el día que la fase 5 dé veredicto, el reparto ya lleva semanas funcionando y probado, y la activación es un interruptor y no un estreno.

## 11 · Qué corrige la versión 2, y por qué

Todo esto salió de una revisión externa del 24-sep, **antes de desplegar y antes de que existiera un solo resultado bajo la v1**. Ninguno de estos cambios invalida datos, porque no había datos.

Tres eran **contrato que no coincidía con el código** — el fallo más grave posible en un registro congelado, porque la huella certificaba una declaración que el programa no cumplía:

| | la v1 declaraba | el código hacía | resuelto |
|---|---|---|---|
| **F7-R1** | nada sobre la comparación pareada | la exigía (`pareado_vs_ref.ic_bajo > 0`) | gana el código: la condición entra en la declaración (§2b) |
| **F7-R2** | un empate **impide** activar | desempataba y elegía | gana el código, porque el desempate **no mira resultados**; la declaración lo dice ahora (§2) |
| **F7-R3** | cortacircuitos condicionado a que la referencia no cayera | no lo comprobaba | gana la declaración: el código ahora lo exige (§6) |

Y tres correcciones de fondo:

| | qué estaba mal | corregido |
|---|---|---|
| **F7-R4** | `evaluar_reversion()` devolvía una decisión y **nadie la llamaba**. El −10 % se presentó como protección operativa sin serlo | se aplica sola en el bucle, con prueba de extremo a extremo (§6) |
| **F7-R5** | la aritmética de la fracción se apoyaba en «≈2 planes decisorios/día», que era **el atasco de un bug leído como tasa de llegada** | remedido: 17,6 creados y ≈10,5 medibles al día. Fracción **50 % → 25 %** (§3) |
| **F7-R6** | elegir el máximo de diez políticas sin defensa contra coronar una ganadora por azar | tercera condición: la ventaja pareada tiene que aguantar el **corte por mitades** (§2c) |

Tres afirmaciones de la v1 que además eran retóricamente excesivas y quedan retiradas:

- «el 10 % tardaría 250 días» — eran 48, y el motivo para descartarlo es otro.
- «la fracción no acota el riesgo, solo el aprendizaje» — **sí lo acota**. El cortacircuitos complementa ese límite, no lo sustituye.
- «un horizonte de 12 h no puede permitirse una prueba larga» — sí puede; lo que exige es comprobar la estabilidad entre regímenes.

Y una precisión sobre el origen de estas reglas: se fijaron **antes del veredicto sobre la población decisoria**, habiendo visto ya un parcial del universo entero. Es lo que se puede afirmar con verdad, y es menos de lo que la v1 daba a entender.
