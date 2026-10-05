"""Resume analisis7.json en tablas para RESULTADOS.md (no calcula nada nuevo)."""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
d = json.loads((AQUI / "analisis7.json").read_text(encoding="utf-8"))
C = d["coste_principal"]


def fmt(x):
    return "—" if x is None else f"{x:+.2f}"


print(f"filas {d['filas']}, monedas {d['monedas']}, meses {d['meses']}")
print(f"\nCANDIDATAS con coste {C}: {len(d['candidatas'])}")
for c in d["candidatas"]:
    print(" ", c["idea"], c["geometria"], "SÓLIDA" if c["solida"] else "", c["ic95"])

# la mejor geometría de cada idea según la EXPLORACIÓN (como se habría elegido sin ver el futuro)
print("\n| idea | elegida en exploración | exploración: aciertos · neto | comprobación: aciertos · neto | meses + | neto con 0,2 (expl / comp) |")
print("|---|---|---|---|---|---|")
for nombre, g in d["ideas"].items():
    validas = {k: v for k, v in g.items() if v["exploracion"].get("n")}
    if not validas:
        continue
    k, v = max(validas.items(), key=lambda kv: kv[1]["exploracion"][f"neto_{C}"])
    e, c = v["exploracion"], v["comprobacion"]
    print(f"| {nombre} | {k} | {e['aciertos_pct']:.0f} % · {fmt(e[f'neto_{C}'])} | "
          f"{c.get('aciertos_pct', 0):.0f} % · {fmt(c.get(f'neto_{C}'))} | {v['meses_positivos']}/7 | "
          f"{fmt(e['neto_0.2'])} / {fmt(c.get('neto_0.2'))} |")

print("\nGeometría de Felix (12 h, +2,67 / −1,8), neto por mes con coste", C)
print("| idea | " + " | ".join(d["meses"]) + " |")
for nombre, g in d["ideas"].items():
    v = g.get("12h|TP2.67|SL1.8")
    if v:
        print(f"| {nombre[:45]} | " + " | ".join(fmt(v["meses"].get(m)) for m in d["meses"]) + " |")

print("\nMODELO (largo, +2,67/−1,8, 12 h):")
for k, v in d["modelo"].items():
    if k.startswith("top"):
        e, c = v["exploracion"], v["comprobacion"]
        print(f"  {k}: expl {e.get('aciertos_pct')} % {fmt(e.get(f'neto_{C}'))} n={e.get('n')} | "
              f"comp {c.get('aciertos_pct')} % {fmt(c.get(f'neto_{C}'))} n={c.get('n')} | meses {v['meses']}")
print("  pesos:", d["modelo"]["pesos_mayores"][:8])
print("\nRÉGIMEN:", json.dumps(d["regimen"], ensure_ascii=False))
