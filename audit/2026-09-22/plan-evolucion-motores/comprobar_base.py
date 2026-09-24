"""Read-only source checks. Test databases and transports are mocked by tests."""
import datetime
import json
from pathlib import Path
import subprocess

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
node=Path(r'C:\Users\felix\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
checks=[('backend-tests',[str(ROOT/'backend/venv/Scripts/python.exe'),'-m','unittest','discover','-s','tests','-v'],ROOT/'backend'),('frontend-tests',[str(node),'--test','tests/analysis.test.ts','tests/reading.test.ts'],ROOT/'frontend'),('frontend-types',[str(node),'node_modules/typescript/bin/tsc','-p','tsconfig.app.json','--noEmit','--incremental','false'],ROOT/'frontend')]
results=[]
for name,cmd,cwd in checks:
    try:
        p=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
        output=p.stdout+p.stderr
        (BASE/'datos'/f'{name}.txt').write_text(output,encoding='utf8')
        result={'check':name,'returncode':p.returncode,'tail':output.splitlines()[-9:]}
    except (OSError,subprocess.TimeoutExpired) as exc:
        result={'check':name,'error':str(exc)}
    results.append(result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
(BASE/'datos/baseline-checks.json').write_text(json.dumps({'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'results':results},ensure_ascii=False,indent=2),encoding='utf8')
