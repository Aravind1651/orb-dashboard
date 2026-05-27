# ORB Dashboard — 30-Min Opening Range Breakout

A full-stack Python + HTML/JS application that runs the **30-Minute Opening Range Breakout (ORB)** strategy in real-time for Indian stocks on NSE.

## Tracked Stocks
| Stock | Symbol | Exchange |
|-------|--------|----------|
| BSE Ltd | `BSE.NS` | NSE |
| Suzlon Energy | `SUZLON.NS` | NSE |
| IFCI | `IFCI.NS` | NSE |
| HFCL | `HFCL.NS` | NSE |
| TMCV (Tata Motors CV) | `TMCV.NS` | NSE |

## Strategy Logic
- **Opening Range**: 9:15 AM – 9:45 AM IST (30 minutes)
- **Entry**: 5-min candle close above OR High → BUY | below OR Low → SELL
- **Stop Loss**: `range_low − ATR × multiplier` (long) / `range_high + ATR × multiplier` (short)
- **Target**: `entry + risk × R:R ratio`
- **Square Off**: Automatically at 3:15 PM IST

## Quick Start

### 1. Install Dependencies
```powershell
cd C:\Users\ARAVIND\.gemini\antigravity\scratch\orb-dashboard
pip install -r requirements.txt
```

### 2. Run the Dashboard
```powershell
python run.py
```

### 3. Open Dashboard
Navigate to: **http://localhost:8000**

## Features
- ✅ Real-time WebSocket push for live alerts
- ✅ Per-stock cards with OR High/Low levels, price position bar
- ✅ BUY/SELL signal alerts with Entry, SL, TP, R:R
- ✅ SL Hit / TP Hit / Square Off tracking
- ✅ Sound alerts (configurable)
- ✅ Daily history archive (auto at 3:30 PM IST)
- ✅ History browser with date + symbol filters
- ✅ Configurable ATR Length, ATR Multiplier, R:R Ratio
- ✅ Responsive dark glassmorphism UI

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/api/stocks` | Current stock states |
| GET | `/api/alerts/today` | Today's alerts |
| GET | `/api/alerts/history` | Historical alerts |
| POST | `/api/config` | Update strategy config |
| POST | `/api/refresh` | Force data refresh |
| POST | `/api/test-signal` | Inject test signal (dev) |
| GET | `/api/health` | Server health check |
| WS | `/ws` | Real-time WebSocket |

## Data Source
Uses **yfinance** (Yahoo Finance) with ~15-minute delayed data.
For live trading, integrate Zerodha Kite Connect or Angel One SmartAPI.

## Project Structure
```
orb-dashboard/
├── backend/
│   ├── main.py          # FastAPI + WebSocket server
│   ├── orb_engine.py    # ORB strategy logic
│   ├── data_feed.py     # yfinance polling
│   ├── database.py      # SQLite storage
│   └── models.py        # Pydantic models
├── frontend/
│   ├── index.html       # Dashboard UI
│   ├── style.css        # Dark theme
│   └── app.js           # WebSocket client
├── data/
│   └── alerts.db        # SQLite database (auto-created)
├── requirements.txt
└── run.py               # Launcher
```
