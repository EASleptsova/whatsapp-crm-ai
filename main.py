from __future__ import annotations

"""
FastAPI app — WhatsApp webhook + REST API for FarmFresh Boxes.

Endpoints:
  POST /webhook          Twilio WhatsApp webhook
  POST /test/message     Simulate inbound message (no Twilio needed)
  GET  /health           Health check + stats
  GET  /customers        All customers
  GET  /customers/{id}   Customer detail with orders + conversations
  GET  /orders           All orders
  GET  /stats            Dashboard stats
"""
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Path
from fastapi.responses import PlainTextResponse

import agent
import crm
import delivery_service
import scheduler as sched
from config import MOCK_MODE, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, BOX_PRICES


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    crm.init_db()
    sched.start_scheduler()
    print(f"🌱  FarmFresh Boxes running  |  mock_mode={MOCK_MODE}")
    yield
    sched.stop_scheduler()


app = FastAPI(
    title="FarmFresh Boxes — WhatsApp CRM",
    description="AI-powered WhatsApp ordering for farm-to-door delivery.",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_if_new_conversation(customer: dict):
    """Clear pending order fields only when a confirmed customer has no upcoming deliveries."""
    if customer.get("stage") != "confirmed":
        return
    upcoming = crm.get_upcoming_orders()
    customer_has_upcoming = any(o["customer_id"] == customer["id"] for o in upcoming)
    if not customer_has_upcoming:
        crm.update_customer(
            customer["id"],
            stage="browsing",
            pending_box_type=None,
            preferred_location=None,
            preferred_day=None,
        )


def _send_whatsapp(to: str, body: str):
    if MOCK_MODE:
        print(f"[MOCK → {to}] {body[:120]}")
        return
    from twilio.rest import Client
    Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN).messages.create(
        from_=TWILIO_WHATSAPP_FROM, to=to, body=body,
    )


def _cancel_active_order(customer_id: int) -> str | None:
    """Cancel the customer's nearest upcoming confirmed order. Returns confirmation message or None."""
    today = datetime.utcnow().date().isoformat()
    orders = crm.get_orders(customer_id)
    active = next(
        (o for o in orders if o["status"] == "confirmed" and o["delivery_date"] >= today),
        None,
    )
    if not active:
        return None
    crm.update_order_status(active["id"], "cancelled")
    crm.update_customer(customer_id, stage="browsing")
    labels = {"fruits": "🍎 Fruits Box", "vegetables": "🥦 Vegetables Box", "mix": "🌿 Mix Box"}
    label  = labels.get(active["box_type"], active["box_type"].title())
    return (
        f"✅ Your order has been cancelled.\n\n"
        f"📦 {label}\n"
        f"📍 {active['delivery_location']}\n"
        f"🚚 Was scheduled for: {active['delivery_date']}\n\n"
        f"Let us know whenever you'd like to place a new order! 🌱"
    )


_CONFIRM_KEYWORDS = {"yes", "y"}
_DECLINE_KEYWORDS = {"no", "n"}

BOX_LABELS = {"fruits": "🍎 Fruits Box", "vegetables": "🥦 Vegetables Box", "mix": "🌿 Mix Box"}


def _order_confirmation_prompt(customer: dict) -> str:
    box   = customer.get("pending_box_type", "")
    loc   = customer.get("preferred_location", "")
    date  = customer.get("pending_delivery_date", "") or customer.get("preferred_day", "")
    price = BOX_PRICES.get(box, 0)
    label = BOX_LABELS.get(box, box.title())
    return (
        f"Ready to place your order? 🛒\n\n"
        f"📦 {label} — €{price:.0f}\n"
        f"📍 {loc}\n"
        f"🚚 Delivery: {date}\n\n"
        f"Reply *YES* to confirm or *NO* to cancel."
    )


def _confirm_order(customer_id: int, order_data: dict) -> str | None:
    """Create an order from agent data. Returns confirmation message or None on failure."""
    # Fall back to stored customer data for fields the AI omitted in this turn
    customer  = crm.get_customer(customer_id)
    box_type  = order_data.get("box_type")  or customer.get("pending_box_type")
    location  = order_data.get("delivery_location") or customer.get("preferred_location")
    date      = order_data.get("delivery_date") or customer.get("pending_delivery_date")

    # Resolve weekday name → nearest actual date
    preferred_day = order_data.get("delivery_day") or customer.get("preferred_day")
    if not date and preferred_day:
        slots = delivery_service.get_available_dates(preferred_day=preferred_day)
        if slots:
            date = slots[0]["date"]

    print(f"[ORDER] box={box_type} date={date} location={location} preferred_day={preferred_day}")
    if not all([box_type, date, location]):
        print(f"[ORDER] Missing fields — order not created")
        return None

    result = delivery_service.create_order(customer_id, box_type, date, location)
    if not result["success"]:
        return None
    crm.update_customer(
        customer_id,
        pending_box_type=None,
        pending_delivery_date=None,
    )

    labels = {"fruits": "🍎 Fruits Box", "vegetables": "🥦 Vegetables Box", "mix": "🌿 Mix Box"}
    label    = labels.get(box_type, box_type.title())
    price    = result["price"]
    order_id = result["order"]["id"]

    return (
        f"✅ Order confirmed! (#{order_id})\n\n"
        f"📦 {label} — €{price:.0f}\n"
        f"📍 {location}\n"
        f"🚚 Delivery: {date}\n\n"
        f"We'll bring it fresh from the farm! See you then 🌱"
    )


# ── Core message handler ──────────────────────────────────────────────────────

def _crm_fields_complete(customer: dict) -> bool:
    """True when the CRM has everything needed to place an order."""
    return bool(
        customer.get("pending_box_type") and
        customer.get("preferred_location") and
        (customer.get("pending_delivery_date") or customer.get("preferred_day"))
    )


def _handle_message(customer_id: int, body: str) -> str:
    customer = crm.get_customer(customer_id)
    words    = set(body.strip().lower().split())

    is_confirm = bool(words & _CONFIRM_KEYWORDS)
    is_decline = bool(words & _DECLINE_KEYWORDS)

    # ── User explicitly confirms → create order directly from CRM fields ──────
    if is_confirm and _crm_fields_complete(customer):
        confirmation = _confirm_order(customer_id, {})
        if confirmation:
            return confirmation

    # ── Awaiting confirmation: don't let agent handle the message ─────────────
    if customer.get("stage") == "awaiting_confirmation":
        if is_decline:
            crm.update_customer(
                customer_id,
                stage="browsing",
                pending_box_type=None,
                pending_delivery_date=None,
                preferred_location=None,
                preferred_day=None,
            )
            return "No problem! Let me know whenever you'd like to order. 🌱"
        # Anything else → repeat the last outbound message from DB (no agent call)
        history = crm.get_conversation_history(customer_id)
        last_outbound = next((h["message"] for h in reversed(history) if h["direction"] == "outbound"), None)
        return last_outbound or _order_confirmation_prompt(customer)

    # ── Normal agent turn ─────────────────────────────────────────────────────
    reply, order_data = agent.process_message(customer_id, body)

    if order_data.get("cancel_order"):
        cancellation = _cancel_active_order(customer_id)
        return cancellation if cancellation else reply

    # Store delivery_date if agent resolved one
    if order_data.get("delivery_date"):
        crm.update_customer(customer_id, pending_delivery_date=order_data["delivery_date"])

    # After any agent turn, if all 3 fields are in CRM, always append the confirmation
    # prompt to whatever the agent said — until user replies YES or NO.
    customer = crm.get_customer(customer_id)
    if _crm_fields_complete(customer):
        crm.update_customer(customer_id, stage="awaiting_confirmation")
        return f"{reply}\n\n{_order_confirmation_prompt(customer)}"

    return reply


# ── Twilio webhook ────────────────────────────────────────────────────────────

@app.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(
    From: str        = Form(...),
    Body: str        = Form(...),
    ProfileName: str = Form(default=""),
):
    phone       = From.replace("whatsapp:", "")
    customer    = crm.get_or_create_customer(phone)
    _reset_if_new_conversation(customer)
    customer_id = customer["id"]

    if not customer.get("name") and ProfileName:
        crm.update_customer(customer_id, name=ProfileName)

    crm.log_message(customer_id, "inbound", Body)

    reply = _handle_message(customer_id, Body)

    crm.log_message(customer_id, "outbound", reply)
    _send_whatsapp(From, reply)
    return PlainTextResponse("", status_code=200)


# ── Test endpoint ─────────────────────────────────────────────────────────────

@app.post("/test/message")
async def test_message(phone: str, message: str, name: str = ""):
    """
    Simulate an inbound WhatsApp message without Twilio.

    Example:
        curl -X POST "http://localhost:8000/test/message?phone=%2B351910000001&message=Quero+uma+caixa+de+frutas&name=Maria"
    """
    customer    = crm.get_or_create_customer(phone)
    _reset_if_new_conversation(customer)
    customer_id = customer["id"]

    if not customer.get("name") and name:
        crm.update_customer(customer_id, name=name)

    crm.log_message(customer_id, "inbound", message)

    reply = _handle_message(customer_id, message)

    crm.log_message(customer_id, "outbound", reply)

    customer = crm.get_customer(customer_id)
    return {
        "customer_id":  customer_id,
        "user_message": message,
        "ai_reply":     reply,
        "order_placed": customer.get("stage") == "confirmed",
        "customer":     customer,
    }


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "mock_mode": MOCK_MODE, "stats": crm.get_dashboard_stats()}


@app.post("/admin/reset-rate-limit")
async def reset_rate_limit():
    import agent as _agent
    _agent._groq_rate_limit_until = 0.0
    return {"status": "cleared"}


@app.get("/customers")
async def list_customers():
    return crm.get_all_customers()


@app.get("/customers/{customer_id}")
async def customer_detail(customer_id: int):
    customer = crm.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {
        "customer":      customer,
        "orders":        crm.get_orders(customer_id),
        "conversations": crm.get_conversation_history(customer_id),
    }


@app.get("/orders")
async def list_orders():
    return crm.get_orders()


@app.get("/orders/upcoming")
async def upcoming_orders():
    return crm.get_upcoming_orders()


@app.get("/stats")
async def stats():
    return crm.get_dashboard_stats()


@app.patch("/orders/{order_id}/deliver")
async def deliver_order(order_id: int):
    orders = crm.get_orders()
    order  = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot deliver a cancelled order")
    crm.update_order_status(order_id, "delivered")
    return {"id": order_id, "status": "delivered"}


@app.patch("/orders/{order_id}/cancel")
async def cancel_order(order_id: int):
    orders = crm.get_orders()
    order  = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "delivered":
        raise HTTPException(status_code=400, detail="Cannot cancel a delivered order")
    crm.update_order_status(order_id, "cancelled")
    crm.update_customer(order["customer_id"], stage="browsing")
    return {"id": order_id, "status": "cancelled"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
