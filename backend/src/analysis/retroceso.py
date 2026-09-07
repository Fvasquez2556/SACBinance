"""
El patron que si resulto: "viene de caer".

De los cuatro ingredientes que se midieron el 7-sep-2026 sobre 191 pares y
627k velas de 1m (research/marea_ingredientes.py), este es el unico que
sobrevivio al grupo de control:

    caida previa >= 2%   ->  llega a +3.2% en 3h el 30.1% de las veces
    control (cualquier instante)                     13.1%
    version cobrable (llega antes de caer -1.2%)     19.8% contra 10.5%

n=1673 detecciones deduplicadas. Es 2.3x la tasa base.

Lo que NO entra aqui, y por que
-------------------------------
La "marea tranquila" que se sospechaba (zona quieta, equilibrada, con volumen
seco) no aporta nada medible por encima de esto: +1.6, +2.1 y +0.1 puntos
segun el ingrediente, con signo inconsistente entre ventanas y n~400, mientras
corta la muestra a la cuarta parte. La quietud SIN caida previa rinde POR
DEBAJO del azar (9.1% contra 10.5%): las zonas tranquilas estan en todas
partes, asi que no discriminan.

Aviso: son 2.7 dias de un solo regimen alcista. El patron hay que revalidarlo
segun se acumulen datos.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config.settings import get_settings

INF = float("inf")


@dataclass
class Retroceso:
    detectado: bool = False
    # Segundo nivel, medido despues (research/suelo_maduro.py, 7-sep-2026):
    # esperar a que el precio ya haya rebotado >=1% del suelo sube el acierto
    # cobrable de 19.5% a 24.4% conservando 960 de 1737 detecciones. Esperar a
    # que el suelo "madure" en cambio NO aporta nada: con el minimo en la vela
    # actual el resultado es el mismo que con 5 velas de antiguedad.
    #
    # Se comprobo tambien si el rebote necesita un TECHO — la sospecha era que
    # rebotar mucho significa movimiento ya gastado, como en
    # alerta_consumido_max. research/techo_rebote.py dice que no: el acierto
    # cobrable sube de forma monotona con el rebote (19.7% entre 0 y 0.5%,
    # 23.8% entre 1 y 1.5%, 29.2% entre 2 y 3%, 30.7% entre 3 y 5%). No hay
    # techo, asi que `confirmado` solo tiene suelo. Ojo: la variable es casi un
    # medidor de momento a 8 minutos, y crecer hasta el borde de lo probado
    # sobre 2.7 dias alcistas es justo lo que se da la vuelta en una caida.
    confirmado: bool = False
    caida_pct: Optional[float] = None       # del pico previo al suelo de la zona
    suelo: Optional[float] = None
    pico_previo: Optional[float] = None
    minutos_desde_suelo: int = 0            # cuanto hace que marco ese suelo
    rebote_pct: Optional[float] = None      # cuanto lleva recuperado desde el suelo
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "detectado": self.detectado,
            "confirmado": self.confirmado,
            "caida_pct": self.caida_pct,
            "suelo": self.suelo,
            "pico_previo": self.pico_previo,
            "minutos_desde_suelo": self.minutos_desde_suelo,
            "rebote_pct": self.rebote_pct,
            "reason": self.reason,
        }


def detectar_retroceso(candles_1m: list) -> Retroceso:
    """
    candles_1m: buffer de velas 1m cerradas, la ultima es la actual.

    Replica exactamente la medicion del estudio: el suelo se busca en las
    ultimas `retroceso_velas_zona` velas y el pico en las
    `retroceso_lookback` que las preceden.
    """
    s = get_settings()
    res = Retroceso()

    zona = s.retroceso_velas_zona
    atras = s.retroceso_lookback
    if len(candles_1m) < zona + atras:
        res.reason = "datos insuficientes"
        return res

    v = list(candles_1m)
    seg = v[-zona:]
    prev = v[-(zona + atras):-zona]

    pico = max(c.h for c in prev)
    if pico <= 0:
        return res
    suelo = min(c.l for c in seg)
    res.pico_previo = pico
    res.suelo = suelo
    res.caida_pct = round((suelo - pico) / pico * 100.0, 2)

    # Cuanto hace que se marco ese suelo: distingue "acaba de caer" de
    # "cayo y lleva rato aguantando". Solo informativo, no filtra: el estudio
    # no encontro que la espera cambiara el resultado.
    for i, c in enumerate(reversed(seg)):
        if c.l <= suelo * 1.0001:
            res.minutos_desde_suelo = i
            break

    precio = float(v[-1].c)
    if suelo > 0:
        res.rebote_pct = round((precio - suelo) / suelo * 100.0, 2)

    if res.caida_pct > -s.retroceso_caida_min:
        res.reason = (f"caida previa {res.caida_pct}% insuficiente "
                      f"(minimo {-s.retroceso_caida_min}%)")
        return res

    res.detectado = True
    res.confirmado = (res.rebote_pct is not None
                      and res.rebote_pct >= s.retroceso_rebote_min)
    res.reason = (f"cayo {res.caida_pct}% desde {pico} | suelo {suelo} hace "
                  f"{res.minutos_desde_suelo}min | rebotado {res.rebote_pct}%"
                  + (" | REBOTE CONFIRMADO" if res.confirmado else ""))
    return res


# --- Probabilidad medida de llegar a la meta -------------------------------
#
# research/tabla_meta.py, 215,373 muestras del recorrido real de 1332 senales.
# Para cada muestra: lo que faltaba para la meta, la edad de la senal, y si
# llego en las 6h siguientes.
#
# Por que hace falta la EDAD y no basta la distancia
# --------------------------------------------------
# La tabla anterior era solo por distancia y ponia 12% en la banda 3-5%. Pero
# una senal recien emitida esta SIEMPRE a 3.2% de su meta — precio = entry en
# ese instante — asi que el tablero le pegaba un 12% a cada alerta nueva. La
# medicion directa sobre las 767 senales cerradas, desde su entry y a 6h:
# 27.5%. Un factor de 2.3.
#
# Afinar las bandas no bastaba: "3.0-3.5%" da 15.5% sobre 16,919 muestras, pero
# las que ademas son recien emitidas dan 24.8%. La banda mezclaba dos cosas
# que no se parecen en nada:
#
#     recien emitida a 3.2%     acaba de pasar las puertas del sistema
#     diez horas viva a 3.2%    lleva medio dia sin ir a ninguna parte
#
# La distancia sola no las separa. La edad si.
#
#     le falta        0-15min    15-60min      1-6h       >6h
#       0-0.5%              —       90%         91%        89%
#     2.5-3.0%            32%       25%         24%        19%
#     3.0-3.5%            20%       18%         15%        15%   <- alerta nueva
#       > 7%                —         —          4%         2%
#
# Celdas con menos de 60 casos se dejan a None y caen al tramo de edad
# siguiente, que siempre tiene mas muestra.
_TABLA_META = (
    # (limite de distancia, ((limite de edad en min, prob, n), ...))
    (0.5, ((15, None, 4), (60, 90.0, 60), (360, 91.0, 1224), (INF, 89.0, 5815))),
    (1.0, ((15, None, 3), (60, 81.0, 107), (360, 75.0, 1906), (INF, 73.0, 7135))),
    (1.5, ((15, None, 12), (60, 71.0, 173), (360, 63.0, 2607), (INF, 58.0, 8777))),
    (2.0, ((15, None, 35), (60, 54.0, 411), (360, 43.0, 4302), (INF, 42.0, 10470))),
    (2.5, ((15, 48.0, 125), (60, 45.0, 753), (360, 33.0, 6263), (INF, 30.0, 12668))),
    (3.0, ((15, 32.0, 615), (60, 25.0, 2131), (360, 24.0, 9493), (INF, 19.0, 15548))),
    (3.5, ((15, 20.0, 2368), (60, 18.0, 3619), (360, 15.0, 11652), (INF, 15.0, 15573))),
    (4.0, ((15, 26.0, 400), (60, 18.0, 2104), (360, 15.0, 8785), (INF, 11.0, 13181))),
    (5.0, ((15, 48.0, 64), (60, 21.0, 902), (360, 14.0, 9006), (INF, 7.0, 20796))),
    (7.0, ((15, None, 10), (60, 35.0, 231), (360, 9.0, 4981), (INF, 5.0, 17955))),
    (INF, ((15, None, 0), (60, None, 14), (360, 4.0, 1179), (INF, 2.0, 11916))),
)


def _monotona(tabla: tuple) -> tuple:
    """
    Fuerza que alejarse de la meta nunca suba la probabilidad.

    La tabla cruda tiene celdas que la rompen: 4-5% a los 15min da 48.4% con
    n=64, y 5-7% entre 15 y 60min da 34.6% con n=231, ambas por encima de sus
    vecinas mas cercanas a la meta. Puede ser real —una caida violenta rebota
    violenta— pero con esas muestras es indistinguible del ruido, y en pantalla
    quedaria un par MAS lejos de su objetivo con MAS probabilidad, que se lee
    como un fallo. Se aplica minimo acumulado bajando por la distancia.

    Ajusta hacia abajo, nunca hacia arriba: en la duda, el numero conservador.
    """
    n_edades = len(tabla[0][1])
    tope = [None] * n_edades
    salida = []
    for dist, celdas in tabla:
        fila = []
        for i, (edad, p, n) in enumerate(celdas):
            if p is not None:
                if tope[i] is not None and p > tope[i]:
                    p = tope[i]
                tope[i] = p
            fila.append((edad, p, n))
        salida.append((dist, tuple(fila)))
    return tuple(salida)


_TABLA_META = _monotona(_TABLA_META)


def prob_llegar_meta(dist_pct: float, edad_min: float = 0.0) -> tuple:
    """
    dist_pct: lo que le falta al precio actual para la meta, en %.
    edad_min: minutos desde que se emitio la senal.

    Devuelve (probabilidad_observada, n_de_la_celda). Si ya paso la meta, 100.
    """
    if dist_pct <= 0:
        return 100.0, 0
    for limite, celdas in _TABLA_META:
        if dist_pct < limite:
            # Primera celda de edad que aplique Y tenga muestra suficiente. Si
            # la del tramo joven se descarto por pocas, cae a la siguiente.
            for edad_lim, p, n in celdas:
                if edad_min < edad_lim and p is not None:
                    return p, n
            for edad_lim, p, n in reversed(celdas):
                if p is not None:
                    return p, n
            return 0.0, 0
    return 2.0, 11916
