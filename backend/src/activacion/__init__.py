"""
Fase 7a: las reglas de activacion y reversion, congeladas sin activar nada.

`activacion_enabled` esta en False y no hay rival atado. Lo unico que corre es
el reparto por episodio, en sombra, para que el dia del veredicto la
activacion sea un interruptor y no un estreno.
"""
from src.activacion.almacen import (
    ACTIVACION_SCHEMA,
    ActivacionRechazada,
    AlmacenActivacion,
)
from src.activacion.registro import (
    BRAZO_REFERENCIA,
    BRAZO_RIVAL,
    BRAZOS,
    FRACCION_RIVAL,
    brazo_de,
    huella,
)
from src.activacion.veredicto import elegir_rival, puede_activarse

__all__ = [
    "ACTIVACION_SCHEMA", "ActivacionRechazada", "AlmacenActivacion",
    "BRAZO_REFERENCIA", "BRAZO_RIVAL", "BRAZOS", "FRACCION_RIVAL",
    "brazo_de", "huella", "elegir_rival", "puede_activarse",
]
