# -*- coding: utf-8 -*-
"""
Averigua el chat_id de Telegram sin pasar por el navegador.

Por que existe
--------------
El camino manual (abrir api.telegram.org/bot<TOKEN>/getUpdates en el navegador)
falla de dos formas facilmente:

  - El navegador cachea la respuesta. Si abres la URL ANTES de escribirle al
    bot, te guarda un `result:[]` y al recargar te sigue enseñando ese, aunque
    ya hayas mandado mensajes.
  - Obliga a tener el token pegado en la barra de direcciones, donde acaba en
    el historial y en cualquier captura de pantalla.

Este script lee el token del .env que ya esta en el servidor, asi que el token
no pasa por ningun sitio nuevo.

Uso
---
    cd ~/sacbinance/backend
    ./venv/bin/python ../deploy/telegram_chatid.py

Se puede ejecutar ANTES de escribirle al bot: si la cola esta vacia se queda
esperando dos minutos con long polling y recoge el mensaje en cuanto llega.
Mirar una sola vez obligaba a acertar el orden y fallaba en silencio cuando
Telegram ya habia entregado esos updates.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def leer_env(ruta: Path) -> dict:
    """Lee un .env sencillo. No usa pydantic para no arrastrar el proyecto."""
    datos = {}
    if not ruta.exists():
        return datos
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        datos[k.strip().upper()] = v.strip().strip('"').strip("'")
    return datos


def pedir(token: str, metodo: str, params: str = "") -> dict:
    url = f"https://api.telegram.org/bot{token}/{metodo}{params}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    raiz = Path(__file__).resolve().parent.parent
    env = leer_env(raiz / "backend" / ".env")
    token = env.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN", "")
    token = token.strip()

    if not token:
        print("No hay TELEGRAM_TOKEN en backend/.env")
        print("Pon primero solo el token (el chat_id lo saca este script):")
        print("    TELEGRAM_TOKEN=el_token_de_botfather")
        return 1

    # Nunca imprimir el token entero
    print(f"token leido del .env (...{token[-6:]})")

    try:
        yo = pedir(token, "getMe")
    except Exception as e:
        print(f"No se pudo hablar con Telegram: {e}")
        return 1
    if not yo.get("ok"):
        print(f"Token rechazado: {yo.get('description')}")
        print("Si lo revocaste en @BotFather, pon el nuevo en el .env.")
        return 1
    bot = yo["result"]
    print(f"bot: @{bot.get('username')} ({bot.get('first_name')})")

    # Un webhook activo deja getUpdates siempre vacio, y es un fallo que no
    # da ningun error: conviene descartarlo antes de culpar a otra cosa.
    try:
        wh = pedir(token, "getWebhookInfo")
        if wh.get("ok") and wh["result"].get("url"):
            print(f"\nOJO: hay un webhook puesto ({wh['result']['url']}).")
            print("Mientras exista, getUpdates devuelve vacio siempre. Quitalo:")
            print(f"    https://api.telegram.org/bot<TOKEN>/deleteWebhook")
            return 1
    except Exception:
        pass

    def recoger(params: str) -> dict:
        """Saca los chats de una respuesta de getUpdates."""
        r = pedir(token, "getUpdates", params)
        if not r.get("ok"):
            print(f"getUpdates fallo: {r.get('description')}")
            return {}
        out = {}
        for u in r.get("result", []):
            msg = (u.get("message") or u.get("edited_message")
                   or u.get("channel_post") or {})
            ch = msg.get("chat") or {}
            if ch.get("id") is not None:
                out[ch["id"]] = ch
        return out

    chats = recoger("?offset=0&timeout=0")

    # Si la cola esta vacia, ESPERAR en vez de rendirse. Mirar una sola vez
    # obliga a acertar el orden (escribir al bot y luego ejecutar) y falla en
    # silencio cuando Telegram ya entrego esos updates: un update recogido no
    # se vuelve a entregar, asi que el segundo intento sale vacio aunque el
    # mensaje se enviara de verdad.
    if not chats:
        restante = 120
        print(f"\nLa cola esta vacia. Esperando {restante}s.")
        print(f"AHORA: abre Telegram y mandale cualquier cosa a "
              f"@{bot.get('username')}")
        print("(con escribir 'hola' y enviar basta)\n")
        while restante > 0 and not chats:
            trozo = min(30, restante)
            try:
                chats = recoger(f"?offset=-1&timeout={trozo}")
            except Exception as e:
                print(f"  reintentando ({type(e).__name__})")
            restante -= trozo
            if not chats and restante > 0:
                print(f"  esperando... quedan {restante}s")

    if not chats:
        print("\nSigue sin llegar nada. Las dos causas reales suelen ser:")
        print(f"  1. El chat que tienes abierto no es @{bot.get('username')}.")
        print("     Comprueba el nombre exacto tocando el titulo del chat.")
        print("  2. El token del .env es de otro bot distinto al que escribes.")
        print("\nAtajo que no falla: escribe a @userinfobot en Telegram. Te")
        print("responde con tu id, y en un chat privado ese id ES el chat_id.")
        return 2

    print("\nchat_id encontrado:")
    for cid, ch in chats.items():
        quien = ch.get("first_name") or ch.get("title") or ch.get("username") or ""
        print(f"    {cid}    ({ch.get('type')}  {quien})")

    if len(chats) == 1:
        cid = next(iter(chats))
        print("\nAñade esto al final de backend/.env:")
        print("    TELEGRAM_ENABLED=true")
        print(f"    TELEGRAM_CHAT_ID={cid}")
        print("\nY reinicia:  sudo systemctl restart sacbinance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
