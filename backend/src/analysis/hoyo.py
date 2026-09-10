"""
Medicion en sombra: entrar en el hoyo, no en la señal.

Que se mide y por que
---------------------
Hoy el sistema propone entrar al precio de la señal. Medido sobre 1347 señales
con velas de 1m, eso da **-0.26% por operacion, con el intervalo de confianza
entero por debajo de cero** (bootstrap agrupado por par). Es decir: entrar
donde el sistema dice pierde dinero de forma consistente.

Felix propuso otra cosa a partir del caso MARSCOIN del 9-sep: el sistema
predijo suelo 0.13254 y techo 0.15192, y el precio toco 0.13100 y luego
0.15200. Clavo los dos extremos. Si la señal acierta el RANGO aunque falle el
punto de entrada, entonces no hay que comprar en la señal — hay que esperar a
que el precio baje cerca del stop y comprar ahi, apuntando al mismo TP.

Simulado sobre esos mismos 1347 casos, el precio baja hasta el disparo en el
83.7% de las señales, y la regla con stop fijo de -3% dio +0.25% por operacion
[+0.05, +0.46]. Pero ese numero se eligio DESPUES de ver los datos, y el 67%
del beneficio viene de posiciones que a las 24h seguian abiertas. Por eso esto
se mide en sombra y no decide nada.

Las tres reglas
---------------
Todas entran al mismo sitio — `stop_loss` de la señal mas un margen — y
apuntan al mismo take profit que el sistema fijo. Cambia solo donde va el stop:

    A     al mismo % por debajo de la nueva entrada que el sistema pedia
          desde la suya (si el sistema pedia -4.65%, el stop va -4.65% bajo
          el hoyo, no bajo la señal)
    C2    stop fijo de -2.0% bajo la entrada
    C3    stop fijo de -3.0% bajo la entrada

La version literal de la idea — dejar el stop en el SL del sistema, con solo
el margen de riesgo — se midio y es la peor de todas (77.7% paradas). No se
sigue.

Supuestos, todos conservadores
------------------------------
- El fill se apunta al precio del disparo, no al de apertura de la vela. Si el
  mercado abriera con hueco por debajo, el comprador real conseguiria mejor
  precio; aqui se anota el peor.
- Si una vela contiene a la vez el disparo y el stop, se cuenta como parada.
  No se puede saber el orden dentro del minuto, y suponer lo contrario seria
  regalarse operaciones.
- Si una vela contiene a la vez el stop y el take profit, se cuenta como
  parada, por lo mismo.
- En la vela de ENTRADA no se concede el objetivo. Su maximo pudo ocurrir
  ANTES de que la orden se llenara: una vela que recorre 104 -> 106 -> 99 ->
  100 con la compra en 100 tiene su techo en un momento en que todavia no
  habia posicion. Se marca `hoyo_ambiguo` y se espera a la siguiente vela.

Esto NO decide nada. Ninguna alerta, ningun score, ningun veto lee estos
campos. Solo escribe en `outcomes` para poder validarlo contra dias que
todavia no existen.
"""
from __future__ import annotations

from typing import Optional

from src.config.settings import get_settings

# Las tres reglas y como sale el stop de cada una a partir del fill.
# 'a' es la unica que depende de la señal (usa su sl_pct); las otras son fijas.
REGLAS = ("a", "c2", "c3")

RESUELTO_TP = "TP"
RESUELTO_SL = "SL"

# Celdas del cruce que mejor separo en la simulacion: la velocidad con que el
# precio cae hasta el hoyo, y el ancho del stop que el sistema habia pedido.
CELDA_RAPIDO_ESTRECHO = "RAPIDO_ESTRECHO"
CELDA_RAPIDO_ANCHO = "RAPIDO_ANCHO"
CELDA_LENTO_ESTRECHO = "LENTO_ESTRECHO"
CELDA_LENTO_ANCHO = "LENTO_ANCHO"


def _stops(fill: float, sl_pct: Optional[float]) -> dict:
    """El nivel de stop de cada regla, en precio."""
    s = get_settings()
    niveles = {
        "c2": fill * (1.0 - s.hoyo_stop_c2 / 100.0),
        "c3": fill * (1.0 - s.hoyo_stop_c3 / 100.0),
    }
    # La regla A necesita el ancho que el sistema pidio desde su propia entrada.
    if sl_pct is not None and sl_pct < 0:
        niveles["a"] = fill * (1.0 + sl_pct / 100.0)
    return niveles


def _celda(ms_disparo: int, sl_pct: Optional[float]) -> str:
    s = get_settings()
    rapido = ms_disparo < s.hoyo_rapido_min * 60_000
    ancho = sl_pct is not None and sl_pct <= -s.hoyo_sl_ancho
    if rapido:
        return CELDA_RAPIDO_ANCHO if ancho else CELDA_RAPIDO_ESTRECHO
    return CELDA_LENTO_ANCHO if ancho else CELDA_LENTO_ESTRECHO


def inicial(stop_loss: Optional[float]) -> dict:
    """Campos que se escriben al abrir el outcome. Vacio si no hay stop."""
    if not stop_loss or stop_loss <= 0:
        return {}
    margen = get_settings().hoyo_margen_pct
    return {"hoyo_disparo": stop_loss * (1.0 + margen / 100.0)}


def campos_memoria() -> dict:
    """Las columnas que arrancan a None en la fila en memoria."""
    campos = {
        "ms_hoyo": None, "hoyo_fill": None, "hoyo_celda": None,
        "hoyo_ambiguo": None,
        "hoyo_mfe_pct": None, "hoyo_mae_pct": None,
        "ms_hoyo_mfe": None, "ms_hoyo_mae": None,
        "precio_ultimo": None,
    }
    for r in REGLAS:
        campos[f"hoyo_{r}"] = None
        campos[f"ms_hoyo_{r}"] = None
    return campos


def actualizar(row: dict, cambios: dict, transcurrido: int,
               high: float, low: float, close: float) -> None:
    """
    Avanza la medicion en sombra con una vela 1m cerrada.

    Escribe en `row` (la fila en memoria) y en `cambios` (lo que se persiste),
    igual que hace el resto del tracker. No devuelve nada ni decide nada.
    """
    disparo = row.get("hoyo_disparo")
    if not disparo:
        return

    row["precio_ultimo"] = cambios["precio_ultimo"] = close

    # --- ¿ya entro? ---------------------------------------------------
    if row.get("ms_hoyo") is None:
        if low > disparo:
            return                       # el precio no ha bajado hasta ahi
        row["ms_hoyo"] = cambios["ms_hoyo"] = transcurrido
        # Se anota el peor fill posible: el propio nivel del disparo.
        row["hoyo_fill"] = cambios["hoyo_fill"] = disparo
        row["hoyo_celda"] = cambios["hoyo_celda"] = _celda(
            transcurrido, row.get("sl_pct"))
        row["hoyo_mfe_pct"] = cambios["hoyo_mfe_pct"] = 0.0
        row["hoyo_mae_pct"] = cambios["hoyo_mae_pct"] = 0.0
        # ¿Esta vela habria dado el objetivo? Si es que si, no se puede saber
        # si el maximo llego antes o despues del fill. Se anota la ambiguedad
        # y NO se concede.
        tp0 = row.get("take_profit")
        if tp0 and high >= tp0:
            row["hoyo_ambiguo"] = cambios["hoyo_ambiguo"] = 1
        else:
            row["hoyo_ambiguo"] = cambios["hoyo_ambiguo"] = 0
        # El stop SI se aplica en esta vela: es el supuesto pesimista.
        fill0 = row["hoyo_fill"]
        niveles0 = _stops(fill0, row.get("sl_pct"))
        for regla0, stop0 in niveles0.items():
            if low <= stop0:
                row[f"hoyo_{regla0}"] = cambios[f"hoyo_{regla0}"] = RESUELTO_SL
                row[f"ms_hoyo_{regla0}"] = cambios[f"ms_hoyo_{regla0}"] = transcurrido
        return   # el objetivo espera a la siguiente vela

    fill = row.get("hoyo_fill")
    if not fill:
        return

    # --- excursiones desde el hoyo ------------------------------------
    up = (high - fill) / fill * 100.0
    dn = (low - fill) / fill * 100.0
    if up > (row.get("hoyo_mfe_pct") or 0.0):
        row["hoyo_mfe_pct"] = cambios["hoyo_mfe_pct"] = round(up, 3)
        row["ms_hoyo_mfe"] = cambios["ms_hoyo_mfe"] = transcurrido
    if dn < (row.get("hoyo_mae_pct") or 0.0):
        row["hoyo_mae_pct"] = cambios["hoyo_mae_pct"] = round(dn, 3)
        row["ms_hoyo_mae"] = cambios["ms_hoyo_mae"] = transcurrido

    # --- desenlace de cada regla --------------------------------------
    tp = row.get("take_profit")
    niveles = _stops(fill, row.get("sl_pct"))
    for regla, stop in niveles.items():
        k = f"hoyo_{regla}"
        if row.get(k) is not None:
            continue                      # esta regla ya se resolvio
        if low <= stop:                   # el stop manda: ver docstring
            res = RESUELTO_SL
        elif tp and high >= tp:
            res = RESUELTO_TP
        else:
            continue
        row[k] = cambios[k] = res
        row[f"ms_hoyo_{regla}"] = cambios[f"ms_hoyo_{regla}"] = transcurrido


def resultado(row: dict, regla: str) -> Optional[float]:
    """
    El % que habria dado esa regla en esa señal. None si nunca entro.

    Tres desenlaces: TP (se cobra el take profit del sistema), SL (se paga el
    stop de la regla) o ninguno, en cuyo caso se valora al ultimo precio visto
    dentro de la ventana.
    """
    fill = row.get("hoyo_fill")
    if not fill:
        return None
    des = row.get(f"hoyo_{regla}")
    if des == RESUELTO_TP:
        tp = row.get("take_profit")
        return (tp - fill) / fill * 100.0 if tp else None
    if des == RESUELTO_SL:
        stop = _stops(fill, row.get("sl_pct")).get(regla)
        return (stop - fill) / fill * 100.0 if stop else None
    ultimo = row.get("precio_ultimo")
    return (ultimo - fill) / fill * 100.0 if ultimo else None
