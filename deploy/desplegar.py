"""Despliegue del backend de SAC desde un commit de git, archivo por archivo y con sumas verificadas.

Por qué existe: el servidor se actualizaba copiando archivos a mano y nadie podía saber qué versión
corría (INFORME del 3-oct-2026, E5). Este script sube SOLO lo que cambió entre dos commits y deja
constancia en el servidor (DESPLIEGUE.json).

    python deploy/desplegar.py estado                       # qué difiere entre el servidor y git
    python deploy/desplegar.py plan --base A --commit B     # qué haría, sin tocar nada
    python deploy/desplegar.py aplicar --base A --commit B  # respalda, sube, verifica y registra

Reglas:
- Solo toca los archivos que cambian entre BASE y COMMIT dentro de backend/main.py, backend/src,
  backend/tests y backend/requirements.txt. El resto del servidor queda igual.
- Si un archivo del servidor no coincide ni con BASE ni con COMMIT, alguien lo cambió fuera de git:
  se detiene y lo muestra (usa --forzar solo si sabes por qué).
- Antes de reemplazar, guarda los originales en respaldos/<fecha>-<commit>/antes.tgz.
- No reinicia nada: al final indica el comando (necesita sudo).
Las sumas se comparan sin retornos de carro (\\r), para que una copia hecha desde Windows no parezca distinta.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

HOST = "sac"
RAIZ = "/home/flox/sacbinance"
RAICES = ["backend/main.py", "backend/src", "backend/tests", "backend/requirements.txt"]
REPO = Path(__file__).resolve().parents[1]


def git(*args: str, binario: bool = False):
    r = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=REPO, capture_output=True, check=True)
    return r.stdout if binario else r.stdout.decode("utf-8")


def ssh(comando: str, entrada: bytes | None = None) -> str:
    r = subprocess.run(["ssh", HOST, comando], input=entrada, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ssh falló ({r.returncode}): {r.stderr.decode('utf-8', 'replace')[:500]}")
    return r.stdout.decode("utf-8", "replace")


def suma(datos: bytes) -> str:
    return hashlib.sha256(datos.replace(b"\r", b"")).hexdigest()


def contenido(commit: str, ruta: str) -> bytes:
    return git("cat-file", "blob", f"{commit}:{ruta}", binario=True)


def resolver(commit: str) -> str:
    return git("rev-parse", "--verify", f"{commit}^{{commit}}").strip()


def sumas_servidor(rutas: list[str]) -> dict[str, str | None]:
    """sha256 (sin \\r) de cada ruta en el servidor; None si no existe."""
    if not rutas:
        return {}
    script = (f"cd {RAIZ} && while IFS= read -r f; do "
              "if [ -f \"$f\" ]; then printf '%s %s\\n' \"$(tr -d '\\r' < \"$f\" | sha256sum | cut -d' ' -f1)\" \"$f\"; "
              "else printf 'FALTA %s\\n' \"$f\"; fi; done")
    salida = ssh(script, ("\n".join(rutas) + "\n").encode())
    res: dict[str, str | None] = {}
    for linea in salida.splitlines():
        h, _, ruta = linea.partition(" ")
        res[ruta] = None if h == "FALTA" else h
    return res


def cambios(base: str, commit: str) -> list[tuple[str, str]]:
    salida = git("diff", "--name-status", "--no-renames", base, commit, "--", *RAICES)
    return [(l.split("\t")[0], l.split("\t")[1]) for l in salida.splitlines() if l.strip()]


def plan(base: str, commit: str) -> dict:
    lista = cambios(base, commit)
    servidor = sumas_servidor([r for _, r in lista])
    filas, deriva = [], []
    for tipo, ruta in lista:
        h_base = suma(contenido(base, ruta)) if tipo != "A" else None
        h_nuevo = suma(contenido(commit, ruta)) if tipo != "D" else None
        h_srv = servidor.get(ruta)
        if h_srv == h_nuevo:
            accion = "ya_esta"
        elif h_srv == h_base:
            accion = "borrar" if tipo == "D" else "actualizar"
        else:
            accion = "DERIVA"          # el servidor tiene otra cosa: cambiado fuera de git
            deriva.append(ruta)
        filas.append({"ruta": ruta, "tipo": tipo, "accion": accion,
                      "base": h_base, "nuevo": h_nuevo, "servidor": h_srv})
    return {"base": base, "commit": commit, "archivos": filas, "deriva": deriva}


def imprimir(p: dict) -> None:
    print(f"base   {p['base'][:10]}\ncommit {p['commit'][:10]}")
    for f in p["archivos"]:
        print(f"  {f['accion']:10s} {f['tipo']}  {f['ruta']}")
    if not p["archivos"]:
        print("  (nada cambia en backend entre esos commits)")


def aplicar(p: dict, forzar: bool) -> None:
    if p["deriva"] and not forzar:
        sys.exit("ALTO: estos archivos del servidor no coinciden ni con la base ni con el commit "
                 "(alguien los cambió fuera de git):\n  " + "\n  ".join(p["deriva"]))
    subir = [f for f in p["archivos"] if f["accion"] in ("actualizar", "DERIVA") and f["tipo"] != "D"]
    borrar = [f for f in p["archivos"] if f["accion"] == "borrar"]
    if not subir and not borrar:
        print("Nada que hacer: el servidor ya tiene este commit en esos archivos.")
        return
    marca = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    respaldo = f"respaldos/{marca}-{p['commit'][:10]}"
    existentes = [f["ruta"] for f in subir + borrar if f["servidor"] is not None]

    # 1. respaldo de lo que se va a reemplazar
    ssh(f"cd {RAIZ} && mkdir -p {respaldo}" +
        (f" && tar czf {respaldo}/antes.tgz " + " ".join(f"'{r}'" for r in existentes) if existentes else ""))

    # 2. subir a una carpeta temporal y verificar ahí
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in subir:
            datos = contenido(p["commit"], f["ruta"])
            info = tarfile.TarInfo(f["ruta"])
            info.size, info.mode, info.mtime = len(datos), 0o644, int(time.time())
            tar.addfile(info, io.BytesIO(datos))
    tmp = f"{respaldo}/nuevo"
    ssh(f"cd {RAIZ} && mkdir -p {tmp} && tar xzf - -C {tmp}", buf.getvalue())
    en_tmp = sumas_servidor([f"{tmp}/{f['ruta']}" for f in subir])
    malos = [f["ruta"] for f in subir if en_tmp.get(f"{tmp}/{f['ruta']}") != f["nuevo"]]
    if malos:
        sys.exit("ALTO: la copia temporal no coincide; no se tocó nada en producción:\n  " + "\n  ".join(malos))

    # 3. mover a su lugar (mv dentro del mismo disco: cada archivo cambia de golpe)
    movs = " && ".join(f"mkdir -p \"$(dirname '{f['ruta']}')\" && mv -f '{tmp}/{f['ruta']}' '{f['ruta']}'"
                       for f in subir)
    dels = " && ".join(f"rm -f '{f['ruta']}'" for f in borrar)
    ssh(f"cd {RAIZ} && " + " && ".join(x for x in (movs, dels) if x))

    # 4. verificar en su lugar y dejar constancia
    final = sumas_servidor([f["ruta"] for f in subir + borrar])
    mal = [f["ruta"] for f in subir if final.get(f["ruta"]) != f["nuevo"]] + \
          [f["ruta"] for f in borrar if final.get(f["ruta"]) is not None]
    registro = {"commit": p["commit"], "base": p["base"], "utc": marca, "respaldo": respaldo,
                "archivos": [{"ruta": f["ruta"], "sha256_sin_cr": f["nuevo"], "accion": f["accion"]} for f in subir] +
                            [{"ruta": f["ruta"], "accion": "borrado"} for f in borrar],
                "verificado": not mal}
    ssh(f"cd {RAIZ} && cat > DESPLIEGUE.json && cat DESPLIEGUE.json >> respaldos/historial.jsonl && echo >> respaldos/historial.jsonl",
        json.dumps(registro, ensure_ascii=False).encode())
    if mal:
        sys.exit("ALTO: tras mover, estos archivos no coinciden (el respaldo está en "
                 f"{RAIZ}/{respaldo}/antes.tgz):\n  " + "\n  ".join(mal))
    print(f"Listo: {len(subir)} archivos actualizados y {len(borrar)} borrados, verificados por sha256.")
    print(f"Respaldo: {RAIZ}/{respaldo}/antes.tgz")
    print("Falta reiniciar (pide tu contraseña):  sudo systemctl restart sacbinance")


def estado(commit: str) -> None:
    """Compara todo el backend del servidor con un commit (por defecto HEAD)."""
    rutas = [r for r in git("ls-tree", "-r", "--name-only", commit, "--", *RAICES).splitlines()
             if "__pycache__" not in r]
    servidor = sumas_servidor(rutas)
    iguales, distintos, faltan = [], [], []
    for r in rutas:
        h = servidor.get(r)
        if h is None:
            faltan.append(r)
        elif h == suma(contenido(commit, r)):
            iguales.append(r)
        else:
            distintos.append(r)
    en_servidor = set(ssh(f"cd {RAIZ} && find backend/src backend/tests backend/main.py -type f -name '*.py' "
                          "-not -path '*/__pycache__/*' | sort").split())
    solo_servidor = sorted(en_servidor - set(rutas))
    try:
        ultimo = json.loads(ssh(f"cat {RAIZ}/DESPLIEGUE.json 2>/dev/null || echo null"))
    except json.JSONDecodeError:
        ultimo = None
    print(f"commit {commit[:10]}: {len(iguales)} iguales, {len(distintos)} distintos, "
          f"{len(faltan)} faltan en el servidor, {len(solo_servidor)} solo en el servidor")
    for nombre, lista in (("DISTINTOS", distintos), ("FALTAN EN EL SERVIDOR", faltan),
                          ("SOLO EN EL SERVIDOR (no están en git)", solo_servidor)):
        if lista:
            print(f"\n{nombre}:")
            for r in lista:
                print("  " + r)
    print("\nÚltimo despliegue registrado:", (ultimo or {}).get("commit", "ninguno")[:10] if ultimo else "ninguno")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["estado", "plan", "aplicar"])
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--base", help="commit que el servidor tiene hoy en esos archivos (por defecto, el padre)")
    ap.add_argument("--forzar", action="store_true", help="sube aunque el servidor tenga cambios fuera de git")
    a = ap.parse_args()
    commit = resolver(a.commit)
    if a.modo == "estado":
        estado(commit)
        return
    base = resolver(a.base or f"{commit}^")
    p = plan(base, commit)
    imprimir(p)
    if a.modo == "aplicar":
        aplicar(p, a.forzar)
    elif p["deriva"]:
        print("\nOJO: hay archivos con DERIVA; 'aplicar' se detendrá sin --forzar.")


if __name__ == "__main__":
    main()
