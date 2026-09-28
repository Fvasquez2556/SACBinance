"""
El bucle: descubrir avisos, congelar su contexto, simular, preguntar, etiquetar.

Dos modos, que se guardan en la base y no en el entorno (un reinicio no cambia
de modo por accidente):

- **RODAJE**: solo observa. Registra casos, contexto y salud, sin Kronos ni
  API. Sirve de linea base para saber si despues la IA estorba, y para probar
  la ingesta con avisos reales sin gastar.
- **MEDICION**: todo. Empieza con `python -m sac_ia medir`, que exige 48 h de
  rodaje y guarda la huella del estudio.

Lo que llega tarde no se paga: un aviso visto despues de su plazo de 120 s se
registra como caso (cuenta en la cobertura), pero no se le pide nada a nadie.
"""
from __future__ import annotations

import json
import random
import signal
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from sac_ia import barreras, contexto, etiquetas, kronos_adapter, llm, registro, salud
from sac_ia.almacen import Almacen
from sac_ia.config import Config
from sac_ia.fuente import FuenteSAC
from sac_ia.presupuesto import Presupuesto

RODAJE, MEDICION = "RODAJE", "MEDICION"
ABANDONO_PENDIENTE_MS = 6 * 3600_000
CALENTAR_CADA_MS = 10 * 60_000     # si Kronos no carga, no se reintenta en cada vuelta
MARGEN_LLM_S = 30          # lo que se deja a Luna y Sol despues de Kronos
PASOS_FUTUROS = registro.HORIZONTE_MS // kronos_adapter.PASO_MS


class Servicio:
    def __init__(self, cfg: Config, fuente: FuenteSAC, almacen: Almacen, cliente=None,
                 motor: Optional[kronos_adapter.MotorKronos] = None,
                 velas_kronos: Optional[Callable] = None,
                 reloj: Callable[[], int] = llm.ahora_ms) -> None:
        self.cfg, self.fuente, self.a = cfg, fuente, almacen
        self.cliente, self.motor, self.reloj = cliente, motor, reloj
        self.velas_kronos = velas_kronos or (lambda s, t, n: kronos_adapter.velas_binance(
            cfg.binance_rest, s, t, n))
        self.presupuesto = Presupuesto(almacen, cfg.tope_diario_usd, cfg.tope_total_usd)
        self.recorrido = etiquetas.importar_recorrido(cfg.sac_backend)
        self.parar = False
        self._proxima_salud = 0
        self._ultima_etiqueta = 0
        self._ultimo_calentar = 0
        self._azar = random.Random()

    # --- Estado ------------------------------------------------------------------

    def modo(self) -> str:
        return MEDICION if self.a.meta("inicio_medicion_ms") else RODAJE

    def iniciar(self) -> dict:
        info = self.fuente.comprobar_esquema()
        ahora = self.reloj()
        if self.a.meta("inicio_rodaje_ms") is None:
            self.a.fijar_meta("inicio_rodaje_ms", ahora)
        if self.a.meta("cursor_alerta") is None:
            # Se empieza por el aviso siguiente: los viejos ya no se pueden
            # predecir, y medirlos seria un replay disfrazado.
            self.a.fijar_meta("cursor_alerta", self.fuente.ultimo_id())
        self.a.evento(ahora, "ARRANQUE", json.dumps({**info, "modo": self.modo(),
                                                      "huella": registro.huella()}))
        return info

    # --- Descubrir y revisar ---------------------------------------------------------

    def descubrir(self, ahora: int) -> int:
        cursor = int(self.a.meta("cursor_alerta", "0"))
        nuevas = 0
        while True:
            filas = self.fuente.alertas_desde(cursor, 100)
            if not filas:
                break
            for f in filas:
                if f["telegram"] not in ("no_procede", "fallo"):
                    self.a.agregar_pendiente(f["id"], ahora, f["telegram"])
                    nuevas += 1
                cursor = f["id"]
            self.a.fijar_meta("cursor_alerta", cursor)
        return nuevas

    def revisar(self, ahora: int) -> list[int]:
        """Una alerta puede pasar a 'enviado' segundos despues: se reconsulta por id."""
        pendientes = self.a.pendientes()
        estados = self.fuente.estado_telegram([p["alerta_id"] for p in pendientes])
        enviados, descartados, hechos = [], set(), set()
        for p in pendientes:
            estado = estados.get(p["alerta_id"])
            if estado == "enviado":
                enviados.append(p["alerta_id"])
            elif estado in ("no_procede", "fallo") or p["alerta_id"] not in estados:
                self.a.quitar_pendiente(p["alerta_id"])
                descartados.add(p["alerta_id"])
        if enviados:
            hechos = self.procesar(enviados, ahora)
        for p in pendientes:
            i = p["alerta_id"]
            if i in hechos:
                self.a.quitar_pendiente(i)
            elif i not in descartados:
                # Enviado pero sin plan notificado legible todavia (SAC aun no
                # volco), o sin estado final: se reintenta hasta el abandono.
                if ahora - p["visto_ms"] > ABANDONO_PENDIENTE_MS:
                    self.a.quitar_pendiente(i)
                    self.a.evento(ahora, "PENDIENTE_ABANDONADO",
                                  f"alerta {i} sin estado final o sin plan: {estados.get(i)}")
                else:
                    self.a.tocar_pendiente(i, ahora, estados.get(i))
        return sorted(hechos)

    # --- Un lote de avisos -------------------------------------------------------------

    def _registrar(self, alerta_id: int, ahora: int, modo: str):
        """(caso, contexto) si es nuevo; "existe" si ya estaba; None si aun no se puede leer."""
        aviso = self.fuente.aviso(alerta_id)
        if aviso is None:
            return None
        n, al, plan = aviso["notificacion"], aviso["alerta"], aviso.get("plan") or {}
        as_of = int(n["ts_activado"])
        niveles = contexto.niveles(aviso)
        caso = {
            "caso_id": alerta_id, "symbol": al["symbol"], "ts_alerta_ms": int(al["ts_ms"]),
            "as_of_ms": as_of, "visto_ms": ahora,
            "entrada": niveles["entrada"], "objetivo": niveles["objetivo_tp"],
            "stop": niveles["stop"], "meta_precio": niveles["meta_precio"],
            "plan_id": plan.get("plan_id"), "episode_id": plan.get("episode_id"),
            "ordinal_episodio": plan.get("ordinal_episodio"),
            "score": al.get("score"), "escenario": al.get("display_state"),
            "modo": modo, "tardio": int(ahora > as_of + registro.PLAZO_DECISION_MS),
            "huella": registro.huella(),
            "fuente_json": json.dumps(aviso, ensure_ascii=False, default=str),
        }
        if not self.a.registrar_caso(caso):
            return "existe"                              # ya estaba: no se repite nada
        ctx = contexto.construir(aviso, self.fuente, as_of)
        self.a.guardar_contexto(alerta_id, contexto.VERSION, ctx,
                                contexto.huella_contexto(ctx), ahora)
        return caso, ctx

    def procesar(self, ids: list[int], ahora: int) -> set:
        """Devuelve los ids ya resueltos (nuevos o repetidos); el resto se reintenta."""
        modo = self.modo()
        hechos, lote = set(), []
        for i in ids:
            r = self._registrar(i, ahora, modo)
            if r is None:
                continue
            hechos.add(i)
            if r != "existe":
                lote.append(r)
        if modo == RODAJE or not lote:
            return hechos
        vivos = [(c, x) for c, x in lote if not c["tardio"]]
        for caso, _ in lote:
            if caso["tardio"]:
                self._no_ejecutado(caso["caso_id"], "visto despues del plazo de decision", ahora)
        if not vivos:
            return hechos
        # Aviso por aviso, el mas urgente primero: Luna y Sol del primero salen
        # en cuanto termina su Kronos, mientras Kronos sigue con el siguiente.
        # En lote, tres avisos juntos tardaban 72 s en el servidor y ninguno
        # llegaba a tiempo; asi el tercero termina hacia los 51 s.
        vivos.sort(key=lambda par: par[0]["as_of_ms"])
        with ThreadPoolExecutor(max_workers=4) as ex:
            futuros = []
            for caso, ctx in vivos:
                resumen, motivo = self.kronos_de(caso)
                deadline = caso["as_of_ms"] + registro.PLAZO_DECISION_MS
                for brazo, cfg_brazo in registro.BRAZOS_LLM.items():
                    entrada = (contexto.con_kronos(ctx, resumen, motivo) if cfg_brazo["con_kronos"]
                               else contexto.sin_kronos(ctx))
                    futuros.append(ex.submit(llm.decidir, self.cliente, brazo, entrada,
                                             caso["caso_id"], deadline, self.presupuesto,
                                             self.cfg.llm_timeout_s, self.reloj))
            for f in futuros:
                self.a.guardar_decision(f.result())
        return hechos

    def _no_ejecutado(self, caso_id: int, motivo: str, ahora: int) -> None:
        self.a.guardar_kronos({"caso_id": caso_id, "estado": "NO_EJECUTADO", "motivo": motivo,
                               "creado_ms": ahora})
        for brazo, cfg_brazo in registro.BRAZOS_LLM.items():
            self.a.guardar_decision({"caso_id": caso_id, "brazo": brazo,
                                     "modelo": cfg_brazo["modelo"], "estado": "NO_EJECUTADA",
                                     "motivo": motivo, "a_tiempo": 0})

    # --- Kronos ---------------------------------------------------------------------------

    def kronos_de(self, c: dict) -> tuple[Optional[dict], str]:
        """(resumen para el LLM o None, motivo) de UN aviso. Guarda su fila de kronos."""
        k = registro.KRONOS

        def fallo(estado, motivo):
            self.a.guardar_kronos({"caso_id": c["caso_id"], "estado": estado, "motivo": motivo,
                                   "modelo": k["modelo"], "creado_ms": self.reloj()})
            return None, motivo

        if self.motor is None or not self.motor.instalado():
            return fallo("NO_EJECUTADO", "Kronos no instalado")
        try:
            velas = self.velas_kronos(c["symbol"], c["as_of_ms"], k["lookback"])
        except Exception as exc:                           # noqa: BLE001
            return fallo("FALLO", f"velas de Binance: {type(exc).__name__}")
        problema = kronos_adapter.serie_util(velas, k["lookback"])
        if problema:
            return fallo("FALLO", problema)
        # El plazo es el de ESTE aviso, descontado lo que Luna y Sol necesitan.
        plazo = c["as_of_ms"] + registro.PLAZO_DECISION_MS
        timeout = min(self.cfg.kronos_timeout_s, (plazo - self.reloj()) / 1000 - MARGEN_LLM_S)
        if timeout < 5:
            return fallo("FALLO", "sin tiempo para simular")
        semilla = k["semilla_base"] + c["caso_id"]
        try:
            respuesta = self.motor.simular(
                [{"caso_id": c["caso_id"], "velas": velas, "semilla": semilla}], timeout)
        except Exception as exc:                           # noqa: BLE001
            return fallo("FALLO", f"{type(exc).__name__}: {str(exc)[:200]}")

        crudas = respuesta["trayectorias"].get(c["caso_id"]) or []
        primera = velas[-1]["t"] + kronos_adapter.PASO_MS
        tray = [kronos_adapter.futuras(t, primera, c["as_of_ms"], PASOS_FUTUROS) for t in crudas]
        r = barreras.resumir(tray, c["entrada"], c["meta_precio"], c["stop"],
                             k["max_invalidas_frac"])
        ruta, sha = kronos_adapter.guardar_artefacto(
            self.cfg.artefactos, c["caso_id"],
            {"caso_id": c["caso_id"], "modelo": k["modelo"], "semilla": semilla,
             "primera_apertura_ms": primera, "entrada": velas, "trayectorias": crudas})
        self.a.guardar_kronos({
            "caso_id": c["caso_id"], "estado": "OK" if not r["abstiene"] else "FALLO",
            "motivo": None if not r["abstiene"] else "demasiadas trayectorias invalidas",
            "modelo": k["modelo"], "n_trayectorias": r["n_trayectorias"],
            "n_validas": r["n_validas"], "n_meta": r["cuenta"]["META"],
            "n_stop": r["cuenta"]["STOP"], "n_ninguna": r["cuenta"]["NINGUNA"],
            "n_ambigua": r["cuenta"]["AMBIGUA"], "p_meta": r["p_meta_antes_que_stop"],
            "resumen_json": r, "artefacto": ruta, "artefacto_sha256": sha,
            "latencia_ms": respuesta.get("latencia_ms"), "creado_ms": self.reloj()})
        if r["abstiene"]:
            return None, "demasiadas trayectorias invalidas"
        visible = {k2: r[k2] for k2 in (
            "n_trayectorias", "n_validas", "p_meta_antes_que_stop", "p_stop_antes_que_meta",
            "p_ninguna", "p_ambigua", "retorno_final_pct", "max_subida_pct_p50",
            "max_bajada_pct_p50", "nota")}
        visible["horizonte"] = f"{PASOS_FUTUROS} velas de {k['tf']}"
        return visible, ""

    # --- Mantenimiento -------------------------------------------------------------------

    def etiquetar(self, ahora: int, maximo: int = 200) -> int:
        hechas = 0
        for caso in self.a.casos_por_etiquetar()[:maximo]:
            fila = etiquetas.etiquetar(caso, self.fuente, self.recorrido, ahora)
            if fila:
                self.a.guardar_etiqueta(fila)
                hechas += 1
        return hechas

    def calentar(self, ahora: int) -> None:
        """
        Kronos cargado ANTES de que llegue el aviso. Si se cargara al llegar, el
        tiempo de carga saldria del plazo de 120 s de ese aviso; y tras un
        timeout el proceso muere, asi que se recarga aqui, fuera del plazo.
        """
        if (self.modo() != MEDICION or self.motor is None or not self.motor.instalado()
                or self.motor.vivo() or ahora - self._ultimo_calentar < CALENTAR_CADA_MS):
            return
        self._ultimo_calentar = ahora
        try:
            self.motor.arrancar()
            self.a.evento(self.reloj(), "KRONOS_CARGADO", registro.KRONOS["modelo"])
        except Exception as exc:                           # noqa: BLE001
            self.a.evento(self.reloj(), "KRONOS_NO_CARGA", f"{type(exc).__name__}: {exc}"[:300])

    def paso(self) -> None:
        ahora = self.reloj()
        self.descubrir(ahora)
        self.revisar(ahora)
        if ahora >= self._proxima_salud:
            # Intervalo con azar: la edad de la ultima vela depende de en que
            # segundo del minuto se mire. Con un intervalo fijo, un cambio de
            # fase entre rodaje y medicion moveria el p95 hasta 30 s sin que
            # nada cambiara en SAC.
            self._proxima_salud = ahora + int(self.cfg.salud_cada_s * 1000
                                              * (0.5 + self._azar.random()))
            self.a.guardar_salud(salud.muestrear(self.fuente, self.cfg.sac_backend,
                                                 self.modo(), ahora))
        if ahora - self._ultima_etiqueta >= self.cfg.etiquetas_cada_s * 1000:
            self._ultima_etiqueta = ahora
            self.etiquetar(ahora)
        self.calentar(self.reloj())

    def servir(self) -> None:
        def _alto(*_):
            self.parar = True
        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(s, _alto)
            except (ValueError, OSError):
                pass
        self.iniciar()
        try:
            while not self.parar:
                try:
                    self.paso()
                except sqlite3.OperationalError as exc:
                    # SAC ocupado o reiniciando: se espera, no se insiste.
                    self.a.evento(self.reloj(), "FUENTE_OCUPADA", str(exc)[:300])
                time.sleep(self.cfg.poll_s)
        finally:
            if self.motor is not None:
                self.motor.parar()
            self.a.evento(self.reloj(), "PARADA", "")
