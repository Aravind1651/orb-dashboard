"""
ORB Engine — Python equivalent of the Pine Script strategy.

Strategy Logic:
  - Session: 9:15 AM IST market open
  - Opening Range: 9:15 AM – 9:45 AM (30 minutes, using 5-min candles)
  - After 9:45 AM: Monitor for breakout of OR High/Low
  - Entry: Close > OR High → LONG | Close < OR Low → SHORT
  - SL: range_low - ATR*multiplier (for long) | range_high + ATR*multiplier (for short)
  - TP: entry + risk * RR (for long) | entry - risk * RR (for short)
  - Square Off: 3:15 PM IST
  - One position at a time per stock
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional, Dict, List
import pandas as pd
import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

SESSION_START = time(9, 15)
OR_END = time(9, 45)
SQUARE_OFF_TIME = time(15, 15)
MARKET_CLOSE = time(15, 30)


@dataclass
class StockORBState:
    """Per-stock state machine for the ORB strategy."""
    symbol: str
    display_name: str

    # Opening Range
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    range_defined: bool = False

    # Position tracking
    position: str = "FLAT"      # FLAT, LONG, SHORT
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    active_alert_id: Optional[int] = None

    # Market data
    current_price: Optional[float] = None
    atr: Optional[float] = None
    last_updated: Optional[str] = None
    last_candle_time: Optional[datetime] = None

    # Daily reset tracking
    date_initialized: Optional[str] = None

    # Signal dedup: track already-fired signals in this session
    signals_fired: List[str] = field(default_factory=list)  # ["LONG", "SHORT"]

    def reset_daily(self):
        """Reset state for a new trading day."""
        self.range_high = None
        self.range_low = None
        self.range_defined = False
        self.position = "FLAT"
        self.entry_price = None
        self.stop_loss = None
        self.target_price = None
        self.active_alert_id = None
        self.signals_fired = []
        logger.info(f"[{self.symbol}] Daily state reset")

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "display_name": self.display_name,
            "current_price": self.current_price,
            "range_high": self.range_high,
            "range_low": self.range_low,
            "range_defined": self.range_defined,
            "position": self.position,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "atr": self.atr,
            "last_updated": self.last_updated,
            "market_status": self._get_market_status(),
        }

    def _get_market_status(self) -> str:
        now_ist = datetime.now(IST).time()
        if now_ist < SESSION_START or now_ist >= MARKET_CLOSE:
            return "CLOSED"
        elif SESSION_START <= now_ist < OR_END:
            return "BUILDING_OR"
        elif OR_END <= now_ist < SQUARE_OFF_TIME:
            return "TRADING"
        elif SQUARE_OFF_TIME <= now_ist < MARKET_CLOSE:
            return "SQUARE_OFF"
        return "CLOSED"


def compute_atr(df: pd.DataFrame, length: int = 14) -> Optional[float]:
    """
    Compute ATR using Wilder's method (same as Pine Script ta.atr()).
    Requires OHLCV DataFrame with columns: open, high, low, close.
    Returns the most recent ATR value.
    """
    if len(df) < 2:
        return None
    try:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)

        # Use Wilder's smoothing (same as Pine Script)
        atr_series = tr.ewm(alpha=1/length, adjust=False).mean()
        val = atr_series.iloc[-1]
        return round(float(val), 4) if pd.notna(val) else None
    except Exception as e:
        logger.warning(f"ATR computation error: {e}")
        return None


class ORBEngine:
    """
    Central engine managing all stock states and processing candles.
    Equivalent to the Pine Script strategy() block.
    """
    STOCKS = [
        {"symbol": "BSE.NS",    "display_name": "BSE Ltd"},
        {"symbol": "SUZLON.NS", "display_name": "Suzlon Energy"},
        {"symbol": "IFCI.NS",   "display_name": "IFCI"},
        {"symbol": "HFCL.NS",   "display_name": "HFCL"},
        {"symbol": "TMCV.NS",   "display_name": "TMCV"},
    ]

    def __init__(self):
        self.states: Dict[str, StockORBState] = {}
        self.config = {
            "atr_length": 14,
            "atr_multiplier": 1.0,
            "rr_ratio": 2.0,
        }
        self._init_states()

    def _init_states(self):
        for stock in self.STOCKS:
            self.states[stock["symbol"]] = StockORBState(
                symbol=stock["symbol"],
                display_name=stock["display_name"]
            )

    def update_config(self, atr_length: int, atr_multiplier: float, rr_ratio: float):
        self.config["atr_length"] = atr_length
        self.config["atr_multiplier"] = atr_multiplier
        self.config["rr_ratio"] = rr_ratio
        logger.info(f"Strategy config updated: {self.config}")

    def reset_all_daily(self):
        """Reset all stock states for a new trading day."""
        for state in self.states.values():
            state.reset_daily()

    def process_candles(self, symbol: str, df: pd.DataFrame) -> List[dict]:
        """
        Process a DataFrame of 5-min candles for a symbol.
        Returns a list of signal dicts (may be empty).

        df columns: open, high, low, close, volume
        df index: DatetimeIndex (IST-aware)
        """
        if symbol not in self.states:
            return []

        state = self.states[symbol]
        signals = []

        if df is None or df.empty:
            return []

        today_str = datetime.now(IST).date().isoformat()

        # Reset state if it's a new day
        if state.date_initialized != today_str:
            state.reset_daily()
            state.date_initialized = today_str

        # Compute ATR from full history
        atr_val = compute_atr(df, self.config["atr_length"])
        state.atr = atr_val

        # Separate today's candles
        today_df = df[df.index.date == datetime.now(IST).date()]
        if today_df.empty:
            state.current_price = float(df["close"].iloc[-1]) if not df.empty else None
            return []

        # Process each today candle in order
        for candle_time, row in today_df.iterrows():
            # Normalize to IST
            if hasattr(candle_time, 'tzinfo') and candle_time.tzinfo is not None:
                candle_ist = candle_time.astimezone(IST)
            else:
                candle_ist = IST.localize(candle_time.replace(tzinfo=None))

            t = candle_ist.time()
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])

            state.current_price = close
            state.last_updated = datetime.now(IST).isoformat()

            # Skip if already processed this candle
            if state.last_candle_time and candle_ist <= state.last_candle_time:
                continue

            # ── Build Opening Range (9:15–9:44) ──────────────────────
            if SESSION_START <= t < OR_END:
                if state.range_high is None:
                    state.range_high = high
                    state.range_low = low
                else:
                    state.range_high = max(state.range_high, high)
                    state.range_low = min(state.range_low, low)
                state.range_defined = False

            # ── Mark range as ready after 9:45 ───────────────────────
            elif t >= OR_END and not state.range_defined and state.range_high is not None:
                state.range_defined = True
                logger.info(
                    f"[{symbol}] OR defined — High: {state.range_high:.2f}, "
                    f"Low: {state.range_low:.2f}"
                )

            # ── Square Off at 3:15 PM ─────────────────────────────────
            if t >= SQUARE_OFF_TIME and state.position != "FLAT":
                signal = self._build_signal(
                    state, "SQUARE_OFF", close,
                    sl=None, tp=None
                )
                state.position = "FLAT"
                state.entry_price = None
                state.stop_loss = None
                state.target_price = None
                signals.append(signal)
                logger.info(f"[{symbol}] Square off at {close}")
                state.last_candle_time = candle_ist
                continue

            # ── Trading Zone (9:45–15:14) ─────────────────────────────
            if (state.range_defined and
                    OR_END <= t < SQUARE_OFF_TIME and
                    state.atr is not None):

                # ── LONG Signal ────────────────────────────────────────
                if (close > state.range_high and
                        state.position == "FLAT" and
                        "LONG" not in state.signals_fired):

                    sl = state.range_low - (state.atr * self.config["atr_multiplier"])
                    risk = close - sl
                    tp = close + (risk * self.config["rr_ratio"])

                    signal = self._build_signal(state, "BUY", close, sl=sl, tp=tp)
                    state.position = "LONG"
                    state.entry_price = close
                    state.stop_loss = sl
                    state.target_price = tp
                    state.signals_fired.append("LONG")
                    signals.append(signal)
                    logger.info(f"[{symbol}] BUY @ {close:.2f} SL:{sl:.2f} TP:{tp:.2f}")

                # ── SHORT Signal ───────────────────────────────────────
                elif (close < state.range_low and
                        state.position == "FLAT" and
                        "SHORT" not in state.signals_fired):

                    sl = state.range_high + (state.atr * self.config["atr_multiplier"])
                    risk = sl - close
                    tp = close - (risk * self.config["rr_ratio"])

                    signal = self._build_signal(state, "SELL", close, sl=sl, tp=tp)
                    state.position = "SHORT"
                    state.entry_price = close
                    state.stop_loss = sl
                    state.target_price = tp
                    state.signals_fired.append("SHORT")
                    signals.append(signal)
                    logger.info(f"[{symbol}] SELL @ {close:.2f} SL:{sl:.2f} TP:{tp:.2f}")

                # ── Check SL/TP hits ────────────────────────────────────
                elif state.position == "LONG" and state.stop_loss and state.target_price:
                    if low <= state.stop_loss:
                        signal = self._build_signal(state, "SL_HIT", state.stop_loss, sl=None, tp=None)
                        signals.append(signal)
                        state.position = "FLAT"
                        logger.info(f"[{symbol}] Stop Loss hit @ {state.stop_loss:.2f}")
                    elif high >= state.target_price:
                        signal = self._build_signal(state, "TP_HIT", state.target_price, sl=None, tp=None)
                        signals.append(signal)
                        state.position = "FLAT"
                        logger.info(f"[{symbol}] Target hit @ {state.target_price:.2f}")

                elif state.position == "SHORT" and state.stop_loss and state.target_price:
                    if high >= state.stop_loss:
                        signal = self._build_signal(state, "SL_HIT", state.stop_loss, sl=None, tp=None)
                        signals.append(signal)
                        state.position = "FLAT"
                        logger.info(f"[{symbol}] Stop Loss hit @ {state.stop_loss:.2f}")
                    elif low <= state.target_price:
                        signal = self._build_signal(state, "TP_HIT", state.target_price, sl=None, tp=None)
                        signals.append(signal)
                        state.position = "FLAT"
                        logger.info(f"[{symbol}] Target hit @ {state.target_price:.2f}")

            state.last_candle_time = candle_ist

        return signals

    def _build_signal(self, state: StockORBState, signal_type: str,
                       price: float, sl: Optional[float], tp: Optional[float]) -> dict:
        """Build a signal dict from current state."""
        now_ist = datetime.now(IST)
        risk = None
        rr = None
        if sl and tp and signal_type in ("BUY", "SELL"):
            if signal_type == "BUY":
                risk = price - sl
            else:
                risk = sl - price
            rr = round(self.config["rr_ratio"], 2)

        return {
            "symbol": state.symbol,
            "display_name": state.display_name,
            "signal_type": signal_type,
            "entry_price": round(price, 2),
            "stop_loss": round(sl, 2) if sl else None,
            "target_price": round(tp, 2) if tp else None,
            "risk_reward": rr,
            "atr": round(state.atr, 4) if state.atr else None,
            "range_high": round(state.range_high, 2) if state.range_high else None,
            "range_low": round(state.range_low, 2) if state.range_low else None,
            "timestamp": now_ist.isoformat(),
            "date": now_ist.date().isoformat(),
            "status": "ACTIVE",
        }

    def get_all_states(self) -> List[dict]:
        return [state.to_dict() for state in self.states.values()]
