"""Reutiliza el inventario de solo lectura e incluye informe y cartera."""
from pathlib import Path

source_path = Path(__file__).resolve().parent.parent / 'revision-codex' / 'inspeccionar.py'
source = source_path.read_text(encoding='utf8')
needle = "'almacen.py')]"
assert needle in source
source = source.replace(needle, "'almacen.py', 'informe.py', 'cartera.py')]")
exec(compile(source, str(source_path), 'exec'))
