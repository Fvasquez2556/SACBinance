"""Convierte la fuente congelada del histórico en la referencia (referencia.json) y elige la
variante principal según REGLAS.md. Se ejecuta en local; no toca el servidor."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parent
REPO = ROOT.parents[2]
sys.path.insert(0, str(REPO))

from moderadas_sombra import core as K          # noqa: E402
from moderadas_sombra import resumen as S       # noqa: E402

def cargar(ruta):
    blob = ruta.read_bytes()
    lineas = gzip.decompress(blob).decode().splitlines()
    cab = json.loads(lineas[0])
    regs = [json.loads(x) for x in lineas[1:-1]]
    return cab, regs, hashlib.sha256(blob).hexdigest()



if __name__ == "__main__":
    OUT = ROOT / sys.argv[1] if len(sys.argv) > 1 else ROOT
    cab, regs, sha = cargar(OUT / "fuente.jsonl.gz")
    ref, completos = S.referencia(regs, sha)
    principal, top = S.elegir_principal(ref, completos)
    ref["principal"] = {k: principal[k] for k in ("ventana_min", "variante", "nombre", "neto_por_senal", "mitades",
                                                  "positiva_en_ambas", "cumple_reglas", "ic95_por_moneda")}
    ref["mejores_moderada_primera"] = top
    (OUT / "referencia.json").write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "PRINCIPAL.json").write_text(json.dumps(ref["principal"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"senales": ref["senales"], "principal": ref["principal"], "top": top}, ensure_ascii=False,
                     indent=1))
