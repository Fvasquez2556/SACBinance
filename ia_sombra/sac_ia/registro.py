"""
El estudio, congelado antes de ver un solo resultado.

Aqui no se decide nada en tiempo de ejecucion: es la declaracion de que se va a
medir, con que vara y que cuenta como "ayuda" o "entorpece". Igual que en la
fase 7 (`backend/src/activacion/registro.py`), la declaracion entera se reduce
a una huella de contenido. El servicio guarda la huella al empezar la medicion
y el informe se niega a emitir veredicto si la huella cambio despues: cambiar
una linea es abrir otro estudio, no reescribir este en silencio.

Por que estas decisiones y no otras
-----------------------------------
- **Poblacion: los avisos que llegan a Telegram.** Es lo que el operador ve y
  lo unico sobre lo que la IA podria ayudarle. ~23 al dia (258 entre el 10 y
  el 22-sep).
- **Etiqueta principal: la meta del operador antes que el stop, en 12 h.** El
  operador busca +3,2 % neto, no el TP del plan: el 21-sep se midio que el
  51,5 % de los avisos que tocan +3,2 % no cobran nunca su TP. La meta bruta es
  3,2 + 0,5 de coste = 3,7 %. Si una misma vela toca meta y stop, gana el stop
  (regla del evaluador comun: una duda no se convierte en ganancia).
- **Metrica principal: AUC de la probabilidad de Sol.** El operador toma 1-2
  de ~20 avisos al dia; lo que le sirve es que la IA los ordene. Es tambien la
  metrica con mas potencia: con ~300 casos el IC95 se separa de 0,5 solo si el
  AUC es >= ~0,58. Todo lo medido en el proyecto da 0,47-0,53.
- **Cobertura minima 0,99.** Las velas que faltan borran la barrera mas
  cercana y fabrican objetivos (medido el 24-sep: +26,67 pp de habilidad falsa
  entre 0,75 y 0,90 de cobertura).
- **Bootstrap por par Y por dia.** El 84 % de las señales nace con otra del
  mismo par en ventana; tratar cada aviso como independiente estrecha el
  intervalo a mentira.
- **Solo cuenta lo que llego a tiempo.** Una decision que llega despues de
  120 s desde el aviso ya no podia usarse; se guarda, pero no entra.

El documento de diseño completo esta en la conversacion del 24-sep-2026 y en
la memoria del proyecto (`plan_ia_experimental`).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ESTUDIO_VERSION = "ia-sombra-v1"
FECHA_REGISTRO = "2026-09-24"

RAIZ = Path(__file__).resolve().parent
PROMPT_DECISION = RAIZ / "prompts" / "decision_v1.md"

# --- Tiempos ------------------------------------------------------------------
PLAZO_DECISION_MS = 120_000          # desde que SAC activa el aviso
HORIZONTE_MS = 12 * 3600_000         # el de los planes (signal_expiry_hours)
RODAJE_MIN_MS = 48 * 3600_000        # linea base de salud sin IA cargada
MEDICION_MS = 14 * 24 * 3600_000     # ventana del veredicto
ESPERA_ETIQUETA_MS = 30 * 60_000     # margen para el flush y la reparacion de velas
ABANDONO_ETIQUETA_MS = 24 * 3600_000 # pasado esto se cierra con la cobertura que haya

# --- La etiqueta ----------------------------------------------------------------
OBJETIVO_OPERADOR_PCT = 3.2          # settings.objetivo_operador_pct al congelar
COSTE_PCT = 0.5                      # settings.coste_operacion_pct al congelar
META_BRUTA_PCT = OBJETIVO_OPERADOR_PCT + COSTE_PCT
COBERTURA_MINIMA = 0.99

# --- Los brazos -------------------------------------------------------------------
# REFERENCIA: el aviso tal cual, sin IA. Es el denominador de todo.
# KRONOS: frecuencia de trayectorias simuladas que tocan la meta antes que el
#   stop. Sin LLM. Se juzga solo por AUC: no tiene umbral de entrada, porque
#   no hay datos previos sobre los que fijarlo sin mirar el test.
# LUNA y SOL: mismo contexto, mismo prompt, mismo resumen de Kronos. Solo
#   cambia el modelo, para que la comparacion aisle el modelo.
# CASCADA: se DERIVA despues, sin llamadas extra: entra solo si Luna dice
#   ENTRAR y Sol tambien. Asi se mide lo que el chat de origen proponia
#   ("Luna filtra, Sol decide") sin perder lo que Luna descarta.
BRAZO_REFERENCIA = "REFERENCIA"
BRAZO_KRONOS = "KRONOS"
BRAZO_CASCADA = "CASCADA"

BRAZOS_LLM = {
    "LUNA": {"modelo": "gpt-6-luna", "esfuerzo": "low", "max_salida": 6000,
             "con_kronos": True},
    "SOL": {"modelo": "gpt-6-sol", "esfuerzo": "low", "max_salida": 8000,
            "con_kronos": True},
}
BRAZO_PRINCIPAL = "SOL"

# --- Kronos -----------------------------------------------------------------------
# Medido el 24-sep en la laptop (i5-1135G7, 2 hilos): Kronos recalcula la
# secuencia entera en cada paso, asi que el coste es trayectorias x pasos x
# contexto x parametros. Kronos-small con velas de 15 m (32 x 49 pasos,
# contexto 256) pasaba de 10 minutos por aviso; Kronos-mini con velas de 1 h
# (32 x 13 pasos, contexto 128) tarda ~5 s. El servidor es mas lento y pueden
# llegar tres avisos juntos: dentro de 120 s solo cabe lo segundo. Se fija
# ANTES de medir; cambiarlo cambia la huella.
KRONOS = {
    # Codigo: github.com/shiyu-coder/Kronos (MIT), commit del 13-abr-2026.
    "codigo_commit": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
    "modelo": "NeoQuasar/Kronos-mini",                       # 4,1 M parametros, 16 MB
    "revision_modelo": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
    "tokenizador": "NeoQuasar/Kronos-Tokenizer-2k",          # 16 MB
    "revision_tokenizador": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
    "max_contexto": 2048,
    "tf": "1h",
    "lookback": 128,                                         # 5,3 dias
    # 13 pasos: el primero empieza antes del aviso (la vela de 1 h en curso)
    # y se descarta para no contar como futuro algo que ya habia pasado. Los
    # 12 restantes son las 12 h del plan.
    "pasos": 13,
    "trayectorias": 32,
    "temperatura": 1.0,
    "top_p": 0.9,
    "semilla_base": 20260924,
    "max_invalidas_frac": 0.25,
}

# --- Tarifas (USD por millon de tokens), leidas el 24-sep-2026 de
# https://developers.openai.com/api/docs/pricing. Sin tarifa no se llama.
TARIFAS = {
    "gpt-6-sol": {"entrada": 2.00, "cache": 0.20, "salida": 10.00},
    "gpt-6-luna": {"entrada": 0.10, "cache": 0.01, "salida": 0.50},
}

# --- La salida que se exige al modelo ------------------------------------------------
ACCIONES = ("ENTRAR", "ESPERAR", "RECHAZAR")
CONFIANZAS = ("BAJA", "MEDIA", "ALTA")
CODIGOS = (
    "TENDENCIA_A_FAVOR", "TENDENCIA_EN_CONTRA",
    "MOMENTUM_FUERTE", "MOMENTUM_AGOTADO",
    "VOLUMEN_CONFIRMA", "VOLUMEN_DEBIL",
    "RESISTENCIA_CERCA", "SOPORTE_CERCA",
    "STOP_DENTRO_DEL_RUIDO", "STOP_HOLGADO",
    "META_CERCA", "META_LEJOS",
    "BTC_A_FAVOR", "BTC_EN_CONTRA",
    "KRONOS_A_FAVOR", "KRONOS_EN_CONTRA", "KRONOS_NO_DISPONIBLE",
    "SOBREEXTENDIDO", "REPETICION_DEL_MOVIMIENTO",
    "DATOS_INSUFICIENTES", "OTRO",
)
ESQUEMA_DECISION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["accion", "p_meta", "confianza", "codigos", "razon"],
    "properties": {
        "accion": {"type": "string", "enum": list(ACCIONES)},
        "p_meta": {"type": "number", "minimum": 0, "maximum": 1},
        "confianza": {"type": "string", "enum": list(CONFIANZAS)},
        "codigos": {"type": "array",
                    "items": {"type": "string", "enum": list(CODIGOS)}},
        "razon": {"type": "string"},
    },
}
RAZON_MAX_CHARS = 400

# --- El veredicto ----------------------------------------------------------------------
N_MINIMO = 250
BOOTSTRAP_B = 2000
BOOTSTRAP_SEMILLA = 20260924
COBERTURA_A_TIEMPO_MIN = 0.90
ATRASO_VELA_P95_MAX_DELTA_MS = 2000

CRITERIOS = {
    "ENTORPECE": (
        "cualquiera: el p95 de la edad de la ultima vela de SAC sube mas de "
        "2 s respecto al rodaje; el IC95 del AUC de Sol (bootstrap por par) "
        "queda entero bajo 0,5; o los avisos que Sol acepta rinden menos que "
        "los que rechaza con el IC95 entero bajo 0"
    ),
    "AYUDA": (
        "todas: n >= 250 casos maduros con cobertura >= 0,99 y decision a "
        "tiempo; limite inferior del IC95 del AUC de Sol > 0,5 con bootstrap "
        "por par Y por dia; AUC > 0,5 en las dos mitades temporales; lo que Sol "
        "acepta rinde mas que tomar todos los avisos; Sol responde a tiempo en "
        ">= 90 % de los casos"
    ),
    "INCONCLUSO": (
        "lo demas. Si no estorba y cuesta poco, sigue en sombra hasta el dia "
        "30; si no, se apaga"
    ),
}

# Predicciones registradas por Claude el 24-sep-2026, antes de ningun dato.
# Si el resultado sale mucho mejor, sospechar del metodo antes que celebrar.
PREDICCIONES = {
    "SOL": {"auc": (0.50, 0.56), "p_ayuda": 0.15},
    "KRONOS": {"auc": (0.48, 0.54), "p_pasar": 0.10},
    "veredicto_mas_probable": "INCONCLUSO",
}


def declaracion() -> dict:
    """Todo lo que define el estudio, serializable y ordenado."""
    return {
        "version": ESTUDIO_VERSION,
        "fecha_registro": FECHA_REGISTRO,
        "plazo_decision_ms": PLAZO_DECISION_MS,
        "horizonte_ms": HORIZONTE_MS,
        "rodaje_min_ms": RODAJE_MIN_MS,
        "medicion_ms": MEDICION_MS,
        "objetivo_operador_pct": OBJETIVO_OPERADOR_PCT,
        "coste_pct": COSTE_PCT,
        "cobertura_minima": COBERTURA_MINIMA,
        "brazos_llm": BRAZOS_LLM,
        "brazo_principal": BRAZO_PRINCIPAL,
        "kronos": KRONOS,
        "tarifas": TARIFAS,
        "esquema": ESQUEMA_DECISION,
        "n_minimo": N_MINIMO,
        "bootstrap": [BOOTSTRAP_B, BOOTSTRAP_SEMILLA],
        "cobertura_a_tiempo_min": COBERTURA_A_TIEMPO_MIN,
        "atraso_vela_p95_max_delta_ms": ATRASO_VELA_P95_MAX_DELTA_MS,
        "criterios": CRITERIOS,
        "predicciones": PREDICCIONES,
    }


def prompt_decision() -> str:
    return PROMPT_DECISION.read_text(encoding="utf-8")


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def huella() -> str:
    """Declaracion + prompt. Cambiar cualquiera de los dos cambia la huella."""
    contenido = json.dumps(declaracion(), sort_keys=True, ensure_ascii=False)
    return sha256_texto(contenido + "\n" + prompt_decision())[:16]
