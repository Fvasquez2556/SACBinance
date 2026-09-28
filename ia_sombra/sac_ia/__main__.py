"""
python -m sac_ia <orden>

  servir                 el servicio (lo que arranca systemd)
  estado                 salud operativa; nunca enseña decisiones ni resultados
  informe [--desvelar]   el veredicto; cegado hasta que cierre la ventana
  medir [--forzar]       pasa de RODAJE a MEDICION y congela la huella;
                         antes hace una consulta real a Luna y Sol
  probar-kronos [-n N]   benchmark con los ultimos N avisos reales; no escribe nada
  probar-llm --si-gastar una llamada real a Luna y otra a Sol (~1 centavo)
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from sac_ia import config, contexto, informe, kronos_adapter, llm, registro
from sac_ia.almacen import Almacen
from sac_ia.fuente import FuenteSAC


def _servicio(cfg, con_ia: bool = True):
    from sac_ia.servicio import Servicio
    motor = kronos_adapter.MotorKronos.desde_config(cfg) if con_ia else None
    return Servicio(cfg, FuenteSAC(cfg.sac_db), Almacen(cfg.ia_db),
                    cliente=llm.crear_cliente(cfg) if con_ia else None, motor=motor)


def consulta_de_prueba(cfg) -> list[dict]:
    """
    Una llamada real a cada brazo con el ultimo aviso enviado (menos de un
    centavo). Usa un presupuesto aparte, en memoria: no gasta del tope del
    estudio ni deja filas en su base.
    """
    fuente = FuenteSAC(cfg.sac_db)
    fila = fuente.conn.execute("SELECT a.id FROM alertas_emitidas a JOIN notificacion_planes p "
                               "ON p.alerta_id = a.id WHERE a.telegram = 'enviado' "
                               "ORDER BY a.id DESC LIMIT 1").fetchall()
    if not fila:
        return [{"brazo": "-", "estado": "SIN_AVISOS", "motivo": "no hay avisos enviados en SAC"}]
    caso_id = fila[0][0]
    aviso = fuente.aviso(caso_id)
    ctx = contexto.con_kronos(contexto.construir(aviso, fuente,
                                                 int(aviso["notificacion"]["ts_activado"])),
                              None, "prueba sin Kronos")
    cliente = llm.crear_cliente(cfg)
    from sac_ia.presupuesto import Presupuesto
    prueba = Presupuesto(Almacen(":memory:"), 1.0, 1.0)
    return [llm.decidir(cliente, brazo, ctx, caso_id, llm.ahora_ms() + 120_000, prueba,
                        cfg.llm_timeout_s) for brazo in registro.BRAZOS_LLM]


def cmd_medir(cfg, forzar: bool, prueba=consulta_de_prueba) -> int:
    a = Almacen(cfg.ia_db)
    ahora = llm.ahora_ms()
    if a.meta("inicio_medicion_ms"):
        print("La medicion ya empezo:", informe._fecha(int(a.meta("inicio_medicion_ms"))))
        return 1
    rodaje = a.meta("inicio_rodaje_ms")
    problemas = []
    if rodaje is None:
        problemas.append("el servicio nunca arranco en rodaje")
    elif ahora - int(rodaje) < registro.RODAJE_MIN_MS:
        problemas.append(f"rodaje de {(ahora - int(rodaje)) / 3.6e6:.1f} h; hacen falta "
                         f"{registro.RODAJE_MIN_MS / 3.6e6:.0f} h de linea base")
    if not kronos_adapter.MotorKronos.desde_config(cfg).instalado():
        problemas.append(f"Kronos no esta instalado en {cfg.kronos_codigo}")
    if llm.crear_cliente(cfg) is None:
        problemas.append(f"no hay clave de OpenAI en {cfg.clave_openai}")
    else:
        # Una medicion que se queda sin saldo a medio camino no da veredicto:
        # se comprueba con una llamada real antes de empezar, no con la clave.
        print("Consulta de prueba a Luna y Sol (menos de un centavo)...")
        for d in prueba(cfg):
            if d["estado"] != "OK":
                problemas.append(f"la consulta de prueba a {d['brazo']} devolvio {d['estado']}: "
                                 f"{d.get('motivo') or ''}"[:300])
    if problemas and not forzar:
        print("No se empieza a medir:\n- " + "\n- ".join(problemas))
        return 1
    a.fijar_meta("inicio_medicion_ms", ahora)
    a.fijar_meta("huella_medicion", registro.huella())
    a.evento(ahora, "INICIO_MEDICION", json.dumps({"huella": registro.huella(),
                                                   "forzado": bool(problemas)}))
    print(f"Medicion iniciada {informe._fecha(ahora)} con huella {registro.huella()}. "
          f"Veredicto el {informe._fecha(ahora + registro.MEDICION_MS)}.")
    return 0


def cmd_probar_kronos(cfg, n: int) -> int:
    fuente = FuenteSAC(cfg.sac_db)
    filas = fuente.conn.execute(
        "SELECT a.id, a.symbol, p.ts_activado FROM alertas_emitidas a JOIN notificacion_planes p "
        "ON p.alerta_id = a.id WHERE a.telegram = 'enviado' ORDER BY a.id DESC LIMIT ?",
        (n,)).fetchall()
    if not filas:
        print("No hay avisos enviados en la base de SAC.")
        return 1
    k = registro.KRONOS
    casos = []
    for alerta_id, symbol, _ in filas:
        # Ahora mismo, no en el pasado: se mide la latencia, no la prediccion.
        velas = kronos_adapter.velas_binance(cfg.binance_rest, symbol, llm.ahora_ms(), k["lookback"])
        problema = kronos_adapter.serie_util(velas, k["lookback"])
        if problema:
            print(f"{symbol}: {problema}")
            continue
        casos.append({"caso_id": alerta_id, "velas": velas, "semilla": k["semilla_base"]})
    motor = kronos_adapter.MotorKronos.desde_config(cfg)
    t0 = time.monotonic()
    motor.arrancar()
    print(f"Carga del modelo {k['modelo']}: {time.monotonic() - t0:.1f} s")
    for tam in (1, len(casos)):
        t0 = time.monotonic()
        r = motor.simular(casos[:tam], timeout_s=600)
        print(f"{tam} aviso(s) × {k['trayectorias']} trayectorias × {k['pasos']} pasos: "
              f"{time.monotonic() - t0:.1f} s (en el hijo {r['latencia_ms'] / 1000:.1f} s)")
    motor.parar()
    return 0


def cmd_probar_llm(cfg) -> int:
    if llm.crear_cliente(cfg) is None:
        print(f"No hay clave en {cfg.clave_openai}")
        return 1
    resultados = consulta_de_prueba(cfg)
    for d in resultados:
        d.pop("respuesta_json", None)
        print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0 if all(d["estado"] == "OK" for d in resultados) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sac_ia")
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("servir")
    sub.add_parser("estado")
    i = sub.add_parser("informe")
    i.add_argument("--desvelar", action="store_true")
    i.add_argument("--salida")
    m = sub.add_parser("medir")
    m.add_argument("--forzar", action="store_true")
    k = sub.add_parser("probar-kronos")
    k.add_argument("-n", type=int, default=3)
    llm_p = sub.add_parser("probar-llm")
    llm_p.add_argument("--si-gastar", action="store_true")
    args = p.parse_args(argv)
    cfg = config.cargar()

    if args.orden == "servir":
        _servicio(cfg).servir()
        return 0
    if args.orden == "estado":
        print(json.dumps(informe.operativo(Almacen(cfg.ia_db), llm.ahora_ms()),
                         ensure_ascii=False, indent=1, default=str))
        return 0
    if args.orden == "informe":
        texto = informe.generar(Almacen(cfg.ia_db), llm.ahora_ms(), args.desvelar)
        if args.salida:
            with open(args.salida, "w", encoding="utf-8") as f:
                f.write(texto)
        print(texto)
        return 0
    if args.orden == "medir":
        return cmd_medir(cfg, args.forzar)
    if args.orden == "probar-kronos":
        return cmd_probar_kronos(cfg, args.n)
    if args.orden == "probar-llm":
        if not args.si_gastar:
            print("Esta orden gasta dinero real. Repite con --si-gastar.")
            return 1
        return cmd_probar_llm(cfg)
    return 2


if __name__ == "__main__":
    sys.exit(main())
