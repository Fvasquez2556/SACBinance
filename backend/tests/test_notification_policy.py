"""Delivery regressions. All Telegram calls are fakes; no network or real DB."""
import asyncio
import json
import sqlite3
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.config.settings import get_settings
from src.notify.policy import NOTIFICATION_SCHEMA, NotificationPolicy, candidate_reason
from src.notify.service import NotificationService
from src.notify.telegram import texto_evento_plan
from src.persistence.db import Database
from src.state.engine import StateEngine

NOW=10_000_000


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:')
        self.conn.executescript(NOTIFICATION_SCHEMA)
        self.policy=NotificationPolicy(self.conn)

    def tearDown(self):
        self.conn.close()

    def plan(self,i=1,symbol='TESTUSDT',now=NOW,tp=105):
        self.policy.reserve(i,symbol,i,now,now,{'entry':100,'take_profit':tp,'stop_loss':98},{})
        self.policy.receipt(i,100+i)

    def candle(self,high,low,close,t=NOW+60000):
        self.policy.observe('TESTUSDT',t,t+60000,high,low,close,12,.8)

    def kinds(self):
        return [r['tipo'] for r in self.policy.rows('SELECT tipo FROM notificacion_eventos ORDER BY ts_ms')]

    def test_tp_and_meta_share_one_event_and_duplicate_candles_are_ignored(self):
        self.plan()
        self.candle(106,99,105)
        self.candle(106,99,105)
        self.candle(109,99,108,t=NOW+120000)
        self.assertEqual(self.kinds(),['TP_META'])

    def test_stop_wins_an_ambiguous_candle_and_later_rebound_is_not_a_win(self):
        self.plan()
        self.candle(106,97,104)
        self.candle(110,99,109,t=NOW+120000)
        self.assertEqual(self.kinds(),['SL'])
        event=self.policy.pending('TESTUSDT',NOW+300000)[0]
        self.assertTrue(json.loads(event['snapshot'])['ambiguous'])
        self.assertIn('orden desconocido',texto_evento_plan(event))

    def test_meta_does_not_terminate_a_plan_whose_tp_is_higher(self):
        self.plan()
        self.candle(103.3,99,103)
        self.assertEqual(self.policy.active('TESTUSDT')['estado'],'ABIERTO')
        first=self.policy.pending('TESTUSDT',NOW+120000)[0]
        self.policy.delivered(first['event_key'],True)
        self.candle(106,102,105,t=NOW+120000)
        self.assertEqual(self.kinds(),['META','TP'])

    def test_unsent_meta_is_superseded_by_stop(self):
        self.plan()
        self.candle(103.3,99,103)
        self.candle(103,97,98,t=NOW+120000)
        self.assertEqual([r['tipo'] for r in self.policy.pending('TESTUSDT',NOW+240000)],['SL'])

    def test_short_tp_closes_notification_plan_without_later_meta_claim(self):
        self.plan(tp=102)
        self.candle(102.1,99,102)
        self.candle(106,100,105,t=NOW+120000)
        self.assertEqual(self.kinds(),['TP'])

    def test_near_stop_is_relative_to_plan_risk_and_only_once(self):
        self.plan()
        self.candle(100,99,99.1)
        self.assertEqual(self.kinds(),[])
        self.candle(99,98.2,98.3,t=NOW+120000)
        self.candle(99,98.1,98.2,t=NOW+180000)
        self.assertEqual(self.kinds(),['CERCA_SL'])

    def test_late_candle_cannot_invent_a_tp_or_inflate_mfe(self):
        self.plan()
        self.candle(130,99,120,t=NOW+12*3600000)
        self.assertEqual(self.kinds(),['VENCIDO'])
        row=self.policy.rows('SELECT * FROM notificacion_planes')[0]
        self.assertEqual(row['mfe'],0)

    def test_no_notifications_from_pre_entry_or_out_of_order_candles(self):
        self.plan()
        self.candle(106,97,104,t=NOW-1)
        self.assertEqual(self.kinds(),[])

    def test_global_budget_survives_restart_and_critical_event_still_passes(self):
        for i in range(1,4):self.plan(i,'TESTUSDT' if i==1 else f'P{i}USDT')
        restarted=NotificationPolicy(self.conn)
        self.assertIn('limite global',restarted.budget_reason('NEWUSDT',NOW+60000,3,45))
        self.candle(101,97,98)
        self.assertEqual(self.kinds(),['SL'])

    def test_existing_symbol_is_deduplicated_even_when_a_new_signal_has_an_id(self):
        self.plan()
        self.assertTrue(self.policy.budget_reason('TESTUSDT',NOW+120000,3,45))
        self.assertEqual(self.policy.budget_reason('OTHERUSDT',NOW+120000,3,45),'')

    def test_failed_initial_send_does_not_spend_hourly_budget(self):
        self.plan()
        self.policy.receipt(1,None)
        self.assertEqual(self.policy.budget_reason('OTHERUSDT',NOW,1,45),'')

    def test_interrupted_send_keeps_its_slot_without_blocking_pair_forever(self):
        self.policy.reserve(1,'TESTUSDT',1,NOW,NOW,{'entry':100,'take_profit':105,'stop_loss':98},{})
        self.policy.uncertain(1)
        self.assertIn('limite global',self.policy.budget_reason('OTHERUSDT',NOW,1,45))
        self.assertEqual(self.policy.budget_reason('TESTUSDT',NOW+3600001,1,45),'')

    def test_successful_event_receipt_survives_restart(self):
        self.plan();self.candle(101,97,98)
        event=self.policy.pending('TESTUSDT',NOW+120000)[0]
        self.policy.delivered(event['event_key'],True)
        self.assertEqual(NotificationPolicy(self.conn).pending('TESTUSDT',NOW+180000),[])

    def test_failed_followup_has_backoff_and_is_retryable(self):
        self.plan();self.candle(101,97,98)
        event=self.policy.pending('TESTUSDT',NOW+120000)[0]
        self.policy.attempted(event['event_key'],NOW+120000)
        self.policy.delivered(event['event_key'],False)
        self.assertEqual(self.policy.pending('TESTUSDT',NOW+130000),[])
        self.assertEqual(len(self.policy.pending('TESTUSDT',NOW+181000)),1)


def snapshot(score=80):
    return {'score':score,'vol_24h':5_000_000,'display_state':'SUBIENDO',
            'impulso':{'valid':True,'fase':'SOSTENIDA','consumido_pct':1},
            'trade_levels':{'valid':True,'entry':100,'stop_loss':98,'take_profit':105},
            'macro_trends':{'1h':'ALCISTA','15m':'ALCISTA','4h':'ALCISTA'}}


class EligibilityTests(unittest.TestCase):
    def test_continuation_does_not_require_a_prior_capitulation(self):
        self.assertEqual(candidate_reason(snapshot(),{},get_settings()),'')

    def test_rebound_still_needs_confirmation(self):
        snap=snapshot();snap['display_state']='TOCÓ_FONDO'
        self.assertIn('rebote',candidate_reason(snap,{'detectado':True},get_settings()))

    def test_bad_economics_and_missing_liquidity_are_rejected(self):
        snap=snapshot();snap['trade_levels']['take_profit']=103
        self.assertIn('meta',candidate_reason(snap,{},get_settings()))
        snap=snapshot();snap['vol_24h']=None
        self.assertIn('volumen',candidate_reason(snap,{},get_settings()))
        snap=snapshot();snap['trade_levels']['tp_blocked_by_resistance']=True
        self.assertIn('resistencia',candidate_reason(snap,{},get_settings()))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        settings=get_settings().model_copy(update={'db_path':':memory:'})
        with patch('src.persistence.db.get_settings',return_value=settings):self.db=Database()
        self.telegram=SimpleNamespace(activo=True,avisar=AsyncMock(return_value=True),
            mensaje_id=lambda symbol:1000,responder_a=AsyncMock(return_value=True),
            actualizar_mensaje=AsyncMock(return_value=True))
        self.states={}
        self.service=NotificationService(self.db,self.telegram,self.states.get)

    async def asyncTearDown(self):
        await self.service.close()
        self.db._conn.close()

    def candidate(self,i,score=80):
        now=int(time.time()*1000)
        symbol=f'PAIR{i}USDT';snap=snapshot(score)
        alert={'ts_emision':now,'signal_id':i,'accionable':True}
        self.states[symbol]=SimpleNamespace(candles=[SimpleNamespace(t=now//60000*60000-60000)],
            metrics=SimpleNamespace(price=100),display_state='SUBIENDO',alerta=alert)
        return {'symbol':symbol,'alert_id':i,'snap':snap,'retro':{},'alert':alert}

    async def test_ranked_batch_sends_only_three_and_records_the_suppression(self):
        cs=[self.candidate(i,76+i) for i in range(1,5)]
        self.service._candidates={c['symbol']:c for c in cs}
        with patch('src.notify.service.asyncio.sleep',new=AsyncMock()):await self.service._batch()
        self.assertEqual(self.telegram.avisar.await_count,3)
        self.assertEqual([x.args[0] for x in self.telegram.avisar.await_args_list],['PAIR4USDT','PAIR3USDT','PAIR2USDT'])
        self.assertIsNone(self.service.policy.active('PAIR1USDT'))

    async def test_stale_or_moved_entry_is_not_published_after_batch_delay(self):
        c=self.candidate(1);self.states[c['symbol']].metrics.price=101
        await self.service._send_candidate(c)
        self.telegram.avisar.assert_not_awaited()

    async def test_concurrent_candidates_cannot_overrun_the_global_limit(self):
        await asyncio.gather(*(self.service._send_candidate(self.candidate(i)) for i in range(1,6)))
        self.assertEqual(self.telegram.avisar.await_count,3)

    async def test_failed_transport_does_not_leave_a_pending_plan_forever(self):
        c=self.candidate(1)
        self.telegram.avisar.side_effect=RuntimeError('fake transport failure')
        with self.assertRaises(RuntimeError):
            await self.service._send_candidate(c)
        self.assertIsNone(self.service.policy.active(c['symbol']))
        self.assertEqual(self.service.policy.rows('SELECT estado FROM notificacion_planes')[0]['estado'],'INCIERTO')

    async def test_terminal_message_once_and_no_gain_after_stop(self):
        c=self.candidate(1);await self.service._send_candidate(c)
        row=self.service.policy.active(c['symbol']);t=(row['ts_activado']//60000+1)*60000
        await self.service.observe(c['symbol'],t,t+60000,106,97,104)
        await self.service.observe(c['symbol'],t+60000,t+120000,110,100,109)
        self.assertEqual(self.telegram.responder_a.await_count,1)
        self.assertIn('STOP DEL PLAN',self.telegram.responder_a.await_args.args[1])

    async def test_routine_tracking_edits_without_sending(self):
        c=self.candidate(1);await self.service._send_candidate(c)
        row=self.service.policy.active(c['symbol']);t=(row['ts_activado']//60000+1)*60000
        await self.service.observe(c['symbol'],t,t+60000,101,99,100.5)
        self.telegram.responder_a.assert_not_awaited()
        self.telegram.actualizar_mensaje.assert_awaited()

    async def test_legacy_rupture_horizon_never_sends_a_new_message(self):
        engine=StateEngine.__new__(StateEngine);engine._tg=self.telegram
        event={'symbol':'TESTUSDT','price_open':100,'last_price':101,'direction':'RUPTURA_ALCISTA','telegram_message_id':42}
        await engine._avisar_seguimiento_ruptura({'ruptura':event,'horizontes':[15]})
        self.telegram.actualizar_mensaje.assert_awaited_once()
        self.telegram.responder_a.assert_not_awaited()
        self.telegram.avisar.assert_not_awaited()

    async def test_new_raw_rupture_is_only_recorded_not_pushed(self):
        engine=StateEngine.__new__(StateEngine);engine._tg=self.telegram
        from unittest.mock import Mock
        engine._ruptures=SimpleNamespace(marcar_telegram=Mock())
        await engine._avisar_ruptura({'id':1,'symbol':'TESTUSDT'})
        engine._ruptures.marcar_telegram.assert_called_once()
        self.telegram.avisar.assert_not_awaited()

    async def test_expiry_without_new_candles_only_edits_the_existing_thread(self):
        c=self.candidate(1);await self.service._send_candidate(c)
        row=self.service.policy.active(c['symbol'])
        await self.service.maintenance(row['ts_open']+13*3600000)
        self.telegram.responder_a.assert_not_awaited()
        self.telegram.actualizar_mensaje.assert_awaited()
        self.assertIsNone(self.service.policy.active(c['symbol']))

    async def test_legacy_open_plan_is_adopted_without_repeating_past_meta(self):
        now=int(time.time()*1000);conn=self.db._conn
        conn.execute("INSERT INTO signals(id,symbol,ts_open,display_state,entry,take_profit,stop_loss,status) VALUES(1,'OLDUSDT',?,'SUBIENDO',100,106,98,'OPEN')",(now-600000,))
        conn.execute("INSERT INTO alertas_emitidas(id,ts_ms,symbol,signal_id,entry,take_profit,stop_loss,telegram) VALUES(1,?,'OLDUSDT',1,100,106,98,'enviado')",(now-600000,))
        conn.execute("INSERT INTO telegram_hilos(symbol,message_id,ts_ms) VALUES('OLDUSDT',44,?)",(now-600000,))
        conn.execute("INSERT INTO outcomes(signal_id,symbol,ts_open,entry,ms_up_32) VALUES(1,'OLDUSDT',?,100,60000)",(now-600000,))
        conn.commit()
        policy=NotificationPolicy(conn);policy.adopt_legacy(now,12)
        row=policy.active('OLDUSDT')
        self.assertEqual(row['message_id'],44)
        self.assertEqual(row['meta'],1)
        t=(now//60000+1)*60000
        policy.observe('OLDUSDT',t,t+60000,104,100,103,12,.8)
        self.assertEqual(policy.pending('OLDUSDT',t+60000),[])
        policy.observe('OLDUSDT',t+60000,t+120000,107,102,106,12,.8)
        self.assertEqual([e['tipo'] for e in policy.pending('OLDUSDT',t+120000)],['TP'])


if __name__=='__main__':unittest.main()
