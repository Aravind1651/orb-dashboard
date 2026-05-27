"""
SQLite database layer using aiosqlite.
Manages today's alerts and historical archive.
Auto-archives at market close (3:30 PM IST) and resets for next day.
"""
import aiosqlite
import asyncio
import logging
import os
from datetime import datetime, date
from typing import List, Optional
import pytz

logger = logging.getLogger(__name__)

# On Render: use /data mount (persistent disk). Locally: use ./data folder.
_DATA_DIR = "/data" if os.path.exists("/data") else os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(_DATA_DIR, "alerts.db")
IST = pytz.timezone("Asia/Kolkata")



async def get_db():
    return await aiosqlite.connect(DB_PATH)


async def init_db():
    """Create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                display_name TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                target_price REAL,
                risk_reward REAL,
                atr REAL,
                range_high REAL,
                range_low REAL,
                timestamp TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                display_name TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                target_price REAL,
                risk_reward REAL,
                atr REAL,
                range_high REAL,
                range_low REAL,
                timestamp TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT DEFAULT 'ACTIVE',
                archived_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategy_config (
                id INTEGER PRIMARY KEY,
                atr_length INTEGER DEFAULT 14,
                atr_multiplier REAL DEFAULT 1.0,
                rr_ratio REAL DEFAULT 2.0,
                updated_at TEXT
            )
        """)
        # Insert default config if not exists
        await db.execute("""
            INSERT OR IGNORE INTO strategy_config (id, atr_length, atr_multiplier, rr_ratio, updated_at)
            VALUES (1, 14, 1.0, 2.0, ?)
        """, (datetime.now(IST).isoformat(),))
        await db.commit()
    logger.info(f"Database initialized at {DB_PATH}")


async def save_alert(alert: dict) -> int:
    """Save a new alert to today's alerts table."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO alerts (symbol, display_name, signal_type, entry_price,
                stop_loss, target_price, risk_reward, atr, range_high, range_low,
                timestamp, date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert["symbol"], alert["display_name"], alert["signal_type"],
            alert["entry_price"], alert.get("stop_loss"), alert.get("target_price"),
            alert.get("risk_reward"), alert.get("atr"),
            alert.get("range_high"), alert.get("range_low"),
            alert["timestamp"], alert["date"], alert.get("status", "ACTIVE")
        ))
        await db.commit()
        return cursor.lastrowid


async def get_today_alerts() -> List[dict]:
    """Get all alerts for today."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts WHERE date = ? ORDER BY id DESC",
            (today,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_history(filter_date: Optional[str] = None, symbol: Optional[str] = None) -> List[dict]:
    """Get historical alerts with optional date/symbol filter."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM history WHERE 1=1"
        params = []
        if filter_date:
            query += " AND date = ?"
            params.append(filter_date)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY id DESC LIMIT 500"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_history_dates() -> List[str]:
    """Get list of all dates that have history records."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT date FROM history ORDER BY date DESC LIMIT 90"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def archive_today_and_reset():
    """
    Archive today's alerts to history table and clear today's alerts.
    Called at market close (3:30 PM IST).
    """
    today = date.today().isoformat()
    archived_at = datetime.now(IST).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        # Copy today's alerts to history
        await db.execute("""
            INSERT INTO history (symbol, display_name, signal_type, entry_price,
                stop_loss, target_price, risk_reward, atr, range_high, range_low,
                timestamp, date, status, archived_at)
            SELECT symbol, display_name, signal_type, entry_price,
                stop_loss, target_price, risk_reward, atr, range_high, range_low,
                timestamp, date, status, ?
            FROM alerts
            WHERE date = ?
        """, (archived_at, today))
        # Clear today's alerts
        await db.execute("DELETE FROM alerts WHERE date = ?", (today,))
        await db.commit()
    logger.info(f"Archived {today} alerts to history and reset today's table")


async def update_alert_status(alert_id: int, status: str):
    """Update the status of an alert (e.g., HIT_TP, HIT_SL, SQUARED_OFF)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alerts SET status = ? WHERE id = ?",
            (status, alert_id)
        )
        await db.commit()


async def get_strategy_config() -> dict:
    """Get current strategy configuration."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM strategy_config WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {"atr_length": 14, "atr_multiplier": 1.0, "rr_ratio": 2.0}


async def update_strategy_config(atr_length: int, atr_multiplier: float, rr_ratio: float):
    """Update strategy configuration."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE strategy_config
            SET atr_length = ?, atr_multiplier = ?, rr_ratio = ?, updated_at = ?
            WHERE id = 1
        """, (atr_length, atr_multiplier, rr_ratio, datetime.now(IST).isoformat()))
        await db.commit()
