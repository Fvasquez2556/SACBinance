"""
El contrato de lectura: que significa cada porcentaje que aparece en pantalla.

El problema que resuelve
------------------------
El numero 3,2 estaba haciendo DOS trabajos distintos en el sistema, y la
interfaz los pintaba igual:

    objetivo_operador_pct = 3.2    se compara contra `reward_neto_pct`  -> NETO
    outcome_tracker.OBJETIVO = 3.2 es una excursion de precio (`mfe_pct`) -> BRUTO

Son iguales hoy por casualidad. `PairCard` dice «Precio toco +3.2%» (bruto) y
`analysis.ts` dice «por debajo del objetivo de +3.2%» (neto): mismo numero,
misma pinta, significados distintos. Y ademas estaban escritos a mano en unos
quince sitios, asi que cambiar el ajuste dejaba todos esos textos mintiendo.

Si la fase 5 recomienda mover el objetivo a +4,2 % neto —que es justo su rival
principal—, sin esto la pantalla seguiria diciendo 3,2 y algunos textos
mentirian de una forma que PARECE correcta, que es la peor.

La regla que impone este modulo
-------------------------------
**Ningun porcentaje viaja sin decir si es bruto o neto.** Un `Porcentaje` sabe
su tipo, sabe convertirse al otro y sabe escribirse. La interfaz no vuelve a
componer la etiqueta a mano.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import get_settings

BRUTO = "BRUTO"
NETO = "NETO"


@dataclass(frozen=True)
class Porcentaje:
    """Un porcentaje que sabe lo que es."""
    pct: float
    tipo: str
    coste_pct: float = 0.0

    def a_neto(self) -> "Porcentaje":
        if self.tipo == NETO:
            return self
        return Porcentaje(round(self.pct - self.coste_pct, 4), NETO, self.coste_pct)

    def a_bruto(self) -> "Porcentaje":
        if self.tipo == BRUTO:
            return self
        return Porcentaje(round(self.pct + self.coste_pct, 4), BRUTO, self.coste_pct)

    @property
    def etiqueta(self) -> str:
        """«+3,2 % neto». Nunca sale un porcentaje sin su tipo."""
        signo = "+" if self.pct >= 0 else ""
        return f"{signo}{self.pct:g} % {self.tipo.lower()}"

    def como_dict(self) -> dict:
        return {"pct": self.pct, "tipo": self.tipo, "etiqueta": self.etiqueta,
                "coste_pct": self.coste_pct}


def contrato_de_lectura() -> dict:
    """
    Lo que la interfaz necesita para escribir cualquier porcentaje sin
    inventarse ni el numero ni su naturaleza.

    Se publica en `/api/contrato` y lo consumen el tablero y Telegram. Nadie
    vuelve a escribir "3.2" a mano.
    """
    s = get_settings()
    from src.analysis.outcome_tracker import OBJETIVO as HITO_BRUTO

    coste = s.coste_operacion_pct
    objetivo = Porcentaje(s.objetivo_operador_pct, NETO, coste)
    hito = Porcentaje(HITO_BRUTO, BRUTO, coste)

    return {
        # A donde apunta el operador. Es NETO: ya descuenta comisiones y
        # deslizamiento, y es contra lo que se mide `objetivo_alcanzable`.
        "objetivo_operador": objetivo.como_dict(),
        "objetivo_operador_bruto": objetivo.a_bruto().como_dict(),
        # El hito con el que se mide la FORMA del recorrido. Es BRUTO: es una
        # excursion de precio, no una ganancia embolsada. Coincide en numero
        # con el objetivo por historia, no por definicion.
        "hito_referencia": hito.como_dict(),
        "hito_referencia_neto": hito.a_neto().como_dict(),
        "coinciden": abs(objetivo.a_bruto().pct - hito.pct) < 1e-9,
        "coste_pct": coste,
        "horizonte_horas": s.signal_expiry_hours,
        "episodio_horas": s.episodio_silencio_horas,
        "exigir_objetivo": s.exigir_objetivo_operador,
        "aviso": (
            "El objetivo del operador es NETO: ya descuenta el coste. El hito "
            "de referencia es BRUTO: es un movimiento del precio, no una "
            "ganancia cobrada. Coincidir en numero no es significar lo mismo."),
    }
