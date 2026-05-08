"""
AI agent for FarmFresh Boxes WhatsApp ordering.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

import crm
from config import GROQ_API_KEY, GROQ_MODEL, BUSINESS_NAME, DELIVERY_LOCATIONS, BOX_PRICES

# ── System prompt ─────────────────────────────────────────────────────────────

_LOCATIONS_STR = ", ".join(DELIVERY_LOCATIONS)
_MENU_STR = "\n".join(
    f"  - {k.title()} Box: €{v:.0f}/week"
    for k, v in BOX_PRICES.items()
)

SYSTEM_PROMPT = f"""You are a friendly WhatsApp assistant for {BUSINESS_NAME}, a farm-to-door delivery service.

OUR BOXES:
{_MENU_STR}
  - Fruits Box: seasonal mixed fruits, ~5kg. Great for snacking and smoothies.
  - Vegetables Box: fresh seasonal veggies, ~6kg. Perfect for cooking.
  - Mix Box: half fruits, half veggies, ~5.5kg. Best of both worlds.

DELIVERY:
  - Available Mon–Sat, any week
  - Locations we deliver to: {_LOCATIONS_STR}

YOUR JOB — collect these 3 things naturally:
  1. Box type (fruits / vegetables / mix)
  2. Delivery day or date
  3. Delivery location

COLLECTION RULES:
- Never confirm or describe a box without also asking for any missing details in the same message.
- If you know the box but not the day or location, ask for BOTH in one message.
- Never split "what day?" and "what location?" into separate turns.
- NEVER say "order confirmed", "order placed", or anything implying the order was created — that is handled externally.

CANCELLATIONS:
- If the customer asks to cancel their order, confirm you'll cancel it and set cancel_order: true.
- If they have no active order, let them know politely.

RULES:
- Keep replies SHORT (2-4 sentences). This is WhatsApp.
- Be warm and enthusiastic about the produce 🌱
- If the customer asks about what's in season or freshness, reassure them it's all harvested this week.
- Never invent prices or locations not listed above.
- After every message, call update_order_info with whatever you've learned so far.
"""

# ── Tool schema ───────────────────────────────────────────────────────────────

_TOOL_PROPERTIES = {
    "customer_name": {
        "type": "string",
        "description": "Customer's name if they mentioned it",
    },
    "box_type": {
        "type": "string",
        "enum": ["fruits", "vegetables", "mix"],
        "description": "Which box the customer wants. Omit if not yet known.",
    },
    "delivery_day": {
        "type": "string",
        "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "description": "Preferred day of the week for delivery. Omit if not yet known.",
    },
    "delivery_date": {
        "type": "string",
        "description": "Specific delivery date in YYYY-MM-DD format if determined",
    },
    "delivery_location": {
        "type": "string",
        "description": f"Delivery location, must be one of: {_LOCATIONS_STR}",
    },
    "stage": {
        "type": "string",
        "enum": ["new", "browsing", "selecting", "confirmed", "awaiting_confirmation", "cancelled"],
        "description": "Current conversation stage",
    },
    "cancel_order": {
        "type": "boolean",
        "description": "Set to true ONLY when the customer explicitly asks to cancel their current order.",
    },
}
_TOOL_REQUIRED = ["stage"]

# ── CRM helpers ───────────────────────────────────────────────────────────────

def _sanitize(data: dict) -> dict:
    cleaned = {}
    for k, v in data.items():
        if v in (None, "null", "none", "None", ""):
            continue
        if v == "false":
            cleaned[k] = False
        elif v == "true":
            cleaned[k] = True
        else:
            cleaned[k] = v
    return cleaned


def _apply_tool_data(customer_id: int, data: dict):
    data = _sanitize(data)
    updates = {}
    if data.get("customer_name"):
        updates["name"] = data["customer_name"]
    if data.get("delivery_location"):
        updates["preferred_location"] = data["delivery_location"]
    if data.get("delivery_day"):
        updates["preferred_day"] = data["delivery_day"]
    if data.get("box_type"):
        updates["pending_box_type"] = data["box_type"]
    if data.get("stage"):
        updates["stage"] = data["stage"]
    if updates:
        crm.update_customer(customer_id, **updates)


def _build_system_prompt(customer_id: int) -> str:
    """System prompt + current CRM state. No history — CRM is the memory."""
    customer = crm.get_customer(customer_id)
    orders   = crm.get_orders(customer_id)

    state_lines = []
    if customer:
        if customer.get("name"):
            state_lines.append(f"Customer name: {customer['name']}")

        today    = datetime.utcnow().date().isoformat()
        upcoming = [o for o in orders if o.get("status") == "confirmed" and o.get("delivery_date", "") >= today]
        delivered_count = sum(1 for o in orders if o.get("status") == "delivered")

        state_lines.append(f"Upcoming orders: {len(upcoming)}")
        state_lines.append(f"Delivered orders: {delivered_count}")

        if upcoming:
            for o in upcoming:
                state_lines.append(f"  - {o['box_type'].title()} Box → {o['delivery_location']} on {o['delivery_date']}")

        # What has been collected so far for the current order
        collected = []
        if customer.get("pending_box_type"):
            collected.append(f"box={customer['pending_box_type']}")
        if customer.get("preferred_location"):
            collected.append(f"location={customer['preferred_location']}")
        if customer.get("preferred_day"):
            collected.append(f"day={customer['preferred_day']}")
        if customer.get("pending_delivery_date"):
            collected.append(f"date={customer['pending_delivery_date']}")

        if collected:
            state_lines.append(f"Collected so far: {', '.join(collected)}")
        else:
            state_lines.append("Collected so far: nothing yet")

    state = "\n".join(state_lines)
    return SYSTEM_PROMPT + f"\n\nCURRENT STATE (from database — ground truth):\n{state}"

# ── Rate-limit state ──────────────────────────────────────────────────────────

_groq_rate_limit_until: float = 0.0


def _parse_groq_wait(error_msg: str) -> float:
    match = re.search(r"(\d+)m(\d+(?:\.\d+)?)s", error_msg)
    if match:
        return int(match.group(1)) * 60 + float(match.group(2))
    match = re.search(r"(\d+(?:\.\d+)?)s", error_msg)
    if match:
        return float(match.group(1))
    return 60.0


# ── Agent ─────────────────────────────────────────────────────────────────────

_tool_def = {
    "type": "function",
    "function": {
        "name": "update_order_info",
        "description": "Update customer order data from the conversation. Call after every message.",
        "parameters": {"type": "object", "properties": _TOOL_PROPERTIES, "required": _TOOL_REQUIRED},
    },
}


def process_message(customer_id: int, user_message: str) -> tuple[str, dict]:
    """Call Groq, update CRM via tool, return (reply_text, order_data)."""
    global _groq_rate_limit_until
    from groq import Groq, BadRequestError, RateLimitError

    # Rate-limit guard
    if _groq_rate_limit_until:
        remaining = _groq_rate_limit_until - time.time()
        if remaining > 0:
            mins, secs = int(remaining // 60), int(remaining % 60)
            wait_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            return (
                f"Sorry, I've hit my AI limit for now 🙏 I'll be back in ~{wait_str}. "
                "Your conversation is saved — just message me then and we'll pick up where we left off!",
                {},
            )
        _groq_rate_limit_until = 0.0

    client = Groq(api_key=GROQ_API_KEY)

    messages = [
        {"role": "system", "content": _build_system_prompt(customer_id)},
        {"role": "user",   "content": user_message},
    ]

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL, messages=messages,
            tools=[_tool_def], tool_choice="auto", max_tokens=1024,
        )
    except RateLimitError as e:
        wait = _parse_groq_wait(str(e))
        _groq_rate_limit_until = time.time() + wait
        print(f"[GROQ] Rate limited. Resuming in {wait:.0f}s.")
        remaining = _groq_rate_limit_until - time.time()
        mins, secs = int(remaining // 60), int(remaining % 60)
        wait_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        return (
            f"Sorry, I've hit my AI limit for now 🙏 I'll be back in ~{wait_str}. "
            "Your conversation is saved — just message me then and we'll pick up where we left off!",
            {},
        )
    except BadRequestError as e:
        print(f"[GROQ] BadRequestError: {e}")
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL, messages=messages, max_tokens=512,
            )
            return response.choices[0].message.content or "", {}
        except Exception as e2:
            print(f"[GROQ] Retry failed: {e2}")
            return "Sorry, I had a little hiccup! Could you say that again? 😊", {}
    except Exception as e:
        print(f"[GROQ] API error: {e}")
        return "Sorry, I'm having trouble right now. Please try again in a few minutes! 🙏", {}

    msg        = response.choices[0].message
    reply_text = msg.content or ""
    order_data = {}

    if msg.tool_calls:
        tc = next((t for t in msg.tool_calls if t.function.name == "update_order_info"), None)
        if tc:
            data = _sanitize(json.loads(tc.function.arguments))
            _apply_tool_data(customer_id, data)
            if data.get("cancel_order"):
                order_data = {"cancel_order": True}
            if not reply_text:
                messages += [
                    {"role": "assistant", "content": None, "tool_calls": msg.tool_calls},
                    {"role": "tool", "tool_call_id": tc.id, "content": "Order data saved."},
                ]
                try:
                    cont = client.chat.completions.create(
                        model=GROQ_MODEL, messages=messages, max_tokens=512,
                    )
                    reply_text = cont.choices[0].message.content or ""
                except RateLimitError as e:
                    wait = _parse_groq_wait(str(e))
                    _groq_rate_limit_until = time.time() + wait
                    print(f"[GROQ] Rate limited on follow-up. Resuming in {wait:.0f}s.")
                    reply_text = "I've saved your info! Just send me the last detail and we're good. 🌱"

    return reply_text or "Hey! 👋 Welcome to FarmFresh. What can I get for you today?", order_data
