"""\nAvisos por Telegram.\n\nPor que hace falta\n------------------\nEl tablero solo sirve mientras alguien lo mira. Una señal que aparece a las\n03:00 y se agota a las 05:00 no existe si no hay nada que la empuje al telefono.\n\nPor que no avisa de todo\n------------------------\nEl sistema emite unas 460 señales al dia. Una notificacion que suena 460 veces\nse silencia el primer dia, y entonces no avisa de nada. Medido en\nresearch/volumen_avisos.py, el patron validado corta ese ritmo a algo humano:\n\ntodas las señales                        460.7/dia   cobra 38.0%\npatron: viene de caer >=2%                36.1/dia   cobra 42.3%\npatron CONFIRMADO (rebote >=1%)           23.6/dia   cobra 41.2%\nconfirmado + score>=75 + vol24h>=2M       14.8/dia   cobra 50.0%   <- este\n\nUnos 15 avisos al dia, uno cada hora y media. El ritmo es un hecho aritmetico;\nlos porcentajes de acierto todavia no, porque salen de n=20 y hay que\nrevalidarlos segun se acumulen datos.\n\nUn aviso por señal, no uno por cambio\n-------------------------------------\nCuando la señal cambia de estado se EDITA el mensaje ya enviado en vez de\nmandar otro. Asi el aviso de las 03:00 se actualiza solo y el historial no se\nllena de repeticiones del mismo par.\n\nNada aqui puede tumbar el engine: todo va envuelto y un fallo de red se\nregistra y se olvida.\n"""
from __future__ import annotations

import asyncio
import datetime as dt
import html
import json
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

    async def avisar_ruptura(self, texto: str) -> Optional[int]:
        """Envia una ruptura sin reemplazar el hilo de una alerta TP/SL."""
        r = await self._pedir("sendMessage", {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if r and "message_id" in r:
            return int(r["message_id"])
        return None

    async def responder_a(self, message_id: int, texto: str) -> bool:
        """Cuelga un seguimiento de un mensaje de ruptura concreto."""
        r = await self._pedir("sendMessage", {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_to_message_id": int(message_id),
            "allow_sending_without_reply": True,
        })
        return r is not None

    async def actualizar(self, symbol: str, texto: str) -> bool:
        """\nEdita el aviso que ya se mando para ese par. Devuelve False si no habia\nninguno, para que el llamante decida si manda uno nuevo o lo deja.\n"""
        mid = self._mensajes.get(symbol)
        if mid is None:
            return False
        return await self.actualizar_mensaje(mid, texto)

    async def actualizar_mensaje(self, message_id: int, texto: str) -> bool:
        """Actualiza el mismo mensaje; no crea un aviso periodico nuevo."""
        r = await self._pedir("editMessageText", {
            "chat_id": self.chat_id,
            "message_id": int(message_id),
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        return r is not None

    def mensaje_id(self, symbol: str) -> Optional[int]:
        return self._mensajes.get(symbol)

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


def texto_ruptura(symbol: str, ruptura: dict) -> str:
    """Aviso inicial de una ruptura que queda abierta a seguimiento de 24 h."""
    par = symbol.replace("USDT", "")
    alcista = ruptura.get("direction") == "RUPTURA_ALCISTA"
    icono = "📈" if alcista else "📉"
    titulo = "RUPTURA ALCISTA CORTA" if alcista else "RUPTURA BAJISTA CORTA"
    lineas = [
        f"{icono} <b>{par}</b>  ·  {titulo}",
        "",
        f"precio de ruptura <code>{ruptura.get('price_open')}</code>",
        f"criterio: {ruptura.get('reason', 'sin detalle')}",
    ]
    score = ruptura.get("score")
    rango = ruptura.get("rango_1h_pct")
    if score is not None or rango is not None:
        lineas.append(f"score {_fmt(score, 0)}  ·  rango 1h {_fmt(rango, 2, '%')}")
    lineas += [
        "",
        "Seguimiento: 15 min, 1 h, 4 h y 24 h.",
        _enlace(symbol),
    ]
    return "\n".join(lineas)


def texto_seguimiento_ruptura(symbol: str, ruptura: dict, minutos: int) -> str:
    """Resumen de una ruptura con retorno normalizado a su direccion."""
    par = symbol.replace("USDT", "")
    alcista = ruptura.get("direction") == "RUPTURA_ALCISTA"
    icono = "📈" if alcista else "📉"
    titulo = "alcista" if alcista else "bajista"
    retorno = ruptura.get(f"ret_{minutos}m_pct")
    lineas = [
        f"{icono} <b>{par}</b>  ·  seguimiento {titulo} a {minutos} min",
        "",
        f"precio inicial <code>{ruptura.get('price_open')}</code>   "
        f"ahora <code>{ruptura.get('last_price')}</code>",
        f"retorno a favor {_fmt(retorno, 2, '%')}",
        f"máx. a favor {_fmt(ruptura.get('mfe_direction_pct'), 2, '%')}   "
        f"máx. en contra {_fmt(ruptura.get('mae_direction_pct'), 2, '%')}",
        f"subida máxima {_fmt(ruptura.get('max_up_pct'), 2, '%')}   "
        f"bajada máxima {_fmt(ruptura.get('max_down_pct'), 2, '%')}",
        "",
        _enlace(symbol),
    ]
    return "\n".join(lineas)


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


def texto_meta(symbol: str, alerta: dict) -> str:
    """La meta fija de +3.2% se alcanzo, aunque el TP fuera distinto."""
    par = symbol.replace("USDT", "")
    return "\n".join([
        f"✅ <b>{par}</b>  ·  META +3.2% ALCANZADA",
        "",
        f"entrada <code>{alerta.get('entry')}</code>   "
        f"ahora <code>{alerta.get('precio_actual')}</code>",
        f"maximo {_fmt(alerta.get('mfe_pct'), 2, '%')}   "
        f"minimo {_fmt(alerta.get('mae_pct'), 2, '%')}",
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


def _linea_identidad(ctx: dict, alerta_id) -> str:
    """
    Quien es este plan, en palabras.

    Antes decia «Plan #4871»: un identificador de base de datos que no dice si
    es la primera oportunidad de un movimiento o la quinta repeticion del
    mismo. La fase 1 guarda episodio y ordinal desde hace dias; solo faltaba
    sacarlos al mensaje.
    """
    partes = [f"Plan #{alerta_id}"]
    ep = ctx.get('episode_id')
    if ep:
        ordinal = ctx.get('ordinal_episodio')
        if ordinal == 1:
            partes.append(f"episodio {ep} · <b>primera oportunidad</b>")
        elif ordinal:
            partes.append(f"episodio {ep} · oportunidad n.º {ordinal}")
        else:
            partes.append(f"episodio {ep}")
    tf = ctx.get('trigger_tf')
    if tf:
        partes.append(f"disparado en {html.escape(str(tf))}")
    return ' · '.join(partes)


def _linea_alcance(ctx: dict) -> str:
    """
    ¿Esto afecta a algo que ya tomaste, o solo describe otra oportunidad?

    Es la distincion que el plan de la fase 6 pide explicitamente. Un aviso de
    seguimiento sobre un plan que no tomaste no exige nada de ti; uno sobre el
    que si tomaste, si. Sin decirlo, todos los mensajes piden la misma
    atencion y acaban sin pedir ninguna.
    """
    if ctx.get('operacion_abierta'):
        return ("⚠️ <b>Afecta a tu operación abierta</b> en este par.")
    return ("Solo describe una oportunidad: no tienes ninguna operación "
            "registrada en este par.")


def texto_plan_notificado(plan: dict, titulo: str = "PLAN EN SEGUIMIENTO") -> str:
    """Frozen plan, without mixing historical excursions with win probabilities."""
    ctx = plan.get('contexto') or {}
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    entry, tp, sl = plan['entry'], plan['take_profit'], plan['stop_loss']
    current = plan.get('last_price') or entry
    gross = (tp / entry - 1) * 100
    cost = ctx.get('coste_pct')
    stamp = dt.datetime.fromtimestamp(plan['ts_open']/1000,dt.timezone.utc).strftime('%d/%m %H:%M UTC')
    lines = [f"<b>{html.escape(plan['symbol'])} · {titulo}</b>",
             f"{_linea_identidad(ctx, plan['alerta_id'])} · detectado {stamp}",
             "Señal de 1m · niveles de 1h · volatilidad de 15m",
             "",f"entrada <code>{entry}</code>",
             f"TP <code>{tp}</code> ({gross:+.2f}% bruto)",
             f"SL <code>{sl}</code> ({(sl/entry-1)*100:+.2f}%)",
             f"ahora <code>{current}</code> ({(current/entry-1)*100:+.2f}%)"]
    if cost is not None:
        lines.append(f"TP tras coste supuesto {cost:.2f}%: {gross-cost:+.2f}%")
    lines += _lineas_niveles(ctx, entry, tp)
    trends = ctx.get('macro_trends') or {}
    if trends:
        lines.append('Contexto al detectar: ' + ' · '.join(
            f"{tf} {html.escape(str(trends.get(tf,'sin datos')))}" for tf in ('15m','1h','4h')))
    lines += [_linea_alcance(ctx),
              f"Estado del plan: {html.escape(plan.get('estado','ABIERTO'))}",
              f"Máx. favorable {_fmt(plan.get('mfe'),2,'%')} · adverso {_fmt(plan.get('mae'),2,'%')}",
              "Seguimiento simulado. Los cambios menores actualizan este mensaje.",
              _enlace(plan['symbol'])]
    return '\n'.join(lines)


def _lineas_niveles(ctx: dict, entry: float, tp: float) -> list:
    """
    Sobre que se apoya el stop, y que hay que romper antes del TP.

    Son los dos numeros que el mensaje daba por sabidos. El soporte explica de
    donde sale el stop —no es un porcentaje redondo, es un nivel con toques— y
    la resistencia dice si el precio tiene algo por delante antes del objetivo.
    """
    lineas = []
    soporte = ctx.get('soporte')
    if soporte:
        toques = ctx.get('toques_soporte')
        marca = f" · {toques} toques" if toques else ""
        base = ctx.get('sl_basis') or ''
        lineas.append(f"soporte que sostiene el SL <code>{soporte}</code>"
                      f" ({(soporte/entry-1)*100:+.2f}%){marca}"
                      + (f" · {html.escape(base)}" if base else ""))
    resistencia = ctx.get('resistencia')
    if resistencia:
        toques = ctx.get('toques_resistencia')
        marca = f" · {toques} toques" if toques else ""
        if ctx.get('tp_bloqueado'):
            lineas.append(f"techo que debe romper <code>{resistencia}</code>"
                          f" ({(resistencia/entry-1)*100:+.2f}%){marca} — esta entre la "
                          f"entrada y el TP")
        elif resistencia > tp:
            lineas.append(f"techo mas cercano <code>{resistencia}</code>"
                          f" ({(resistencia/entry-1)*100:+.2f}%){marca} — por encima del TP")
    return lineas


def texto_evento_plan(event: dict) -> str:
    plan = json.loads(event['snapshot'])
    kind = event['tipo']
    titles = {'SL':'STOP DEL PLAN ALCANZADO','TP':'TP DEL PLAN ALCANZADO',
              'TP_META':'TP Y +3.2% BRUTO ALCANZADOS','META':'+3.2% BRUTO ALCANZADO',
              'CERCA_SL':'PRECIO CERCA DEL STOP','VENCIDO':'PLAN VENCIDO'}
    text = texto_plan_notificado(plan,titles[kind])
    stamp = dt.datetime.fromtimestamp(event['ts_ms']/1000,dt.timezone.utc).strftime('%d/%m %H:%M UTC')
    text += f"\nEvento observado: {stamp}"
    if kind=='META':
        text += '\nEl TP del plan sigue pendiente. Este hito no descuenta costes.'
    if kind=='SL':
        text += '\nEste plan deja de generar avisos de ganancia; el recorrido posterior queda en la UI.'
    if plan.get('ambiguous'):
        text += '\nSL y meta/TP aparecen en la misma vela: orden desconocido; no se contabiliza como éxito.'
    return text
