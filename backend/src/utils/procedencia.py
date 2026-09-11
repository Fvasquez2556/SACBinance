"""
De donde viene cada fila: que codigo y que configuracion la produjeron.

Sin esto no se puede separar "la regla no funciona" de "cambiamos un umbral a
mitad de la ventana". El 10-sep habia 2.114 outcomes sin las columnas de
contexto y ninguna forma de saber con que version se generaron: los cambios de
parametros y los cambios de mercado quedaban mezclados en la misma tabla.

Se calcula UNA vez al arrancar.

Que entra en el hash, y por que cambio el criterio
--------------------------------------------------
Hasta el esquema v11 el hash se construia con una lista de PREFIJOS permitidos
("score_", "sl_", ...). Un ajuste que no empezara por uno de ellos quedaba
fuera en silencio, y la auditoria del 10-sep encontro cinco que deciden y no
entraban: `rr_target`, `coste_operacion_pct`, `exigir_objetivo_operador`,
`flow_min_trades` y `rise_z`. Cambiar cualquiera de ellos NO movia el hash, asi
que dos configuraciones que producen señales distintas quedaban etiquetadas
como la misma.

Ahora es al reves: entra TODO ajuste declarado, salvo una lista corta y
explicita de los que no pueden alterar ningun numero (credenciales, endpoints,
rutas, puerto y nivel de log). El error posible cambia de lado a proposito: de
mas entra el hash cambia cuando no hacia falta — dos versiones donde habia una,
que se nota y se corrige — y de menos se pierde la evidencia sin que nadie se
entere, que es lo que paso.
"""
from __future__ import annotations

import hashlib
import subprocess
from typing import Optional

_version: Optional[str] = None
_hash: Optional[str] = None

# Version del ESQUEMA del hash. Va dentro del texto que se firma, asi que los
# hashes de antes de este cambio no se pueden confundir con los de ahora: son
# valores distintos porque cubren cosas distintas.
_ESQUEMA = "v2"

# Lo unico que queda fuera. Nada de esto entra en una decision: son la puerta
# de entrada de los datos, donde se guardan y como se registra.
_EXCLUIDOS = frozenset({
    "binance_rest_base",
    "binance_ws_raw",
    "db_path",
    "api_host",
    "api_port",
    "cors_origins",
    "log_level",
    # Credenciales: ademas de no decidir nada, no tienen que acabar en ningun
    # texto que se firme y se guarde.
    "telegram_token",
    "telegram_chat_id",
})


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return "desconocido"


def _campos(settings) -> list:
    """
    Los ajustes declarados, en orden estable.

    Se prefiere `model_dump()` (pydantic) porque da exactamente los campos
    declarados: sin propiedades derivadas, sin metodos y sin atributos de
    clase. `dir()` es el plan B para cualquier objeto de configuracion que no
    sea un modelo pydantic.
    """
    try:
        datos = settings.model_dump()
        return sorted(datos.items())
    except Exception:
        pass
    out = []
    for k in sorted(dir(settings)):
        if k.startswith("_"):
            continue
        try:
            v = getattr(settings, k)
        except Exception:
            continue
        if callable(v):
            continue
        out.append((k, v))
    return out


def _config_hash(settings) -> str:
    partes = [_ESQUEMA]
    for k, v in _campos(settings):
        if k in _EXCLUIDOS:
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
