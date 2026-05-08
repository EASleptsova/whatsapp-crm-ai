<div align="center">

# 🌱 FarmFresh Boxes — WhatsApp CRM

**AI-powered WhatsApp ordering system for a farm-to-door delivery business. Customers chat, pick their box, schedule delivery, and get confirmed — all without human involvement. Supports Claude, Gemini, and Groq as AI backends.**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Claude](https://img.shields.io/badge/Claude-Haiku_4.5-D97706?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3-F55036?style=flat-square&logo=groq&logoColor=white)](https://groq.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.39-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)

</div>

---

## What this does

A customer messages your WhatsApp. An AI agent greets them, presents three box options, collects their preferred delivery day and location, and places the order automatically. Your team sees everything live on a dashboard — upcoming deliveries, revenue, popular boxes, and all conversations.

No human needed until the driver shows up.

---

## Box Options

| Box               | Contents                           | Price    |
| ----------------- | ---------------------------------- | -------- |
| 🍎 Fruits Box     | Seasonal mixed fruits, ~5 kg       | €28/week |
| 🥦 Vegetables Box | Fresh seasonal veggies, ~6 kg      | €24/week |
| 🌿 Mix Box        | Half fruits, half veggies, ~5.5 kg | €26/week |

Delivery: **Monday–Saturday** to configurable locations (default: Lisbon Downtown, Cascais, Sintra, Oeiras).

---

## Features

| Feature                     | Details                                                         |
| --------------------------- | --------------------------------------------------------------- |
| **AI Ordering Agent**       | Collects box type, delivery day, and location conversationally  |
| **Auto Order Confirmation** | Creates order and sends confirmation when all info is collected |
| **Dual Follow-up**          | Re-engages browsers after 24h and repeat customers after 7 days |
| **Analytics Dashboard**     | Revenue, box popularity, upcoming deliveries, customer funnel   |
| **Mock Mode**               | Full end-to-end flow with no Twilio or payment needed           |

---

## Architecture

```
WhatsApp Customer
      ↓
Twilio → POST /webhook → FastAPI
      ↓
  Groq Agent
  (collects box, day, location via tool calling)
      ↓
  SQLite CRM (customers, orders, conversations)
      ↓
  Order confirmed → WhatsApp confirmation sent
      ↓
  APScheduler → follow-ups (browsers & repeat customers)
      ↓
  Streamlit Dashboard (revenue, deliveries, conversations)
```

---

## Tech Stack

| Layer       | Technology                                                                   |
| ----------- | ---------------------------------------------------------------------------- |
| AI Agent    | [Groq LLaMA 3.3](https://groq.com)                                           |
| Backend API | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) |
| WhatsApp    | [Twilio WhatsApp API](https://www.twilio.com/whatsapp)                       |
| Database    | SQLite                                                                       |
| Dashboard   | [Streamlit](https://streamlit.io)                                            |
| Scheduler   | [APScheduler](https://apscheduler.readthedocs.io)                            |

---

## Quick Start

> **Python 3.9+** required. On macOS/Linux use `python3`; once the venv is active, `python` works too.

```bash
cd farmfresh-whatsapp-crm

python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
# → add your AI provider key to .env
```

**Seed demo data (optional but recommended):**

```bash
python3 seed_data.py
```

**Start the API:**

```bash
python3 main.py
# API at http://localhost:8000 · Docs at http://localhost:8000/docs
```

**Start the dashboard (separate terminal, venv active):**

```bash
streamlit run dashboard.py
# Dashboard at http://localhost:8501
```

---

## Testing without WhatsApp

```bash
# New customer asking about boxes
curl -X POST "http://localhost:8000/test/message?phone=%2B351910000099&message=Ola%2C+quero+uma+caixa&name=Sofia"

# Picking the mix box
curl -X POST "http://localhost:8000/test/message?phone=%2B351910000099&message=Quero+a+caixa+mista"

# Choosing day and location
curl -X POST "http://localhost:8000/test/message?phone=%2B351910000099&message=Terca-feira+em+Cascais"
```

Or use the interactive docs at `http://localhost:8000/docs`.

---

## Connecting WhatsApp (Production)

<details>
<summary>Click to expand</summary>

1. Create a [Twilio account](https://www.twilio.com/try-twilio)
2. Enable the WhatsApp Sandbox at `console.twilio.com`
3. Update `.env`:
   ```env
   TWILIO_ACCOUNT_SID=ACxxx
   TWILIO_AUTH_TOKEN=your_token
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   MOCK_MODE=false
   ```
4. Expose locally with [ngrok](https://ngrok.com):
   ```bash
   ngrok http 8000
   ```
5. Set `https://your-id.ngrok.io/webhook` as the Twilio webhook URL

</details>

---

## Configuration

| Variable                | Default                   | Description                        |
| ----------------------- | ------------------------- | ---------------------------------- |
| `AI_PROVIDER`           | `groq`                    | `groq`                             |
| `GROQ_API_KEY`          | —                         | Groq API key                       |
| `GROQ_MODEL`            | `llama-3.3-70b-versatile` | Groq model ID                      |
| `BUSINESS_NAME`         | `FarmFresh Boxes`         | Used in agent's system prompt      |
| `DELIVERY_LOCATIONS`    | `Lisbon Downtown,...`     | Comma-separated delivery areas     |
| `PRICE_FRUITS`          | `28.0`                    | Fruits box price (€)               |
| `PRICE_VEGETABLES`      | `24.0`                    | Vegetables box price (€)           |
| `PRICE_MIX`             | `26.0`                    | Mix box price (€)                  |
| `FOLLOW_UP_DELAY_HOURS` | `24`                      | Hours before nudging browsers      |
| `REPEAT_CUSTOMER_DAYS`  | `7`                       | Days before nudging past customers |
| `MOCK_MODE`             | `true`                    | Suppress real Twilio sends         |

---

## Project Structure

```
farmfresh-whatsapp-crm/
├── main.py               FastAPI app — webhook + REST API
├── agent.py              AI agent (Groq)
├── crm.py                SQLite CRM — customers, orders, conversations
├── delivery_service.py   Delivery date generation + order creation
├── scheduler.py          APScheduler follow-ups
├── dashboard.py          Streamlit analytics dashboard
├── seed_data.py          Demo data generator
├── config.py             Environment variable loader
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Follow-up Logic

| Trigger                 | Audience           | Message                                               |
| ----------------------- | ------------------ | ----------------------------------------------------- |
| 24h no order            | Browsing customers | "Still thinking? Here's what's fresh this week 🌿"    |
| 7 days since last order | Past customers     | "Ready for your next box? 🥦 What day works for you?" |

---

## Contributing

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Test: `python3 seed_data.py && python3 main.py`
4. Open a pull request

---

<img width="1726" height="902" alt="Screenshot 2026-05-07 at 19 03 13" src="https://github.com/user-attachments/assets/9809c630-3e58-4424-a33c-039c434c9f3b" />
<img width="1727" height="903" alt="Screenshot 2026-05-07 at 19 03 41" src="https://github.com/user-attachments/assets/c95bcc36-7f35-4812-bc38-881d604d38c6" />
<img width="1727" height="898" alt="Screenshot 2026-05-07 at 19 06 08" src="https://github.com/user-attachments/assets/de1c5a71-b58c-46e1-b20e-e30bde6f37f4" />
<img width="1722" height="895" alt="Screenshot 2026-05-07 at 19 04 39" src="https://github.com/user-attachments/assets/ba3ae986-a968-4efe-a75e-b621f2c606c1" />
<img width="1728" height="901" alt="Screenshot 2026-05-07 at 19 04 13" src="https://github.com/user-attachments/assets/966b41ab-3756-46fd-a4ff-22198513a789" />

## License

MIT

---

<div align="center">

Built with [Claude](https://anthropic.com) · [FastAPI](https://fastapi.tiangolo.com) · [Streamlit](https://streamlit.io) · 🌱

</div>
