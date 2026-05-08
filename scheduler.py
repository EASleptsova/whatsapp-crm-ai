"""
Background follow-up scheduler for FarmFresh Boxes.

Two jobs:
  1. Abandoned browsers  — customer showed interest but didn't order in 24h
  2. Repeat customers    — customer ordered 7+ days ago, nudge for next box
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import crm
from config import FOLLOW_UP_DELAY_HOURS, REPEAT_CUSTOMER_DAYS, MOCK_MODE

scheduler = BackgroundScheduler(timezone="UTC")


def _send_whatsapp(phone: str, message: str):
    if MOCK_MODE:
        print(f"[MOCK FOLLOW-UP → {phone}] {message[:80]}...")
        return
    from twilio.rest import Client
    from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
    Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN).messages.create(
        from_=TWILIO_WHATSAPP_FROM, to=f"whatsapp:{phone}", body=message,
    )


def check_follow_ups():
    now       = datetime.utcnow()
    customers = crm.get_all_customers()

    for c in customers:
        history  = crm.get_conversation_history(c["id"])
        inbound  = [h for h in history if h["direction"] == "inbound"]
        outbound = [h for h in history if h["direction"] == "outbound"]
        if not inbound:
            continue

        last_in  = datetime.fromisoformat(inbound[-1]["timestamp"])
        last_out = datetime.fromisoformat(outbound[-1]["timestamp"]) if outbound else None
        name     = c.get("name") or "there"

        # ── Abandoned browser: browsing/selecting, gone quiet for 24h ──────────
        if c["stage"] in ("browsing", "selecting", "new"):
            hours_silent = (now - last_in).total_seconds() / 3600
            already_nudged = last_out and last_out > last_in
            if hours_silent >= FOLLOW_UP_DELAY_HOURS and not already_nudged:
                msg = (
                    f"Hey {name}! 🌿 Still thinking about a box? "
                    f"This week we have some amazing seasonal produce fresh from the farm. "
                    f"Just reply with *fruits*, *vegetables*, or *mix* and we'll sort you out! 🥦🍎"
                )
                try:
                    _send_whatsapp(c["phone"], msg)
                    crm.log_message(c["id"], "outbound", msg)
                    print(f"[SCHEDULER] Abandoned cart nudge → {c['phone']}")
                except Exception as e:
                    print(f"[SCHEDULER] Failed: {e}")

        # ── Repeat customer: confirmed, last delivery 7+ days ago, no upcoming orders ──
        elif c["stage"] == "confirmed":
            orders = crm.get_orders(c["id"])
            if not orders:
                continue
            today_str = now.date().isoformat()
            # Skip if they have an upcoming confirmed order
            if any(o.get("status") == "confirmed" and o.get("delivery_date", "") >= today_str for o in orders):
                continue
            # Use the most recent delivery_date (orders sorted by delivery_date DESC)
            last_order_date = datetime.fromisoformat(orders[0]["delivery_date"])
            days_since = (now.date() - last_order_date.date()).days
            already_nudged = last_out and (now - last_out).days < REPEAT_CUSTOMER_DAYS

            if days_since >= REPEAT_CUSTOMER_DAYS and not already_nudged:
                last_box = orders[0].get("box_type", "box")
                msg = (
                    f"Hey {name}! 👋 It's been a week — ready for your next {last_box} box? 🚜 "
                    f"Just say the word and we'll schedule your delivery. "
                    f"What day works best for you this week?"
                )
                try:
                    _send_whatsapp(c["phone"], msg)
                    crm.log_message(c["id"], "outbound", msg)
                    crm.update_customer(c["id"], stage="browsing")
                    print(f"[SCHEDULER] Repeat nudge → {c['phone']}")
                except Exception as e:
                    print(f"[SCHEDULER] Failed: {e}")


def start_scheduler():
    scheduler.add_job(
        check_follow_ups,
        trigger=IntervalTrigger(hours=1),
        id="follow_up_check",
        replace_existing=True,
    )
    scheduler.start()
    print("[SCHEDULER] Started — checking follow-ups every hour")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[SCHEDULER] Stopped")
