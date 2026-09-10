import json,pathlib
R=pathlib.Path(__file__).resolve().parent
p=json.loads((R/'profile.json').read_text());q=json.loads((R/'queries.json').read_text());prov=json.loads((R/'provenance.json').read_text())
data={'queries':{}}
for key,rows in p.items():
 if not rows or key in ('cases','foreign_keys'):continue
 data['queries'][key]={'rows':rows,'source':{'name':'SQLite de producción: '+key,'type':'file','provider':'SQLite','files':['snapshot.db'],'tables':[],'sql':q.get(key,''),'description':'Copia consistente y de solo lectura. Commit '+prov['commit']+'. Métricas descriptivas; no son operaciones ejecutadas.','timeRange':{'start':'2026-09-05T03:56:00Z','end':'2026-09-10T21:57:00Z'},'caveats':['Ventanas de outcomes con huecos y defectos temporales; señales simuladas, sin fills reales.']}}
(R/'report_snapshot.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
