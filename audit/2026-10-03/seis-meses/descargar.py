"""Descarga las velas de 1 minuto oficiales de Binance (data.binance.vision) y verifica cada archivo.

- Meses completos: marzo a agosto de 2026 (archivos mensuales).
- Septiembre y 1-oct: archivos diarios (el mensual de septiembre aún no está publicado).
- Cada .zip se comprueba contra el .CHECKSUM (sha256) que publica Binance. Si no coincide, se borra y se reintenta.
- Solo descarga datos de mercado públicos: no usa claves ni toca el servidor de SAC.

Destino: E:/SACBinance/data/binance_vision/spot_1m/<SYMBOL>/ (carpeta fuera de git).
Uso:  python descargar.py [--prueba]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI.parents[2] / "data" / "binance_vision" / "spot_1m"
BASE = "https://data.binance.vision/data/spot"
MESES = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
DIAS = [(dt.date(2026, 9, 1) + dt.timedelta(days=k)).isoformat() for k in range(31)]   # 1-sep .. 1-oct
HILOS = 8


def bajar(url: str, intentos: int = 4) -> bytes | None:
    for k in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sacbinance-investigacion"}),
                                        timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"no se pudo bajar {url}")


def tarea(symbol: str, tipo: str, periodo: str) -> dict:
    nombre = f"{symbol}-1m-{periodo}.zip"
    url = f"{BASE}/{tipo}/klines/{symbol}/1m/{nombre}"
    ruta = DESTINO / symbol / nombre
    res = {"symbol": symbol, "archivo": nombre, "tipo": tipo}
    try:
        suma_txt = bajar(url + ".CHECKSUM")
        if suma_txt is None:
            res["estado"] = "no_existe"
            return res
        esperado = suma_txt.decode().split()[0].strip().lower()
        if ruta.exists() and hashlib.sha256(ruta.read_bytes()).hexdigest() == esperado:
            res.update(estado="ya_estaba", sha256=esperado, bytes=ruta.stat().st_size)
            return res
        for _ in range(3):
            datos = bajar(url)
            if datos is None:
                res["estado"] = "no_existe"
                return res
            if hashlib.sha256(datos).hexdigest() == esperado:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                tmp = ruta.with_suffix(".parcial")
                tmp.write_bytes(datos)
                tmp.replace(ruta)
                res.update(estado="ok", sha256=esperado, bytes=len(datos))
                return res
        res["estado"] = "checksum_no_coincide"
    except Exception as e:  # se registra y se sigue con el resto
        res.update(estado="error", detalle=str(e)[:200])
    return res


def main():
    monedas = json.loads((AQUI / "monedas.json").read_text(encoding="utf-8"))["monedas"]
    if "--prueba" in sys.argv:
        monedas = monedas[:2]
    trabajos = [(s, "monthly", m) for s in monedas for m in MESES] + [(s, "daily", d_) for s in monedas for d_ in DIAS]
    print(f"{len(monedas)} monedas, {len(trabajos)} archivos -> {DESTINO}", flush=True)
    t0 = time.time()
    resultados = []
    with ThreadPoolExecutor(HILOS) as ex:
        futuros = [ex.submit(tarea, *t) for t in trabajos]
        for k, f in enumerate(as_completed(futuros), 1):
            resultados.append(f.result())
            if k % 500 == 0 or k == len(futuros):
                mb = sum(r.get("bytes", 0) for r in resultados) / 1e6
                print(f"{k}/{len(futuros)} | {mb:.0f} MB | {time.time() - t0:.0f} s", flush=True)
    resumen = {}
    for r in resultados:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
    manifiesto = {"creado_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                  "fuente": BASE, "meses": MESES, "dias": [DIAS[0], DIAS[-1]], "monedas": len(monedas),
                  "resumen": resumen, "segundos": round(time.time() - t0),
                  "megabytes": round(sum(r.get("bytes", 0) for r in resultados) / 1e6, 1),
                  "archivos": sorted(resultados, key=lambda r: (r["symbol"], r["archivo"]))}
    (AQUI / ("descarga_prueba.json" if "--prueba" in sys.argv else "descarga.json")).write_bytes(
        json.dumps(manifiesto, indent=1, ensure_ascii=False).encode())
    print(json.dumps({k: v for k, v in manifiesto.items() if k != "archivos"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
