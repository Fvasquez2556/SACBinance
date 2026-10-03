import argparse
import json
from pathlib import Path
import sys

from .informe import generar
from .observador import ciclo


def main():
    raiz = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Sombra de las señales MODERADA (y FUERTE como comparación)")
    p.add_argument("orden", choices=("una-vez", "informe"))
    p.add_argument("--fuente", type=Path, default=raiz.parent / "backend/data/sacbinance.db")
    p.add_argument("--db", type=Path, default=raiz / "datos" / "moderadas_sombra_v2.db")
    p.add_argument("--referencia", type=Path, default=raiz / "referencia.json")
    p.add_argument("--max-senales", type=int, default=400)
    a = p.parse_args()
    if a.orden == "informe":
        print(generar(a.db, a.referencia))
        return 0
    r = ciclo(a.fuente, a.db, max_senales=a.max_senales)
    print(json.dumps(r, ensure_ascii=False, allow_nan=False))
    return 1 if r.get("errores") else 0


if __name__ == "__main__":
    sys.exit(main())
