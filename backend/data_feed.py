"""
Data Feed — polls yfinance every 30 seconds during market hours.
Fetches 5-min OHLCV candles for all tracked symbols.
Handles timezone normalization to IST.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd
import pytz
import yfinance as yf

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

SYMBOLS = ["BSE.NS", "SUZLON.NS", "IFCI.NS", "HFCL.NS", "TMCV.NS"]
POLL_INTERVAL_SECONDS = 30
CANDLE_CACHE: Dict[str, pd.DataFrame] = {}


def is_market_hours() -> bool:
    """Check if current IST time is within market hours (9:00 AM – 3:35 PM Mon-Fri)."""
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = now.time()
    from datetime import time
    return time(9, 0) <= t <= time(15, 35)


def fetch_candles(symbol: str, period: str = "2d", interval: str = "5m") -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data from yfinance and normalize to IST.
    Returns DataFrame with IST-aware DatetimeIndex, or None on error.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)

        if df is None or df.empty:
            logger.warning(f"[{symbol}] No data returned from yfinance")
            return None

        # Normalize column names to lowercase
        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]]

        # Ensure index is timezone-aware IST
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        # Drop rows with NaN close
        df = df.dropna(subset=["close"])
        return df

    except Exception as e:
        logger.error(f"[{symbol}] Error fetching data: {e}")
        return None


def fetch_all_candles() -> Dict[str, Optional[pd.DataFrame]]:
    """Fetch candles for all tracked symbols."""
    results = {}
    for symbol in SYMBOLS:
        results[symbol] = fetch_candles(symbol)
    return results


class DataFeed:
    """
    Async data feed manager.
    Polls yfinance on a schedule and calls back the engine processor.
    """
    def __init__(self, engine, broadcast_fn):
        self.engine = engine
        self.broadcast_fn = broadcast_fn
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the polling loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("DataFeed polling started")

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DataFeed polling stopped")

    async def _poll_loop(self):
        """Main polling loop — runs in background."""
        logger.info("Polling loop running...")
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _tick(self):
        """
        Single poll cycle:
        1. Fetch data for all symbols
        2. Process through ORB engine
        3. Broadcast any signals + state updates
        """
        if not is_market_hours():
            # Outside market hours: just broadcast state (for UI status)
            states = self.engine.get_all_states()
            await self.broadcast_fn({
                "type": "state_update",
                "data": {"stocks": states},
                "timestamp": datetime.now(IST).isoformat()
            })
            return

        logger.debug("Fetching market data...")
        # Run yfinance in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        all_data = await loop.run_in_executor(None, fetch_all_candles)

        all_signals = []
        for symbol, df in all_data.items():
            signals = self.engine.process_candles(symbol, df)
            all_signals.extend(signals)

        # Broadcast each signal
        for signal in all_signals:
            await self.broadcast_fn({
                "type": "alert",
                "data": signal,
                "timestamp": signal["timestamp"]
            })

        # Broadcast consolidated state update
        states = self.engine.get_all_states()
        await self.broadcast_fn({
            "type": "state_update",
            "data": {"stocks": states},
            "timestamp": datetime.now(IST).isoformat()
        })

    async def force_refresh(self):
        """Manually trigger one poll cycle immediately."""
        await self._tick()
