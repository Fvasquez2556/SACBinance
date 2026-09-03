import { useCallback, useEffect, useRef, useState } from "react";
import type { PairState } from "../types";

type Permission = "default" | "granted" | "denied" | "unsupported";

const TIER_RANK: Record<string, number> = {
  NINGUNO: 0,
  VIGILANCIA: 1,
  MODERADA: 2,
  FUERTE: 3,
  "EXTRA-FUERTE": 4,
};

/**
 * Notificaciones push del navegador.
 * Dispara una alerta cuando un par entra en BREAKOUT_INCIPIENTE o sube a
 * tier FUERTE / EXTRA-FUERTE. Anti-spam: 1 notificacion por par cada 5 min.
 */
export function useNotifications() {
  const [permission, setPermission] = useState<Permission>(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission
  );
  const lastNotified = useRef<Map<string, number>>(new Map());
  const prevState = useRef<Map<string, { display: string; tier: string }>>(new Map());

  const requestPermission = useCallback(async () => {
    if (typeof Notification === "undefined") {
      setPermission("unsupported");
      return;
    }
    const result = await Notification.requestPermission();
    setPermission(result as Permission);
  }, []);

  useEffect(() => {
    if (typeof Notification !== "undefined") {
      setPermission(Notification.permission as Permission);
    }
  }, []);

  const fire = useCallback((title: string, body: string) => {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") {
      return;
    }
    try {
      new Notification(title, { body, icon: "/vite.svg", tag: title });
    } catch {
      /* noop */
    }
  }, []);

  /** Procesa el mapa de pares y dispara notificaciones por cambios relevantes. */
  const check = useCallback(
    (pairs: Map<string, PairState>) => {
      if (typeof Notification === "undefined" || Notification.permission !== "granted") {
        return;
      }
      const now = Date.now();
      for (const p of pairs.values()) {
        const prev = prevState.current.get(p.symbol);
        prevState.current.set(p.symbol, { display: p.display_state, tier: p.tier });
        if (!prev) continue;

        const enteredBreakout =
          p.display_state === "BREAKOUT_INCIPIENTE" &&
          prev.display !== "BREAKOUT_INCIPIENTE";
        const tierUp =
          TIER_RANK[p.tier] >= TIER_RANK["FUERTE"] &&
          TIER_RANK[p.tier] > TIER_RANK[prev.tier];

        if (!enteredBreakout && !tierUp) continue;

        const last = lastNotified.current.get(p.symbol) ?? 0;
        if (now - last < 5 * 60 * 1000) continue;
        lastNotified.current.set(p.symbol, now);

        const sym = p.symbol.replace("USDT", "");
        const tl = p.trade_levels;
        const niveles = tl?.valid
          ? ` · Entrada ${tl.entry} · TP ${tl.take_profit} · SL ${tl.stop_loss}`
          : "";
        if (enteredBreakout) {
          fire(`🚀 ${sym} — BREAKOUT`, `Score ${p.score} · ${p.tier}${niveles}`);
        } else {
          fire(
            `📈 ${sym} — ${p.display_state.replace("_", " ")}`,
            `${p.tier} · Score ${p.score}${niveles}`
          );
        }
      }
    },
    [fire]
  );

  return { permission, requestPermission, check };
}
