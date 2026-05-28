"""
FastAPI main application.
Provides REST API + WebSocket server for the ORB Dashboard.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import List, Optional, Set

import pytz
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.database import (
    init_db, save_alert, get_today_alerts, get_history,
    get_history_dates, archive_today_and_reset,
    get_strategy_config, update_strategy_config
)
from backend.orb_engine import ORBEngine
from backend.data_feed import DataFeed
from backend.backtester import run_backtest, ALL_STOCKS

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Connection Manager
# ─────────────────────────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info(f"WS connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        logger.info(f"WS disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: dict):
        """Broadcast to all connected clients, removing stale connections."""
        stale = set()
        payload = json.dumps(message, default=str)
        for ws in self.active.copy():
            try:
                await ws.send_text(payload)
            except Exception:
                stale.add(ws)
        for ws in stale:
            self.active.discard(ws)


manager = ConnectionManager()
engine = ORBEngine()
data_feed: Optional[DataFeed] = None


# ─────────────────────────────────────────────────────────────────────────────
# Broadcast callback — called by DataFeed with signals + state updates
# Also saves alerts to DB
# ─────────────────────────────────────────────────────────────────────────────
async def on_broadcast(message: dict):
    """Broadcast message to all WS clients. If alert, also save to DB."""
    if message.get("type") == "alert":
        signal = message["data"]
        alert_id = await save_alert(signal)
        message["data"]["id"] = alert_id
    await manager.broadcast(message)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan: startup + shutdown
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_feed

    # Init DB
    await init_db()

    # Load saved config into engine
    cfg = await get_strategy_config()
    engine.update_config(
        atr_length=cfg["atr_length"],
        atr_multiplier=cfg["atr_multiplier"],
        rr_ratio=cfg["rr_ratio"]
    )

    # Start data feed
    data_feed = DataFeed(engine=engine, broadcast_fn=on_broadcast)
    await data_feed.start()

    # Schedule daily archive job
    asyncio.create_task(_daily_archive_loop())

    # Heartbeat loop
    asyncio.create_task(_heartbeat_loop())

    logger.info("ORB Dashboard server started ✓")
    yield

    # Shutdown
    if data_feed:
        await data_feed.stop()
    logger.info("Server stopped")


# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ORB Trading Dashboard",
    description="30-Min Opening Range Breakout Strategy — Live Alerts",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Background tasks
# ─────────────────────────────────────────────────────────────────────────────
async def _daily_archive_loop():
    """Check every minute if it's time to archive today's alerts (3:30 PM IST)."""
    archived_today = False
    last_reset_date = None

    while True:
        await asyncio.sleep(60)
        now_ist = datetime.now(IST)
        today = now_ist.date().isoformat()

        # Reset archive flag for new day
        if last_reset_date != today:
            archived_today = False
            last_reset_date = today
            # Also reset ORB engine states for new day
            engine.reset_all_daily()
            await manager.broadcast({
                "type": "day_reset",
                "data": {"message": "New trading day started", "date": today},
                "timestamp": now_ist.isoformat()
            })
            logger.info(f"New day detected: {today} — engine reset")

        # Archive at 3:30 PM
        if now_ist.hour == 15 and now_ist.minute >= 30 and not archived_today:
            await archive_today_and_reset()
            archived_today = True
            await manager.broadcast({
                "type": "day_archived",
                "data": {"message": "Day alerts archived", "date": today},
                "timestamp": now_ist.isoformat()
            })


async def _heartbeat_loop():
    """Send heartbeat every 15 seconds to keep connections alive."""
    while True:
        await asyncio.sleep(15)
        if manager.active:
            await manager.broadcast({
                "type": "heartbeat",
                "data": {
                    "time": datetime.now(IST).isoformat(),
                    "connections": len(manager.active)
                },
                "timestamp": datetime.now(IST).isoformat()
            })


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state on connect
        states = engine.get_all_states()
        today_alerts = await get_today_alerts()
        cfg = await get_strategy_config()

        await websocket.send_text(json.dumps({
            "type": "init",
            "data": {
                "stocks": states,
                "today_alerts": today_alerts,
                "config": cfg,
                "server_time": datetime.now(IST).isoformat()
            },
            "timestamp": datetime.now(IST).isoformat()
        }, default=str))

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                msg = json.loads(data)
                # Handle ping
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "data": {},
                        "timestamp": datetime.now(IST).isoformat()
                    }))
            except asyncio.TimeoutError:
                pass  # Heartbeat will handle keep-alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ─────────────────────────────────────────────────────────────────────────────
# REST Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/api/alerts/today")
async def api_today_alerts():
    """Get all alerts for today."""
    alerts = await get_today_alerts()
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/api/alerts/history")
async def api_history(
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD"),
    symbol: Optional[str] = Query(None, description="Symbol filter e.g. SUZLON.NS")
):
    """Get historical alerts with optional filters."""
    history = await get_history(filter_date=date, symbol=symbol)
    dates = await get_history_dates()
    return {"history": history, "count": len(history), "available_dates": dates}


@app.get("/api/stocks")
async def api_stocks():
    """Get current state of all tracked stocks."""
    states = engine.get_all_states()
    return {"stocks": states, "timestamp": datetime.now(IST).isoformat()}


@app.get("/api/config")
async def api_get_config():
    """Get current strategy configuration."""
    cfg = await get_strategy_config()
    return cfg


class ConfigUpdateRequest(BaseModel):
    atr_length: int = 14
    atr_multiplier: float = 1.0
    rr_ratio: float = 2.0


@app.post("/api/config")
async def api_update_config(req: ConfigUpdateRequest):
    """Update strategy configuration."""
    await update_strategy_config(req.atr_length, req.atr_multiplier, req.rr_ratio)
    engine.update_config(req.atr_length, req.atr_multiplier, req.rr_ratio)
    return {"status": "updated", "config": req.dict()}


@app.post("/api/refresh")
async def api_refresh():
    """Force an immediate data refresh."""
    if data_feed:
        asyncio.create_task(data_feed.force_refresh())
        return {"status": "refresh triggered"}
    return {"status": "feed not running"}


@app.post("/api/test-signal")
async def api_test_signal(symbol: str = "BSE.NS", signal_type: str = "BUY"):
    """
    DEV ONLY: Inject a test signal to verify UI rendering.
    Supports: BUY, SELL, SL_HIT, TP_HIT, SQUARE_OFF
    """
    now_ist = datetime.now(IST)
    is_exit = signal_type in ("SL_HIT", "TP_HIT", "SQUARE_OFF")

    SIMULATED_ENTRY = 980.00
    direction = "LONG"

    exit_prices = {
        "SL_HIT":     960.00,
        "TP_HIT":     1040.00,
        "SQUARE_OFF": 995.00,
    }
    exit_price = exit_prices.get(signal_type, 1000.00)

    pnl_points  = round(exit_price - SIMULATED_ENTRY, 2) if is_exit else None
    pnl_percent = round((pnl_points / SIMULATED_ENTRY) * 100, 2) if pnl_points is not None else None

    display_names = {
        "BSE.NS": "BSE Ltd", "SUZLON.NS": "Suzlon Energy",
        "IFCI.NS": "IFCI",   "HFCL.NS": "HFCL", "TMCV.NS": "TMCV"
    }
    test_signal = {
        "symbol":         symbol,
        "display_name":   display_names.get(symbol, symbol.split(".")[0]),
        "signal_type":    signal_type,
        "direction":      direction,
        "entry_price":    exit_price if is_exit else 1000.00,
        "original_entry": SIMULATED_ENTRY if is_exit else None,
        "stop_loss":      960.00 if not is_exit else None,
        "target_price":   1040.00 if not is_exit else None,
        "risk_reward":    2.0 if not is_exit else None,
        "pnl_points":     pnl_points,
        "pnl_percent":    pnl_percent,
        "atr":            15.50,
        "range_high":     1005.00,
        "range_low":      985.00,
        "timestamp":      now_ist.isoformat(),
        "date":           now_ist.date().isoformat(),
        "status":         "ACTIVE",
    }
    alert_id = await save_alert(test_signal)
    test_signal["id"] = alert_id
    await manager.broadcast({
        "type": "alert",
        "data": test_signal,
        "timestamp": now_ist.isoformat()
    })
    return {"status": "test signal sent", "signal": test_signal}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time_ist": datetime.now(IST).isoformat(),
        "ws_connections": len(manager.active),
        "feed_running": data_feed._running if data_feed else False
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backtest Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/backtest/stocks")
async def api_backtest_stocks():
    """Return full stock list for backtest dropdown (tracked + Nifty 50)."""
    return {"stocks": ALL_STOCKS}


@app.get("/api/backtest")
async def api_backtest(
    symbol: str = Query("SUZLON.NS", description="Stock symbol e.g. SUZLON.NS"),
    period: str = Query("1mo",       description="Period: 1d 1w 1mo 6mo 1y 2y"),
):
    """
    Run ORB backtest for a symbol over a period.
    Returns per-trade results and summary statistics.
    """
    valid_periods = {"1d", "1w", "1mo", "6mo", "1y", "2y"}
    if period not in valid_periods:
        raise HTTPException(status_code=400, detail=f"Invalid period. Use one of: {valid_periods}")

    cfg = await get_strategy_config()
    config = {
        "atr_length":     cfg.get("atr_length",     14),
        "atr_multiplier": cfg.get("atr_multiplier", 1.0),
        "rr_ratio":       cfg.get("rr_ratio",       2.0),
    }
    try:
        result = await run_backtest(symbol=symbol, period=period, config=config)
        return result
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
