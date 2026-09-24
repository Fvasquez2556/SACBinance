"""
¿Estorba la IA a SAC? Se mide igual antes y durante, para poder compararlo.

La señal principal es la edad de la ultima vela de 1 m que SAC ya guardo: si el
recolector o el volcado a disco se retrasan porque Kronos se come la CPU, esa
edad sube. Se muestrea igual durante el rodaje (sin Kronos ni API) y durante la
medicion; el veredicto compara los dos p95.

Tambien se anota el PID de SAC: si cambia, SAC se reinicio, y un reinicio
durante la medicion hay que explicarlo antes de absolver a la IA.
En Windows (desarrollo) lo que depende de /proc queda en null.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sac_ia.fuente import FuenteSAC

PROC = Path("/proc")


def _leer(ruta: Path) -> Optional[str]:
    try:
        return ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def carga_1m() -> Optional[float]:
    texto = _leer(PROC / "loadavg")
    return float(texto.split()[0]) if texto else None


def mem_disponible_mb() -> Optional[float]:
    texto = _leer(PROC / "meminfo")
    for linea in (texto or "").splitlines():
        if linea.startswith("MemAvailable:"):
            return round(int(linea.split()[1]) / 1024, 1)
    return None


def rss_mb(pid: int | str = "self") -> Optional[float]:
    texto = _leer(PROC / str(pid) / "status")
    for linea in (texto or "").splitlines():
        if linea.startswith("VmRSS:"):
            return round(int(linea.split()[1]) / 1024, 1)
    return None


def cpu_s(pid: int) -> Optional[float]:
    texto = _leer(PROC / str(pid) / "stat")
    if not texto:
        return None
    campos = texto.rsplit(")", 1)[-1].split()
    try:
        return round((int(campos[11]) + int(campos[12])) / os.sysconf("SC_CLK_TCK"), 2)
    except (IndexError, ValueError, AttributeError, OSError):
        return None


def pid_sac(sac_backend: Path) -> Optional[int]:
    """El proceso `python main.py` cuyo directorio de trabajo es el backend de SAC."""
    if not PROC.is_dir():
        return None
    objetivo = str(Path(sac_backend).resolve())
    for entrada in PROC.iterdir():
        if not entrada.name.isdigit():
            continue
        cmd = _leer(entrada / "cmdline") or ""
        if "main.py" not in cmd:
            continue
        try:
            if os.readlink(entrada / "cwd") == objetivo:
                return int(entrada.name)
        except OSError:
            continue
    return None


def muestrear(fuente: FuenteSAC, sac_backend: Path, modo: str, ahora_ms: int) -> dict:
    pid = pid_sac(sac_backend)
    return {"ts_ms": ahora_ms, "modo": modo,
            "edad_vela_ms": fuente.edad_ultima_vela_ms(ahora_ms),
            "carga_1m": carga_1m(), "mem_disponible_mb": mem_disponible_mb(),
            "rss_ia_mb": rss_mb(), "sac_pid": pid,
            "sac_rss_mb": rss_mb(pid) if pid else None,
            "sac_cpu_s": cpu_s(pid) if pid else None}
