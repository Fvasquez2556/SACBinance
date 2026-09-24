import sqlite3,json,gzip,sys
db=sqlite3.connect('file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro',uri=True)
db.row_factory=sqlite3.Row; db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
cols=['signal_id','symbol','ts_open','entry','take_profit','stop_loss','score','tier','display_state','taxonomia',
      'rango_1h_pct','atr_pct','sigma_pct','ruido_1m_pct','vol_ratio','vol_24h','vol_1m_medio','z_rise','z_drop',
      'velocity','ret_1m_pct','drawdown_pct','consumido_pct','fuerza_impulso','fase_impulso','pos_en_rango',
      'dist_soporte_pct','dist_resistencia_pct','rsi5','rsi14','rsi14_15m','macd_hist','macd_hist_15m','bb_position',
      'buy_ratio_30s','flow_trades_30s','flow_disponible','btc_regime','macro_gate_mult','score_trend','es_fakeout',
      'senal_n','atr_percentile','reward_neto_pct','strategy_version','config_hash','cobertura_velas']
rows=[dict(r) for r in db.execute(f"SELECT {','.join(cols)} FROM outcomes")]
db.rollback(); db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(rows).encode()))
