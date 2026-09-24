"""
Lo que el usuario tomo de verdad, separado de lo que el sistema propuso.

Fase 3 del plan de evolucion. Hasta ahora «mis operaciones» no existia como
dato: el tablero enseñaba señales y el operador tenia que acordarse de cual
habia tomado. De ahi salen dos errores que este modulo hace imposibles.

**Que una señal posterior le cambie el resultado a la que tomaste.** Si tomas
la señal A y despues aparece la B del mismo par con otros niveles y acaba en
stop, la A sigue midiendose contra SU entrada y SUS niveles. La B se conserva
como alternativa no tomada del episodio, con su perdida intacta. Los niveles se
copian al abrir: la operacion no sigue vivo al plan.

**Que un mensaje de Telegram cuente como una compra.** Aqui no se registra nada
que el usuario no haya declarado. Ni el envio, ni la emision, ni que el precio
tocara la entrada: solo un acto explicito suyo.

Tres tipos que no se mezclan nunca
----------------------------------
- `SIMULADA`   — «sigo esta entrada» sin dinero detras. Es un marcador.
- `DECLARADA`  — el usuario dice que la ejecuto, con su precio y su hora.
- `IMPORTADA`  — vendria del exchange. Todavia no hay importacion; el tipo
                 existe para que el dia que la haya no se confunda con las
                 otras dos.

El resumen los reporta por separado. Sumar una ganancia simulada con una real
es la forma mas rapida de creerse un historial que no existe.

Reentrar es otra operacion
--------------------------
Una perdida seguida de una reentrada que gana son dos operaciones, no una
recuperada. El saldo agregado las suma; el resultado de cada una se queda como
fue.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

TIPOS = ("SIMULADA", "DECLARADA", "IMPORTADA")
ESTADOS = ("ABIERTA", "CERRADA", "CANCELADA")
EVENTOS = ("APERTURA", "PARCIAL", "CIERRE", "AJUSTE", "NOTA")

OPERACIONES_SCHEMA = """
CREATE TABLE IF NOT EXISTS operaciones (
    operacion_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id          INTEGER,
    episode_id       INTEGER,
    symbol           TEXT    NOT NULL,
    tipo             TEXT    NOT NULL,
    estado           TEXT    NOT NULL DEFAULT 'ABIERTA',
    ts_apertura      INTEGER NOT NULL,
    precio_entrada   REAL    NOT NULL,
    cantidad         REAL,
    cantidad_abierta REAL,
    objetivo         REAL,
    stop             REAL,
    coste_pct        REAL    NOT NULL DEFAULT 0,
    ts_cierre        INTEGER,
    precio_salida    REAL,
    motivo_cierre    TEXT,
    resultado_pct    REAL,
    resultado_moneda REAL,
    nota             TEXT,
    creada_ms        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operaciones_estado ON operaciones (estado, ts_apertura DESC);
CREATE INDEX IF NOT EXISTS idx_operaciones_symbol ON operaciones (symbol, ts_apertura DESC);
CREATE INDEX IF NOT EXISTS idx_operaciones_plan ON operaciones (plan_id);

CREATE TABLE IF NOT EXISTS operacion_eventos (
    evento_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    operacion_id INTEGER NOT NULL,
    tipo         TEXT    NOT NULL,
    ts_ms        INTEGER NOT NULL,
    precio       REAL,
    cantidad     REAL,
    nota         TEXT,
    datos        TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_operacion_eventos ON operacion_eventos (operacion_id, ts_ms);
"""


class ErrorDiario(ValueError):
    """Lo que el diario se niega a registrar, con el motivo en el texto."""


class Diario:
    def __init__(self, conn: sqlite3.Connection, *, coste_pct: float = 0.0) -> None:
        self.db = conn
        self.coste_pct = coste_pct

    # --- Lectura -----------------------------------------------------------

    def filas(self, sql: str, args=()) -> list[dict]:
        cur = self.db.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def operacion(self, operacion_id: int) -> Optional[dict]:
        filas = self.filas("SELECT * FROM operaciones WHERE operacion_id = ?",
                           (operacion_id,))
        if not filas:
            return None
        op = filas[0]
        op["eventos"] = self.filas(
            "SELECT * FROM operacion_eventos WHERE operacion_id = ? ORDER BY ts_ms, evento_id",
            (operacion_id,))
        return op

    def listar(self, estado: Optional[str] = None, symbol: Optional[str] = None,
               limite: int = 100) -> list[dict]:
        cond, args = [], []
        if estado:
            cond.append("estado = ?")
            args.append(estado.upper())
        if symbol:
            cond.append("symbol = ?")
            args.append(symbol.upper())
        donde = f"WHERE {' AND '.join(cond)}" if cond else ""
        args.append(limite)
        return self.filas(
            f"SELECT * FROM operaciones {donde} ORDER BY ts_apertura DESC LIMIT ?", args)

    def abiertas_por_symbol(self, symbol: str) -> list[dict]:
        return self.listar(estado="ABIERTA", symbol=symbol)

    # --- Alta --------------------------------------------------------------

    def abrir(self, *, symbol: str, ts_ms: int, precio_entrada: float,
              tipo: str = "SIMULADA", plan_id: Optional[int] = None,
              cantidad: Optional[float] = None, objetivo: Optional[float] = None,
              stop: Optional[float] = None, nota: Optional[str] = None,
              coste_pct: Optional[float] = None) -> dict:
        """
        Registra que el usuario tomo esta entrada. Nadie mas puede llamar a esto.

        Los niveles se **copian** del plan en este instante. Si mañana el motor
        propone otros, esta operacion conserva los suyos: es lo que separa una
        operacion de una alerta.
        """
        tipo = (tipo or "SIMULADA").upper()
        if tipo not in TIPOS:
            raise ErrorDiario(f"tipo desconocido: {tipo}")
        if not precio_entrada or precio_entrada <= 0:
            raise ErrorDiario("la entrada necesita un precio mayor que cero")
        if cantidad is not None and cantidad <= 0:
            raise ErrorDiario("la cantidad, si se indica, tiene que ser mayor que cero")

        episode_id = None
        if plan_id is not None:
            plan = self.filas(
                """SELECT plan_id, episode_id, symbol, take_profit, stop_loss
                   FROM planes WHERE plan_id = ?""", (plan_id,))
            if not plan:
                raise ErrorDiario(f"el plan {plan_id} no existe")
            plan = plan[0]
            if plan["symbol"].upper() != symbol.upper():
                raise ErrorDiario("el plan es de otro par")
            episode_id = plan["episode_id"]
            objetivo = objetivo if objetivo is not None else plan["take_profit"]
            stop = stop if stop is not None else plan["stop_loss"]

        coste = self.coste_pct if coste_pct is None else coste_pct
        cur = self.db.execute(
            """INSERT INTO operaciones
               (plan_id, episode_id, symbol, tipo, estado, ts_apertura, precio_entrada,
                cantidad, cantidad_abierta, objetivo, stop, coste_pct, nota, creada_ms)
               VALUES (?,?,?,?,'ABIERTA',?,?,?,?,?,?,?,?,?)""",
            (plan_id, episode_id, symbol.upper(), tipo, ts_ms, float(precio_entrada),
             cantidad, cantidad, objetivo, stop, coste, nota, ts_ms))
        operacion_id = int(cur.lastrowid)
        self._evento(operacion_id, "APERTURA", ts_ms, precio=float(precio_entrada),
                     cantidad=cantidad, nota=nota)
        self.db.commit()
        return self.operacion(operacion_id)

    def _evento(self, operacion_id: int, tipo: str, ts_ms: int,
                precio: Optional[float] = None, cantidad: Optional[float] = None,
                nota: Optional[str] = None, datos: Optional[dict] = None) -> int:
        cur = self.db.execute(
            """INSERT INTO operacion_eventos
               (operacion_id, tipo, ts_ms, precio, cantidad, nota, datos)
               VALUES (?,?,?,?,?,?,?)""",
            (operacion_id, tipo, ts_ms, precio, cantidad, nota,
             json.dumps(datos or {}, ensure_ascii=False)))
        return int(cur.lastrowid)

    # --- Salidas -----------------------------------------------------------

    def parcial(self, operacion_id: int, ts_ms: int, precio: float,
                cantidad: float) -> dict:
        """Cierra parte de la posicion. Sin cantidad declarada no hay parciales."""
        op = self._abierta(operacion_id)
        if op["cantidad"] is None:
            raise ErrorDiario("esta operacion no declaro cantidad: solo admite cierre total")
        if cantidad <= 0:
            raise ErrorDiario("la cantidad del parcial tiene que ser mayor que cero")
        if cantidad > (op["cantidad_abierta"] or 0) + 1e-12:
            raise ErrorDiario("el parcial no puede superar lo que queda abierto")
        restante = round((op["cantidad_abierta"] or 0) - cantidad, 12)
        self._evento(operacion_id, "PARCIAL", ts_ms, precio=float(precio), cantidad=cantidad)
        self.db.execute("UPDATE operaciones SET cantidad_abierta = ? WHERE operacion_id = ?",
                        (restante, operacion_id))
        if restante <= 1e-12:
            self._liquidar(operacion_id, ts_ms, "PARCIALES")
        self.db.commit()
        return self.operacion(operacion_id)

    def cerrar(self, operacion_id: int, ts_ms: int, precio: float,
               motivo: str = "MANUAL") -> dict:
        """Cierra lo que quede abierto al precio indicado."""
        op = self._abierta(operacion_id)
        if not precio or precio <= 0:
            raise ErrorDiario("el cierre necesita un precio mayor que cero")
        self._evento(operacion_id, "CIERRE", ts_ms, precio=float(precio),
                     cantidad=op["cantidad_abierta"])
        self.db.execute("UPDATE operaciones SET cantidad_abierta = 0 WHERE operacion_id = ?",
                        (operacion_id,))
        self._liquidar(operacion_id, ts_ms, motivo)
        self.db.commit()
        return self.operacion(operacion_id)

    def cancelar(self, operacion_id: int, ts_ms: int, nota: str = "") -> dict:
        """
        Se registro por error y nunca existio. No es una perdida de cero: es que
        no hubo operacion, y por eso no entra en ningun agregado.
        """
        self._abierta(operacion_id)
        self._evento(operacion_id, "AJUSTE", ts_ms, nota=nota or "cancelada")
        self.db.execute(
            """UPDATE operaciones SET estado = 'CANCELADA', ts_cierre = ?,
                                      motivo_cierre = 'CANCELADA'
               WHERE operacion_id = ?""", (ts_ms, operacion_id))
        self.db.commit()
        return self.operacion(operacion_id)

    def anotar(self, operacion_id: int, ts_ms: int, nota: str) -> dict:
        if self.operacion(operacion_id) is None:
            raise ErrorDiario(f"la operacion {operacion_id} no existe")
        self._evento(operacion_id, "NOTA", ts_ms, nota=nota)
        self.db.commit()
        return self.operacion(operacion_id)

    def _abierta(self, operacion_id: int) -> dict:
        op = self.operacion(operacion_id)
        if op is None:
            raise ErrorDiario(f"la operacion {operacion_id} no existe")
        if op["estado"] != "ABIERTA":
            raise ErrorDiario(f"la operacion {operacion_id} ya esta {op['estado'].lower()}")
        return op

    def _liquidar(self, operacion_id: int, ts_ms: int, motivo: str) -> None:
        """
        El resultado sale de las salidas registradas, no del plan.

        Con parciales se pondera por cantidad; sin cantidad declarada, la unica
        salida posible es el cierre total. El coste se descuenta una vez, sobre
        el porcentaje, que es como lo mide el resto del sistema.
        """
        op = self.operacion(operacion_id)
        salidas = [e for e in op["eventos"] if e["tipo"] in ("PARCIAL", "CIERRE")
                   and e["precio"]]
        if not salidas:
            return
        pesos = [(e["precio"], e["cantidad"] if e["cantidad"] else 1.0) for e in salidas]
        total = sum(c for _, c in pesos)
        precio_salida = sum(p * c for p, c in pesos) / total if total else salidas[-1]["precio"]
        bruto = (precio_salida / op["precio_entrada"] - 1) * 100.0
        neto = bruto - (op["coste_pct"] or 0.0)
        moneda = (op["cantidad"] * op["precio_entrada"] * neto / 100.0
                  if op["cantidad"] else None)
        self.db.execute(
            """UPDATE operaciones SET estado = 'CERRADA', ts_cierre = ?, precio_salida = ?,
                      motivo_cierre = ?, resultado_pct = ?, resultado_moneda = ?
               WHERE operacion_id = ?""",
            (ts_ms, round(precio_salida, 12), motivo, round(neto, 4),
             round(moneda, 8) if moneda is not None else None, operacion_id))

    # --- Vista en vivo y agregados -----------------------------------------

    def con_precio(self, operacion: dict, precio_actual: Optional[float]) -> dict:
        """
        Añade el resultado no realizado. Va marcado como tal: mientras la
        operacion siga abierta, esa cifra no es una ganancia, es una posicion.
        """
        fila = dict(operacion)
        if fila["estado"] == "ABIERTA" and precio_actual and precio_actual > 0:
            bruto = (precio_actual / fila["precio_entrada"] - 1) * 100.0
            fila["no_realizado_pct"] = round(bruto - (fila["coste_pct"] or 0.0), 4)
            fila["precio_actual"] = precio_actual
        else:
            fila["no_realizado_pct"] = None
        return fila

    def resumen(self) -> dict:
        """
        Cuentas por tipo, sin mezclar. Una ganancia simulada y una declarada no
        se suman: el dia que se sumen, el historial deja de significar nada.
        """
        por_tipo = self.filas(
            """SELECT tipo, estado, COUNT(*) n,
                      ROUND(AVG(resultado_pct), 4) media_pct,
                      ROUND(SUM(resultado_pct), 4) suma_pct,
                      SUM(resultado_pct > 0) positivas
               FROM operaciones GROUP BY tipo, estado""")
        moneda = self.filas(
            """SELECT tipo, ROUND(SUM(resultado_moneda), 8) suma
               FROM operaciones WHERE estado = 'CERRADA' AND resultado_moneda IS NOT NULL
               GROUP BY tipo""")
        return {"por_tipo": por_tipo, "moneda_por_tipo": moneda,
                "abiertas": self.filas(
                    "SELECT COUNT(*) n FROM operaciones WHERE estado = 'ABIERTA'")[0]["n"]}
