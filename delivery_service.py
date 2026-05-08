"""
Delivery scheduling service for FarmFresh Boxes.

Generates available delivery dates and creates confirmed orders in the CRM.
Set preferred_day to filter dates to a specific weekday (e.g. 'tuesday').
"""
from datetime import datetime, timedelta

import crm
from config import DELIVERY_LOCATIONS, BOX_PRICES

_DAY_TO_WEEKDAY = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5,
}

BOX_EMOJI = {"fruits": "🍎", "vegetables": "🥦", "mix": "🌿"}
BOX_LABELS = {"fruits": "Fruits Box", "vegetables": "Vegetables Box", "mix": "Mix Box"}


def get_available_dates(preferred_day: str = None, weeks_ahead: int = 3) -> list[dict]:
    """
    Return up to 6 delivery dates within the next N weeks.
    If preferred_day is set, only that weekday is returned.
    Deliveries run Mon–Sat (no Sundays).
    """
    dates = []
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    preferred_weekday = _DAY_TO_WEEKDAY.get(preferred_day) if preferred_day else None

    for offset in range(1, weeks_ahead * 7 + 8):
        if len(dates) >= 6:
            break
        day = base + timedelta(days=offset)
        if day.weekday() == 6:                                      # skip Sunday
            continue
        if preferred_weekday is not None and day.weekday() != preferred_weekday:
            continue
        dates.append({
            "date":    day.strftime("%Y-%m-%d"),
            "display": day.strftime("%A, %d %B"),
        })

    return dates


def create_order(
    customer_id: int,
    box_type: str,
    delivery_date: str,
    delivery_location: str,
    notes: str = None,
) -> dict:
    price = BOX_PRICES.get(box_type, 26.0)
    order = crm.create_order(customer_id, box_type, delivery_date, delivery_location, price, notes)
    return {"success": True, "order": order, "price": price}


def get_locations() -> list[str]:
    return DELIVERY_LOCATIONS


def format_box_menu() -> str:
    lines = []
    for key, label in BOX_LABELS.items():
        emoji = BOX_EMOJI[key]
        price = BOX_PRICES[key]
        lines.append(f"  {emoji} *{label}* — €{price:.0f}/week")
    return "\n".join(lines)
