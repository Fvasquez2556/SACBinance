"""Ejecuta core.py + historico.py en el servidor (solo lectura) y congela la salida con su huella."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).parent
REPO = ROOT.parents[2]
OUT = ROOT / sys.argv[1] if len(sys.argv) > 1 else ROOT       # p. ej. "v2": cada versión en su carpeta
OUT.mkdir(exist_ok=True)
core = (REPO / "moderadas_sombra/core.py").read_bytes()
driver = (ROOT / "historico.py").read_bytes()
reglas = (ROOT / "REGLAS.md").read_bytes()
t0 = time.time()
r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sac",
                    "nice -n 19 ionice -c3 python3 -"], input=core + b"\n\n" + driver,
                   capture_output=True, timeout=3600)
if r.returncode:
    raise SystemExit("Fallo remoto: " + r.stderr.decode(errors="replace")[-3000:])
blob = r.stdout
lineas = gzip.decompress(blob).decode().splitlines()
cabecera, cierre = json.loads(lineas[0]), json.loads(lineas[-1])
(OUT / "fuente.jsonl.gz").write_bytes(blob)
meta = {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob),
        "core_sha256": hashlib.sha256(core).hexdigest(), "historico_sha256": hashlib.sha256(driver).hexdigest(),
        "reglas_sha256": hashlib.sha256(reglas).hexdigest(), **cabecera, **cierre,
        "lineas": len(lineas), "segundos": round(time.time() - t0, 1)}
meta.pop("tipo", None)
(OUT / "fuente-metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(meta, indent=2, ensure_ascii=False))
