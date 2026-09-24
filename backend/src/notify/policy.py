"""Persistent notification episodes, independent of the exploratory trackers.

Only frozen, notified plans produce push events. A market state or a clock
horizon never creates another trade. SQLite commits precede network requests;
successful receipts and the hourly budget survive restarts.
"""
from __future__ import annotations

import json
import math
import sqlite3

NOTIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS notificacion_planes (
    alerta_id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    signal_id INTEGER,
    ts_open INTEGER NOT NULL,
    ts_activado INTEGER NOT NULL,
    message_id INTEGER,
    entry REAL NOT NULL, take_profit REAL NOT NULL, stop_loss REAL NOT NULL,
    contexto TEXT NOT NULL DEFAULT '{}',
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
    meta INTEGER NOT NULL DEFAULT 0,
    cerca_sl INTEGER NOT NULL DEFAULT 0,
    last_candle INTEGER,
    last_edit INTEGER NOT NULL DEFAULT 0,
    last_price REAL,
    mfe REAL NOT NULL DEFAULT 0, mae REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notificacion_symbol ON notificacion_planes(symbol,estado);
CREATE INDEX IF NOT EXISTS idx_notificacion_hora ON notificacion_planes(ts_activado);
CREATE TABLE IF NOT EXISTS notificacion_eventos (
    event_key TEXT PRIMARY KEY,
    alerta_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    tipo TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
    intento_ms INTEGER NOT NULL DEFAULT 0,
    intentos INTEGER NOT NULL DEFAULT 0,
    snapshot TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notificacion_pendiente ON notificacion_eventos(symbol,estado,intento_ms);
"""


def candidate_reason(snap: dict, retro: dict, settings) -> str:
    """Observable eligibility, not a probability or a newly trained strategy."""
    plan = snap.get('trade_levels') or {}
    if not plan.get('valid'):
        return 'sin plan valido'
    entry, tp, sl = (plan.get(k) for k in ('entry', 'take_profit', 'stop_loss'))
    if not all(isinstance(x, (float, int)) and math.isfinite(x) for x in (entry, tp, sl)):
        return 'niveles incompletos'
    if not 0 < sl < entry < tp:
        return 'niveles incoherentes'
    reward = (tp / entry - 1) * 100 - settings.coste_operacion_pct
    risk = (1 - sl / entry) * 100
    if reward + 1e-8 < settings.objetivo_operador_pct:
        return 'TP neto inferior a la meta configurada'
    if risk > settings.max_risk_pct + 1e-8:
        return 'riesgo superior al limite'
    if plan.get('tp_bloqueado') or plan.get('tp_blocked_by_resistance'):
        return 'resistencia antes del TP'
    if (snap.get('score') or 0) < settings.aviso_score_min:
        return 'score inferior al filtro de avisos'
    if (snap.get('vol_24h') or 0) < settings.aviso_vol24h_min:
        return 'volumen insuficiente o sin medir'
    if snap.get('is_fakeout'):
        return 'posible falsa ruptura'
    if snap.get('display_state') in ('TOCÓ_FONDO', 'CONSOLIDANDO'):
        if not retro.get('detectado') or (settings.aviso_solo_confirmado and not retro.get('confirmado')):
            return 'giro sin rebote confirmado'
    elif snap.get('display_state') in ('SUBIENDO', 'BREAKOUT_INCIPIENTE'):
        impulse = snap.get('impulso') or {}
        if not impulse.get('valid') or impulse.get('fase') not in ('ACELERANDO', 'SOSTENIDA'):
            return 'continuacion sin impulso sostenido'
        if (impulse.get('consumido_pct') or 0) > settings.alerta_consumido_max:
            return 'movimiento ya extendido'
    else:
        return 'estado sin escenario comprador'
    return ''


def candidate_rank(snap: dict) -> tuple:
    p = snap['trade_levels']
    risk = p['entry'] - p['stop_loss']
    return ((p['take_profit'] - p['entry']) / risk,
            snap.get('score') or 0, snap.get('vol_24h') or 0)


class NotificationPolicy:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection

    def rows(self, sql: str, args=()) -> list[dict]:
        cur = self.db.execute(sql, args)
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def active(self, symbol: str) -> dict | None:
        rows = self.rows("SELECT * FROM notificacion_planes WHERE symbol=? AND estado IN ('ABIERTO','PENDIENTE') ORDER BY ts_open DESC LIMIT 1", (symbol,))
        return rows[0] if rows else None

    def symbols(self) -> set[str]:
        return {r['symbol'] for r in self.rows("SELECT symbol FROM notificacion_planes WHERE estado='ABIERTO'")}

    def budget_reason(self, symbol: str, now: int, limit: int, cooldown_min: int) -> str:
        if self.active(symbol):
            return 'ya hay un plan notificado para este movimiento'
        rows = self.rows("SELECT symbol,ts_activado FROM notificacion_planes WHERE ts_activado>? AND (message_id IS NOT NULL OR estado IN ('PENDIENTE','INCIERTO'))",(now-max(60,cooldown_min)*60000,))
        if any(r['symbol'] == symbol and now-r['ts_activado'] < cooldown_min*60000 for r in rows):
            return 'cooldown del par'
        if sum(now-r['ts_activado'] < 3600000 for r in rows) >= limit:
            return f'limite global de {limit} oportunidades por hora'
        return ''

    def reserve(self, alert_id: int, symbol: str, signal_id, opened: int,
                now: int, plan: dict, context: dict) -> bool:
        cur = self.db.execute("""INSERT OR IGNORE INTO notificacion_planes
            (alerta_id,symbol,signal_id,ts_open,ts_activado,entry,take_profit,stop_loss,contexto,last_price)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (alert_id,symbol,signal_id,opened,now,
            plan['entry'],plan['take_profit'],plan['stop_loss'],json.dumps(context),plan['entry']))
        self.db.commit()
        return bool(cur.rowcount)

    def receipt(self, alert_id: int, message_id: int | None):
        self.db.execute("UPDATE notificacion_planes SET estado=?,message_id=? WHERE alerta_id=?",
                        ('ABIERTO' if message_id else 'FALLO',message_id,alert_id))
        self.db.commit()

    def uncertain(self, alert_id: int):
        # An interrupted send may have reached Telegram. Reserve its hourly
        # slot, without resending an old entry or blocking the pair forever.
        self.db.execute("UPDATE notificacion_planes SET estado='INCIERTO' WHERE alerta_id=? AND estado='PENDIENTE'",(alert_id,))
        self.db.commit()

    def adopt_legacy(self, now: int, expiry_hours: int):
        """Continue only known notified plans, without replaying historic hits."""
        old = self.rows("""SELECT a.*,t.message_id,t.ts_ms AS hilo_ts,s.status AS signal_status,
                   o.ms_up_32,o.ms_tp,o.ms_sl,o.mfe_pct,o.mae_pct
            FROM alertas_emitidas a LEFT JOIN telegram_hilos t ON t.symbol=a.symbol
            LEFT JOIN signals s ON s.id=a.signal_id LEFT JOIN outcomes o ON o.signal_id=a.signal_id
            WHERE a.telegram='enviado' AND a.ts_ms>=? ORDER BY a.ts_ms""", (now-25*3600000,))
        for r in old:
            if not all(r.get(k) for k in ('entry','take_profit','stop_loss')):
                continue
            same_thread = r['hilo_ts'] is not None and abs(r['hilo_ts']-r['ts_ms']) < 120000
            is_open = same_thread and r['signal_status']=='OPEN' and now-r['ts_ms'] < expiry_hours*3600000
            estado = 'ABIERTO' if is_open else 'HISTORICO'
            self.db.execute("""INSERT OR IGNORE INTO notificacion_planes
                (alerta_id,symbol,signal_id,ts_open,ts_activado,message_id,entry,take_profit,stop_loss,
                 estado,meta,cerca_sl,last_candle,mfe,mae)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (r['id'],r['symbol'],r['signal_id'],r['ts_ms'],r['ts_ms'],
                r['message_id'] if same_thread else -1,r['entry'],r['take_profit'],r['stop_loss'],estado,
                int(r['ms_up_32'] is not None),1,now//60000*60000,r['mfe_pct'] or 0,r['mae_pct'] or 0))
        # A process interrupted during an initial send has no trustworthy receipt.
        # Do not resend an old entry automatically on startup.
        self.db.execute("UPDATE notificacion_planes SET estado='INCIERTO' WHERE estado='PENDIENTE'")
        self.db.commit()

    def _event(self, row: dict, kind: str, now: int, ambiguous=False):
        snapshot = dict(row, ambiguous=ambiguous)
        self.db.execute("""INSERT OR IGNORE INTO notificacion_eventos
            (event_key,alerta_id,symbol,tipo,ts_ms,snapshot) VALUES (?,?,?,?,?,?)""",
            (f"{row['alerta_id']}:{kind}",row['alerta_id'],row['symbol'],kind,now,json.dumps(snapshot)))

    def observe(self, symbol: str, candle_ms: int, now: int, high: float,
                low: float, close: float, expiry_hours: int, near_fraction: float):
        row = self.active(symbol)
        if not row or row['estado']!='ABIERTO' or candle_ms < row['ts_activado']:
            return
        if row['last_candle'] is not None and candle_ms <= row['last_candle']:
            return
        row['last_candle'] = candle_ms
        if now-row['ts_open'] >= expiry_hours*3600000:
            row['estado']='VENCIDO'
            self._event(row,'VENCIDO',now)
        else:
            row['last_price'] = close
            row['mfe'] = max(row['mfe'],(high/row['entry']-1)*100)
            row['mae'] = min(row['mae'],(low/row['entry']-1)*100)
        if row['estado']=='VENCIDO':
            pass
        elif low <= row['stop_loss']:
            row['estado']='SL'
            self._event(row,'SL',now,ambiguous=high>=min(row['take_profit'],row['entry']*1.032))
        elif high >= row['take_profit']:
            row['estado']='TP'
            meta_now = not row['meta'] and high >= row['entry']*1.032
            if meta_now: row['meta']=1
            self._event(row,'TP_META' if meta_now else 'TP',now)
        elif high >= row['entry']*1.032 and not row['meta']:
            row['meta']=1
            self._event(row,'META',now)
        elif (not row['cerca_sl'] and close <= row['entry']-(row['entry']-row['stop_loss'])*near_fraction):
            row['cerca_sl']=1
            self._event(row,'CERCA_SL',now)
        self.db.execute("""UPDATE notificacion_planes SET estado=?,meta=?,cerca_sl=?,last_candle=?,
            last_price=?,mfe=?,mae=? WHERE alerta_id=?""",tuple(row[k] for k in
            ('estado','meta','cerca_sl','last_candle','last_price','mfe','mae','alerta_id')))
        # Do not deliver a stale proximity/milestone after a terminal event.
        if row['estado'] in ('SL','TP','VENCIDO'):
            self.db.execute("""UPDATE notificacion_eventos SET estado='SUPERADO'
                WHERE alerta_id=? AND tipo IN ('META','CERCA_SL') AND estado IN ('PENDIENTE','FALLO')""",(row['alerta_id'],))
        self.db.commit()

    def pending(self, symbol: str, now: int) -> list[dict]:
        return self.rows("""SELECT e.*,p.message_id FROM notificacion_eventos e
            JOIN notificacion_planes p USING(alerta_id) WHERE e.symbol=?
            AND e.estado IN ('PENDIENTE','FALLO') AND e.intento_ms<=? ORDER BY e.ts_ms""",(symbol,now-60000))

    def attempted(self, key: str, now: int):
        self.db.execute("UPDATE notificacion_eventos SET intento_ms=?,intentos=intentos+1 WHERE event_key=?",(now,key))
        self.db.commit()

    def delivered(self, key: str, ok: bool):
        self.db.execute("UPDATE notificacion_eventos SET estado=? WHERE event_key=?",('ENVIADO' if ok else 'FALLO',key))
        self.db.commit()

    def edit_due(self, symbol: str, now: int, minutes: int) -> dict | None:
        row = self.active(symbol)
        if not row or not row['message_id'] or row['estado']!='ABIERTO' or now-row['last_edit'] < minutes*60000:
            return None
        self.db.execute('UPDATE notificacion_planes SET last_edit=? WHERE alerta_id=?',(now,row['alerta_id']))
        self.db.commit()
        return row

    def expire(self, now: int, hours: int):
        for row in self.rows("SELECT * FROM notificacion_planes WHERE estado='ABIERTO' AND ts_open<=?",(now-hours*3600000,)):
            row['estado']='VENCIDO'
            self._event(row,'VENCIDO',now)
            self.db.execute("UPDATE notificacion_planes SET estado='VENCIDO' WHERE alerta_id=?",(row['alerta_id'],))
            self.db.execute("UPDATE notificacion_eventos SET estado='SUPERADO' WHERE alerta_id=? AND tipo IN ('META','CERCA_SL') AND estado IN ('PENDIENTE','FALLO')",(row['alerta_id'],))
        self.db.commit()
