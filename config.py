import os
from dotenv import load_dotenv

load_dotenv()

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID",   "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN",    "your_twilio_auth_token_here")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "gsk_mock-key-replace-me")
GROQ_MODEL   = os.getenv("GROQ_MODEL",   "llama-3.3-70b-versatile")

# ── Google Calendar ───────────────────────────────────────────────────────────
GOOGLE_CALENDAR_ID       = os.getenv("GOOGLE_CALENDAR_ID",       "your.email@gmail.com")
GOOGLE_CREDENTIALS_FILE  = os.getenv("GOOGLE_CREDENTIALS_FILE",  "credentials.json")
CALENDAR_MODE            = os.getenv("CALENDAR_MODE",            "mock")   # "mock" | "google"

# ── App ───────────────────────────────────────────────────────────────────────
DATABASE_PATH      = os.getenv("DATABASE_PATH",      "crm.db")
BUSINESS_NAME      = os.getenv("BUSINESS_NAME",      "FarmFresh Boxes")
BUSINESS_TIMEZONE  = os.getenv("BUSINESS_TIMEZONE",  "Europe/Lisbon")
MOCK_MODE          = os.getenv("MOCK_MODE",           "true").lower() == "true"

# ── Delivery ──────────────────────────────────────────────────────────────────
DELIVERY_LOCATIONS = os.getenv(
    "DELIVERY_LOCATIONS",
    "Lisbon Downtown,Cascais,Sintra,Oeiras"
).split(",")

BOX_PRICES = {
    "fruits":     float(os.getenv("PRICE_FRUITS",     "28.0")),
    "vegetables": float(os.getenv("PRICE_VEGETABLES", "24.0")),
    "mix":        float(os.getenv("PRICE_MIX",        "26.0")),
}

# ── Follow-up ─────────────────────────────────────────────────────────────────
FOLLOW_UP_DELAY_HOURS    = int(os.getenv("FOLLOW_UP_DELAY_HOURS",    "24"))
REPEAT_CUSTOMER_DAYS     = int(os.getenv("REPEAT_CUSTOMER_DAYS",     "7"))
