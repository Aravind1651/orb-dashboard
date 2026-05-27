"""
Pydantic models for the ORB Dashboard.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class StrategyConfig(BaseModel):
    atr_length: int = 14
    atr_multiplier: float = 1.0
    rr_ratio: float = 2.0


class StockState(BaseModel):
    symbol: str
    display_name: str
    current_price: Optional[float] = None
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    range_defined: bool = False
    position: str = "FLAT"  # FLAT, LONG, SHORT
    atr: Optional[float] = None
    last_updated: Optional[str] = None
    market_status: str = "CLOSED"  # OPEN, BUILDING_OR, TRADING, CLOSED


class AlertSignal(BaseModel):
    id: Optional[int] = None
    symbol: str
    display_name: str
    signal_type: str        # BUY, SELL, SQUARE_OFF
    entry_price: float
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    risk_reward: Optional[float] = None
    atr: Optional[float] = None
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    timestamp: str
    date: str
    status: str = "ACTIVE"  # ACTIVE, HIT_TP, HIT_SL, SQUARED_OFF


class WSMessage(BaseModel):
    type: str               # alert, state_update, heartbeat, day_reset
    data: dict
    timestamp: str


class HistoryFilter(BaseModel):
    date: Optional[str] = None
    symbol: Optional[str] = None
