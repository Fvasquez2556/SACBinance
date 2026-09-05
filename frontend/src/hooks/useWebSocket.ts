import { useEffect, useRef, useState } from "react";
import type { PairState, WSMessage } from "../types";

// Mismo origen que la pagina: en dev Vite lo proxea al backend,
// en produccion FastAPI sirve frontend + API + WS en el mismo puerto.
const WS_URL = (() => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
})();
const RECONNECT_DELAY = 3000;

export function useWebSocket() {
  const [pairs, setPairs] = useState<Map<string, PairState>>(new Map());
  const [connected, setConnected] = useState(false);
  const [lastTs, setLastTs] = useState<number>(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;

    const connect = () => {
      if (!aliveRef.current) return;
      // Evitar conexiones duplicadas
      if (
        wsRef.current &&
        (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      let ws: WebSocket;
      try {
        ws = new WebSocket(WS_URL);
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        if (!aliveRef.current) {
          ws.close();
          return;
        }
        setConnected(true);
      };

      ws.onclose = () => {
        setConnected(false);
        if (aliveRef.current) scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose se dispara despues; el reconnect se maneja alli
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };

      ws.onmessage = (ev) => {
        try {
          const msg: WSMessage = JSON.parse(ev.data);
          if (msg.type === "ping") return;

          if (msg.type === "snapshot" && msg.pairs) {
            const map = new Map<string, PairState>();
            for (const p of msg.pairs) map.set(p.symbol, p);
            setPairs(map);
            setLastTs(msg.ts);
          } else if (msg.type === "update") {
            // Broadcast diferencial: `pairs` trae solo los que cambiaron y
            // `removed` los que salieron del listado. Sin borrar estos ultimos
            // las filas viejas se quedarian pegadas para siempre.
            const changed = msg.pairs ?? [];
            const removed = msg.removed ?? [];
            if (changed.length || removed.length) {
              setPairs((prev) => {
                const next = new Map(prev);
                for (const p of changed) next.set(p.symbol, p);
                for (const sym of removed) next.delete(sym);
                return next;
              });
            }
            setLastTs(msg.ts);
          } else if (
            [
              "alert",
              "transition",
              "early",
              "alert_tendencia",
              "alert_ignicion",
              "alert_base_rebote",
            ].includes(msg.type) &&
            msg.symbol
          ) {
            setPairs((prev) => {
              const pair = prev.get(msg.symbol!);
              if (!pair) return prev;
              const next = new Map(prev);
              next.set(msg.symbol!, {
                ...pair,
                ...(msg as unknown as Partial<PairState>),
              });
              return next;
            });
          }
        } catch {
          /* ignore parse errors */
        }
      };
    };

    const scheduleReconnect = () => {
      if (!aliveRef.current) return;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
    };

    connect();

    return () => {
      aliveRef.current = false;
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
      const ws = wsRef.current;
      if (ws) {
        ws.onopen = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        if (
          ws.readyState === WebSocket.OPEN ||
          ws.readyState === WebSocket.CONNECTING
        ) {
          ws.close();
        }
      }
      wsRef.current = null;
    };
  }, []);

  return { pairs, connected, lastTs };
}
