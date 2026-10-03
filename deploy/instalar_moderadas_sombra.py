"""Instalador sin privilegios del observador moderadas_sombra; conserva el resto del crontab.

Ejecutar después de copiar moderadas_sombra/ y deploy/ejecutar_moderadas_sombra.sh al
repositorio del servidor. No reinicia ni configura ningún servicio existente.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/home/flox/sacbinance')
MARK = '# SAC_MODERADAS_SOMBRA_V1'
DATA = ROOT / 'moderadas_sombra/datos'
COMMAND = ('* * * * * /bin/sh /home/flox/sacbinance/deploy/ejecutar_moderadas_sombra.sh > '
           '/home/flox/sacbinance/moderadas_sombra/datos/ultimo-ciclo.json 2> '
           '/home/flox/sacbinance/moderadas_sombra/datos/ultimo-error.log ' + MARK)


def install():
    source = ROOT / 'backend/data/sacbinance.db'
    if not source.is_file():
        raise RuntimeError('Falta la base de producción; no se programó nada')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'cron']).returncode:
        raise RuntimeError('cron no está activo; no se programó nada')
    if not (ROOT / 'moderadas_sombra/referencia.json').is_file():
        raise RuntimeError('Falta referencia.json (sale del histórico); no se programó nada')
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    script = ROOT / 'deploy/ejecutar_moderadas_sombra.sh'
    script.chmod(0o700)
    tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'moderadas_sombra/tests', '-t', '.'],
                           cwd=ROOT)
    if tests.returncode:
        raise RuntimeError('Fallaron las pruebas; no se programó nada')
    first = subprocess.run([sys.executable, '-m', 'moderadas_sombra', 'una-vez'], cwd=ROOT,
                           capture_output=True, text=True, timeout=55)
    if first.returncode:
        raise RuntimeError('Falló el ciclo inicial de solo lectura: ' + first.stdout + first.stderr)
    prior = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    if prior.returncode and 'no crontab' not in prior.stderr.lower():
        raise RuntimeError('No se pudo leer el crontab: ' + prior.stderr)
    before = prior.stdout if prior.returncode == 0 else ''
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    backup = DATA / ('crontab-antes-' + stamp + '.txt')
    backup.write_text(before, encoding='utf-8')
    lines = [line for line in before.splitlines() if MARK not in line]
    after = '\n'.join(lines + [COMMAND]) + '\n'
    subprocess.run(['crontab', '-'], input=after, text=True, check=True)
    actual = subprocess.check_output(['crontab', '-l'], text=True)
    if actual != after:
        raise RuntimeError('El crontab instalado no coincide con el solicitado')
    files = sorted(p for p in (ROOT / 'moderadas_sombra').rglob('*')
                   if p.is_file() and 'datos' not in p.parts and '__pycache__' not in p.parts)
    receipt = {'installed_utc': stamp, 'scheduler': 'crontab del usuario, cada minuto', 'backup': str(backup),
               'source_mode': 'ro + query_only + autorizador SELECT', 'shadow_db': str(DATA / 'moderadas_sombra_v2.db'),
               'crontab_sha256': hashlib.sha256(actual.encode()).hexdigest(),
               'files_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
               'initial_cycle': json.loads(first.stdout)}
    (DATA / 'instalacion_v2.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    install()
