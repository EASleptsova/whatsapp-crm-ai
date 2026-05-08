"""
Seed the database with realistic FarmFresh demo data.

Run once:
    python3 seed_data.py
"""
import crm
from datetime import datetime, timedelta

CUSTOMERS = [
    {
        "phone": "+351910000001",
        "name": "Maria Silva",
        "preferred_location": "Lisbon Downtown",
        "preferred_day": "tuesday",
        "stage": "confirmed",
        "total_orders": 3,
    },
    {
        "phone": "+351910000002",
        "name": "João Ferreira",
        "preferred_location": "Cascais",
        "preferred_day": "friday",
        "stage": "confirmed",
        "total_orders": 1,
    },
    {
        "phone": "+351910000003",
        "name": "Ana Costa",
        "preferred_location": "Sintra",
        "preferred_day": "wednesday",
        "stage": "browsing",
        "total_orders": 0,
    },
    {
        "phone": "+351910000004",
        "name": "Pedro Rodrigues",
        "preferred_location": "Oeiras",
        "preferred_day": "monday",
        "stage": "confirmed",
        "total_orders": 2,
    },
    {
        "phone": "+351910000005",
        "name": "Sofia Mendes",
        "preferred_location": "Cascais",
        "preferred_day": "thursday",
        "stage": "selecting",
        "total_orders": 0,
    },
    {
        "phone": "+351910000006",
        "name": "Rui Oliveira",
        "preferred_location": "Lisbon Downtown",
        "preferred_day": "saturday",
        "stage": "confirmed",
        "total_orders": 5,
    },
    {
        "phone": "+351910000007",
        "name": "Catarina Nunes",
        "preferred_location": "Oeiras",
        "preferred_day": "wednesday",
        "stage": "confirmed",
        "total_orders": 10,
    },
]

ORDERS = [
    # Maria — 3 orders
    {
        "phone": "+351910000001",
        "box_type": "fruits",
        "delivery_location": "Lisbon Downtown",
        "days_offset": 7,
    },
    {
        "phone": "+351910000001",
        "box_type": "mix",
        "delivery_location": "Lisbon Downtown",
        "days_offset": 2,
    },
    {
        "phone": "+351910000001",
        "box_type": "fruits",
        "delivery_location": "Lisbon Downtown",
        "days_offset": -3,   # past delivery
    },
    # João — 1 order
    {
        "phone": "+351910000002",
        "box_type": "vegetables",
        "delivery_location": "Cascais",
        "days_offset": 4,
    },
    # Pedro — 2 orders
    {
        "phone": "+351910000004",
        "box_type": "mix",
        "delivery_location": "Oeiras",
        "days_offset": 1,
    },
    {
        "phone": "+351910000004",
        "box_type": "vegetables",
        "delivery_location": "Oeiras",
        "days_offset": -7,
    },
    # Rui — 5 orders (loyal customer)
    {
        "phone": "+351910000006",
        "box_type": "vegetables",
        "delivery_location": "Lisbon Downtown",
        "days_offset": 3,
    },
    {
        "phone": "+351910000006",
        "box_type": "vegetables",
        "delivery_location": "Lisbon Downtown",
        "days_offset": -4,
    },
    {
        "phone": "+351910000006",
        "box_type": "mix",
        "delivery_location": "Lisbon Downtown",
        "days_offset": -11,
    },
    {
        "phone": "+351910000006",
        "box_type": "vegetables",
        "delivery_location": "Lisbon Downtown",
        "days_offset": -18,
    },
    {
        "phone": "+351910000006",
        "box_type": "fruits",
        "delivery_location": "Lisbon Downtown",
        "days_offset": -25,
    },
    # Catarina — 10 orders (multi-order test case)
    *[
        {"phone": "+351910000007", "box_type": ["fruits", "vegetables", "mix"][i % 3], "delivery_location": "Oeiras", "days_offset": (i + 1) * 7}
        for i in range(10)
    ],
]

CONVERSATIONS = {
    "+351910000001": [
        ("inbound",  "Olá! Quero encomendar uma caixa"),
        ("outbound", "Olá Maria! 🌱 Que bom ter notícias suas! Temos 3 opções: 🍎 Caixa de Frutas (€28), 🥦 Caixa de Legumes (€24) ou 🌿 Caixa Mista (€26). O que prefere?"),
        ("inbound",  "Quero a caixa de frutas! Entregam em Lisboa?"),
        ("outbound", "Claro que sim! 🍎 Entregamos em Lisboa Downtown, Cascais, Sintra e Oeiras. Que dia funciona melhor para si?"),
        ("inbound",  "Terças-feiras seria perfeito"),
        ("outbound", "✅ Ótimo! Caixa de Frutas entregue em Lisboa Downtown na próxima terça. Vemo-nos em breve! 🚜"),
    ],
    "+351910000003": [
        ("inbound",  "Bom dia, como funciona a entrega?"),
        ("outbound", "Bom dia! 🌿 Entregamos semanalmente às portas de casa! Temos: 🍎 Caixa de Frutas (€28), 🥦 Legumes (€24) ou 🌿 Mista (€26). Qual prefere?"),
        ("inbound",  "Ainda estou a pensar... os legumes são de que região?"),
        ("outbound", "São todos da nossa quinta em Santarém — colhidos esta semana! 🌱 Os legumes da época incluem courgette, cenoura, tomate e feijão verde. Quer experimentar a caixa de legumes?"),
        ("inbound",  "Vou pensar um pouco mais"),
        ("outbound", "Claro, sem pressão! 😊 Estou aqui quando quiser. Esta semana ainda temos disponibilidade para Sintra."),
    ],
    "+351910000005": [
        ("inbound",  "Oi! Queria saber mais sobre as vossas caixas"),
        ("outbound", "Olá Sofia! 👋 Que bom! Temos 3 caixas semanais diretamente da quinta: 🍎 Frutas (€28), 🥦 Legumes (€24) e 🌿 Mista (€26). Qual soa melhor?"),
        ("inbound",  "A mista parece boa! Entregam em Cascais?"),
        ("outbound", "Sim, entregamos em Cascais! 🚜 Que dia prefere para a entrega?"),
    ],
}


from config import BOX_PRICES

def seed():
    crm.init_db()
    today = datetime.utcnow().date()

    # Create customers
    customer_ids = {}
    for c_data in CUSTOMERS:
        phone = c_data.pop("phone")
        c = crm.get_or_create_customer(phone)
        crm.update_customer(c["id"], **c_data)
        customer_ids[phone] = c["id"]

    # Create orders
    for o in ORDERS:
        phone    = o["phone"]
        cid      = customer_ids[phone]
        del_date = (today + timedelta(days=o["days_offset"])).isoformat()
        price    = BOX_PRICES[o["box_type"]]
        with crm.get_db() as conn:
            conn.execute(
                "INSERT INTO orders (customer_id, box_type, delivery_date, delivery_location, price, status) VALUES (?, ?, ?, ?, ?, ?)",
                (cid, o["box_type"], del_date, o["delivery_location"], price,
                 "delivered" if o["days_offset"] < 0 else "confirmed"),
            )

    # Add conversations
    for phone, messages in CONVERSATIONS.items():
        cid = customer_ids[phone]
        for direction, message in messages:
            crm.log_message(cid, direction, message)

    stats = crm.get_dashboard_stats()
    print(f"✅ Seed complete: {stats['total_customers']} customers · {stats['orders_this_week']} orders this week · €{stats['revenue_this_week']:.0f} revenue")


if __name__ == "__main__":
    seed()
