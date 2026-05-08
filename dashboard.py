"""
Streamlit dashboard for FarmFresh Boxes.

Run: streamlit run dashboard.py
"""
import pandas as pd
import streamlit as st
from datetime import datetime

import crm

st.set_page_config(
    page_title="FarmFresh Boxes",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #f0faf4; }
[data-testid="stSidebar"]          { background: #1a3c2e; }
[data-testid="stSidebar"] *        { color: #d4edda !important; }

.kpi-card {
    background: white;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 1px 4px rgba(0,0,0,.07);
    border-left: 4px solid;
    margin-bottom: .5rem;
}
.kpi-card.green  { border-color: #22c55e; }
.kpi-card.teal   { border-color: #14b8a6; }
.kpi-card.orange { border-color: #f97316; }
.kpi-card.blue   { border-color: #3b82f6; }
.kpi-label { font-size: 11px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: .06em; }
.kpi-value { font-size: 2rem; font-weight: 800; color: #111827; line-height: 1.1; }
.kpi-sub   { font-size: 12px; color: #9ca3af; margin-top: 2px; }

.bubble-in  { background:#f1f5f9; border-radius:16px 16px 16px 4px; padding:9px 14px; margin:5px 25% 5px 0; font-size:14px; line-height:1.5; }
.bubble-out { background:#dcfce7; border-radius:16px 16px 4px 16px; padding:9px 14px; margin:5px 0 5px 25%; font-size:14px; line-height:1.5; text-align:right; }
.bubble-meta { font-size:10px; color:#94a3b8; margin-top:2px; }

.box-badge { display:inline-block; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.box-fruits      { background:#fef3c7; color:#92400e; }
.box-vegetables  { background:#dcfce7; color:#166534; }
.box-mix         { background:#ede9fe; color:#5b21b6; }
.status-confirmed { background:#dcfce7; color:#166534; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
.status-delivered { background:#dbeafe; color:#1e40af; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
.status-cancelled { background:#fee2e2; color:#991b1b; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
</style>
""", unsafe_allow_html=True)

BOX_EMOJI  = {"fruits": "🍎", "vegetables": "🥦", "mix": "🌿"}
STAGE_EMOJI = {"new": "🆕", "browsing": "👀", "selecting": "🛒", "confirmed": "✅", "cancelled": "❌"}


def kpi(label, value, color, sub=""):
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="kpi-card {color}"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def box_badge(box_type: str) -> str:
    emoji = BOX_EMOJI.get(box_type, "📦")
    label = box_type.title() if box_type else "—"
    return f'<span class="box-badge box-{box_type}">{emoji} {label}</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## 🌱 FarmFresh Boxes")
        st.markdown("*Farm-to-door delivery*")
        st.markdown("---")
        page = st.radio("", ["📊 Overview", "📦 Orders", "👥 Customers", "💬 Conversations"])
        st.markdown("---")
        stats = crm.get_dashboard_stats()
        st.metric("Orders this week", stats["orders_this_week"])
        st.metric("Revenue this week", f"€{stats['revenue_this_week']:.0f}")
        st.metric("Upcoming deliveries", stats["upcoming_deliveries"])
        st.markdown("---")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    return page


# ── Overview ──────────────────────────────────────────────────────────────────

def render_overview():
    st.title("📊 Overview")
    stats = crm.get_dashboard_stats()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Orders this week",    stats["orders_this_week"],            "green",  f"+{stats['new_today']} customers today")
    with c2:
        kpi("Revenue this week",   f"€{stats['revenue_this_week']:.0f}", "teal")
    with c3:
        kpi("Upcoming deliveries", stats["upcoming_deliveries"],         "orange")
    with c4:
        kpi("Total customers",     stats["total_customers"],             "blue")

    st.markdown("---")
    col1, col2 = st.columns(2)

    # Box popularity
    with col1:
        st.subheader("Box Popularity")
        pop = stats.get("box_popularity", {})
        if pop:
            df = pd.DataFrame([
                {"Box": f"{BOX_EMOJI.get(k,'📦')} {k.title()}", "Orders": v}
                for k, v in pop.items()
            ])
            st.bar_chart(df.set_index("Box"), use_container_width=True, color="#22c55e")
        else:
            st.info("No orders yet.")

    # Orders by location
    with col2:
        st.subheader("Orders by Location")
        loc = stats.get("by_location", {})
        if loc:
            df = pd.DataFrame([{"Location": k, "Orders": v} for k, v in loc.items()])
            st.bar_chart(df.set_index("Location"), use_container_width=True, color="#14b8a6")
        else:
            st.info("No orders yet.")

    # Upcoming deliveries
    st.markdown("---")
    st.subheader("🚚 Upcoming Deliveries (next 7 days)")
    upcoming = crm.get_upcoming_orders(7)
    if upcoming:
        rows = []
        for o in upcoming:
            rows.append({
                "Date":     o["delivery_date"],
                "Customer": o.get("name") or o.get("phone", "—"),
                "Box":      f"{BOX_EMOJI.get(o['box_type'],'')} {o['box_type'].title()}",
                "Location": o["delivery_location"],
                "Price":    f"€{o['price']:.0f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No upcoming deliveries.")

    # Customer funnel
    st.markdown("---")
    st.subheader("Customer Funnel")
    stage_data = stats.get("by_stage", {})
    total = stats["total_customers"] or 1
    cols = st.columns(len(STAGE_EMOJI))
    for i, (stage, emoji) in enumerate(STAGE_EMOJI.items()):
        count = stage_data.get(stage, 0)
        with cols[i]:
            st.metric(f"{emoji} {stage.title()}", count)


# ── Orders ────────────────────────────────────────────────────────────────────

def render_orders():
    st.title("📦 Orders")
    orders = crm.get_orders()

    if not orders:
        st.info("No orders yet. Use `POST /test/message` to simulate a conversation.")
        return

    # Filters
    fc1, fc2 = st.columns(2)
    with fc1:
        box_filter = st.selectbox("Box type", ["All", "fruits", "vegetables", "mix"])
    with fc2:
        status_filter = st.selectbox("Status", ["All", "confirmed", "delivered", "cancelled"])

    filtered = orders
    if box_filter != "All":
        filtered = [o for o in filtered if o.get("box_type") == box_filter]
    if status_filter != "All":
        filtered = [o for o in filtered if o.get("status") == status_filter]

    st.caption(f"{len(filtered)} orders")

    rows = []
    for o in filtered:
        rows.append({
            "ID":        o["id"],
            "Date":      o["delivery_date"],
            "Customer":  o.get("name") or o.get("phone", "—"),
            "Box":       f"{BOX_EMOJI.get(o['box_type'],'')} {o['box_type'].title()}",
            "Location":  o["delivery_location"],
            "Price":     f"€{o['price']:.0f}",
            "Status":    o.get("status", "confirmed").title(),
            "Ordered":   o.get("created_at", "")[:10],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    total_rev = sum(o["price"] for o in filtered if o.get("status") != "cancelled")
    st.markdown(f"**Total revenue (filtered): €{total_rev:.0f}**")


# ── Customers ─────────────────────────────────────────────────────────────────

def render_customers():
    st.title("👥 Customers")
    customers = crm.get_all_customers()

    if not customers:
        st.info("No customers yet.")
        return

    search = st.text_input("Search name / phone", placeholder="Maria…")
    if search:
        q = search.lower()
        customers = [c for c in customers if q in (c.get("name") or "").lower() or q in c["phone"]]

    st.caption(f"{len(customers)} customers")

    for c in customers:
        stage = c.get("stage", "new")
        emoji = STAGE_EMOJI.get(stage, "•")
        orders = crm.get_orders(c["id"])
        label  = f"{emoji} {c.get('name') or c['phone']}  —  {c['total_orders']} order(s)"

        with st.expander(label):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Phone:** `{c['phone']}`")
                st.markdown(f"**Name:** {c.get('name') or '—'}")
                st.markdown(f"**Stage:** {stage.title()}")
                st.markdown(f"**Preferred location:** {c.get('preferred_location') or '—'}")
                st.markdown(f"**Preferred day:** {c.get('preferred_day') or '—'}")
            with col2:
                st.markdown(f"**Total orders:** {c['total_orders']}")
                st.markdown(f"**Member since:** {c.get('created_at','')[:10]}")
                if orders:
                    st.markdown("**Order history:**")
                    for o in orders[:3]:
                        emoji  = BOX_EMOJI.get(o["box_type"], "📦")
                        status = o.get("status", "confirmed")
                        st.caption(f"{emoji} {o['box_type'].title()} · {o['delivery_date']} · {o['delivery_location']} · €{o['price']:.0f} · {status.title()}")


# ── Conversations ─────────────────────────────────────────────────────────────

def render_conversations():
    st.title("💬 Conversations")
    customers = crm.get_all_customers()

    if not customers:
        st.info("No conversations yet.")
        return

    options = {
        f"{STAGE_EMOJI.get(c.get('stage','new'),'')} {c.get('name') or c['phone']}": c["id"]
        for c in customers
    }
    chosen    = st.selectbox("Select customer", list(options.keys()))
    cid       = options[chosen]
    customer  = crm.get_customer(cid)
    history   = crm.get_conversation_history(cid, limit=100)

    # Summary strip
    orders = crm.get_orders(cid)
    st.markdown(
        f"""<div style="background:white;border-radius:10px;padding:12px 16px;
            box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:1rem;
            display:flex;gap:2rem;align-items:center;">
            <div><strong>Stage</strong><br>{customer.get('stage','new').title()}</div>
            <div><strong>Orders</strong><br>{customer['total_orders']}</div>
            <div><strong>Pref. location</strong><br>{customer.get('preferred_location') or '—'}</div>
            <div><strong>Pref. day</strong><br>{customer.get('preferred_day') or '—'}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    if not history:
        st.info("No messages yet.")
        return

    for msg in history:
        ts = msg["timestamp"][:16].replace("T", " ")
        if msg["direction"] == "inbound":
            st.markdown(
                f'<div class="bubble-in">{msg["message"]}'
                f'<div class="bubble-meta">📱 Customer · {ts}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="bubble-out">{msg["message"]}'
                f'<div class="bubble-meta">🤖 Agent · {ts}</div></div>',
                unsafe_allow_html=True,
            )


# ── Router ────────────────────────────────────────────────────────────────────

crm.init_db()
page = render_sidebar()

if   page == "📊 Overview":       render_overview()
elif page == "📦 Orders":         render_orders()
elif page == "👥 Customers":      render_customers()
elif page == "💬 Conversations":  render_conversations()
