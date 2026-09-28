"""
Lo que depende de la maquina, no del estudio: rutas, topes de gasto, hilos.

Todo sale de variables de entorno `IA_*` (o de `ia_sombra/.env`, que no se
sube al repositorio). Cambiar algo de aqui no cambia la huella: son decisiones
operativas. Lo que cambia la medicion vive en `registro.py`.

La clave de OpenAI NUNCA va en el entorno ni en el repositorio: se lee de un
fichero con permisos 0600 que solo este servicio puede abrir. SAC no la ve.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ_IA = Path(__file__).resolve().parent.parent       # ia_sombra/
RAIZ_REPO = RAIZ_IA.parent                               # SACBinance/


def _leer_env(ruta: Path) -> dict:
    """`CLAVE=valor` por linea; sin comillas ni interpolacion."""
    datos = {}
    if not ruta.is_file():
        return datos
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        datos[clave.strip()] = valor.strip()
    return datos


@dataclass(frozen=True)
class Config:
    sac_db: Path
    sac_backend: Path
    ia_db: Path
    artefactos: Path
    clave_openai: Path
    kronos_codigo: Path
    kronos_hilos: int
    kronos_timeout_s: float
    binance_rest: str
    poll_s: float
    tope_diario_usd: float
    tope_total_usd: float
    llm_timeout_s: float
    salud_cada_s: float
    etiquetas_cada_s: float


def cargar(env: dict | None = None) -> Config:
    fichero = _leer_env(RAIZ_IA / ".env")
    e = {**fichero, **os.environ, **(env or {})}

    def ruta(clave: str, defecto: Path) -> Path:
        valor = e.get(clave)
        return Path(valor).expanduser().resolve() if valor else defecto

    return Config(
        sac_db=ruta("IA_SAC_DB", RAIZ_REPO / "backend" / "data" / "sacbinance.db"),
        sac_backend=ruta("IA_SAC_BACKEND", RAIZ_REPO / "backend"),
        ia_db=ruta("IA_DB", RAIZ_IA / "datos" / "ia_sombra.db"),
        artefactos=ruta("IA_ARTEFACTOS", RAIZ_IA / "datos" / "artefactos"),
        clave_openai=ruta("IA_CLAVE_OPENAI", RAIZ_IA / "secretos" / "openai.key"),
        kronos_codigo=ruta("IA_KRONOS_CODIGO", RAIZ_IA / "vendor" / "Kronos"),
        kronos_hilos=int(e.get("IA_KRONOS_HILOS", "1")),
        kronos_timeout_s=float(e.get("IA_KRONOS_TIMEOUT_S", "60")),
        binance_rest=e.get("IA_BINANCE_REST", "https://api.binance.com"),
        poll_s=float(e.get("IA_POLL_S", "5")),
        tope_diario_usd=float(e.get("IA_TOPE_DIARIO_USD", "1.50")),
        tope_total_usd=float(e.get("IA_TOPE_TOTAL_USD", "15.00")),
        llm_timeout_s=float(e.get("IA_LLM_TIMEOUT_S", "60")),
        salud_cada_s=float(e.get("IA_SALUD_CADA_S", "30")),
        etiquetas_cada_s=float(e.get("IA_ETIQUETAS_CADA_S", "300")),
    )
