"""
Tests for order placement, status queries, and cancellation.

Agent is mocked — these tests cover the routing/business logic in main.py
independently of any AI provider.

Key scenarios verified:
- Agent sets order_ready → order is created
- Agent misses order_ready but reply sounds confirmed → fallback creates order
- Status query reply sounds confirmed → NO duplicate order (has_upcoming guard)
- Past order + new pending fields → new order IS allowed
- cancel_order flag via chat → order cancelled, stage reset
- No active order to cancel → graceful, agent reply preserved
- PATCH /orders/{id}/cancel and /deliver endpoints
- Guard rails: can't deliver cancelled, can't cancel delivered, 404 on missing
"""
import os
import sys

# Set the test DB path BEFORE importing config/crm/main so config.py picks
# it up at import time (python-dotenv does not override existing env vars).
_TEST_DB = "/tmp/farmfresh_test.db"
os.environ["DATABASE_PATH"] = _TEST_DB
os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("AI_PROVIDER", "claude")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import sqlite3
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

import crm
import main as main_module
from fastapi.testclient import TestClient

PHONE       = "+351910000099"
FUTURE_DATE = (datetime.utcnow().date() + timedelta(days=3)).isoformat()
PAST_DATE   = (datetime.utcnow().date() - timedelta(days=3)).isoformat()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_db():
    """Each test gets a clean, freshly initialised database."""
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)
    crm.init_db()


@pytest.fixture()
def client(fresh_db):
    """FastAPI test client with scheduler disabled."""
    with patch("scheduler.start_scheduler"), patch("scheduler.stop_scheduler"):
        with TestClient(main_module.app) as c:
            yield c


# ── DB helpers ────────────────────────────────────────────────────────────────

def _send(client, message, phone=PHONE):
    return client.post("/test/message", params={"phone": phone, "message": message})


def _customer_with_pending_fields(phone=PHONE, box="mix", location="Cascais", day="wednesday"):
    """Customer who has all order fields set but no confirmed order yet."""
    c = crm.get_or_create_customer(phone)
    crm.update_customer(
        c["id"],
        stage="selecting",
        pending_box_type=box,
        preferred_location=location,
        preferred_day=day,
    )
    return c


def _customer_with_active_order(phone=PHONE, delivery_date=None):
    """Customer with a future confirmed order."""
    date = delivery_date or FUTURE_DATE
    c = crm.get_or_create_customer(phone)
    crm.update_customer(
        c["id"],
        stage="confirmed",
        pending_box_type="mix",
        preferred_location="Cascais",
        preferred_day="wednesday",
    )
    order = crm.create_order(c["id"], "mix", date, "Cascais", 26.0)
    return c, order


# ── Order placement ───────────────────────────────────────────────────────────

def test_order_created_after_user_confirms(client):
    """
    New flow: agent collects fields → confirmation prompt shown → user says YES → order created.
    No order is created until the user explicitly confirms.
    """
    import agent as agent_module

    collected = {"box_type": "mix", "delivery_date": FUTURE_DATE,
                 "delivery_location": "Cascais", "delivery_day": "wednesday", "stage": "selecting"}

    def mock_collect(customer_id, message):
        # Simulate what the real agent does: persist fields in CRM before returning
        agent_module._apply_tool_data(customer_id, collected)
        return "I have everything I need!", collected

    # Step 1: agent collects fields → confirmation prompt appended, no order yet
    with patch("agent.process_message", side_effect=mock_collect):
        resp = _send(client, "I want a mix box on Wednesday in Cascais")

    assert resp.status_code == 200
    c = crm.get_or_create_customer(PHONE)
    assert crm.get_orders(c["id"]) == []  # no order yet
    assert "YES" in resp.json()["ai_reply"] or "yes" in resp.json()["ai_reply"].lower()
    assert crm.get_customer(c["id"])["stage"] == "awaiting_confirmation"

    # Step 2: user says YES → order created
    resp2 = _send(client, "yes")
    assert resp2.status_code == 200
    orders = crm.get_orders(c["id"])
    assert len(orders) == 1
    assert orders[0]["box_type"] == "mix"
    assert orders[0]["delivery_location"] == "Cascais"
    assert f"#{orders[0]['id']}" in resp2.json()["ai_reply"]


def test_fallback_creates_order_when_agent_misses_order_ready(client):
    """
    If the agent doesn't set order_ready but:
      - all required fields are in the CRM, AND
      - the reply sounds like a confirmation
    then the fallback creates the order.
    """
    _customer_with_pending_fields()
    with patch("agent.process_message", return_value=(
        "Your order is confirmed and will be delivered on Wednesday!",
        {},
    )):
        resp = _send(client, "yes")

    assert resp.status_code == 200
    c = crm.get_or_create_customer(PHONE)
    assert len(crm.get_orders(c["id"])) == 1


def test_fallback_does_not_fire_when_fields_missing(client):
    """Fallback must not create an order if the customer has no fields stored."""
    crm.get_or_create_customer(PHONE)  # bare customer, no fields
    with patch("agent.process_message", return_value=(
        "Your order is confirmed!",
        {},
    )):
        resp = _send(client, "yes")

    assert resp.status_code == 200
    c = crm.get_or_create_customer(PHONE)
    assert crm.get_orders(c["id"]) == []


def test_fallback_does_not_fire_on_non_confirmation_reply(client):
    """Fallback only fires when the reply sounds like a confirmation."""
    _customer_with_pending_fields()
    with patch("agent.process_message", return_value=(
        "What location would you like your box delivered to?",
        {},
    )):
        resp = _send(client, "mix box please")

    assert resp.status_code == 200
    c = crm.get_or_create_customer(PHONE)
    assert crm.get_orders(c["id"]) == []


# ── Status query must not duplicate orders ────────────────────────────────────

def test_status_query_does_not_create_duplicate_order(client):
    """
    Customer asks 'what's my order?'. Agent replies with confirmation-sounding text.
    Since the customer already has an upcoming confirmed order, NO new order is created.
    """
    c, _ = _customer_with_active_order()
    with patch("agent.process_message", return_value=(
        f"Your mix box will be delivered to Cascais on {FUTURE_DATE}. It's confirmed! 🌿",
        {},
    )):
        resp = _send(client, "what is my order status?")

    assert resp.status_code == 200
    assert len(crm.get_orders(c["id"])) == 1  # still just the original


def test_multiple_status_queries_do_not_stack_orders(client):
    """Asking status several times never creates additional orders."""
    c, _ = _customer_with_active_order()
    reply = (f"Your confirmed order: mix box to Cascais on {FUTURE_DATE}.", {})
    with patch("agent.process_message", return_value=reply):
        for _ in range(3):
            _send(client, "status?")

    assert len(crm.get_orders(c["id"])) == 1


def _insert_old_order(customer_id, delivery_date, days_ago=10):
    """Insert an order with a created_at well in the past so just_created=False."""
    past_ts = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
    conn = sqlite3.connect(_TEST_DB)
    conn.execute(
        "INSERT INTO orders (customer_id, box_type, delivery_date, delivery_location, price, status, created_at)"
        " VALUES (?, 'mix', ?, 'Cascais', 26.0, 'confirmed', ?)",
        (customer_id, delivery_date, past_ts),
    )
    conn.execute(
        "UPDATE customers SET total_orders = total_orders + 1, stage = 'confirmed' WHERE id = ?",
        (customer_id,),
    )
    conn.commit()
    conn.close()


def test_past_order_does_not_block_new_order(client):
    """
    Customer whose confirmed order date has passed (no upcoming orders)
    can place a new one via the fallback.
    """
    c = crm.get_or_create_customer(PHONE)
    _insert_old_order(c["id"], PAST_DATE)
    crm.update_customer(
        c["id"],
        stage="selecting",
        pending_box_type="fruits",
        preferred_location="Sintra",
        preferred_day="friday",
    )
    with patch("agent.process_message", return_value=(
        "Your fruits box will be delivered to Sintra on Friday!",
        {},
    )):
        _send(client, "yes")

    assert len(crm.get_orders(c["id"])) == 2


# ── History / info queries must never place orders ────────────────────────────

def test_order_count_query_does_not_place_order(client):
    """'How many orders do I have?' should never create a new order."""
    c, _ = _customer_with_active_order()
    with patch("agent.process_message", return_value=(
        "You have 2 confirmed orders in total. Your latest is a Mix Box to Cascais.",
        {},
    )):
        resp = _send(client, "how many orders do i have?")

    assert resp.status_code == 200
    assert len(crm.get_orders(c["id"])) == 1


def test_history_query_with_past_orders_and_pending_fields_does_not_place_order(client):
    """
    Customer with past orders and stale pending fields asks about history.
    Even though fields are set and reply contains 'confirmed', no order is placed
    because the customer is not in an active ordering flow (stage='confirmed').
    """
    c = crm.get_or_create_customer(PHONE)
    _insert_old_order(c["id"], PAST_DATE)
    # Stale fields from a previous ordering session
    crm.update_customer(
        c["id"],
        pending_box_type="mix",
        preferred_location="Cascais",
        preferred_day="wednesday",
        # stage stays 'confirmed' (set by create_order)
    )
    with patch("agent.process_message", return_value=(
        "You have 1 confirmed order. It was a Mix Box delivered to Cascais on " + PAST_DATE + ".",
        {},
    )):
        resp = _send(client, "how many orders do i have?")

    assert resp.status_code == 200
    assert len(crm.get_orders(c["id"])) == 1  # no new order


def test_fallback_still_works_during_active_ordering(client):
    """Fallback still fires for customers in 'selecting' stage with confirmation-sounding reply."""
    _customer_with_pending_fields(day="friday")
    with patch("agent.process_message", return_value=(
        "Your order will be delivered on Friday — all confirmed!",
        {},
    )):
        _send(client, "yes")

    c = crm.get_or_create_customer(PHONE)
    assert len(crm.get_orders(c["id"])) == 1


# ── Cancellation via chat ─────────────────────────────────────────────────────

def test_cancel_via_chat_cancels_active_order(client):
    c, order = _customer_with_active_order()
    with patch("agent.process_message", return_value=(
        "Done, your order has been cancelled.",
        {"cancel_order": True},
    )):
        resp = _send(client, "please cancel my order")

    assert resp.status_code == 200
    orders = crm.get_orders(c["id"])
    assert orders[0]["status"] == "cancelled"
    assert crm.get_customer(c["id"])["stage"] == "browsing"


def test_cancel_via_chat_preserves_agent_reply_when_no_active_order(client):
    """If there is no active order to cancel, the agent's reply is sent as-is."""
    crm.get_or_create_customer(PHONE)
    with patch("agent.process_message", return_value=(
        "You don't have an active order to cancel.",
        {"cancel_order": True},
    )):
        resp = _send(client, "cancel my order")

    assert resp.status_code == 200
    assert "don't have" in resp.json()["ai_reply"].lower()


def test_cancel_only_affects_upcoming_order_not_past(client):
    """A past confirmed order is not touched by _cancel_active_order."""
    c = crm.get_or_create_customer(PHONE)
    crm.create_order(c["id"], "mix", PAST_DATE, "Cascais", 26.0)
    with patch("agent.process_message", return_value=(
        "You don't have an active order to cancel.",
        {"cancel_order": True},
    )):
        _send(client, "cancel")

    orders = crm.get_orders(c["id"])
    assert orders[0]["status"] == "confirmed"  # past order untouched


# ── Cancel / deliver via API ──────────────────────────────────────────────────

def test_cancel_order_via_api(client):
    c, order = _customer_with_active_order()
    resp = client.patch(f"/orders/{order['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert crm.get_orders(c["id"])[0]["status"] == "cancelled"
    assert crm.get_customer(c["id"])["stage"] == "browsing"


def test_deliver_order_via_api(client):
    c, order = _customer_with_active_order()
    resp = client.patch(f"/orders/{order['id']}/deliver")
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"
    assert crm.get_orders(c["id"])[0]["status"] == "delivered"


def test_cannot_deliver_cancelled_order(client):
    _, order = _customer_with_active_order()
    crm.update_order_status(order["id"], "cancelled")
    resp = client.patch(f"/orders/{order['id']}/deliver")
    assert resp.status_code == 400


def test_cannot_cancel_delivered_order(client):
    _, order = _customer_with_active_order()
    crm.update_order_status(order["id"], "delivered")
    resp = client.patch(f"/orders/{order['id']}/cancel")
    assert resp.status_code == 400


def test_order_not_found_returns_404(client):
    resp = client.patch("/orders/9999/cancel")
    assert resp.status_code == 404


# ── Awaiting confirmation: only YES/NO accepted ───────────────────────────────

def _awaiting_customer(phone=PHONE):
    """Customer in awaiting_confirmation stage with all fields set."""
    c = crm.get_or_create_customer(phone)
    crm.update_customer(
        c["id"],
        stage="awaiting_confirmation",
        pending_box_type="mix",
        preferred_location="Cascais",
        preferred_day="wednesday",
    )
    crm.log_message(c["id"], "outbound",
                    "Ready to place your order? 📦 Mix Box — Cascais — Wednesday\nReply YES or NO.")
    return c


@pytest.mark.parametrize("message", [
    "maybe", "confirm", "sure", "ok", "I confirm", "sounds good",
    "what was that?", "tell me more", "hmm", "3", "👍",
])
def test_non_yes_no_repeats_last_message_no_order(client, message):
    """Any message that is not yes/no repeats the last outbound and never creates an order."""
    c = _awaiting_customer()

    agent_called = False
    def fail_if_called(*_):
        nonlocal agent_called
        agent_called = True
        return "", {}

    with patch("agent.process_message", side_effect=fail_if_called):
        resp = _send(client, message)

    assert resp.status_code == 200
    assert not agent_called, f"Agent must not be called for '{message}'"
    assert crm.get_orders(c["id"]) == []
    assert crm.get_customer(c["id"])["stage"] == "awaiting_confirmation"
    # Reply must be the previous outbound message
    assert "YES or NO" in resp.json()["ai_reply"]


@pytest.mark.parametrize("message", ["yes", "y"])
def test_yes_creates_order(client, message):
    """Only 'yes' and 'y' must create the order."""
    _awaiting_customer()
    resp = _send(client, message)
    assert resp.status_code == 200
    c = crm.get_or_create_customer(PHONE)
    assert len(crm.get_orders(c["id"])) == 1


@pytest.mark.parametrize("message", ["no", "n"])
def test_no_cancels_confirmation(client, message):
    """Only 'no' and 'n' must clear fields and return to browsing."""
    _awaiting_customer()
    resp = _send(client, message)
    assert resp.status_code == 200
    c = crm.get_or_create_customer(PHONE)
    assert crm.get_orders(c["id"]) == []
    assert crm.get_customer(c["id"])["stage"] == "browsing"
    assert crm.get_customer(c["id"])["pending_box_type"] is None
