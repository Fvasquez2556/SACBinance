# -*- coding: utf-8 -*-
"""
Comprueba que los avisos de Telegram pueden salir de verdad.

Por que existe este fichero
---------------------------
El 9-sep se descubrio que los avisos de seguimiento — bajadas, stop, TP y
hitos — llevaban desde su despliegue sin enviarse ni una sola vez. El motor
llamaba a `Telegram.responder(...)`, ese metodo nunca se habia escrito, y el
`except Exception` que envuelve cada envio convertia el AttributeError en un
WARNING entre miles de lineas de log. Doce de quince pares avisados cruzaron
un escalon de bajada ese dia y el telefono no sono ninguna vez.

Un envio de aviso NO puede tumbar el analisis, asi que el `except` ancho se
queda. Lo que hace falta es comprobar antes de arrancar que los metodos que el
motor invoca existen de verdad.

Se ejecuta solo:  python comprobar_avisos.py
Devuelve 0 si todo esta bien, 1 si falta algo.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import sys

RAIZ = pathlib.Path(__file__).parent
sys.path.insert(0, str(RAIZ))


def metodos_invocados(fichero: pathlib.Path, atributo: str) -> set:
    """Todos los `self.<atributo>.<algo>(...)` que aparecen en un fichero."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    encontrados = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        if not isinstance(f, ast.Attribute):
            continue
        duenio = f.value
        if (isinstance(duenio, ast.Attribute)
                and duenio.attr == atributo
                and isinstance(duenio.value, ast.Name)
                and duenio.value.id == "self"):
            encontrados.add(f.attr)
    return encontrados


def main() -> int:
    from src.notify.telegram import Telegram

    fallos = []

    # --- 1. Los metodos que el motor le pide a Telegram existen ---
    engine = RAIZ / "src" / "state" / "engine.py"
    pedidos = metodos_invocados(engine, "_tg")
    disponibles = {m for m in dir(Telegram) if not m.startswith("__")}
    faltan = sorted(pedidos - disponibles)
    print(f"metodos de Telegram que usa el motor: {sorted(pedidos)}")
    if faltan:
        fallos.append(f"el motor llama a metodos que NO existen: {faltan}")
    else:
        print("  todos existen")

    # --- 2. Los que envian algo son corrutinas, y se esperan con await ---
    for nombre in sorted(pedidos & disponibles):
        m = getattr(Telegram, nombre)
        if nombre in ("olvidar", "tiene_mensaje"):
            if inspect.iscoroutinefunction(m):
                fallos.append(f"{nombre} no deberia ser async")
        elif not inspect.iscoroutinefunction(m):
            fallos.append(f"{nombre} deberia ser async (se llama con await)")

    # --- 3. Los redactores de texto devuelven algo imprimible ---
    from src.notify.telegram import (texto_alerta, texto_bajada, texto_hito,
                                     texto_stop, texto_tp)
    alerta = {
        "symbol": "PRUEBAUSDT", "entry": 100.0, "meta": 103.2,
        "take_profit": 103.2, "stop_loss": 97.0, "precio_actual": 99.0,
        "delta_pct": -1.0, "mfe_pct": 0.5, "mae_pct": -1.0, "score": 86,
        "tier": "FUERTE", "estado": "VIVA", "senal_n": 2,
        "entry_primera": 98.0, "dist_meta_pct": 4.2, "prob_meta": 0.21,
        "display_state": "SUBIENDO", "sl_pct": -3.0, "tp_pct": 3.2,
    }
    pruebas = [
        ("texto_alerta", lambda: texto_alerta("PRUEBAUSDT", alerta, {}, {})),
        ("texto_bajada", lambda: texto_bajada("PRUEBAUSDT", alerta, 0.9)),
        ("texto_stop", lambda: texto_stop("PRUEBAUSDT", alerta)),
        ("texto_tp", lambda: texto_tp("PRUEBAUSDT", alerta)),
        ("texto_hito LLEGO", lambda: texto_hito("PRUEBAUSDT", alerta, "LLEGO")),
        ("texto_hito SUPERO", lambda: texto_hito("PRUEBAUSDT", alerta, "SUPERO")),
    ]
    print()
    for nombre, fn in pruebas:
        try:
            t = fn()
        except Exception as e:
            fallos.append(f"{nombre} lanza {type(e).__name__}: {e}")
            print(f"  {nombre:<20} FALLA — {type(e).__name__}: {e}")
            continue
        if not isinstance(t, str) or not t.strip():
            fallos.append(f"{nombre} no devuelve texto")
            print(f"  {nombre:<20} devuelve {t!r}")
        else:
            print(f"  {nombre:<20} ok ({len(t)} caracteres)")

    # --- 4. El hilo sobrevive a un reinicio ---
    # Se prueba contra una copia de la base, nunca contra la real.
    import shutil, tempfile, os, time as _t
    from src.config.settings import get_settings
    print()
    origen = get_settings().db_path
    tmp = pathlib.Path(tempfile.mkdtemp()) / "copia.db"
    try:
        if pathlib.Path(origen).exists():
            for suf in ("", "-wal", "-shm"):
                if os.path.exists(origen + suf):
                    shutil.copy(origen + suf, str(tmp) + suf)
        import src.persistence.db as dbmod
        get_settings().db_path = str(tmp)
        dbmod._db = None
        db = dbmod.get_db()
        ahora = int(_t.time() * 1000)
        db.guardar_hilo_telegram("PRUEBAUSDT", 424242, ahora)
        db.guardar_hilo_telegram("CADUCADAUSDT", 1, ahora - 72 * 3600_000)
        vivos = db.get_hilos_telegram(ahora - 25 * 3600_000)
        if vivos.get("PRUEBAUSDT") != 424242:
            fallos.append("el hilo no se recupera tras guardarlo")
            print("  hilo guardado -> NO se recupera")
        elif "CADUCADAUSDT" in vivos:
            fallos.append("los hilos caducados no se limpian")
            print("  hilo caducado -> NO se limpia")
        else:
            print(f"  hilo guardado y recuperado ok, caducados limpiados "
                  f"({len(vivos)} vigentes)")
        db.borrar_hilo_telegram("PRUEBAUSDT")
        if "PRUEBAUSDT" in db.get_hilos_telegram(0):
            fallos.append("borrar_hilo_telegram no borra")
    except Exception as e:
        fallos.append(f"la prueba del hilo persistido lanza {type(e).__name__}: {e}")
        print(f"  prueba del hilo FALLA — {type(e).__name__}: {e}")
    finally:
        get_settings().db_path = origen
        import src.persistence.db as dbmod
        dbmod._db = None
        shutil.rmtree(tmp.parent, ignore_errors=True)

    print()
    if fallos:
        print("FALLOS:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("Todo correcto: los avisos pueden salir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
