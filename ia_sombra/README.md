# IA en sombra

Kronos + GPT-6 **Luna** y **Sol** evaluando, a ciegas, cada aviso que SACBinance manda a Telegram. Es un servicio aparte: **lee** la base de SAC en solo lectura y **escribe** solo en la suya (`datos/ia_sombra.db`). SAC no cambia en nada y no sabe que existe.

A los 14 días de medición, `python -m sac_ia informe` da el veredicto: **AYUDA**, **ENTORPECE** o **INCONCLUSO**, con los criterios congelados en [`sac_ia/registro.py`](sac_ia/registro.py) antes de ver ningún resultado.

## Qué hace con cada aviso

1. Ve que la alerta pasó a `enviado` en `alertas_emitidas`, lee su plan en `notificacion_planes` y congela el contexto con los datos disponibles hasta ese instante.
2. Pide a Binance las últimas 128 velas cerradas de 1 h y genera 16 trayectorias de 12 h con Kronos-mini, en un proceso hijo con plazo (~17 s por aviso en el servidor, con un hilo). Se eligió así tras medirlo: Kronos-small con velas de 15 m pasaba de 10 minutos por aviso, y con 32 trayectorias tres avisos juntos no cabían en el plazo.
3. En cuanto Kronos termina con un aviso, pasa el contexto y su resumen a Luna y a Sol en paralelo, sin esperar a los demás avisos del mismo lote. Cada uno devuelve `ENTRAR`/`ESPERAR`/`RECHAZAR` y la probabilidad de tocar la meta del operador (+3,2 % neto) antes que el stop.
4. Doce horas después etiqueta lo que pasó con el mismo evaluador de recorridos que usa SAC (`backend/src/evaluacion/recorrido.py`).

Todo tiene que ocurrir en menos de 120 s desde el aviso. Lo que llega tarde se guarda, pero no cuenta.

## Brazos

| brazo | qué es |
|---|---|
| REFERENCIA | el aviso tal cual, sin IA |
| KRONOS | frecuencia de trayectorias que tocan la meta antes que el stop; se juzga solo por AUC |
| LUNA | `gpt-6-luna` con contexto + Kronos |
| SOL | `gpt-6-sol` con el mismo contexto + Kronos: **el brazo principal** |
| CASCADA | se deriva sin llamadas extra: entra si Luna y Sol dicen `ENTRAR` |

## Instalación en el servidor

```bash
bash deploy/instalar_ia.sh
```

Ese script solo instala. El orden completo:

1. `sudo cp deploy/sac-ia.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now sac-ia`. Arranca en **RODAJE**: registra avisos y la salud de SAC, sin Kronos ni API.
2. `venv/bin/python -m sac_ia probar-kronos -n 3` mide la latencia real de Kronos en este equipo.
3. La clave de OpenAI va en `secretos/openai.key`, con `chmod 600`. Nunca va en el repositorio ni en el `.env` de SAC.
4. `venv/bin/python -m sac_ia probar-llm --si-gastar` hace una llamada real a cada modelo (~1 centavo).
5. Tras 48 h de rodaje, `venv/bin/python -m sac_ia medir` congela la huella y empieza la ventana de 14 días.

## Gasto

Se reserva el peor caso antes de cada llamada y se liquida con el uso real. Los topes por defecto son **$1,50 al día y $15 en total** (`IA_TOPE_DIARIO_USD`, `IA_TOPE_TOTAL_USD`). El tope último son los créditos prepagados de OpenAI con la recarga automática **apagada**.

## Consultar

- `python -m sac_ia estado`: salud, cobertura, gasto y latencia. Nunca muestra decisiones ni resultados.
- `python -m sac_ia informe`: cegado hasta que cierra la ventana. `--desvelar` existe, pero queda anotado en la base.

## Apagar

`sudo systemctl disable --now sac-ia`. La base y los artefactos se conservan para auditoría. SAC sigue igual.

## Pruebas

```bash
../backend/venv/bin/python -m unittest discover -s tests
```

Usan el Python de SAC porque crean una base de SAC real con su propio esquema. Kronos y OpenAI se sustituyen por dobles.
