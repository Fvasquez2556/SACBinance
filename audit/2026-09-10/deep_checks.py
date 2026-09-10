import json,pathlib,sqlite3,urllib.request,datetime
ROOT=pathlib.Path(__file__).resolve().parent
db=sqlite3.connect((ROOT/'snapshot.db').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
Q={
'mars':"SELECT s.id,datetime(s.ts_open/1000,'unixepoch') utc,s.entry,s.stop_loss,s.take_profit,s.status,o.ms_sl/60000.0 sl_min,o.ms_tp/60000.0 tp_min,o.ms_up_32/60000.0 up32_min,o.mfe_pct FROM signals s JOIN outcomes o ON s.id=o.signal_id WHERE s.symbol='MARSCOINUSDT'",
'time_issues':"SELECT signal_id,symbol,datetime(ts_open/1000,'unixepoch') opened,ms_tp,ms_sl,ms_up_32,(ts_last-ts_open)/3600000.0 duration_h FROM outcomes WHERE ms_tp<0 OR ms_sl<0 OR ms_up_32<0 OR ms_tp>86400000 OR ms_sl>86400000 ORDER BY ts_open LIMIT 12",
'target_all':"SELECT count(*) n,sum((take_profit/entry-1)*100<3.2) below32,sum(result_pct>=3.2) realised_gross32 FROM signals",
'context':"SELECT count(*) n,sum(flow_trades_30s=0) no_flow,sum(senal_n=0) zero_senal,sum(retro_confirmado=1 AND retro_caida_pct>-2) confirmed_without_drop,sum(ruido_1m_pct IS NOT NULL AND ruido_1m_pct>abs(sl_pct)) stop_inside_noise FROM outcomes WHERE retro_caida_pct IS NOT NULL",
'log_signal_link':"SELECT count(*) alerts,sum(message LIKE '%entry=%') valid_level_alerts,sum(message LIKE '%entry=%' AND NOT EXISTS(SELECT 1 FROM signals s WHERE s.symbol=a.symbol AND abs(s.ts_open-a.ts_ms)<2000)) with_levels_without_new_signal FROM analysis_log a WHERE level='ALERT'",
'duplicates':"SELECT count(*) repeated_symbol_timestamp_groups FROM (SELECT symbol,ts_open,count(*) n FROM signals GROUP BY symbol,ts_open HAVING n>1)",
'metadata_age':"SELECT count(*) n,datetime(min(updated),'unixepoch') oldest_utc,datetime(max(updated),'unixepoch') newest_utc FROM pair_metadata",
'shadow_hoyo_mature':"SELECT sombra,cerrado,count(*) n,sum(hoyo_fill IS NOT NULL) filled,sum(hoyo_a='TP') a_tp,sum(hoyo_c2='TP') c2_tp,sum(hoyo_c3='TP') c3_tp FROM outcomes WHERE hoyo_disparo IS NOT NULL GROUP BY sombra,cerrado",
'legacy_vs_current':"SELECT case when retro_caida_pct IS NULL then 'legacy' else 'context_saved' end cohort,count(*) n,sum(cerrado) closed FROM outcomes GROUP BY cohort",
'veto_reason_counts':"SELECT CASE WHEN message LIKE '%ya hay una alerta viva%' THEN 'active_alert' WHEN message LIKE '%cooldown%' THEN 'cooldown' WHEN message LIKE '%cuchillo%' THEN 'falling_knife' WHEN message LIKE '%AGOTADA%' THEN 'exhausted' WHEN message LIKE '%DESACELERANDO%' THEN 'decelerating' WHEN message LIKE '%consumido%' THEN 'consumed' ELSE 'other' END reason,count(*) n FROM analysis_log WHERE level='VETO_ALERTA' GROUP BY reason",
}
r={k:[dict(v) for v in db.execute(q)] for k,q in Q.items()}
with urllib.request.urlopen('https://api.binance.com/api/v3/exchangeInfo',timeout=25) as response:info=json.load(response)
sys_path=str(ROOT/'production'/'backend')
import sys
sys.path.insert(0,sys_path)
from src.data_ingestion.universe import _is_leveraged,_is_stablecoin
current=[x for x in info['symbols'] if x.get('quoteAsset')=='USDT' and x.get('status')=='TRADING' and x.get('isSpotTradingAllowed')]
r['current_exclusion_review']={'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'https://api.binance.com/api/v3/exchangeInfo','active_usdt_spot':len(current),'excluded_as_leveraged':[x['symbol'] for x in current if _is_leveraged(x['baseAsset'])],'excluded_as_stable_or_fiat_or_gold':[x['symbol'] for x in current if _is_stablecoin(x['baseAsset'])]}
(ROOT/'deep_checks.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
(ROOT/'deep_queries.json').write_text(json.dumps(Q,indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))
