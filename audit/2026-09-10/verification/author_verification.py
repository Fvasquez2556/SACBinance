"""Build a durable, evidence-bound follow-up report; preserve original audit."""
import collections,datetime,json,pathlib,shutil,uuid
R=pathlib.Path(__file__).resolve().parent
def read(name):return json.loads((R/name).read_text(encoding='utf-8'))
old=json.loads((R.parent/'findings.json').read_text(encoding='utf-8'))
p=read('provenance.json');d=read('data_checks.json');b=read('behaviour_checks.json');runtime=read('runtime_checks.json');extra=read('extra_checks.json')
details=[
('F01','Parcial','P1','Se añadió un bucle REST y cobertura al cerrar.',
 'Persisten 2,344 minutos-par ausentes en 224 símbolos después del despliegue (2,342 huecos internos, de 1–2 minutos). Una vela ADAUSDT ausente sí existe en Binance. El detector mira únicamente el último minuto; un hueco interno deja de ser visible cuando vuelve el stream. Además, preload_1m ignora cualquier reparación de un par ya cargado y preload_htf vuelve a añadir velas repetidas. El hidratador tampoco reprocesa outcomes durante la reparación periódica. El log registra 65 reparaciones y 126 reconexiones de shortlist en el tramo inspeccionado; ambos streams siguen acoplados.',
 'Separar la suscripción de trades, detectar huecos por secuencia temporal, fusionar buffers sin duplicados y reprocesar los seguimientos desde la primera vela ausente. Exigir continuidad antes de considerar válido un desenlace.',
 'backend/main.py:271; backend/src/state/engine.py:347; backend/src/data_ingestion/hydrator.py:92; backend/src/data_ingestion/ws_manager.py:213'),
('F02','Parcial','P1','El corte previo a la emisión, el rechazo posterior a 24h y el cierre por reloj pasan sus pruebas. Ya no hay outcomes abiertos con más de 24h.',
 'Queda un borde temporal: se compara la apertura de la vela con el vencimiento, aunque su máximo puede ocurrir después. Una prueba concede TP a una vela que termina fuera de ventana. También permanecen 27 signals OPEN de más de 12h, hasta 138.27h; el reloj nuevo solo cierra outcomes. No hay todavía ninguna ventana de 24h madura de b8a3d64.',
 'Definir intervalos completos por cierre de vela y dar un reloj común a signals, outcomes y alertas; no atribuir un precio actual al vencimiento histórico sin reconstrucción.',
 'backend/src/analysis/outcome_tracker.py:471; backend/src/analysis/signal_tracker.py:80; backend/main.py:315'),
('F03','Parcial','P1','Se calcula reward_neto_pct y existe un veto configurable.',
 'exigir_objetivo_operador=false en la configuración efectiva comprobada. De 46 alertas registradas, 26 tienen TP bruto menor que 3.2% y 29 no llegan a 3.2% neto bajo el coste configurado de 0.5 puntos porcentuales. De 29 señales nuevas, 14 fallan incluso el objetivo bruto y 15 el neto. La interfaz compilada tampoco contiene el nuevo aviso. El coste es una hipótesis fija, no una medición de tus comisiones y fills.',
 'Acordar y aplicar la elegibilidad de 3.2% desde la entrada propuesta, etiquetando lo demás como observación. Compilar la interfaz y documentar el supuesto de costes; no ampliar el stop solo para aumentar el TP.',
 'backend/src/config/settings.py:165; backend/src/analysis/trade_levels.py:199; backend/src/state/engine.py:855; frontend/src/components/PairDetail.tsx:134'),
('F04','Parcial','P1','Las 46 alertas con niveles del log tienen registro en alertas_emitidas.',
 '17 de las 46 tienen signal_id NULL y carecen de un outcome propio para evaluar esos niveles. La identidad del plan recibido sigue separada de su resultado. Además, la prueba de un rechazo simulado de Telegram termina en enviado: _pedir devuelve None y avisar no comunica el fallo al llamante. No se detectó un rechazo real en el log INFO revisado; este último defecto es reproducido, no una pérdida de mensajes demostrada.',
 'Asignar plan_id persistente y seguimiento a cada alerta operable, enlazar reemplazos y hacer que Telegram devuelva un resultado verificable antes de marcar enviado.',
 'backend/src/state/engine.py:1021; backend/src/state/engine.py:1132; backend/src/notify/telegram.py:81; backend/src/notify/telegram.py:122'),
('F05','Parcial','P1','El tracker vivo ya no concede TP en la vela ambigua de entrada; la prueba de la vela siguiente también pasa.',
 'research/entrada_en_el_hoyo.py sigue simulando desde la vela de fill y puede conceder su máximo anterior a la compra. También usa min(apertura, disparo), mientras el tracker usa el disparo. La corrección del simulador vivo no corrige los estudios ni los registros históricos.',
 'Compartir una única función de ejecución conservadora entre seguimiento y estudios, versionar las reglas y recalcular los análisis afectados.',
 'backend/src/analysis/hoyo.py:145; research/entrada_en_el_hoyo.py:107; research/entrada_en_el_hoyo.py:122'),
('F06','Parcial','P1','El código de la interfaz añade hist y una explicación de frecuencia de tocar la meta.',
 'Ese texto no está en el JavaScript servido. La tabla fija, el ajuste monotónico y el uso de prob_meta para ordenar siguen iguales. No hay calibración fuera de muestra de TP antes de SL, ni probabilidad de conseguir 3.2% neto.',
 'Desplegar la aclaración visible y reservar cualquier porcentaje de éxito para una medición de planes completos, con muestra independiente, costes y validación temporal.',
 'frontend/src/components/PairRow.tsx:368; backend/src/analysis/retroceso.py:160; backend/src/state/engine.py:232'),
('F07','Corregido','P2','El error de nombres de indicadores está corregido y pasa la prueba con los cuatro campos y sus marcos temporales.',
 '69/69 outcomes nuevos guardan RSI14 de 1m; 65/69 guardan los tres indicadores de 15m. Las cuatro ausencias restantes deben conservarse como ausencias de disponibilidad, no convertirse en cero: TAO, LUNC y KAITO al inicio, y GPS más tarde. El error general que producía NULL en todos los registros ya no se reproduce.',
 'Añadir una razón de indisponibilidad y comprobar calentamiento de 15m antes de usar esos campos como filtro. Los campos antiguos no se rellenan con indicadores de hoy.',
 'backend/src/analysis/outcome_tracker.py:97; backend/src/state/symbol_state.py:391'),
('F08','Parcial','P2','Se añade flow_disponible y los 69 outcomes nuevos lo guardan.',
 'El engine recibe la shortlist solicitada aunque WSManager rechace el cambio por churn. La prueba de sustituir 1 par de 40 reproduce la divergencia entre disponibilidad marcada y suscripción real. Solo 4/69 filas se marcan disponibles y 2 de esas 4 tienen cero trades; esto por sí solo no demuestra falta de compradores ni desconexión.',
 'Publicar al motor la suscripción realmente aceptada y su última recepción, con estado y edad del dato separados del volumen de compras.',
 'backend/main.py:225; backend/src/data_ingestion/ws_manager.py:227; backend/src/state/engine.py:302'),
('F09','Parcial','P2','Se actualiza metadata por hora: 184 pares tienen datos recientes, incluidos JUP y SYRUP. Se intenta mantener pares con seguimiento.',
 'Cuando el cambio queda bajo 5%, update_symbols actualiza self.symbols sin reconectar. La próxima comparación ya cree aplicado el universo, de modo que no acumula el cambio pendiente. Una prueba de añadir 1 de 100 pares y repetir el refresco no suscribe WS-B. Los pares hidratados pueden quedar visibles en engine sin recibir ambos streams. El log no registra reconexiones por universo en el tramo comprobado.',
 'Separar universo deseado de universo realmente suscrito y aplicar deltas acumulados a ambos streams; preservar seguimiento sin mantener candidatos fuera del universo por accidente.',
 'backend/main.py:235; backend/src/data_ingestion/ws_manager.py:245'),
('F10','Corregido','P2','El filtro ya no excluye SUPER, JUP y SYRUP por contener UP. Pasan pruebas de monedas normales y de BTCUP, ETHDOWN y BTC3L.',
 'JUP y SYRUP están presentes en metadata reciente de producción. Esto verifica la regresión concreta; la lista de excepciones y exclusiones sigue necesitando mantenimiento cuando cambie el catálogo.',
 'Conservar pruebas sobre los casos conocidos y revisar exclusiones frente al catálogo real de activos.',
 'backend/src/data_ingestion/universe.py:61'),
('F11','Pendiente','P2','Se añadió el rechazo de velas anteriores a la señal como parte de F02.',
 'La idempotencia sigue sin existir: dos entregas de una vela dan n_velas=2 y dos elementos en el buffer. Una vela atrasada hace retroceder ts_last. Esto también puede inflar cobertura_velas; no se observó sobreconteo imposible en los 69 outcomes nuevos, pero el defecto es reproducible.',
 'Usar una identidad única por símbolo, marco y apertura; rechazar repeticiones y procesar reparaciones en orden con checkpoints por plan.',
 'backend/src/state/symbol_state.py:284; backend/src/analysis/outcome_tracker.py:504'),
('F12','Parcial','P2','Los 69 outcomes actuales guardan strategy_version=b8a3d64 y config_hash=50d5bbbe74aa.',
 'El hash no cambia al modificar rr_target, coste_operacion_pct, exigir_objetivo_operador, flow_min_trades o rise_z: las cinco pruebas fallan. La purga sigue reteniendo solo 3 días de velas cortas. Hay 2,484 outcomes cerrados sin cobertura registrada y 2,792 filas sin versión; no existe rehabilitación automática del histórico.',
 'Serializar explícitamente toda la configuración que determina decisiones y conservar suficiente OHLC para reproducir cada evaluación. Marcar y reconstruir o excluir los resultados históricos afectados.',
 'backend/src/utils/procedencia.py:26; backend/src/persistence/db.py:945'),
('F13','Pendiente','P2','No se encontró una corrección en el orden del seguimiento de alertas ni en la persistencia de perfiles.',
 'El retorno de blow-off sigue antes de actualizar AlertManager; la prueba con una vela de agotamiento omite esa actualización. Desde el despliegue se registran 101 eventos BASE, 33 TENDENCIA y 5 IGNICION, pero esa ruta no crea plan/outcome propio para medir su calidad.',
 'Actualizar siempre los planes vivos antes de vetar nuevas señales y persistir identidad, contexto y resultado de cada perfil evaluable.',
 'backend/src/state/engine.py:482; backend/src/state/engine.py:927'),
('F14','Parcial','P2','La API añade pct_en_positivo, pct_sobre_meta y una nota que aclara el carácter bruto.',
 'pct_sobre_meta compara result_pct >= 3.2 bruto y mantiene un umbral fijo; no comprueba rentabilidad neta. No se añaden fills, spread, deslizamiento real ni filtros tickSize. Los indicadores agregados siguen mezclando versiones y datos históricos afectados. El comentario de signal_tracker todavía llama real al win rate simulado.',
 'Separar tasa de tocar TP, cierre positivo, cumplimiento neto y expectativa por plan/versión con denominadores explícitos y datos de ejecución o supuestos visibles.',
 'backend/src/persistence/db.py:710; backend/src/analysis/signal_tracker.py:1; backend/src/analysis/trade_levels.py:67')
]
titles={x['id']:x['title'] for x in old}
findings=[dict(id=i,estado=state,prioridad=priority,hallazgo=titles[i],aplicado=done,evidencia=evidence,pendiente=fix,codigo=source) for i,state,priority,done,evidence,fix,source in details]
(R/'findings_verification.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
counts=collections.Counter(x['estado'] for x in findings)
summary=(f"No se pueden dar por resueltos los errores de la auditoría. De sus 14 hallazgos, {counts['Corregido']} tienen la corrección puntual comprobada, {counts['Parcial']} están corregidos parcialmente y {counts['Pendiente']} siguen pendientes. El backend ejecuta **b8a3d64**, con esquema **v11**, pero la interfaz compilada es anterior a los cambios.")
scope=("Copia consistente y de solo lectura de la base de producción, obtenida el **10 de septiembre de 2026 a las 23:19 de Guatemala** (11-sep 05:19 UTC). Se analiza la cohorte posterior al arranque **10-sep 16:54:02 de Guatemala** (22:54:02 UTC): **6.42 horas, 69 outcomes y 46 alertas registradas**. Ningún outcome de la versión actual ha completado sus 24 horas; esta verificación no demuestra mejora de precisión ni rentabilidad.")
deployment=("## La interfaz corregida no está desplegada\n\nEl servidor contiene los cambios fuente, pero frontend/dist conserva un JavaScript con fecha anterior al despliegue, sin `FRECUENCIA HISTORICA` ni `reward_neto_pct`. El backend sirve precisamente ese directorio con StaticFiles. La compilación de TypeScript local pasa, pero eso no actualiza la copia servida. Falta compilar y desplegar el frontend, y comprobar el recurso servido después.\n\nEl servicio está activo y la integridad SQLite da **ok**. Esto acredita disponibilidad y estructura, no exactitud del seguimiento financiero.")
methods=(f"## Pruebas y límites de la verificación\n\nSe ejecutaron **{len(b['checks'])} comprobaciones dirigidas** contra una copia del código desplegado: **{b['passed']} pasan y {b['failed']} fallan**. Varias pruebas cubren partes del mismo hallazgo; estos números no son un porcentaje de calidad del sistema. Las pruebas de Telegram simulan respuestas y no envían mensajes. La comprobación TypeScript pasa.\n\nLas consultas preservadas separan la cohorte nueva del histórico. Los 2,344 minutos-par faltantes cuentan únicamente huecos internos, no ausencias al inicio o al final de un símbolo. La referencia pública confirma una vela concreta; no se volvió a descargar todo el mercado. Los logs se inspeccionaron en una cola acotada de 12 MB; errores registrados solo a nivel DEBUG pueden no aparecer.\n\nLos costes de 0.5 puntos porcentuales son el supuesto configurado, no comisiones verificadas de tu cuenta. Incluso sin descontarlos, 26 de 46 alertas no llegan a 3.2%. Las estadísticas históricas mezcladas no permiten atribuir mejoras a esta versión.")
next_steps=("## Orden para cerrar la auditoría\n\n1. Reparar ingestión, buffers, orden temporal e idempotencia; un plan con huecos debe quedar incompleto.\n2. Unificar el seguimiento y el vencimiento de signals, outcomes y alertas, con identidad por plan.\n3. Hacer efectivo el criterio de 3.2%, publicar la interfaz y registrar el resultado real de Telegram.\n4. Completar el hash, homogeneizar el simulador del hoyo y reconstruir o excluir etiquetas antiguas afectadas.\n5. Validar sobre ventanas nuevas completas, separadas por versión y fecha, antes de afirmar que mejoró la entrada.\n\nEsta revisión no modifica el servicio, la configuración, las estrategias ni la base de producción. Deja pruebas y criterios de cierre reproducibles.")
md='# Verificación de las correcciones de SACBinance\n\n'+summary+'\n\n'+scope+'\n\n'+deployment+'\n\n'
for f in findings:
 md+=f"## {f['id']} · {f['estado']} · {f['hallazgo']}\n\n**Aplicado:** {f['aplicado']}\n\n**Evidencia y límite:** {f['evidencia']}\n\n**Para cerrar:** {f['pendiente']}\n\nCódigo: {f['codigo']}.\n\n"
md+=methods+'\n\n'+next_steps+'\n\n## Evidencia reproducible\n\n'
for name in ['provenance.json','queries.json','data_checks.json','runtime_checks.json','behaviour_checks.json','extra_checks.json','verify_data.py','verify_behaviour.py','verify_runtime.py','verify_extra.py']:
 md+=f'- [{name}]({name})\n'
md+=f"\nSnapshot SHA-256: `{p['sha256']}`. Código: `{p['commit']}`. Fuente: `{p['source']}`.\n"
(R/'VERIFICACION.md').write_text(md,encoding='utf-8')
app=R/'report'
if not app.exists():shutil.copytree(R.parent/'report',app,ignore=shutil.ignore_patterns('dist','node_modules','.data-app-offline'))
(app/'src/content/report').mkdir(parents=True,exist_ok=True)
narr={'summary':summary,'scope':scope,'deployment':deployment,'methods':methods,'next_steps':next_steps}
(app/'src/content/report/narrative.json').write_text(json.dumps(narr,ensure_ascii=False,indent=2),encoding='utf-8')
base_source={'type':'file','provider':'Auditoría reproducible','files':['../snapshot.db','../production','../data_checks.json','../behaviour_checks.json','../runtime_checks.json','../extra_checks.json'],'description':f"Verificación del commit {p['commit']}; solo lectura en producción.",'timeRange':{'start':'2026-09-10T22:54:02Z','end':p['started_utc']},'caveats':['Solo 6.42 horas de la versión actual; sin ventanas nuevas de 24h maduras.','Simulación de señales; no ejecuciones reales.']}
queries={}
for k,rows in d['queries'].items():
 queries[k]={'rows':rows,'source':{**base_source,'name':k,'sql':read('queries.json')[k]+'\n-- :start='+str(d['start_ms'])+'; :end='+str(d['end_ms'])}}
queries.update({'findings':{'rows':findings,'source':{**base_source,'name':'Contraste de los 14 hallazgos','files':['../findings_verification.json','../../findings.json','../production']}},'tests':{'rows':[dict(x,resultado='Pasa' if x['passed'] else 'Falla',expected=json.dumps(x['expected'],ensure_ascii=False),actual=json.dumps(x['actual'],ensure_ascii=False)) for x in b['checks']],'source':{**base_source,'name':'Pruebas deterministas','files':['../verify_behaviour.py','../behaviour_checks.json']}},'deployment':{'rows':[{'backend_commit':p['commit'],'frontend_actualizado':False,'esquema':11,'integridad':'ok','duracion_horas':6.419136}],'source':{**base_source,'name':'Estado del despliegue','files':['../runtime_checks.json','../extra_checks.json','../provenance.json']}}})
snapshot={'id':'report:sacbinance-verification-20260910','title':'Las correcciones están desplegadas parcialmente','surface':'report','buildStatus':'complete','status':'reviewed','generatedAt':p['finished_utc'],'report':{'asOf':'2026-09-10'},'queries':queries}
(app/'src/data.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'finding_counts':dict(counts),'report':str(app),'markdown':str(R/'VERIFICACION.md')}))
