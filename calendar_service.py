"""
Calendar service with two modes:
  - mock   → stores bookings in SQLite, no external calls (default)
  - google → real Google Calendar API (requires credentials.json + OAuth)

Set CALENDAR_MODE=google in .env to switch to real mode.
"""
import random
import string
from datetime import datetime, timedelta

import crm
from config import CALENDAR_MODE, GOOGLE_CALENDAR_ID, GOOGLE_CREDENTIALS_FILE


def _random_id(length: int = 26) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ── Slot generation ───────────────────────────────────────────────────────────

_DAY_NAME_TO_WEEKDAY = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
}


def get_available_slots(days_ahead: int = 21, preferred_day: str = None) -> list[dict]:
    """
    Return 6 available slots across the next N days.
    If preferred_day is given (e.g. 'tuesday'), only return slots on that weekday.
    """
    slots = []
    base = datetime.now().replace(minute=0, second=0, microsecond=0)
    preferred_weekday = _DAY_NAME_TO_WEEKDAY.get(preferred_day) if preferred_day else None

    for day_offset in range(1, days_ahead + 7):
        if len(slots) >= 6:
            break
        day = base + timedelta(days=day_offset)
        if day.weekday() >= 5:                                      # skip weekends
            continue
        if preferred_weekday is not None and day.weekday() != preferred_weekday:
            continue                                                 # skip wrong days
        for hour in [9, 10, 11, 14, 15, 16]:
            slots.append(
                {
                    "datetime": day.replace(hour=hour, minute=0).isoformat(),
                    "display":  day.replace(hour=hour, minute=0).strftime("%A, %B %-d at %-I:%M %p"),
                    "available": True,
                }
            )
            if len(slots) >= 6:
                break

    return slots[:6]


# ── Public booking entry point ────────────────────────────────────────────────

def book_meeting(lead_id: int, slot_datetime: str, notes: str = None) -> dict:
    if CALENDAR_MODE == "google":
        return _book_google(lead_id, slot_datetime, notes)
    return _book_mock(lead_id, slot_datetime, notes)


# ── Mock backend ──────────────────────────────────────────────────────────────

def _book_mock(lead_id: int, slot_datetime: str, notes: str = None) -> dict:
    event_id = f"mock_{_random_id()}"
    meeting  = crm.create_meeting(lead_id, slot_datetime, event_id, notes)
    crm.update_lead(lead_id, stage="meeting_scheduled")
    return {
        "success":       True,
        "event_id":      event_id,
        "meeting":       meeting,
        "calendar_link": f"https://calendar.google.com/calendar/event?eid={event_id}",
        "mode":          "mock",
    }


# ── Google Calendar backend ───────────────────────────────────────────────────

def _book_google(lead_id: int, slot_datetime: str, notes: str = None) -> dict:
    """
    Real Google Calendar booking.
    Requires:
      1. credentials.json downloaded from Google Cloud Console
      2. google-api-python-client, google-auth-oauthlib installed
      3. First run will open a browser for OAuth consent
    """
    try:
        import os
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds  = None

        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)

        if not creds or not creds.valid:
            flow  = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as fh:
                fh.write(creds.to_json())

        service = build("calendar", "v3", credentials=creds)
        lead    = crm.get_lead(lead_id)
        start   = datetime.fromisoformat(slot_datetime)
        end     = start + timedelta(minutes=30)

        event = {
            "summary":     f"Discovery Call — {lead.get('name', 'Lead')}",
            "description": notes or f"Inbound WhatsApp lead. Need: {lead.get('need', 'N/A')}",
            "start":       {"dateTime": start.isoformat(), "timeZone": "America/New_York"},
            "end":         {"dateTime": end.isoformat(),   "timeZone": "America/New_York"},
        }

        created = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        meeting = crm.create_meeting(lead_id, slot_datetime, created["id"], notes)
        crm.update_lead(lead_id, stage="meeting_scheduled")

        return {
            "success":       True,
            "event_id":      created["id"],
            "meeting":       meeting,
            "calendar_link": created.get("htmlLink"),
            "mode":          "google",
        }

    except Exception as exc:
        print(f"[CALENDAR] Google API error: {exc} — falling back to mock")
        return _book_mock(lead_id, slot_datetime, notes)
