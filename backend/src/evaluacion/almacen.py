"""
Donde se guarda el recorrido de cada plan, y como se reanuda sin repetirlo.

Fase 2, en sombra: escribe tablas nuevas y **no sustituye a ningun tracker**.
Los cuatro seguimientos actuales siguen mandando; esto corre al lado para poder
compararlos antes de tocarlos. El plan lo pide asi de forma explicita: primero
comparar salidas, despues reemplazar, y nunca los cuatro a la vez.

El adaptador de produccion es el de **replay incremental**: cada pasada lee
solo las velas posteriores a la ultima que ya vio, guardadas en el estado. El
adaptador de streaming vive en `adaptadores.py` y comparte la misma funcion
pura, asi que los dos caminos no pueden divergir sin que una prueba lo note.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from src.evaluacion.recorrido import (
    EVALUADOR_VERSION,
    Estado,
    Plan,
    Vela,
    avanzar,
    cerrar_por_reloj,
    cobertura,
    completa,
    resultado_politica,
)

EVALUACION_SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_recorrido (
    plan_id       INTEGER PRIMARY KEY,
    symbol        TEXT    NOT NULL,
    evaluador     TEXT    NOT NULL,
    inicio_ms     INTEGER NOT NULL,
    horizonte_ms  INTEGER NOT NULL,
    entrada       REAL    NOT NULL,
    objetivo      REAL    NOT NULL,
    stop          REAL    NOT NULL,
    n_velas       INTEGER NOT NULL DEFAULT 0,
    cobertura     REAL,
    completa      INTEGER NOT NULL DEFAULT 0,
    ms_objetivo   INTEGER,
    ms_stop       INTEGER,
    ms_desenlace  INTEGER,
    desenlace     TEXT,
    resultado_pct REAL,
    mfe_pct       REAL,
    mae_pct       REAL,
    ms_mfe        INTEGER,
    ms_mae        INTEGER,
    ambiguo       INTEGER NOT NULL DEFAULT 0,
    salto         INTEGER NOT NULL DEFAULT 0,
    precio_stop   REAL,
    cierre_pct    REAL,
    hitos         TEXT    NOT NULL DEFAULT '{}',
    estado        TEXT    NOT NULL DEFAULT '{}',
    ts_evaluado   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recorrido_pendiente
    ON plan_recorrido (completa, ts_evaluado);
CREATE INDEX IF NOT EXISTS idx_recorrido_symbol ON plan_recorrido (symbol, inicio_ms);

CREATE TABLE IF NOT EXISTS plan_horizontes (
    plan_id       INTEGER NOT NULL,
    horizonte_min INTEGER NOT NULL,
    ret_pct       REAL,
    mfe_pct       REAL,
    mae_pct       REAL,
    n_velas       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (plan_id, horizonte_min)
);
"""


class AlmacenRecorridos:
    def __init__(self, conn: sqlite3.Connection, *, coste_pct: float = 0.0,
                 max_por_pasada: int = 60) -> None:
        self.db = conn
        self.coste_pct = coste_pct
        self.max_por_pasada = max_por_pasada

    # --- Lectura -----------------------------------------------------------

    def filas(self, sql: str, args=()) -> list[dict]:
        cur = self.db.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def recorrido(self, plan_id: int) -> Optional[dict]:
        filas = self.filas("SELECT * FROM plan_recorrido WHERE plan_id = ?", (plan_id,))
        return filas[0] if filas else None

    def _plan_de_fila(self, fila: dict) -> Plan:
        return Plan(entrada=fila["entry"], objetivo=fila["take_profit"],
                    stop=fila["stop_loss"], inicio_ms=fila["ts_creado"],
                    horizonte_ms=fila["horizonte_ms"])

    def _velas(self, symbol: str, desde_ms: int, hasta_ms: int) -> list[Vela]:
        return [Vela(t, o, h, l, c) for t, o, h, l, c in self.db.execute(
            """SELECT open_time, o, h, l, c FROM klines
               WHERE symbol = ? AND tf = '1m' AND open_time >= ? AND open_time <= ?
               ORDER BY open_time""", (symbol, desde_ms, hasta_ms))]

    # --- Evaluacion --------------------------------------------------------

    def evaluar_plan(self, fila_plan: dict, ahora_ms: int) -> dict:
        """
        Pone al dia el recorrido de un plan leyendo solo lo que falta.

        Devuelve el estado como diccionario. No decide nada ni avisa a nadie.
        """
        plan = self._plan_de_fila(fila_plan)
        previo = self.recorrido(fila_plan["plan_id"])
        estado = (Estado.desde_dict(json.loads(previo["estado"]))
                  if previo and previo["estado"] else Estado())
        desde = (estado.t_ultima + 1) if estado.t_ultima is not None else plan.inicio_ms
        for vela in self._velas(fila_plan["symbol"], desde, min(ahora_ms, plan.fin_ms)):
            estado = avanzar(plan, estado, vela)
        estado = cerrar_por_reloj(plan, estado, ahora_ms)
        self._guardar(fila_plan, plan, estado, ahora_ms)
        return estado.como_dict()

    def _guardar(self, fila_plan: dict, plan: Plan, estado: Estado,
                 ahora_ms: int) -> None:
        self.db.execute(
            """INSERT INTO plan_recorrido
               (plan_id, symbol, evaluador, inicio_ms, horizonte_ms, entrada, objetivo,
                stop, n_velas, cobertura, completa, ms_objetivo, ms_stop, ms_desenlace,
                desenlace, resultado_pct, mfe_pct, mae_pct, ms_mfe, ms_mae, ambiguo,
                salto, precio_stop, cierre_pct, hitos, estado, ts_evaluado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(plan_id) DO UPDATE SET
                 n_velas=excluded.n_velas, cobertura=excluded.cobertura,
                 completa=excluded.completa, ms_objetivo=excluded.ms_objetivo,
                 ms_stop=excluded.ms_stop, ms_desenlace=excluded.ms_desenlace,
                 desenlace=excluded.desenlace, resultado_pct=excluded.resultado_pct,
                 mfe_pct=excluded.mfe_pct, mae_pct=excluded.mae_pct,
                 ms_mfe=excluded.ms_mfe, ms_mae=excluded.ms_mae,
                 ambiguo=excluded.ambiguo, salto=excluded.salto,
                 precio_stop=excluded.precio_stop, cierre_pct=excluded.cierre_pct,
                 hitos=excluded.hitos, estado=excluded.estado,
                 ts_evaluado=excluded.ts_evaluado""",
            (fila_plan["plan_id"], fila_plan["symbol"], EVALUADOR_VERSION,
             plan.inicio_ms, plan.horizonte_ms, plan.entrada, plan.objetivo, plan.stop,
             estado.n_velas, cobertura(plan, estado, ahora_ms),
             int(completa(plan, ahora_ms)), estado.ms_objetivo, estado.ms_stop,
             estado.ms_desenlace, estado.desenlace,
             resultado_politica(plan, estado, self._coste_de(fila_plan)),
             estado.mfe_pct, estado.mae_pct, estado.ms_mfe, estado.ms_mae,
             int(estado.ambiguo), int(estado.salto), estado.precio_stop,
             estado.cierre_pct, json.dumps(estado.hitos),
             json.dumps(estado.como_dict()), ahora_ms))
        for clave, h in estado.horizontes.items():
            self.db.execute(
                """INSERT INTO plan_horizontes (plan_id, horizonte_min, ret_pct, mfe_pct,
                                                mae_pct, n_velas)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(plan_id, horizonte_min) DO UPDATE SET
                     ret_pct=excluded.ret_pct, mfe_pct=excluded.mfe_pct,
                     mae_pct=excluded.mae_pct, n_velas=excluded.n_velas""",
                (fila_plan["plan_id"], int(clave), h["ret"], h["mfe"], h["mae"], h["n"]))

    def _coste_de(self, fila_plan: dict) -> float:
        """
        El coste que se descuenta es el que el PLAN congelo, no el de la
        configuracion de hoy.

        `planes.coste_pct` se guarda con el plan justamente para esto. Usar el
        global significaba que cambiar el ajuste reescribia el resultado neto
        de toda ventana todavia abierta: el mismo plan, medido con un coste que
        no existia cuando se creo. Un plan es inmutable o no lo es.

        Los planes anteriores a este campo caen al coste global, y eso se nota
        porque la fila no trae el valor — no porque se elija en silencio.
        """
        coste = fila_plan.get("coste_pct")
        return float(coste) if coste is not None else self.coste_pct

    def evaluar_pendientes(self, ahora_ms: int) -> dict:
        """
        Pasada de mantenimiento: planes sin recorrido o con la ventana viva.

        Se limita a `max_por_pasada` para no competir con el ciclo de velas.
        Los que queden esperan a la siguiente pasada: el recorrido se reconstruye
        desde las velas guardadas, asi que llegar tarde no pierde nada.

        **El orden es por antiguedad de la ULTIMA evaluacion, no por fecha del
        plan.** Con 192 planes vivos y 60 por pasada, ordenar por `ts_creado`
        devolvia siempre los 60 mas viejos —todos con la ventana abierta— y los
        132 restantes no se evaluaban hasta que aquellos vencieran, hasta 12 h
        despues. Asi cada plan entra por turno: los que nunca se evaluaron
        primero (su `ts_evaluado` no existe), y despues el que lleva mas tiempo
        sin mirarse.
        """
        pendientes = self.filas(
            """SELECT p.plan_id, p.symbol, p.entry, p.take_profit, p.stop_loss,
                      p.ts_creado, p.horizonte_ms, p.coste_pct
               FROM planes p LEFT JOIN plan_recorrido r ON r.plan_id = p.plan_id
               WHERE r.plan_id IS NULL OR r.completa = 0
               ORDER BY COALESCE(r.ts_evaluado, 0), p.ts_creado LIMIT ?""",
            (self.max_por_pasada,))
        resultados = {"evaluados": 0, "cerrados": 0, "pendientes": len(pendientes)}
        for fila in pendientes:
            estado = self.evaluar_plan(fila, ahora_ms)
            resultados["evaluados"] += 1
            if estado["desenlace"]:
                resultados["cerrados"] += 1
        if resultados["evaluados"]:
            self.db.commit()
        return resultados

    # --- Comparacion en sombra contra lo que ya mide el sistema ------------

    def comparar_con_notificaciones(self) -> dict:
        """
        Misma pregunta, dos medidores. Cualquier diferencia hay que explicarla
        ANTES de retirar el medidor viejo; esa es la condicion de la fase 2.
        """
        filas = self.filas(
            """SELECT n.estado AS legado, r.desenlace AS nuevo, COUNT(*) n
               FROM planes p
               JOIN plan_recorrido r ON r.plan_id = p.plan_id
               JOIN notificacion_planes n ON n.alerta_id = p.legacy_alerta_id
               WHERE n.estado IN ('TP','SL','VENCIDO')
               GROUP BY n.estado, r.desenlace""")
        equivalencia = {"TP": "OBJETIVO", "SL": "STOP", "VENCIDO": "VENCIDO"}
        iguales = sum(f["n"] for f in filas if equivalencia.get(f["legado"]) == f["nuevo"])
        total = sum(f["n"] for f in filas)
        return {"total": total, "coinciden": iguales,
                "discrepancias": [f for f in filas
                                  if equivalencia.get(f["legado"]) != f["nuevo"]],
                "evaluador": EVALUADOR_VERSION}

    def resumen(self) -> dict:
        por_desenlace = self.filas(
            """SELECT desenlace, COUNT(*) n, ROUND(AVG(resultado_pct), 3) media
               FROM plan_recorrido GROUP BY desenlace""")
        cobertura = self.filas(
            """SELECT ROUND(AVG(cobertura), 4) media, MIN(cobertura) minima,
                      SUM(cobertura < 0.9) pobres, COUNT(*) n
               FROM plan_recorrido WHERE completa = 1""")
        return {"por_desenlace": por_desenlace,
                "cobertura": cobertura[0] if cobertura else {},
                "ambiguos": self.filas("SELECT COUNT(*) n FROM plan_recorrido WHERE ambiguo = 1")[0]["n"],
                "saltos": self.filas("SELECT COUNT(*) n FROM plan_recorrido WHERE salto = 1")[0]["n"],
                "evaluador": EVALUADOR_VERSION,
                "ts": int(time.time() * 1000)}
