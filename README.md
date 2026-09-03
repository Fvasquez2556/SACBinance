# SACBinance v3

Sistema de Análisis de Criptomonedas Binance (Spot). Escanea todos los pares USDT
en tiempo real por WebSocket, sigue el ciclo de vida de cada moneda
(CAYENDO → TOCÓ FONDO → CONSOLIDANDO → SUBIENDO → BREAKOUT INCIPIENTE) con
análisis multi-timeframe (pendiente de MAs en 15m/1h/4h/1d) y muestra el historial
de estados por moneda en un dashboard React.

Herramienta de *awareness* + decisión asistida — **no ejecuta trades**. Sin ML:
reglas deterministas + estadística adaptativa (z-scores por moneda, EWMA σ).

## Stack

- **Backend:** Python 3 · FastAPI · WebSocket · SQLite · numpy
- **Frontend:** React + TypeScript + Vite

## Arquitectura

```
Binance REST  → hidratación histórica (5 días, multi-TF)
Binance WS    → kline 1m / 5m / 15m / 1h  +  REST periódico 4h / 1d
      │
      ▼
StateEngine (un SymbolState por moneda)
   ├─ buffers circulares por TF
   ├─ AdaptiveStats (EWMA σ, z-scores)
   ├─ FSM: NEUTRAL / DROPPING / BOTTOMING / VALLEY / RISING / EXHAUSTED
   ├─ macro gate (pendiente MA ponderada por TF + gate BTC)
   ├─ indicadores (EMA / RSI / MACD / BB / ATR)
   ├─ niveles de trading (entry / TP / SL, R:R objetivo)
   └─ veto blow-off
      │
      ▼
Scoring 0-100 (VIGILANCIA / MODERADA / FUERTE / EXTRA-FUERTE)
      │
      ├─ WebSocket → Frontend (dashboard + historial de estados)
      └─ SQLite (symbol_states, analysis_log, señales auto-evaluadas)
```

## Cómo correrlo (local)

```bash
# Backend  → http://localhost:8000
cd backend
python -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py

# Frontend (dev)  → http://localhost:5173
cd frontend
npm install
npm run dev
```

Config opcional en `backend/.env` (copiar de `backend/.env.example`). La API pública
de Binance no requiere llaves.

## Despliegue (Ubuntu, 24/7)

```bash
bash deploy/deploy.sh          # venv + deps + build del frontend
sudo cp deploy/sacbinance.service /etc/systemd/system/
sudo systemctl enable --now sacbinance
```

El backend sirve el frontend compilado (`frontend/dist`) en el mismo puerto — una
sola URL en producción.

## Estructura

```
backend/
  main.py                    orquestación FastAPI + tareas de fondo
  src/
    config/settings.py       toda la configuración (env-overridable)
    data_ingestion/          universe, hydrator, ws_manager, rest_periodic
    state/                   adaptive, symbol_state, state_machine, engine
    analysis/                ma_slopes, macro_gate, consolidation, breakout,
                             levels, trade_levels, scoring, signal_tracker
    flow/aggtrade_flow.py    flujo agresor (taker buy/sell)
    indicators/calculator.py EMA/RSI/MACD/BB/ATR (numpy)
    patterns/blow_off.py     veto de techo parabólico
    persistence/db.py        SQLite (historial + logs + señales)
    api/                     routes, ws_server
frontend/
  src/components/            Dashboard, PairRow, PairDetail, SignalStats,
                             StateHistory, TFConfluence
deploy/
  deploy.sh · sacbinance.service
```
