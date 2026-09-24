"""
Donde vive el reparto por episodio y el estado de la activacion.

Todo lo de esta fase es aditivo y esta APAGADO. La asignacion corre desde ya
en sombra —cada episodio nuevo recibe su brazo y se guarda— para que el dia
que la fase 5 de veredicto el reparto lleve semanas funcionando y activar sea
un interruptor, no un estreno.

Nada de lo que hay aqui toca la emision mientras `activo = 0`.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from src.activacion.registro import (
    BRAZO_REFERENCIA,
    BRAZO_RIVAL,
    BRAZOS,
    REGISTRO_VERSION,
    brazo_de,
    declaracion_json,
    huella,
)

ACTIVACION_SCHEMA = """
CREATE TABLE IF NOT EXISTS activacion_registro (
    huella       TEXT PRIMARY KEY,
    version      TEXT    NOT NULL,
    declaracion  TEXT    NOT NULL,
    ts_congelado INTEGER NOT NULL
);

-- episode_id es la clave primaria a proposito: un episodio tiene UN brazo para
-- siempre. Es la regla "se escribe una vez y no se recalcula" hecha esquema,
-- no confiada a que nadie llame dos veces.
CREATE TABLE IF NOT EXISTS activacion_asignacion (
    episode_id  INTEGER PRIMARY KEY,
    huella      TEXT    NOT NULL,
    brazo       TEXT    NOT NULL,
    symbol      TEXT,
    ts_asignado INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS activacion_estado (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    huella           TEXT    NOT NULL,
    activo           INTEGER NOT NULL DEFAULT 0,
    rival            TEXT,
    aprobado_por     TEXT,
    ts_activado      INTEGER,
    ts_revertido     INTEGER,
    motivo_reversion TEXT
);

CREATE TABLE IF NOT EXISTS activacion_eventos (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    huella  TEXT    NOT NULL,
    tipo    TEXT    NOT NULL,
    detalle TEXT,
    ts_ms   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_act_asig_brazo ON activacion_asignacion (brazo, ts_asignado);
CREATE INDEX IF NOT EXISTS idx_act_eventos_ts ON activacion_eventos (ts_ms);
"""

# Tipos de evento
CONGELADO = "CONGELADO"
ASIGNADO = "ASIGNADO"
ACTIVADO = "ACTIVADO"
REVERTIDO = "REVERTIDO"
INTEGRIDAD = "INTEGRIDAD"


class ActivacionRechazada(Exception):
    """Se intento activar sin cumplir una puerta. Dice cual."""


class AlmacenActivacion:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.db = conn

    # --- El candado --------------------------------------------------------

    def congelar(self, ahora_ms: Optional[int] = None) -> dict:
        """Deja constancia de la declaracion vigente. Idempotente por huella."""
        h = huella()
        ahora_ms = ahora_ms or int(time.time() * 1000)
        fila = self.db.execute(
            "SELECT ts_congelado FROM activacion_registro WHERE huella = ?",
            (h,)).fetchone()
        if fila:
            return {"huella": h, "ts_congelado": fila[0], "nuevo": False}
        self.db.execute(
            """INSERT INTO activacion_registro (huella, version, declaracion,
                                                ts_congelado)
               VALUES (?,?,?,?)""",
            (h, REGISTRO_VERSION, declaracion_json(), ahora_ms))
        self._evento(CONGELADO, {"version": REGISTRO_VERSION}, ahora_ms)
        self.db.commit()
        return {"huella": h, "ts_congelado": ahora_ms, "nuevo": True}

    def _evento(self, tipo: str, detalle: dict, ahora_ms: Optional[int] = None) -> None:
        self.db.execute(
            "INSERT INTO activacion_eventos (huella, tipo, detalle, ts_ms) VALUES (?,?,?,?)",
            (huella(), tipo, json.dumps(detalle, ensure_ascii=False),
             ahora_ms or int(time.time() * 1000)))

    # --- El reparto --------------------------------------------------------

    def asignar(self, episode_id: int, symbol: Optional[str] = None,
                ahora_ms: Optional[int] = None) -> str:
        """
        El brazo de un episodio. Se calcula una vez y se guarda.

        Si ya hay fila, esa manda — aunque la huella haya cambiado desde
        entonces. Un episodio vivo no cambia de brazo a mitad: si lo hiciera,
        sus repeticiones se repartirian entre los dos brazos y la comparacion
        estaria midiendo el mismo movimiento contra si mismo.
        """
        fila = self.db.execute(
            "SELECT brazo FROM activacion_asignacion WHERE episode_id = ?",
            (episode_id,)).fetchone()
        if fila:
            return fila[0]
        brazo = brazo_de(episode_id)
        ahora_ms = ahora_ms or int(time.time() * 1000)
        # INSERT OR IGNORE: si dos pasadas coinciden, la primera gana y la
        # segunda lee lo que quedo. Nunca se pisa una asignacion.
        self.db.execute(
            """INSERT OR IGNORE INTO activacion_asignacion
                   (episode_id, huella, brazo, symbol, ts_asignado)
               VALUES (?,?,?,?,?)""",
            (episode_id, huella(), brazo, symbol, ahora_ms))
        self.db.commit()
        fila = self.db.execute(
            "SELECT brazo FROM activacion_asignacion WHERE episode_id = ?",
            (episode_id,)).fetchone()
        return fila[0] if fila else brazo

    def brazo_de_episodio(self, episode_id: int) -> Optional[str]:
        fila = self.db.execute(
            "SELECT brazo FROM activacion_asignacion WHERE episode_id = ?",
            (episode_id,)).fetchone()
        return fila[0] if fila else None

    def reparto(self) -> dict:
        """
        Cuantos episodios hay en cada brazo. El desequilibrio se reporta, no se
        corrige: forzar un 50/50 exacto introduciria dependencia entre
        episodios, que es justo lo que la asignacion por episodio evita.
        """
        filas = dict(self.db.execute(
            "SELECT brazo, COUNT(*) FROM activacion_asignacion WHERE huella = ? GROUP BY brazo",
            (huella(),)).fetchall())
        n = sum(filas.values())
        return {
            "huella": huella(),
            "n": n,
            "por_brazo": {b: filas.get(b, 0) for b in BRAZOS},
            "fraccion_rival": (round(filas.get(BRAZO_RIVAL, 0) / n, 4) if n else None),
        }

    # --- El estado ---------------------------------------------------------

    def estado(self) -> dict:
        fila = self.db.execute(
            """SELECT huella, activo, rival, aprobado_por, ts_activado,
                      ts_revertido, motivo_reversion
               FROM activacion_estado WHERE id = 1""").fetchone()
        if not fila:
            return {"huella": huella(), "activo": False, "rival": None,
                    "aprobado_por": None, "ts_activado": None,
                    "ts_revertido": None, "motivo_reversion": None}
        cols = ("huella", "activo", "rival", "aprobado_por", "ts_activado",
                "ts_revertido", "motivo_reversion")
        d = dict(zip(cols, fila))
        d["activo"] = bool(d["activo"])
        return d

    def activar(self, rival: str, *, aprobado_por: str,
                puede: dict, ahora_ms: Optional[int] = None) -> dict:
        """
        Ata el rival y enciende. Solo se llama a mano, nunca desde un bucle.

        `puede` es el resultado de `veredicto.puede_activarse()` y `aprobado_por`
        identifica a quien lo reviso. Las dos son obligatorias: la puerta 3 del
        registro es "revisado por el operador, explicito, nunca automatico", y
        una funcion que se pueda llamar sin ellas acabaria llamandose sin ellas.
        """
        if not aprobado_por:
            raise ActivacionRechazada(
                "falta la revision del operador (puerta 3): la activacion nunca "
                "es automatica")
        if puede and puede.get("provisional"):
            raise ActivacionRechazada(
                "la eleccion es provisional: falta el corte por mitades, que es "
                "la condicion que protege de coronar a una ganadora por azar")
        if not puede or not puede.get("listo"):
            raise ActivacionRechazada(
                "la fase 5 no autoriza todavia: "
                + (puede or {}).get("por_que", "sin informe"))
        if puede.get("rival") != rival:
            raise ActivacionRechazada(
                f"el rival pedido ({rival}) no es el que elige la regla "
                f"congelada ({puede.get('rival')})")
        problemas = self.verificar_integridad()
        if problemas:
            raise ActivacionRechazada(
                "la puerta de integridad falla: " + "; ".join(problemas))

        ahora_ms = ahora_ms or int(time.time() * 1000)
        self.db.execute(
            """INSERT INTO activacion_estado
                   (id, huella, activo, rival, aprobado_por, ts_activado)
               VALUES (1,?,1,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   huella=excluded.huella, activo=1, rival=excluded.rival,
                   aprobado_por=excluded.aprobado_por,
                   ts_activado=excluded.ts_activado,
                   ts_revertido=NULL, motivo_reversion=NULL""",
            (huella(), rival, aprobado_por, ahora_ms))
        self._evento(ACTIVADO, {"rival": rival, "aprobado_por": aprobado_por,
                                "por_que": puede.get("por_que")}, ahora_ms)
        self.db.commit()
        return self.estado()

    def revertir(self, motivo: str, ahora_ms: Optional[int] = None) -> dict:
        """
        Apaga. No restaura nada.

        Los planes ya notificados conservan sus niveles y se siguen evaluando
        contra ellos; las operaciones registradas tambien. Restaurar una copia
        antigua borraria eventos posteriores que no tienen que ver con el
        experimento — el plan lo prohibe expresamente.
        """
        ahora_ms = ahora_ms or int(time.time() * 1000)
        self.db.execute(
            """INSERT INTO activacion_estado (id, huella, activo, ts_revertido,
                                              motivo_reversion)
               VALUES (1,?,0,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   activo=0, ts_revertido=excluded.ts_revertido,
                   motivo_reversion=excluded.motivo_reversion""",
            (huella(), ahora_ms, motivo))
        self._evento(REVERTIDO, {"motivo": motivo}, ahora_ms)
        self.db.commit()
        return self.estado()

    # --- La puerta de integridad -------------------------------------------

    def verificar_integridad(self) -> list:
        """
        Lo que tiene que ser cierto para que el reparto signifique algo.

        Devuelve una lista de problemas en castellano llano; vacia es que todo
        esta bien. Se comprueba en cada arranque y antes de activar.
        """
        problemas = []

        malos = self.db.execute(
            "SELECT COUNT(*) FROM activacion_asignacion WHERE brazo NOT IN (?,?)",
            BRAZOS).fetchone()[0]
        if malos:
            problemas.append(f"{malos} episodios con un brazo que no existe")

        # El reparto tiene que ser reproducible: recalcular desde la huella con
        # la que se escribio debe dar lo mismo. Si no, alguien escribio a mano
        # o la regla cambio sin abrir version.
        discrepantes = 0
        for eid, h, brazo in self.db.execute(
                "SELECT episode_id, huella, brazo FROM activacion_asignacion"):
            if brazo_de(eid, h) != brazo:
                discrepantes += 1
        if discrepantes:
            problemas.append(
                f"{discrepantes} asignaciones no se reproducen desde su huella")

        huerfanos = self.db.execute(
            """SELECT COUNT(*) FROM activacion_asignacion a
               LEFT JOIN episodios e ON e.episode_id = a.episode_id
               WHERE e.episode_id IS NULL""").fetchone()[0]
        if huerfanos:
            problemas.append(f"{huerfanos} asignaciones sin episodio")

        est = self.estado()
        if est["activo"] and not est["rival"]:
            problemas.append("activo sin rival atado")
        if est["activo"] and est["huella"] != huella():
            problemas.append(
                "activo bajo una huella distinta de la vigente: el registro "
                "cambio con el experimento en marcha")
        return problemas

    # --- Los disparadores de reversion -------------------------------------

    def evaluar_reversion(self, por_brazo: dict, *,
                          capital_pct_rival: Optional[float] = None,
                          capital_pct_ref: Optional[float] = None) -> dict:
        """
        ¿Toca revertir? Con los umbrales congelados, sin mirar nada mas.

        `por_brazo` es {brazo: {"n": int, "media_pct": float}}. Se separa del
        calculo a proposito: aqui solo se aplica la regla, para que se pueda
        probar con numeros de mesa.

        No existe un disparador de "va ganando": las revisiones son de
        calendario. Parar al ir ganando es elegir el momento que mas favorece.
        """
        from src.activacion.registro import REVERSION
        ref = por_brazo.get(BRAZO_REFERENCIA) or {}
        riv = por_brazo.get(BRAZO_RIVAL) or {}

        suelo = REVERSION["cortacircuitos_pct_capital"]
        if capital_pct_rival is not None and capital_pct_rival <= suelo:
            # La declaracion lo condiciona a que la referencia NO este igual de
            # hundida: si cae todo el mercado, revertir no recupera nada y
            # acabaria el experimento por el motivo equivocado. El codigo no lo
            # comprobaba y la declaracion si — lo encontro una revision externa.
            ref_sana = (capital_pct_ref is None or capital_pct_ref > suelo)
            if not REVERSION["cortacircuitos_exige_referencia_sana"] or ref_sana:
                return {"revertir": True, "motivo": "CORTACIRCUITOS",
                        "detalle": (f"el brazo rival acumula {capital_pct_rival:+.1f} % "
                                    f"del capital, por debajo de {suelo:+.1f} %"
                                    + ("" if capital_pct_ref is None else
                                       f", con la referencia en {capital_pct_ref:+.1f} %"))}

        n_min = REVERSION["daño_n_minimo_por_brazo"]
        if int(ref.get("n") or 0) >= n_min and int(riv.get("n") or 0) >= n_min:
            dif = float(riv.get("media_pct") or 0.0) - float(ref.get("media_pct") or 0.0)
            if dif < -REVERSION["daño_puntos_por_operacion"]:
                return {"revertir": True, "motivo": "DAÑO",
                        "detalle": (f"el rival va {dif:+.2f} puntos por operacion "
                                    f"por debajo de la referencia, con n="
                                    f"{riv.get('n')} y {ref.get('n')}")}

        problemas = self.verificar_integridad()
        if problemas:
            return {"revertir": True, "motivo": "INTEGRIDAD",
                    "detalle": "; ".join(problemas)}

        return {"revertir": False, "motivo": None,
                "detalle": "ningun disparador activo; las revisiones son de calendario"}

    # --- La reversion, APLICADA ---------------------------------------------

    def resultados_por_brazo(self, huella_f5: str,
                             politica_rival: str) -> dict:
        """
        Lo que cada brazo lleva ganado, sobre los planes decisorios emitidos.

        Es la lectura PRINCIPAL declarada en el registro: no depende de que
        tomo el operador. El brazo REFERENCIA se mide con la politica REF y el
        brazo RIVAL con la politica atada, cada uno sobre SUS propios planes.
        """
        out = {}
        for brazo, pol in ((BRAZO_REFERENCIA, "REF"), (BRAZO_RIVAL, politica_rival)):
            filas = self.db.execute(
                """SELECT r.resultado_pct
                   FROM experimento_resultados r
                   JOIN planes p ON p.plan_id = r.plan_id
                   JOIN activacion_asignacion a ON a.episode_id = p.episode_id
                   JOIN alertas_emitidas al ON al.id = p.legacy_alerta_id
                   WHERE r.huella = ? AND r.politica = ?
                     AND a.brazo = ? AND al.telegram = 'enviado'
                     AND p.ordinal_episodio = 1
                     AND r.desenlace IN ('OBJETIVO','STOP')
                     AND r.resultado_pct IS NOT NULL
                   ORDER BY r.ts_creado""",
                (huella_f5, pol, brazo)).fetchall()
            pcts = [float(f[0]) for f in filas]
            n = len(pcts)
            # COMPUESTO, no suma. El umbral del cortacircuitos habla de "% del
            # capital", y con una posicion que se reinvierte entera el capital
            # sigue el producto, no el total de los porcentajes. Sumarlos
            # disparaba el cortacircuitos con diez operaciones normales: lo
            # encontro una prueba de extremo a extremo.
            capital = 1.0
            for x in pcts:
                capital *= (1.0 + x / 100.0)
            out[brazo] = {
                "n": n,
                "media_pct": (sum(pcts) / n) if n else 0.0,
                "capital_pct": (capital - 1.0) * 100.0,
                "politica": pol,
            }
        return out

    def vigilar(self, huella_f5: Optional[str] = None,
                ahora_ms: Optional[int] = None) -> dict:
        """
        Comprueba los disparadores y REVIERTE si toca. Esto es lo que hace que
        el cortacircuitos sea una proteccion y no una funcion que nadie llama.

        Sin activacion no hay nada que vigilar y devuelve en seco: mientras el
        interruptor este apagado, los dos brazos ven la misma emision.

        AVISO que va tambien en el registro: revertir corta la EXPOSICION
        FUTURA. No cierra ninguna posicion abierta, y un stop puesto en el
        exchange tampoco garantiza el precio al que se ejecuta. Lo que esto
        protege es el siguiente plan, no el que ya esta en mercado.
        """
        est = self.estado()
        if not est["activo"] or not est["rival"]:
            return {"vigilado": False, "revertir": False,
                    "detalle": "activacion apagada: nada que vigilar"}
        if huella_f5 is None:
            from src.experimentos.registro import huella as h5
            huella_f5 = h5()
        por_brazo = self.resultados_por_brazo(huella_f5, est["rival"])
        v = self.evaluar_reversion(
            por_brazo,
            capital_pct_rival=por_brazo[BRAZO_RIVAL]["capital_pct"],
            capital_pct_ref=por_brazo[BRAZO_REFERENCIA]["capital_pct"])
        v["vigilado"] = True
        v["por_brazo"] = por_brazo
        if v["revertir"]:
            self.revertir(f"{v['motivo']}: {v['detalle']}", ahora_ms)
            self._evento(INTEGRIDAD if v["motivo"] == "INTEGRIDAD" else REVERTIDO,
                         {"automatico": True, **{k: v[k] for k in ("motivo", "detalle")}},
                         ahora_ms)
            self.db.commit()
        return v
