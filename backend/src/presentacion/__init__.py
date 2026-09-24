"""Fase 6: lo que las fases 1-5 miden, puesto donde se pueda leer."""
from src.presentacion.contrato import BRUTO, NETO, Porcentaje, contrato_de_lectura
from src.presentacion.oportunidades import oportunidades_vivas
from src.presentacion.resultados import POBLACIONES, resultados_por_poblacion

__all__ = ["contrato_de_lectura", "Porcentaje", "BRUTO", "NETO",
           "oportunidades_vivas", "resultados_por_poblacion", "POBLACIONES"]
