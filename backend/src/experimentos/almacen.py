"""
Donde se guarda lo que cada politica congelada habria hecho con cada plan.

Reutiliza el nucleo puro de la fase 2 (`evaluacion/recorrido.py`), que ya esta
auditado: mismas reglas de ventana, de barreras simultaneas, de hueco y de
cobertura. Lo unico que esta fase anade encima es la **entrada diferida**, que
la fase 2 no contempla porque alli la entrada siempre es a mercado.

Todo en sombra. Escribe una tabla propia y no toca ninguna decision.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import replace
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
from src.experimentos.registro import (
    COBERTURA_MINIMA,
    NO_LLENADO,
    SIN_DATOS,
    POLITICAS,
    REGISTRO_VERSION,
    barreras_de,
    declaracion_json,
    huella,
)

MINUTO_MS = 60_000

EXPERIMENTOS_SCHEMA = """
CREATE TABLE IF NOT EXISTS experimento_registro (
    huella       TEXT PRIMARY KEY,
    version      TEXT    NOT NULL,
    declaracion  TEXT    NOT NULL,
    ts_congelado INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS experimento_resultados (
    plan_id        INTEGER NOT NULL,
    politica       TEXT    NOT NULL,
    huella         TEXT    NOT NULL,
    symbol         TEXT    NOT NULL,
    ts_creado      INTEGER NOT NULL,
    entrada        REAL    NOT NULL,
    objetivo       REAL    NOT NULL,
    stop           REAL    NOT NULL,
    tamano         REAL    NOT NULL DEFAULT 1.0,
    ms_fill        INTEGER,
    desenlace      TEXT,
    ms_desenlace   INTEGER,
    resultado_pct  REAL,
    resultado_r    REAL,
    mfe_pct        REAL,
    mae_pct        REAL,
    n_velas        INTEGER NOT NULL DEFAULT 0,
    cobertura      REAL,
    completa       INTEGER NOT NULL DEFAULT 0,
    ambiguo        INTEGER NOT NULL DEFAULT 0,
    salto          INTEGER NOT NULL DEFAULT 0,
    ts_evaluado    INTEGER NOT NULL,
    PRIMARY KEY (plan_id, politica, huella)
);
CREATE INDEX IF NOT EXISTS idx_exp_pendiente ON experimento_resultados (completa, ts_evaluado);
CREATE INDEX IF NOT EXISTS idx_exp_politica ON experimento_resultados (politica, ts_creado);
CREATE INDEX IF NOT EXISTS idx_exp_symbol ON experimento_resultados (symbol, ts_creado);
"""


def _fill(velas, limite: float, inicio_ms: int, fin_ms: int) -> tuple:
    """
    ¿Llego el precio a la entrada diferida dentro de la ventana, y cuando?

    Devuelve (indice_de_la_vela, ms_desde_el_inicio) o (None, None).

    **Solo cuentan las velas cuyo minuto entero cae en la ventana**, la misma
    regla que el nucleo de la fase 2. Sin esto, una vela que EMPIEZA justo al
    vencer el plazo contaba como compra: la orden se llenaba despues de que el
    plan hubiera caducado.

    El fill se anota al precio del limite, no al de apertura. Si el mercado
    abriera con hueco por debajo, el comprador real conseguiria mejor precio;
    aqui se anota el peor.
    """
    for i, v in enumerate(velas):
        if v.t < inicio_ms or v.t + MINUTO_MS > fin_ms:
            continue
        if v.l <= limite:
            return i, v.t - inicio_ms
    return None, None


def _aplicar_vela_del_fill(plan: Plan, estado: Estado, vela: Vela) -> Estado:
    """
    La vela en la que se lleno la orden, con lo que SI se sabe de ella.

    La version anterior la descartaba entera para no regalar un maximo anterior
    al fill. El efecto colateral era mucho peor: tambien perdia el MINIMO, asi
    que una vela que llenaba a 98,5 y se desplomaba a 95 —por debajo del stop—
    no dejaba rastro, y la subida de la vela siguiente se anotaba como
    OBJETIVO. El motor fabricaba una ganancia de una perdida. Lo encontro una
    revision externa.

    Lo que se sabe y lo que no, dentro de ese minuto:
    - El **minimo vino despues del fill**. La orden se lleno bajando, asi que
      cualquier precio por debajo del limite es posterior. Si ese minimo
      perfora el stop, la operacion se paro. Eso es conocimiento, no suposicion.
    - El **maximo puede ser anterior al fill**, asi que el objetivo NO se
      concede aqui. Si ademas lo tocaba, la fila queda marcada `ambiguo`.
    """
    e = replace(estado)
    dt = vela.t - plan.inicio_ms
    e.n_velas += 1
    e.t_ultima = vela.t
    e.ms_ultima = dt
    e.ms_primera = dt
    pct = lambda x: (x / plan.entrada - 1.0) * 100.0
    e.mfe_pct = pct(vela.h)
    e.mae_pct = pct(vela.l)
    e.ms_mfe = e.ms_mae = dt
    e.cierre_pct = pct(vela.c)

    if vela.l <= plan.stop:
        e.ms_stop = dt
        e.precio_stop = plan.stop
        e.desenlace, e.ms_desenlace = "STOP", dt
        if vela.h >= plan.objetivo:
            e.ambiguo = True
    elif vela.h >= plan.objetivo:
        # Toco el objetivo, pero pudo hacerlo antes de que la orden se llenara.
        # No se concede y se deja constancia.
        e.ambiguo = True
    return e


class AlmacenExperimentos:
    def __init__(self, conn: sqlite3.Connection, *, coste_pct: float = 0.5,
                 max_por_pasada: int = 40) -> None:
        self.db = conn
        self.coste_pct = coste_pct
        self.max_por_pasada = max_por_pasada

    # --- El candado --------------------------------------------------------

    def congelar(self, ahora_ms: Optional[int] = None) -> dict:
        """
        Deja constancia de la declaracion vigente. Idempotente por huella.

        Si la huella ya existe, devuelve la fecha en que se congelo — no la
        pisa. Es lo que impide que un cambio de politica se presente como si
        hubiera estado ahi desde el principio.
        """
        h = huella()
        ahora_ms = ahora_ms or int(time.time() * 1000)
        fila = self.db.execute(
            "SELECT ts_congelado FROM experimento_registro WHERE huella = ?",
            (h,)).fetchone()
        if fila:
            return {"huella": h, "ts_congelado": fila[0], "nuevo": False}
        self.db.execute(
            """INSERT INTO experimento_registro (huella, version, declaracion,
                                                 ts_congelado)
               VALUES (?,?,?,?)""",
            (h, REGISTRO_VERSION, declaracion_json(), ahora_ms))
        self.db.commit()
        return {"huella": h, "ts_congelado": ahora_ms, "nuevo": True}

    def congelado_ms(self) -> Optional[int]:
        fila = self.db.execute(
            "SELECT ts_congelado FROM experimento_registro WHERE huella = ?",
            (huella(),)).fetchone()
        return fila[0] if fila else None

    # --- Lectura -----------------------------------------------------------

    def filas(self, sql: str, args=()) -> list[dict]:
        cur = self.db.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _velas(self, symbol: str, desde_ms: int, hasta_ms: int):
        for t, o, h, l, c in self.db.execute(
                """SELECT open_time, o, h, l, c FROM klines
                   WHERE symbol = ? AND tf = '1m' AND open_time >= ? AND open_time <= ?
                   ORDER BY open_time""",
                (symbol, desde_ms, hasta_ms)):
            yield Vela(t=t, o=o, h=h, l=l, c=c)

    # --- Evaluacion --------------------------------------------------------

    def evaluar_plan(self, fila_plan: dict, ahora_ms: int) -> int:
        """Corre las politicas congeladas sobre un plan. Devuelve cuantas midio."""
        h = huella()
        coste = fila_plan.get("coste_pct")
        coste = float(coste) if coste is not None else self.coste_pct
        inicio = int(fila_plan["ts_creado"])
        horizonte = int(fila_plan.get("horizonte_ms") or 12 * 3600_000)
        velas = list(self._velas(symbol=fila_plan["symbol"],
                                 desde_ms=inicio,
                                 hasta_ms=min(ahora_ms, inicio + horizonte)))
        n = 0
        for politica in POLITICAS:
            b = barreras_de(politica, fila_plan, coste)
            if b is None:
                continue
            self._medir(fila_plan, politica, b, velas, inicio, horizonte,
                        ahora_ms, coste, h)
            n += 1
        return n

    def _medir(self, fila_plan, politica, b, velas, inicio, horizonte,
               ahora_ms, coste, h) -> None:
        ms_fill = None
        usadas = velas
        arranque = inicio

        fin = inicio + horizonte
        vela_fill = None

        if b.entrada_limite is not None:
            idx, ms_fill = _fill(velas, b.entrada_limite, inicio, fin)
            if idx is None:
                # No hubo operacion. Se guarda igual: la proporcion de ordenes
                # que nunca se llenan es parte del resultado de la politica,
                # no un hueco en los datos.
                self._guardar(fila_plan, politica, b, None, None, ahora_ms,
                              inicio, horizonte, h, velas=velas,
                              desenlace=(NO_LLENADO if completa_ventana(inicio, horizonte, ahora_ms)
                                         else None))
                return
            vela_fill = velas[idx]
            usadas = velas[idx + 1:]
            arranque = vela_fill.t

        plan = Plan(entrada=b.entrada, objetivo=b.objetivo, stop=b.stop,
                    inicio_ms=arranque, horizonte_ms=max(0, fin - arranque))
        estado = Estado()
        if vela_fill is not None:
            estado = _aplicar_vela_del_fill(plan, estado, vela_fill)
        for v in usadas:
            estado = avanzar(plan, estado, v)
        estado = cerrar_por_reloj(plan, estado, ahora_ms)
        self._guardar(fila_plan, politica, b, plan, estado, ahora_ms, inicio,
                      horizonte, h, ms_fill=ms_fill, coste=coste, velas=velas)

    def _guardar(self, fila_plan, politica, b, plan, estado, ahora_ms, inicio,
                 horizonte, h, *, ms_fill=None, coste=0.0, desenlace=None,
                 velas=None) -> None:
        # Vencer por reloj no es lo mismo que haber observado el recorrido.
        # Sin velas, el evaluador devolvia VENCIDO y -0,5 % neto, y esa
        # perdida inventada entraba en la media como una operacion resuelta.
        # Peor: el plan quedaba excluido de pendientes para siempre, asi que
        # un retraso en recuperar velas fijaba el resultado falso.
        #
        # La regla de cobertura se declara en el registro congelado, ANTES de
        # ver que politica gana: por debajo de COBERTURA_MINIMA no hay
        # medicion, hay SIN_DATOS, y la fila se puede volver a medir.
        cob = _cobertura_observada(velas, inicio, horizonte, ahora_ms)
        if cob < COBERTURA_MINIMA:
            self.db.execute(
                """INSERT INTO experimento_resultados
                   (plan_id, politica, huella, symbol, ts_creado, entrada,
                    objetivo, stop, tamano, desenlace, cobertura, completa,
                    ts_evaluado)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(plan_id, politica, huella) DO UPDATE SET
                     desenlace=excluded.desenlace, cobertura=excluded.cobertura,
                     completa=excluded.completa, ts_evaluado=excluded.ts_evaluado""",
                (fila_plan["plan_id"], politica.clave, h, fila_plan["symbol"],
                 fila_plan["ts_creado"], b.entrada, b.objetivo, b.stop,
                 b.tamano_relativo, SIN_DATOS, cob, 0, ahora_ms))
            return

        if plan is None or estado is None:
            datos = dict(desenlace=desenlace, ms_desenlace=None, resultado_pct=None,
                         resultado_r=None, mfe_pct=None, mae_pct=None, n_velas=0,
                         cobertura=cob, completa=int(completa_ventana(inicio, horizonte, ahora_ms)),
                         ambiguo=0, salto=0)
        else:
            bruto = resultado_politica(plan, estado, coste)
            # El tamano relativo iguala el riesgo monetario: un stop el doble
            # de ancho lleva media posicion, asi que su resultado por unidad de
            # capital arriesgado es la mitad. Sin esto, el eje del stop premia
            # al que mas arriesga.
            neto = None if bruto is None else round(bruto * b.tamano_relativo, 4)
            riesgo = (b.entrada - b.stop) / b.entrada * 100.0
            datos = dict(
                desenlace=estado.desenlace, ms_desenlace=estado.ms_desenlace,
                resultado_pct=neto,
                resultado_r=(None if bruto is None or riesgo <= 0
                             else round(bruto / riesgo, 4)),
                mfe_pct=estado.mfe_pct, mae_pct=estado.mae_pct,
                n_velas=estado.n_velas,
                cobertura=cobertura(plan, estado, ahora_ms),
                completa=int(completa_ventana(inicio, horizonte, ahora_ms)),
                ambiguo=int(estado.ambiguo), salto=int(estado.salto))

        self.db.execute(
            """INSERT INTO experimento_resultados
               (plan_id, politica, huella, symbol, ts_creado, entrada, objetivo,
                stop, tamano, ms_fill, desenlace, ms_desenlace, resultado_pct,
                resultado_r, mfe_pct, mae_pct, n_velas, cobertura, completa,
                ambiguo, salto, ts_evaluado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(plan_id, politica, huella) DO UPDATE SET
                 ms_fill=excluded.ms_fill, desenlace=excluded.desenlace,
                 ms_desenlace=excluded.ms_desenlace,
                 resultado_pct=excluded.resultado_pct,
                 resultado_r=excluded.resultado_r, mfe_pct=excluded.mfe_pct,
                 mae_pct=excluded.mae_pct, n_velas=excluded.n_velas,
                 cobertura=excluded.cobertura, completa=excluded.completa,
                 ambiguo=excluded.ambiguo, salto=excluded.salto,
                 ts_evaluado=excluded.ts_evaluado""",
            (fila_plan["plan_id"], politica.clave, h, fila_plan["symbol"],
             fila_plan["ts_creado"], b.entrada, b.objetivo, b.stop,
             b.tamano_relativo, ms_fill, datos["desenlace"], datos["ms_desenlace"],
             datos["resultado_pct"], datos["resultado_r"], datos["mfe_pct"],
             datos["mae_pct"], datos["n_velas"], datos["cobertura"],
             datos["completa"], datos["ambiguo"], datos["salto"], ahora_ms))

    # --- Pasada de mantenimiento -------------------------------------------

    def evaluar_pendientes(self, ahora_ms: int) -> dict:
        """
        Un plan se mide UNA VEZ, cuando su ventana ya cerro.

        **El turno es por ultimo INTENTO, no por fecha del plan.** Un plan sin
        cobertura suficiente queda `SIN_DATOS` y vuelve a la cola para poder
        medirse si las velas llegan tarde. Ordenando por `ts_creado`, esos
        planes —que son los mas viejos— se reelegian en CADA pasada y se
        comian el presupuesto entero: tres planes bloquearon la cola durante
        12 horas mientras 828 esperaban, y la prueba prospectiva no acumulaba
        nada. Es exactamente la misma hambruna que la fase 2 tuvo que corregir
        en su evaluador, reproducida aqui.

        Ahora un reintento va al final de la cola: cuesta un turno por ciclo
        completo en vez de todos.

        La fase 2 reevalua cada plan en cada pasada porque su tablero necesita
        el recorrido en curso. Aqui no: el registro congelado dice que una
        ventana abierta no entra en ninguna media, asi que medirla antes de
        tiempo es trabajo tirado — y caro, porque cada medida vuelve a recorrer
        las 720 velas por cada una de las 11 politicas. Medido: 83 ms por plan.
        Esperar a que cierre convierte 47 pasadas en una.

        Y solo planes creados DESPUES de la congelacion: terreno nuevo, que es
        la tercera puerta.
        """
        desde = self.congelado_ms()
        if desde is None:
            return {"evaluados": 0, "pendientes": 0, "sin_congelar": True}
        h = huella()
        pendientes = self.filas(
            """SELECT p.plan_id, p.symbol, p.entry, p.take_profit, p.stop_loss,
                      p.ts_creado, p.horizonte_ms, p.coste_pct
               FROM planes p
               LEFT JOIN (SELECT plan_id, MIN(ts_evaluado) ts_evaluado
                          FROM experimento_resultados
                          WHERE huella = ? AND desenlace IS NOT ?
                          GROUP BY plan_id) medidos ON medidos.plan_id = p.plan_id
               LEFT JOIN (SELECT plan_id, MAX(ts_evaluado) ts_intento
                          FROM experimento_resultados WHERE huella = ?
                          GROUP BY plan_id) intentos ON intentos.plan_id = p.plan_id
               WHERE p.ts_creado >= ?
                 AND medidos.plan_id IS NULL
                 AND p.ts_creado + COALESCE(p.horizonte_ms, ?) <= ?
               ORDER BY COALESCE(intentos.ts_intento, 0), p.ts_creado
               LIMIT ?""",
            (h, SIN_DATOS, h, desde, 12 * 3600_000, ahora_ms,
             self.max_por_pasada))
        res = {"evaluados": 0, "medidas": 0, "pendientes": len(pendientes)}
        for fila in pendientes:
            res["medidas"] += self.evaluar_plan(fila, ahora_ms)
            res["evaluados"] += 1
        if res["evaluados"]:
            self.db.commit()
        return res

    # --- Informe -----------------------------------------------------------

    def resumen(self) -> dict:
        """
        El embudo entero, siempre.

        La version anterior filtraba `NO_LLENADO` ANTES de agrupar, asi que su
        propia columna salia siempre a cero y una politica que nunca se llenara
        desaparecia del informe. El registro congelado exige reportar la
        proporcion de ordenes no ejecutadas: una orden que no existio no es una
        operacion de cero, pero tampoco se borra del denominador.

        `elegibles` cuenta todas las oportunidades; `media_pct` promedia solo
        las que tienen resultado medible.
        """
        return {
            "huella": huella(),
            "congelado_ms": self.congelado_ms(),
            "evaluador": EVALUADOR_VERSION,
            "por_politica": self.filas(
                """SELECT politica,
                          COUNT(*) elegibles,
                          SUM(desenlace IN ('OBJETIVO','STOP','VENCIDO')) resueltas,
                          SUM(desenlace = 'OBJETIVO') objetivo,
                          SUM(desenlace = 'STOP') stop,
                          SUM(desenlace = 'VENCIDO') vencido,
                          SUM(desenlace = 'NO_LLENADO') no_llenado,
                          SUM(desenlace = 'SIN_DATOS') sin_datos,
                          SUM(desenlace IS NULL) abiertas,
                          ROUND(AVG(resultado_pct), 4) media_pct,
                          ROUND(AVG(resultado_r), 4) media_r,
                          COUNT(DISTINCT symbol) pares
                   FROM experimento_resultados
                   WHERE huella = ?
                   GROUP BY politica ORDER BY politica""", (huella(),)),
            # Cuantos planes de terreno nuevo esperan todavia a que cierre su
            # ventana. Es la cifra que dice si la prueba avanza; las filas
            # abiertas ya no existen por diseno.
            "pendientes_de_medir": self._pendientes_de_medir(),
        }

    def _pendientes_de_medir(self) -> int:
        desde = self.congelado_ms()
        if desde is None:
            return 0
        return self.db.execute(
            """SELECT COUNT(*) FROM planes p
               LEFT JOIN (SELECT plan_id FROM experimento_resultados
                          WHERE huella = ? AND desenlace IS NOT ?
                          GROUP BY plan_id) e ON e.plan_id = p.plan_id
               WHERE p.ts_creado >= ? AND e.plan_id IS NULL""",
            (huella(), SIN_DATOS, desde)).fetchone()[0]


def completa_ventana(inicio_ms: int, horizonte_ms: int, ahora_ms: int) -> bool:
    return ahora_ms >= inicio_ms + horizonte_ms


def _cobertura_observada(velas, inicio_ms: int, horizonte_ms: int,
                         ahora_ms: int) -> float:
    """
    Velas vistas de la ventana entera frente a las que deberia haber.

    Se mide sobre el plan, no sobre el tramo posterior al fill: una entrada
    diferida que se llena en el minuto 700 no tiene mala cobertura por eso.
    """
    if velas is None:
        return 0.0
    fin = min(ahora_ms, inicio_ms + horizonte_ms)
    esperadas = max(0, (fin - inicio_ms) // MINUTO_MS)
    if esperadas <= 0:
        return 0.0
    vistas = sum(1 for v in velas
                 if inicio_ms <= v.t and v.t + MINUTO_MS <= fin)
    return round(min(1.0, vistas / esperadas), 4)
