"""\nAvisos por Telegram.\n\nPor que hace falta\n------------------\nEl tablero solo sirve mientras alguien lo mira. Una señal que aparece a las\n03:00 y se agota a las 05:00 no existe si no hay nada que la empuje al telefono.\n\nPor que no avisa de todo\n------------------------\nEl sistema emite unas 460 señales al dia. Una notificacion que suena 460 veces\nse silencia el primer dia, y entonces no avisa de nada. Medido en\nresearch/volumen_avisos.py, el patron validado corta ese ritmo a algo humano:\n\ntodas las señales                        460.7/dia   cobra 38.0%\npatron: viene de caer >=2%                36.1/dia   cobra 42.3%\npatron CONFIRMADO (rebote >=1%)           23.6/dia   cobra 41.2%\nconfirmado + score>=75 + vol24h>=2M       14.8/dia   cobra 50.0%   <- este\n\nUnos 15 avisos al dia, uno cada hora y media. El ritmo es un hecho aritmetico;\nlos porcentajes de acierto todavia no, porque salen de n=20 y hay que\nrevalidarlos segun se acumulen datos.\n\nUn aviso por señal, no uno por cambio\n-------------------------------------\nCuando la señal cambia de estado se EDITA el mensaje ya enviado en vez de\nmandar otro. Asi el aviso de las 03:00 se actualiza solo y el historial no se\nllena de repeticiones del mismo par.\n\nNada aqui puede tumbar el engine: todo va envuelto y un fallo de red se\nregistra y se olvida.\n"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional

import aiohttp

from src.config.settings import get_settings
from src.persistence.db import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)

_API = "https://api.telegram.org/bot{token}/{metodo}"

# Telegram tumba la conexion si se le manda demasiado seguido. Con ~15 avisos
# al dia no se roza el limite, pero un fallo que dispare un bucle si.
_MIN_ENTRE_ENVIOS_S = 1.0

_ICONO = {
    "VIVA": "🟢",
    "PERDIENDO_FUERZA": "🟠",
    "EN_RETROCESO": "🔻",
    "EN_VALLE": "⏸",
    "RECUPERANDO": "🔄",
    "CUMPLIDA": "✅",
}


def _fmt(x, dec: int = 2, suf: str = "") -> str:
    return "—" if x is None else f"{x:.{dec}f}{suf}"


class Telegram:
    """Cliente minimo. Se instancia una vez y vive con el engine."""

    def __init__(self) -> None:
        s = get_settings()
        self.token = (s.telegram_token or "").strip()
        self.chat_id = (s.telegram_chat_id or "").strip()
        self.activo = bool(s.telegram_enabled and self.token and self.chat_id)
        self._sesion: Optional[aiohttp.ClientSession] = None
        self._mensajes: Dict[str, int] = {}      # symbol -> message_id
        self._ultimo_envio = 0.0
        self._lock = asyncio.Lock()
        if s.telegram_enabled and not self.activo:
            logger.warning(
                "Telegram activado pero falta telegram_token o telegram_chat_id "
                "en el .env — no se enviaran avisos"
            )
        elif self.activo:
            logger.info("Avisos por Telegram activados")

    async def cerrar(self) -> None:
        if self._sesion and not self._sesion.closed:
            await self._sesion.close()

    async def _pedir(self, metodo: str, payload: dict) -> Optional[dict]:
        if not self.activo:
            return None
        try:
            if self._sesion is None or self._sesion.closed:
                self._sesion = aiohttp.ClientSession()
            async with self._lock:
                espera = _MIN_ENTRE_ENVIOS_S - (time.monotonic() - self._ultimo_envio)
                if espera > 0:
                    await asyncio.sleep(espera)
                self._ultimo_envio = time.monotonic()
            url = _API.format(token=self.token, metodo=metodo)
            async with self._sesion.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
                if not data.get("ok"):
                    logger.warning(f"Telegram {metodo} rechazado: "
                                   f"{data.get('description')}")
                    return None
                return data.get("result")
        except Exception as e:
            # Un aviso perdido no puede parar el analisis
            logger.warning(f"Telegram {metodo} fallo: {type(e).__name__}: {e}")
            return None

    async def probar(self) -> bool:
        """Comprueba credenciales al arrancar. No manda nada al chat."""
        r = await self._pedir("getMe", {})
        if r:
            logger.info(f"Telegram conectado como @{r.get('username')}")
            return True
        return False

    # --- Envio de avisos --------------------------------------------------

    async def avisar(self, symbol: str, texto: str) -> bool:
        """
        Manda un aviso nuevo y recuerda su id para poder editarlo.

        Devuelve si el mensaje llego de verdad. Antes no devolvia nada:
        `_pedir` se traga el rechazo de la API y el fallo de red y devuelve
        None, asi que el llamante marcaba "enviado" sin que hubiera salido
        nada — solo una excepcion, que aqui no se produce nunca, lo habria
        delatado. Lo que se registra en `alertas_emitidas` tiene que ser el
        resultado, no la intencion.
        """
        r = await self._pedir("sendMessage", {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if r and "message_id" in r:
            self._mensajes[symbol] = r["message_id"]
            self._recordar(symbol, r["message_id"])
            return True
        return False

    async def actualizar(self, symbol: str, texto: str) -> bool:
        """\nEdita el aviso que ya se mando para ese par. Devuelve False si no habia\nninguno, para que el llamante decida si manda uno nuevo o lo deja.\n"""
        mid = self._mensajes.get(symbol)
        if mid is None:
            return False
        r = await self._pedir("editMessageText", {
            "chat_id": self.chat_id,
            "message_id": mid,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        return r is not None

    async def responder(self, symbol: str, texto: str) -> bool:
        """
        Cuelga un mensaje del aviso original de ese par.

        Los avisos de seguimiento — las bajadas, el stop, el TP y los hitos —
        tienen que SONAR, y una edicion no hace sonar el telefono. Por eso van
        como mensaje nuevo, pero con `reply_to_message_id` para que Telegram
        los agrupe bajo la alerta a la que pertenecen: el hilo del par cuenta
        la historia entera sin llenar el chat de mensajes sueltos.

        `allow_sending_without_reply` evita el fallo silencioso mas probable:
        si el mensaje original se borro, Telegram rechazaria la respuesta y el
        aviso se perderia. Perder el hilo es peor que perder el hilo Y el
        aviso, asi que en ese caso sale suelto.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        mid = self._mensajes.get(symbol)
        if mid is not None:
            r = await self._pedir("sendMessage", dict(
                payload,
                reply_to_message_id=mid,
                allow_sending_without_reply=True,
            ))
            if r is not None:
                return True
        return await self._pedir("sendMessage", payload) is not None

    def olvidar(self, symbol: str) -> None:
        self._mensajes.pop(symbol, None)
        try:
            get_db().borrar_hilo_telegram(symbol)
        except Exception as e:
            logger.debug(f"[{symbol}] borrar hilo: {e}")

    # --- Persistencia del hilo -------------------------------------------
    #
    # Sin esto, cada reinicio dejaba mudas a todas las alertas ya anunciadas:
    # seguian vivas en el tablero, pero como su message_id vivia solo en
    # memoria, `tiene_mensaje` devolvia False y los avisos de bajada, stop, TP
    # e hito se descartaban en silencio. Una alerta de las 03:00 se quedaba sin
    # seguimiento por un reinicio a las 04:00.
    #
    # Ninguno de los dos metodos puede tumbar un envio: si la base falla, se
    # pierde la continuidad del hilo, no el aviso.

    def _recordar(self, symbol: str, message_id: int) -> None:
        try:
            get_db().guardar_hilo_telegram(
                symbol, message_id, int(time.time() * 1000))
        except Exception as e:
            logger.debug(f"[{symbol}] guardar hilo: {e}")

    def cargar_hilos(self) -> int:
        """
        Recupera los hilos vigentes tras un reinicio. Se llama desde main.

        Solo valen los de las ultimas `seguimiento_horas` — pasada la ventana
        la alerta ya se archivo y responder a su mensaje no tendria sentido.
        """
        if not self.activo:
            return 0
        horas = get_settings().seguimiento_horas + 1   # margen de una hora
        desde = int(time.time() * 1000) - horas * 3600_000
        try:
            self._mensajes = get_db().get_hilos_telegram(desde)
        except Exception as e:
            logger.warning(f"No se pudieron recuperar los hilos de Telegram: {e}")
            return 0
        if self._mensajes:
            logger.info(
                f"Hilos de Telegram recuperados: {len(self._mensajes)} pares "
                f"siguen recibiendo avisos de seguimiento"
            )
        return len(self._mensajes)

    def tiene_mensaje(self, symbol: str) -> bool:
        return symbol in self._mensajes


# --- Redaccion de los mensajes --------------------------------------------

def texto_alerta(symbol: str, alerta: dict, retroceso: dict,
                 sr: Optional[dict] = None) -> str:
    par = symbol.replace("USDT", "")
    est = alerta.get("estado", "")
    ico = _ICONO.get(est, "•")
    lineas = [
        f"{ico} <b>{par}</b>  ·  {est.replace('_', ' ')}",
        "",
        f"entrada <code>{alerta.get('entry')}</code>",
    ]
    tp, sl = alerta.get("tp_pct"), alerta.get("sl_pct")
    if tp is not None or sl is not None:
        lineas.append(f"TP {_fmt(tp, 2, '%')}   SL {_fmt(sl, 2, '%')}")

    alt = alerta.get("entrada_alt")
    if alt:
        lineas.append(f"esperando -{alerta.get('retroceso_pct')}%: "
                      f"<code>{alt}</code>")

    d = alerta.get("dist_meta_pct")
    if d is not None:
        p = alerta.get("prob_meta", 0)
        n = alerta.get("prob_meta_n", 0)
        meta = "meta hecha" if d <= 0 else f"faltan {d:.2f}% para +3.2%"
        lineas.append(f"{meta}  ·  <b>{p:.0f}%</b> medido (n={n})")

    delta = alerta.get("delta_pct")
    if delta is not None:
        lineas.append(f"ahora {alerta.get('precio_actual')}  ({delta:+.2f}%)")

    if retroceso and retroceso.get("detectado"):
        marca = "rebote confirmado" if retroceso.get("confirmado") else "sin confirmar"
        lineas += ["", f"▼ cayo {_fmt(retroceso.get('caida_pct'), 2, '%')} · "
                       f"rebotado {_fmt(retroceso.get('rebote_pct'), 2, '%')} "
                       f"({marca})"]

    if sr and sr.get("lectura"):
        lineas.append(f"⌐ {sr['lectura']}")

    marcas = alerta.get("marcadores") or []
    if marcas:
        pintas = {"MORADO": "🟣", "VERDE": "🟢", "AMARILLO": "🟡", "ROJO": "🔴"}
        lineas.append("".join(pintas.get(m, "") for m in marcas)
                      + f"  MFE {_fmt(alerta.get('mfe_pct'), 2, '%')} · "
                        f"MAE {_fmt(alerta.get('mae_pct'), 2, '%')}")

    tier = alerta.get("tier_emision")
    if tier and tier != "NINGUNO":
        lineas.append(f"<i>{tier} · score {alerta.get('score_emision')}</i>")
    lineas.append("")
    lineas.append(_enlace(symbol))
    return "\n".join(lineas)


def _enlace(symbol: str) -> str:
    """Enlace al grafico del par en Binance, para comprobarlo de un toque."""
    par = symbol.replace("USDT", "")
    return (f'<a href="https://www.binance.com/es/trade/{par}_USDT?type=spot">'
            f"ver {par} en Binance</a>")


def texto_bajada(symbol: str, alerta: dict, nivel: float) -> str:
    """\nAviso de que una alerta viva se esta dando la vuelta.\n\nImporta porque de 1391 senales cerradas, 217 subieron >=2.2% y despues\ncayeron al SL. Saber que una señal se tuerce vale tanto como saber que\nnacio, y el tablero solo lo enseña si alguien lo esta mirando.\n"""
    par = symbol.replace("USDT", "")
    lineas = [
        f"🔻 <b>{par}</b>  ·  baja {nivel}% desde la entrada",
        "",
        f"entrada <code>{alerta.get('entry')}</code>   "
        f"ahora <code>{alerta.get('precio_actual')}</code>",
        f"delta {_fmt(alerta.get('delta_pct'), 2, '%')}   "
        f"minimo {_fmt(alerta.get('mae_pct'), 2, '%')}",
    ]
    sl = alerta.get("stop_loss")
    if sl:
        lineas.append(f"SL del sistema <code>{sl}</code> "
                      f"({_fmt(alerta.get('sl_pct'), 2, '%')})")
    d = alerta.get("dist_meta_pct")
    if d is not None and d > 0:
        lineas.append(f"faltan {d:.2f}% para +3.2%  ·  "
                      f"{alerta.get('prob_meta', 0):.0f}% medido")
    lineas += ["", "Comprueba el grafico antes de decidir.", _enlace(symbol)]
    return "\n".join(lineas)


def texto_hito(symbol: str, alerta: dict, hito: str) -> str:
    """\nLa senal alcanza un hito hacia arriba.\n\nLLEGO   toco +3.2% sobre SU entry: la meta de referencia de Felix.\nSUPERO  paso +4.2% sobre el entry de la PRIMERA señal del episodio. Se\nmide desde ahi a proposito: subir 4.2% desde una entrada tardia\npuede dejarte todavia por debajo del precio de la primera.\n"""
    par = symbol.replace("USDT", "")
    if hito == "SUPERO":
        cab = f"🟣 <b>{par}</b>  ·  SUPERO +4.2%"
        base = alerta.get("entry_primera")
        det = (f"desde la 1a señal <code>{base}</code>  "
               f"({alerta.get('delta_primera_pct', 0):+.2f}%)" if base else "")
    else:
        cab = f"🟢 <b>{par}</b>  ·  LLEGO A +3.2%"
        det = ""
    lineas = [
        cab, "",
        f"entrada <code>{alerta.get('entry')}</code>   "
        f"ahora <code>{alerta.get('precio_actual')}</code>",
        f"maximo {_fmt(alerta.get('mfe_pct'), 2, '%')}   "
        f"minimo {_fmt(alerta.get('mae_pct'), 2, '%')}",
    ]
    if det:
        lineas.append(det)
    n = alerta.get("senal_n")
    if n:
        lineas.append(f"<i>señal nº{n} de este par</i>")
    lineas += ["", _enlace(symbol)]
    return "\n".join(lineas)


def texto_tp(symbol: str, alerta: dict) -> str:
    """El TP que fijo el sistema se ha tocado."""
    par = symbol.replace("USDT", "")
    tp = alerta.get("tp_pct")
    aviso = ""
    if tp is not None and tp < 3.2:
        # El sistema cumplio su promesa y aun asi te quedas corto: pasa en el
        # 71.1% de las que tocan su TP.
        aviso = (f"\nOJO: su TP era {tp:+.2f}%, por debajo de tu objetivo "
                 f"de +3.2%.")
    return "\n".join([
        f"✅ <b>{par}</b>  ·  TOCO SU TP",
        "",
        f"entrada <code>{alerta.get('entry')}</code>   "
        f"TP <code>{alerta.get('take_profit')}</code> "
        f"({_fmt(tp, 2, '%')})",
        f"maximo {_fmt(alerta.get('mfe_pct'), 2, '%')}   "
        f"minimo {_fmt(alerta.get('mae_pct'), 2, '%')}" + aviso,
        "",
        _enlace(symbol),
    ])


def texto_stop(symbol: str, alerta: dict) -> str:
    """El SL que fijo el sistema se ha tocado."""
    par = symbol.replace("USDT", "")
    return "\n".join([
        f"🔴 <b>{par}</b>  ·  TOCO EL SL",
        "",
        f"entrada <code>{alerta.get('entry')}</code>   "
        f"SL <code>{alerta.get('stop_loss')}</code> "
        f"({_fmt(alerta.get('sl_pct'), 2, '%')})",
        f"minimo {_fmt(alerta.get('mae_pct'), 2, '%')}   "
        f"maximo {_fmt(alerta.get('mfe_pct'), 2, '%')}",
        "",
        "Sigue en seguimiento: de las que tocaron el SL, el 37% llego",
        "despues a +3.2%. Tocar el stop no cierra la historia.",
        _enlace(symbol),
    ])
