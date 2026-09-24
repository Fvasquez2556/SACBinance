# ¿+3,2 % neto o +4,2 % neto? · 22-sep-2026

**Respuesta corta: de momento no se toca, y lo poco que dicen los datos apunta a quedarse en 3,2.** Pero el motivo importa más que la respuesta, porque cambia cómo hay que comparar objetivos de aquí en adelante.

## La vuelta que faltaba

Todo lo medido hasta ahora comparaba **esperanza por operación**: +0,33 % para 3,2 contra +0,51 % para 4,2, con el intervalo del 95 % de la actual en [−0,04 %, +0,99 %]. Con esa vara empatan.

Pero esa vara contesta «¿cuánto deja cada señal?», y con **una sola posición** esa no es la pregunta. La pregunta es «¿cuánto deja mi capital al mes?», y ahí entra algo que nadie había medido: **cuánto tiempo ocupa cada objetivo la única posición que hay**.

Un objetivo más lejano tarda más en cobrarse. Mientras tanto la posición está ocupada y las demás oportunidades pasan de largo. La vara correcta no es esperanza por operación: es **esperanza por hora de posición ocupada**.

## Medido sobre 534 recorridos completos

| objetivo | acierta | esperanza/op | minutos medianos | **por hora ocupada** | op./día | 10 USDT a 30 días |
|---|---|---|---|---|---|---|
| +2,7 % neto | 54,7 % | +0,196 % | 387 | +0,0296 % | 3,64 | 12,37 |
| **+3,2 % neto** | 53,2 % | **+0,234 %** | 438 | **+0,0334 %** | 3,42 | **12,71** |
| +4,2 % neto | 50,7 % | +0,230 % | 541 | +0,0296 % | 3,09 | 12,38 |

Por operación, 3,2 y 4,2 **empatan** (+0,234 contra +0,230). Por hora ocupada, 3,2 gana un 13 % — porque libera la posición **1,7 horas antes** de mediana y eso son 0,33 operaciones más al día.

## Y aquí viene el problema

Sobre la población que el operador recibe de verdad —los avisados a Telegram— la respuesta **se da la vuelta**:

| objetivo | acierta | esperanza/op | 10 USDT a 30 días |
|---|---|---|---|
| +2,7 % neto | 53,3 % | −0,211 % | 7,89 |
| +3,2 % neto | 53,3 % | −0,081 % | 9,19 |
| **+4,2 % neto** | 53,3 % | **+0,252 %** | **12,92** |

**n = 15.** Quince operaciones. Las tres aciertan lo mismo (53,3 %): toda la diferencia viene de que un puñado de operaciones siguió subiendo más allá de 3,2. Con quince casos eso lo decide una sola moneda que corrió mucho.

Esto es exactamente lo que le pasó a la regla C3 en septiembre: **+0,25 % que se convirtió en −0,20 % con tres horas más de datos**, sin tocar una línea del script.

## Qué hacer

**No cambiar nada todavía.** Dos poblaciones dan respuestas opuestas, y la que importa tiene quince casos.

Y hay algo que pesa más que la respuesta: sobre 10 USDT a 30 días, la diferencia entre los tres objetivos en el universo entero es de **34 céntimos**. El objetivo no es la palanca. Con una posición y dieciséis oportunidades que pasan de largo cada día, **la palanca es cuál tomas**, no a dónde apuntas.

La fase 5 ya tiene esto encolado: A3 (+4,2 % neto) es su rival principal, contra la referencia y contra A1/A2/A4/A5, sobre terreno nuevo y con la población decisoria. Su puerta del dinero no se puede cerrar antes del **17-oct**.

## Lo que sí cambia desde hoy

La vara. A partir de ahora, comparar objetivos **por operación es insuficiente** cuando solo hay una posición: hay que dividir por el tiempo que la ocupan. Esto se añade a la lectura de la fase 5, no a sus políticas — el registro congelado no se toca.

## Salvedades

534 recorridos de un solo régimen de cuatro días; 15 en la cohorte de Telegram. Retrospectivo: es de donde sale la pregunta, no el veredicto.

Reproducir:

```bash
ssh sac '/home/flox/sacbinance/backend/venv/bin/python -' < objetivo_32_vs_42_remote.py
ssh sac '/home/flox/sacbinance/backend/venv/bin/python - --telegram' < objetivo_32_vs_42_remote.py
```
