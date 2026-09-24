"""One notification thread per frozen plan; bounded discovery, unbounded exits."""
from __future__ import annotations

import asyncio
import copy
import time

from src.config.settings import get_settings
from src.notify.policy import candidate_rank, candidate_reason
from src.notify.telegram import texto_evento_plan, texto_plan_notificado
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, db, telegram, state_for):
        self.db, self.telegram, self.state_for = db,telegram,state_for
        self.policy = db.notification_policy()
        self.policy.adopt_legacy(int(time.time()*1000),get_settings().signal_expiry_hours)
        self._candidates = {}
        self._task = None
        self._lock = asyncio.Lock()

    def symbols(self):
        return self.policy.symbols()

    def _tiene_operacion_abierta(self, symbol) -> bool:
        """
        ¿El usuario tiene una operacion viva en este par?

        Solo lectura del diario de la fase 3. Cualquier fallo devuelve False:
        un aviso que no sabe si te afecta se presenta como si no te afectara,
        que es el lado que no exagera.
        """
        try:
            fila = self.db._conn.execute(
                "SELECT 1 FROM operaciones WHERE symbol = ? AND estado = 'ABIERTA' "
                "LIMIT 1", (symbol,)).fetchone()
            return fila is not None
        except Exception:
            return False

    def _decision(self, alert_id, symbol, state, reason=''):
        self.db.marcar_telegram(alert_id,state,reason)
        self.db.log_analysis(symbol,'NOTIFICACION',f'alerta={alert_id} {state}: {reason}')

    async def consider(self, symbol, alert_id, snap, retro, alert):
        if not alert_id:
            return
        if not self.telegram.activo:
            self._decision(alert_id,symbol,'no_procede','Telegram no activo')
            return
        reason = candidate_reason(snap,retro,get_settings())
        if not reason:
            s=get_settings()
            reason=self.policy.budget_reason(symbol,int(time.time()*1000),s.aviso_max_nuevas_hora,s.aviso_cooldown_min)
        if reason:
            self._decision(alert_id,symbol,'no_procede',reason)
            return
        previous=self._candidates.get(symbol)
        if previous:
            self._decision(previous['alert_id'],symbol,'no_procede','sustituida por candidato mas reciente del mismo par')
        self._candidates[symbol]=copy.deepcopy({'symbol':symbol,'alert_id':alert_id,'snap':snap,'retro':retro,'alert':alert})
        self._decision(alert_id,symbol,'pendiente',f'seleccion de oportunidades en lote de {get_settings().aviso_lote_segundos}s')
        if self._task is None or self._task.done():
            self._task=asyncio.create_task(self._batch())

    async def _batch(self):
        try:
            while self._candidates:
                await asyncio.sleep(get_settings().aviso_lote_segundos)
                candidates=list(self._candidates.values())
                self._candidates.clear()
                candidates.sort(key=lambda c:candidate_rank(c['snap']),reverse=True)
                for candidate in candidates:
                    try:
                        await self._send_candidate(candidate)
                    except Exception as exc:
                        logger.warning(f"[{candidate['symbol']}] seleccion de aviso fallo: {type(exc).__name__}")
                        self._decision(candidate['alert_id'],candidate['symbol'],'fallo','error al preparar o registrar aviso')
        except asyncio.CancelledError:
            raise

    async def _send_candidate(self, c):
        # Validate after acquiring the lock: a previous Telegram request may
        # have taken long enough for the next candidate to become stale.
        async with self._lock:
            await self._send_locked(c)

    async def _send_locked(self, c):
        s=get_settings()
        now=int(time.time()*1000)
        symbol,alert_id=c['symbol'],c['alert_id']
        st=self.state_for(symbol)
        plan=c['snap']['trade_levels']
        reason=''
        if st is None or not st.candles or now-st.candles[-1].t > 180000:
            reason='datos desactualizados durante seleccion'
        elif abs(st.metrics.price/plan['entry']-1)*100 > s.aviso_desvio_entrada_max_pct:
            reason='precio alejado de la entrada congelada durante seleccion'
        elif st.display_state not in ('SUBIENDO','BREAKOUT_INCIPIENTE','TOCÓ_FONDO','CONSOLIDANDO'):
            reason='el escenario dejo de estar vigente durante seleccion'
        elif not st.alerta.get('accionable') or st.alerta.get('ts_emision')!=c['alert']['ts_emision']:
            reason='el plan fue cerrado o sustituido durante seleccion'
        if reason:
            self._decision(alert_id,symbol,'no_procede',reason)
            return
        reason=self.policy.budget_reason(symbol,now,s.aviso_max_nuevas_hora,s.aviso_cooldown_min)
        if reason:
            self._decision(alert_id,symbol,'no_procede',reason)
            return
        alerta=c['alert']
        context={'macro_trends':c['snap'].get('macro_trends') or {},
                 'coste_pct':s.coste_operacion_pct,'score':c['snap'].get('score'),
                 'perfil':c['snap'].get('display_state'),
                 # Los niveles que sostienen y estorban al plan, congelados con
                 # el: el mensaje tiene que decir sobre que se apoya el stop y
                 # que hay que romper para llegar al TP.
                 'soporte':alerta.get('soporte'),'sl_basis':alerta.get('sl_basis'),
                 'resistencia':alerta.get('resistencia'),
                 'tp_bloqueado':alerta.get('tp_bloqueado'),
                 'toques_soporte':alerta.get('toques_soporte'),
                 'toques_resistencia':alerta.get('toques_resistencia'),
                 # Fase 6: identidad legible. Sin esto el mensaje decia
                 # "Plan #4871" —un id de base de datos— y no habia forma de
                 # saber si es la primera oportunidad de un movimiento o la
                 # quinta repeticion del mismo.
                 'plan_id':alerta.get('plan_id'),
                 'episode_id':alerta.get('episode_id'),
                 'ordinal_episodio':alerta.get('ordinal_episodio'),
                 'trigger_tf':(plan or {}).get('tf'),
                 # ¿Esto afecta a algo que el usuario ya tomo, o solo describe
                 # otra oportunidad? Sin la distincion, todos los avisos piden
                 # la misma atencion y acaban sin pedir ninguna.
                 'operacion_abierta':self._tiene_operacion_abierta(symbol)}
        if not self.policy.reserve(alert_id,symbol,c['alert'].get('signal_id'),
                                   c['alert']['ts_emision'],now,plan,context):
            self._decision(alert_id,symbol,'no_procede','plan ya procesado')
            return
        row=self.policy.active(symbol)
        try:
            sent=await self.telegram.avisar(symbol,texto_plan_notificado(dict(row,estado='ABIERTO'),'NUEVO PLAN SELECCIONADO'))
            mid=self.telegram.mensaje_id(symbol) if sent else None
            self.policy.receipt(alert_id,mid)
        except (Exception, asyncio.CancelledError):
            self.policy.uncertain(alert_id)
            raise
        self._decision(alert_id,symbol,'enviado' if mid else 'fallo',
                       'plan seleccionado; seguimiento por eventos' if mid else 'Telegram no confirmo el envio')

    async def observe(self, symbol, candle_ms, now, high, low, close):
        s=get_settings()
        self.policy.observe(symbol,candle_ms,now,high,low,close,s.signal_expiry_hours,s.aviso_stop_cercano_fraccion)
        await self._deliver(symbol,now)
        if self.telegram.activo:
            row=self.policy.edit_due(symbol,now,s.aviso_actualizar_minutos)
            if row:
                await self.telegram.actualizar_mensaje(row['message_id'],texto_plan_notificado(row))

    async def _deliver(self,symbol,now):
        if not self.telegram.activo:
            return
        async with self._lock:
            for event in self.policy.pending(symbol,now):
                self.policy.attempted(event['event_key'],now)
                text=texto_evento_plan(event)
                if event['tipo']=='VENCIDO':
                    ok=await self.telegram.actualizar_mensaje(event['message_id'],text)
                else:
                    ok=await self.telegram.responder_a(event['message_id'],text)
                self.policy.delivered(event['event_key'],ok)
                if ok:
                    self.db.log_analysis(symbol,'NOTIFICACION',f"{event['tipo']} enviado plan={event['alerta_id']}")
                if ok and event['tipo'] in ('SL','TP','TP_META'):
                    await self.telegram.actualizar_mensaje(event['message_id'],text)

    async def maintenance(self,now):
        self.policy.expire(now,get_settings().signal_expiry_hours)
        symbols={r['symbol'] for r in self.policy.rows("SELECT DISTINCT symbol FROM notificacion_eventos WHERE estado IN ('PENDIENTE','FALLO')")}
        for symbol in symbols:
            await self._deliver(symbol,now)

    async def close(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for c in self._candidates.values():
            self._decision(c['alert_id'],c['symbol'],'no_procede','seleccion cancelada al apagar; no se reenvia entrada antigua')
        self._candidates.clear()
