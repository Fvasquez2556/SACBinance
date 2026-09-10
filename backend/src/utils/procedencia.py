"""
De donde viene cada fila: que codigo y que configuracion la produjeron.

Sin esto no se puede separar "la regla no funciona" de "cambiamos un umbral a
mitad de la ventana". El 10-sep habia 2.114 outcomes sin las columnas de
contexto y ninguna forma de saber con que version se generaron: los cambios de
parametros y los cambios de mercado quedaban mezclados en la misma tabla.

Se calcula UNA vez al arrancar. El hash cubre solo los ajustes que cambian una
DECISION — umbrales, pesos, vetos, niveles. Los de infraestructura (puertos,
intervalos de volcado, retencion) quedan fuera a proposito: cambiarlos no
altera ninguna señal y ensuciaria el hash con ruido.
"""
from __future__ import annotations

import hashlib
import subprocess
from typing import Optional

_version: Optional[str] = None
_hash: Optional[str] = None

# Prefijos de ajustes que SI cambian una decision. Todo lo que empiece por uno
# de estos entra en el hash.
_PREFIJOS_DECISION = (
    "score_", "base_score", "alerta_", "aviso_", "veto_", "gate_", "macro_",
    "sl_", "tp_", "min_risk", "max_risk", "objetivo_", "retroceso_", "retro_",
    "sr_", "impulso_", "consumido", "fakeout_", "shortlist_", "min_volume",
    "seguimiento_", "hoyo_", "outcome_window", "forma_dip",
    # El universo decide QUE pares pueden dar señal, asi que es una decision
    # como cualquier otra. Se añadio al descubrir que el hash no cambiaba
    # despues de arreglar el filtro de apalancados.
    "universe_", "max_pairs",
)


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return "desconocido"


def _config_hash(settings) -> str:
    partes = []
    for k in sorted(dir(settings)):
        if k.startswith("_") or not any(k.startswith(x) for x in _PREFIJOS_DECISION):
            continue
        try:
            v = getattr(settings, k)
        except Exception:
            continue
        if callable(v):
            continue
        partes.append(f"{k}={v!r}")
    crudo = "|".join(partes)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:12]


def inicializar(settings) -> tuple:
    """Fija la procedencia del proceso. Se llama una vez, al arrancar."""
    global _version, _hash
    _version = _git_commit()
    _hash = _config_hash(settings)
    return _version, _hash


def version() -> Optional[str]:
    return _version


def config_hash() -> Optional[str]:
    return _hash
