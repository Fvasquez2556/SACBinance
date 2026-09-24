"""Apply narrowly scoped notification method replacements; preserve the engine."""
import ast
from pathlib import Path

p=Path('backend/src/state/engine.py')
source=p.read_text(encoding='utf-8')
methods={
'_avisar_ruptura':'''    async def _avisar_ruptura(self, evento: dict) -> None:
        # A short market-state change has no independent frozen trade plan.
        # Keep collecting it; the selected plan owns the only notification thread.
        self._ruptures.marcar_telegram(
            evento, "no_procede", "movimiento corto medido en UI; avisos unificados en el plan seleccionado")
''',
'_avisar_seguimiento_ruptura':'''    async def _avisar_seguimiento_ruptura(self, seguimiento: dict) -> None:
        # Previously sent rupture messages remain useful, but their clock
        # milestones are silent edits, never additional sendMessage calls.
        evento = seguimiento["ruptura"]
        mid = evento.get("telegram_message_id")
        hitos = set(get_settings().telegram_ruptura_hitos_list)
        disponibles = [h for h in seguimiento["horizontes"] if h in hitos]
        if not mid or not disponibles or not self._tg.activo:
            return
        minutos = max(disponibles)
        await self._tg.actualizar_mensaje(
            mid, texto_seguimiento_ruptura(evento["symbol"], evento, minutos)
            + "\\nActualización del movimiento corto; no invalida por sí sola la estructura de 1h.")
''',
'_refrescar_alerta_viva':'''    async def _refrescar_alerta_viva(
        self, symbol: str, st, now_ms: int, high: float, low: float,
        close: float, impulso, display: str, viene_de_caida: bool,
    ) -> None:
        # Notifications follow their own frozen notified plan, even if the UI
        # alert is reset at +3.2%, replaced, or restored as non-actionable.
        if self._notifications is not None:
            try:
                candle_ms = st.candles[-1].t
                await self._notifications.observe(symbol,candle_ms,now_ms,high,low,close)
            except Exception as exc:
                logger.warning(f"[{symbol}] seguimiento de aviso fallo: {type(exc).__name__}")
        if not get_settings().alerta_congelada_enabled:
            return
        cambio = self._alertas.actualizar(
            symbol, now_ms, high, low, close, impulso,
            display_state=display, viene_de_caida=viene_de_caida)
        if cambio is not None and self._emit:
            await self._emit({"type":"alerta_cambio","ts":now_ms,
                              "symbol":symbol,"alerta":cambio.to_dict()})
        viva = self._alertas.get(symbol)
        if viva is not None:
            # Keep the UI's excursion markers; these lists no longer trigger
            # fixed-percentage drops or duplicate meta/4.2% Telegram messages.
            viva.hitos_nuevos.clear()
            viva.bajadas_nuevas.clear()
        st.alerta = viva.to_dict() if viva is not None else {}
''',
'_quiza_avisar':'''    async def _quiza_avisar(self, symbol: str, st, snap: dict,
                            now_ms: int, alerta_id=None) -> None:
        if self._notifications is None:
            return
        snap = dict(snap)
        if snap.get("vol_24h") is None and self._db is not None:
            row = self._db.get_pair_meta(symbol)
            snap["vol_24h"] = row.get("vol_24h") if row else None
        await self._notifications.consider(
            symbol,alerta_id,snap,st.retroceso or {},st.alerta)
''',
}
tree=ast.parse(source)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StateEngine')
lines=source.splitlines(keepends=True)
edits=[]
for node in cls.body:
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in methods:
        edits.append((node.lineno-1,node.end_lineno,methods[node.name]+'\n'))
assert len(edits)==len(methods)
for start,end,text in sorted(edits,reverse=True):
    lines[start:end]=[text]
p.write_text(''.join(lines),encoding='utf-8')
ast.parse(p.read_text(encoding='utf-8'))
print('Replaced',list(methods))
