"""
SQLite CRM for FarmFresh Boxes.
Tables: customers, orders, conversations.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import DATABASE_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                phone              TEXT UNIQUE NOT NULL,
                name               TEXT,
                preferred_location TEXT,
                preferred_day      TEXT,
                pending_box_type   TEXT,
                stage              TEXT    DEFAULT 'new',
                total_orders       INTEGER DEFAULT 0,
                created_at         TEXT    DEFAULT (datetime('now')),
                updated_at         TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id       INTEGER NOT NULL,
                box_type          TEXT    NOT NULL,
                delivery_date     TEXT    NOT NULL,
                delivery_location TEXT    NOT NULL,
                price             REAL    NOT NULL,
                status            TEXT    DEFAULT 'confirmed',
                notes             TEXT,
                created_at        TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                direction   TEXT    NOT NULL,
                message     TEXT    NOT NULL,
                timestamp   TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)
        for col in ("preferred_day TEXT", "pending_box_type TEXT", "pending_delivery_date TEXT"):
            try:
                conn.execute(f"ALTER TABLE customers ADD COLUMN {col}")
            except Exception:
                pass


# ── Customers ─────────────────────────────────────────────────────────────────

def get_or_create_customer(phone: str) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE phone = ?", (phone,)).fetchone()
        if row:
            return dict(row)
        conn.execute("INSERT INTO customers (phone) VALUES (?)", (phone,))
        row = conn.execute("SELECT * FROM customers WHERE phone = ?", (phone,)).fetchone()
        return dict(row)


def get_customer(customer_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None


def get_all_customers() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def update_customer(customer_id: int, **kwargs):
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [customer_id]
    with get_db() as conn:
        conn.execute(f"UPDATE customers SET {fields} WHERE id = ?", values)


# ── Orders ────────────────────────────────────────────────────────────────────

def create_order(
    customer_id: int,
    box_type: str,
    delivery_date: str,
    delivery_location: str,
    price: float,
    notes: str = None,
) -> dict:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO orders (customer_id, box_type, delivery_date, delivery_location, price, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (customer_id, box_type, delivery_date, delivery_location, price, notes),
        )
        conn.execute(
            "UPDATE customers SET total_orders = total_orders + 1, stage = 'confirmed', updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), customer_id),
        )
        row = conn.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1",
            (customer_id,),
        ).fetchone()
        return dict(row)


def get_orders(customer_id: int = None) -> list[dict]:
    with get_db() as conn:
        if customer_id:
            rows = conn.execute(
                "SELECT * FROM orders WHERE customer_id = ? ORDER BY delivery_date DESC",
                (customer_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT o.*, c.name, c.phone
                   FROM orders o JOIN customers c ON o.customer_id = c.id
                   ORDER BY o.delivery_date DESC""",
            ).fetchall()
        return [dict(r) for r in rows]


def update_order_status(order_id: int, status: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )


def get_latest_order(customer_id: int) -> dict | None:
    """Return the most recently *created* order for a customer (by created_at DESC)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1",
            (customer_id,),
        ).fetchone()
        return dict(row) if row else None


def get_upcoming_orders(days: int = 7) -> list[dict]:
    today = datetime.utcnow().date().isoformat()
    until = (datetime.utcnow().date() + timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT o.*, c.name, c.phone
               FROM orders o JOIN customers c ON o.customer_id = c.id
               WHERE o.delivery_date BETWEEN ? AND ? AND o.status = 'confirmed'
               ORDER BY o.delivery_date""",
            (today, until),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Conversations ─────────────────────────────────────────────────────────────

def log_message(customer_id: int, direction: str, message: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (customer_id, direction, message) VALUES (?, ?, ?)",
            (customer_id, direction, message),
        )


def get_conversation_history(customer_id: int, limit: int = 30) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE customer_id = ? ORDER BY timestamp DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    week_ago  = (datetime.utcnow().date() - timedelta(days=7)).isoformat()
    today_str = datetime.utcnow().date().isoformat()

    with get_db() as conn:
        total_customers = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]

        orders_week = conn.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE created_at >= ? AND status != 'cancelled'",
            (week_ago,),
        ).fetchone()["c"]

        revenue_week = conn.execute(
            "SELECT COALESCE(SUM(price), 0) AS r FROM orders WHERE created_at >= ? AND status != 'cancelled'",
            (week_ago,),
        ).fetchone()["r"]

        upcoming = conn.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE delivery_date >= ? AND status = 'confirmed'",
            (today_str,),
        ).fetchone()["c"]

        new_today = conn.execute(
            "SELECT COUNT(*) AS c FROM customers WHERE created_at >= ?", (today_str,)
        ).fetchone()["c"]

        box_rows = conn.execute(
            "SELECT box_type, COUNT(*) AS c FROM orders WHERE status != 'cancelled' GROUP BY box_type"
        ).fetchall()

        location_rows = conn.execute(
            """SELECT delivery_location, COUNT(*) AS c FROM orders
               WHERE status != 'cancelled' GROUP BY delivery_location ORDER BY c DESC"""
        ).fetchall()

        stage_rows = conn.execute(
            "SELECT stage, COUNT(*) AS c FROM customers GROUP BY stage"
        ).fetchall()

    return {
        "total_customers":     total_customers,
        "orders_this_week":    orders_week,
        "revenue_this_week":   round(revenue_week, 2),
        "upcoming_deliveries": upcoming,
        "new_today":           new_today,
        "box_popularity":      {r["box_type"]: r["c"] for r in box_rows},
        "by_location":         {r["delivery_location"]: r["c"] for r in location_rows},
        "by_stage":            {r["stage"]: r["c"] for r in stage_rows},
    }
