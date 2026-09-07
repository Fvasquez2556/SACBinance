"""
Avisos por Telegram.

Por que hace falta
------------------
El tablero solo sirve mientras alguien lo mira. Una señal que aparece a las
03:00 y se agota a las 05:00 no existe si no hay nada que la empuje al telefono.

Por que no avisa de todo
------------------------
El sistema emite unas 460 señales al dia. Una notificacion que suena 460 veces
se silencia el primer dia, y entonces no avisa de nada. Medido en
research/volumen_avisos.py, el patron validado corta ese ritmo a algo humano:

    todas las señales                        460.7/dia   cobra 38.0%
    patron: viene de caer >=2%                36.1/dia   cobra 42.3%
    patron CONFIRMADO (rebote >=1%)           23.6/dia   cobra 41.2%
    confirmado + score>=75 + vol24h>=2M       14.8/dia   cobra 50.0%   <- este

Unos 15 avisos al dia, uno cada hora y media. El ritmo es un hecho aritmetico;
los porcentajes de acierto todavia no, porque salen de n=20 y hay que
revalidarlos segun se acumulen datos.

Un aviso por señal, no uno por cambio
-------------------------------------
Cuando la señal cambia de estado se EDITA el mensaje ya enviado en vez de
mandar otro. Asi el aviso de las 03:00 se actualiza solo y el historial no se
llena de repeticiones del mismo par.

Nada aqui puede tumbar el engine: todo va envuelto y un fallo de red se
registra y se olvida.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional

import aiohttp

from src.config.settings import get_settings
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

    async def avisar(self, symbol: str, texto: str) -> None:
        """Manda un aviso nuevo y recuerda su id para poder editarlo."""
        r = await self._pedir("sendMessage", {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if r and "message_id" in r:
            self._mensajes[symbol] = r["message_id"]

    async def actualizar(self, symbol: str, texto: str) -> bool:
        """
        Edita el aviso que ya se mando para ese par. Devuelve False si no habia
        ninguno, para que el llamante decida si manda uno nuevo o lo deja.
        """
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

    def olvidar(self, symbol: str) -> None:
        self._mensajes.pop(symbol, None)

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
    return "\n".join(lineas)
