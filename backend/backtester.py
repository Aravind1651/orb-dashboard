"""
ORB Backtester — Simulates the 30-Min Opening Range Breakout strategy
on historical data from yfinance.

Intervals used:
  - 5m  → for 1d, 1w, 1mo  (accurate candle-level simulation)
  - 30m → for 6mo, 1y, 2y  (first 30-min candle = OR)
"""
import asyncio
import logging
from datetime import datetime, timedelta, time, date
from typing import Optional
import pandas as pd
import pytz
import yfinance as yf

from backend.orb_engine import compute_atr

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

SESSION_START  = time(9, 15)
OR_END         = time(9, 45)
SQUARE_OFF_T   = time(15, 15)
MARKET_CLOSE   = time(15, 30)


# ─────────────────────────────────────────────────────────────────────────────
# Stock Lists
# ─────────────────────────────────────────────────────────────────────────────
TRACKED_STOCKS = [
    {"symbol": "SUZLON.NS",  "name": "Suzlon Energy",      "group": "Tracked"},
    {"symbol": "BSE.NS",     "name": "BSE Ltd",             "group": "Tracked"},
    {"symbol": "HFCL.NS",    "name": "HFCL",                "group": "Tracked"},
    {"symbol": "IFCI.NS",    "name": "IFCI",                "group": "Tracked"},
    {"symbol": "TMCV.NS",    "name": "TMCV",                "group": "Tracked"},
]

NIFTY50_STOCKS = [
    {"symbol": "ADANIENT.NS",   "name": "Adani Enterprises",       "group": "Nifty 50"},
    {"symbol": "ADANIPORTS.NS", "name": "Adani Ports",             "group": "Nifty 50"},
    {"symbol": "APOLLOHOSP.NS", "name": "Apollo Hospitals",        "group": "Nifty 50"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints",            "group": "Nifty 50"},
    {"symbol": "AXISBANK.NS",   "name": "Axis Bank",               "group": "Nifty 50"},
    {"symbol": "BAJAJ-AUTO.NS", "name": "Bajaj Auto",              "group": "Nifty 50"},
    {"symbol": "BAJAJFINSV.NS", "name": "Bajaj Finserv",           "group": "Nifty 50"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance",           "group": "Nifty 50"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel",           "group": "Nifty 50"},
    {"symbol": "BPCL.NS",       "name": "BPCL",                    "group": "Nifty 50"},
    {"symbol": "BRITANNIA.NS",  "name": "Britannia",               "group": "Nifty 50"},
    {"symbol": "CIPLA.NS",      "name": "Cipla",                   "group": "Nifty 50"},
    {"symbol": "COALINDIA.NS",  "name": "Coal India",              "group": "Nifty 50"},
    {"symbol": "DIVISLAB.NS",   "name": "Divis Laboratories",      "group": "Nifty 50"},
    {"symbol": "DRREDDY.NS",    "name": "Dr. Reddy's Labs",        "group": "Nifty 50"},
    {"symbol": "EICHERMOT.NS",  "name": "Eicher Motors",           "group": "Nifty 50"},
    {"symbol": "GRASIM.NS",     "name": "Grasim Industries",       "group": "Nifty 50"},
    {"symbol": "HCLTECH.NS",    "name": "HCL Technologies",        "group": "Nifty 50"},
    {"symbol": "HDFCBANK.NS",   "name": "HDFC Bank",               "group": "Nifty 50"},
    {"symbol": "HDFCLIFE.NS",   "name": "HDFC Life Insurance",     "group": "Nifty 50"},
    {"symbol": "HEROMOTOCO.NS", "name": "Hero MotoCorp",           "group": "Nifty 50"},
    {"symbol": "HINDALCO.NS",   "name": "Hindalco Industries",     "group": "Nifty 50"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever",      "group": "Nifty 50"},
    {"symbol": "ICICIBANK.NS",  "name": "ICICI Bank",              "group": "Nifty 50"},
    {"symbol": "INDUSINDBK.NS", "name": "IndusInd Bank",           "group": "Nifty 50"},
    {"symbol": "INFY.NS",       "name": "Infosys",                 "group": "Nifty 50"},
    {"symbol": "ITC.NS",        "name": "ITC",                     "group": "Nifty 50"},
    {"symbol": "JSWSTEEL.NS",   "name": "JSW Steel",               "group": "Nifty 50"},
    {"symbol": "KOTAKBANK.NS",  "name": "Kotak Mahindra Bank",     "group": "Nifty 50"},
    {"symbol": "LT.NS",         "name": "Larsen & Toubro",         "group": "Nifty 50"},
    {"symbol": "MM.NS",         "name": "Mahindra & Mahindra",     "group": "Nifty 50"},
    {"symbol": "MARUTI.NS",     "name": "Maruti Suzuki",           "group": "Nifty 50"},
    {"symbol": "NESTLEIND.NS",  "name": "Nestle India",            "group": "Nifty 50"},
    {"symbol": "NTPC.NS",       "name": "NTPC",                    "group": "Nifty 50"},
    {"symbol": "ONGC.NS",       "name": "ONGC",                    "group": "Nifty 50"},
    {"symbol": "POWERGRID.NS",  "name": "Power Grid Corp",         "group": "Nifty 50"},
    {"symbol": "RELIANCE.NS",   "name": "Reliance Industries",     "group": "Nifty 50"},
    {"symbol": "SBILIFE.NS",    "name": "SBI Life Insurance",      "group": "Nifty 50"},
    {"symbol": "SBIN.NS",       "name": "State Bank of India",     "group": "Nifty 50"},
    {"symbol": "SHREECEM.NS",   "name": "Shree Cement",            "group": "Nifty 50"},
    {"symbol": "SUNPHARMA.NS",  "name": "Sun Pharmaceutical",      "group": "Nifty 50"},
    {"symbol": "TATACONSUM.NS", "name": "Tata Consumer Products",  "group": "Nifty 50"},
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors",             "group": "Nifty 50"},
    {"symbol": "TATASTEEL.NS",  "name": "Tata Steel",              "group": "Nifty 50"},
    {"symbol": "TCS.NS",        "name": "TCS",                     "group": "Nifty 50"},
    {"symbol": "TECHM.NS",      "name": "Tech Mahindra",           "group": "Nifty 50"},
    {"symbol": "TITAN.NS",      "name": "Titan Company",           "group": "Nifty 50"},
    {"symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement",        "group": "Nifty 50"},
    {"symbol": "UPL.NS",        "name": "UPL",                     "group": "Nifty 50"},
    {"symbol": "WIPRO.NS",      "name": "Wipro",                   "group": "Nifty 50"},
]

ALL_STOCKS = TRACKED_STOCKS + NIFTY50_STOCKS


# ─────────────────────────────────────────────────────────────────────────────
# Period → (start, end, interval)
# ─────────────────────────────────────────────────────────────────────────────
def _period_config(period: str):
    today = datetime.now(IST).date()
    configs = {
        "1d":  (today - timedelta(days=2),   today, "5m",  "5-min candles"),
        "1w":  (today - timedelta(weeks=1),  today, "5m",  "5-min candles"),
        "1mo": (today - timedelta(days=30),  today, "5m",  "5-min candles"),
        "6mo": (today - timedelta(days=182), today, "30m", "30-min candles"),
        "1y":  (today - timedelta(days=365), today, "30m", "30-min candles"),
        "2y":  (today - timedelta(days=730), today, "30m", "30-min candles"),
    }
    return configs.get(period, configs["1mo"])


# ─────────────────────────────────────────────────────────────────────────────
# Data fetch (synchronous — run in executor)
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_data(symbol: str, start: date, end: date, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return pd.DataFrame()

        # Flatten MultiIndex columns (yfinance ≥ 0.2 returns MultiIndex)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]

        # Required columns
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                return pd.DataFrame()

        # Convert index to IST
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        return df

    except Exception as e:
        logger.error(f"Fetch error [{symbol}]: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Simulate one trading day
# ─────────────────────────────────────────────────────────────────────────────
def _simulate_day(day_df: pd.DataFrame, config: dict) -> Optional[dict]:
    """
    Run ORB strategy logic on a single day's candles.
    Returns a trade dict or None if no breakout occurred.
    """
    if day_df.empty or len(day_df) < 3:
        return None

    trade_date = day_df.index[0].date().isoformat()
    atr_val = compute_atr(day_df, config.get("atr_length", 14)) or 0.0
    multiplier = config.get("atr_multiplier", 1.0)
    rr = config.get("rr_ratio", 2.0)

    range_high: Optional[float] = None
    range_low:  Optional[float] = None
    range_defined = False
    position  = "FLAT"
    entry_price: Optional[float] = None
    stop_loss:   Optional[float] = None
    target_price: Optional[float] = None
    direction:   Optional[str] = None
    entry_time:  Optional[str] = None

    for ts, row in day_df.iterrows():
        t     = ts.time()
        close = float(row["close"])
        high  = float(row["high"])
        low   = float(row["low"])

        # ── Build Opening Range ────────────────────────────────────────
        if SESSION_START <= t < OR_END:
            if range_high is None:
                range_high, range_low = high, low
            else:
                range_high = max(range_high, high)
                range_low  = min(range_low,  low)

        elif t >= OR_END and not range_defined and range_high is not None:
            range_defined = True

        # ── Square Off ─────────────────────────────────────────────────
        if t >= SQUARE_OFF_T and position != "FLAT":
            pnl = (close - entry_price) if direction == "LONG" else (entry_price - close)
            return _trade(trade_date, direction, entry_price, entry_time,
                          close, ts, "SQUARE_OFF", stop_loss, target_price,
                          range_high, range_low, atr_val, pnl)

        # ── Trading Zone ───────────────────────────────────────────────
        if range_defined and OR_END <= t < SQUARE_OFF_T:
            if position == "FLAT":
                if close > range_high:
                    sl   = range_low - atr_val * multiplier
                    risk = close - sl
                    tp   = close + risk * rr
                    position, direction = "LONG", "LONG"
                    entry_price, stop_loss, target_price = close, sl, tp
                    entry_time = ts.strftime("%H:%M")

                elif close < range_low:
                    sl   = range_high + atr_val * multiplier
                    risk = sl - close
                    tp   = close - risk * rr
                    position, direction = "SHORT", "SHORT"
                    entry_price, stop_loss, target_price = close, sl, tp
                    entry_time = ts.strftime("%H:%M")

            elif position == "LONG":
                if low <= stop_loss:
                    pnl = stop_loss - entry_price
                    return _trade(trade_date, "LONG", entry_price, entry_time,
                                  stop_loss, ts, "SL_HIT", stop_loss, target_price,
                                  range_high, range_low, atr_val, pnl)
                elif high >= target_price:
                    pnl = target_price - entry_price
                    return _trade(trade_date, "LONG", entry_price, entry_time,
                                  target_price, ts, "TP_HIT", stop_loss, target_price,
                                  range_high, range_low, atr_val, pnl)

            elif position == "SHORT":
                if high >= stop_loss:
                    pnl = entry_price - stop_loss
                    return _trade(trade_date, "SHORT", entry_price, entry_time,
                                  stop_loss, ts, "SL_HIT", stop_loss, target_price,
                                  range_high, range_low, atr_val, pnl)
                elif low <= target_price:
                    pnl = entry_price - target_price
                    return _trade(trade_date, "SHORT", entry_price, entry_time,
                                  target_price, ts, "TP_HIT", stop_loss, target_price,
                                  range_high, range_low, atr_val, pnl)

    return None


def _trade(date_str, direction, entry, entry_time, exit_price, exit_ts,
           exit_type, sl, tp, rh, rl, atr, pnl_points) -> dict:
    ep = entry if entry else 1.0
    return {
        "date":        date_str,
        "direction":   direction,
        "entry":       round(entry, 2),
        "entry_time":  entry_time or "—",
        "exit":        round(exit_price, 2),
        "exit_time":   exit_ts.strftime("%H:%M"),
        "exit_type":   exit_type,
        "sl":          round(sl, 2) if sl else None,
        "tp":          round(tp, 2) if tp else None,
        "range_high":  round(rh, 2) if rh else None,
        "range_low":   round(rl, 2) if rl else None,
        "atr":         round(atr, 2),
        "pnl_points":  round(pnl_points, 2),
        "pnl_percent": round((pnl_points / ep) * 100, 2),
        "result":      "WIN" if pnl_points > 0 else ("LOSS" if pnl_points < 0 else "BREAKEVEN"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
async def run_backtest(symbol: str, period: str, config: dict) -> dict:
    """
    Run the ORB backtest. Returns summary + per-day trade list.
    """
    start, end, interval, interval_label = _period_config(period)

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, _fetch_data, symbol, start, end, interval)

    if df.empty:
        return {
            "symbol": symbol, "period": period,
            "summary": {"error": "No data available. Check symbol or try a shorter period."},
            "trades": [],
        }

    # Group by calendar date and simulate each day
    trades = []
    for day_date, day_df in df.groupby(df.index.date):
        # Only include weekdays with enough candles
        if day_date.weekday() >= 5 or len(day_df) < 3:
            continue
        trade = _simulate_day(day_df.copy(), config)
        if trade:
            trades.append(trade)

    # Sort chronologically
    trades.sort(key=lambda t: t["date"])

    wins      = [t for t in trades if t["result"] == "WIN"]
    losses    = [t for t in trades if t["result"] == "LOSS"]
    total_pnl = sum(t["pnl_points"] for t in trades)
    tp_hits   = [t for t in trades if t["exit_type"] == "TP_HIT"]
    sl_hits   = [t for t in trades if t["exit_type"] == "SL_HIT"]
    sq_offs   = [t for t in trades if t["exit_type"] == "SQUARE_OFF"]

    # Equity curve (cumulative P&L per trade)
    cumulative = 0.0
    for t in trades:
        cumulative += t["pnl_points"]
        t["cumulative_pnl"] = round(cumulative, 2)

    summary = {
        "symbol":        symbol,
        "period":        period,
        "interval":      interval,
        "interval_label": interval_label,
        "start_date":    start.isoformat(),
        "end_date":      end.isoformat(),
        "total_trades":  len(trades),
        "wins":          len(wins),
        "losses":        len(losses),
        "breakevens":    len(trades) - len(wins) - len(losses),
        "win_rate":      round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_pnl":     round(total_pnl, 2),
        "avg_pnl":       round(total_pnl / len(trades), 2) if trades else 0,
        "max_win":       round(max((t["pnl_points"] for t in wins),   default=0), 2),
        "max_loss":      round(min((t["pnl_points"] for t in losses), default=0), 2),
        "tp_hits":       len(tp_hits),
        "sl_hits":       len(sl_hits),
        "square_offs":   len(sq_offs),
        "longs":         len([t for t in trades if t["direction"] == "LONG"]),
        "shorts":        len([t for t in trades if t["direction"] == "SHORT"]),
    }

    return {"symbol": symbol, "period": period, "summary": summary, "trades": trades}
