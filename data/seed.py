# data/seed.py
# Seeds the PostgreSQL database with all tables + initial data.
# Called by Docker compose "seed" service on first startup.
# Safe to re-run — uses ON CONFLICT DO NOTHING / DO UPDATE.
#
# Run manually:  python -m data.seed

import json
import asyncio
import asyncpg
from data.db import DATABASE_URL

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sales_daily (
    date              DATE PRIMARY KEY,
    revenue           NUMERIC(12,2),
    orders            INT,
    avg_order_value   NUMERIC(10,2),
    units_sold        INT,
    returns           INT,
    refund_amount     NUMERIC(12,2)
);
CREATE TABLE IF NOT EXISTS product_sales (
    id           SERIAL PRIMARY KEY,
    date         DATE NOT NULL,
    product_name TEXT NOT NULL,
    units_sold   INT,
    revenue      NUMERIC(12,2),
    stock_status TEXT,
    UNIQUE (date, product_name)
);
CREATE TABLE IF NOT EXISTS regional_sales (
    id      SERIAL PRIMARY KEY,
    date    DATE NOT NULL,
    region  TEXT NOT NULL,
    revenue NUMERIC(12,2),
    orders  INT,
    UNIQUE (date, region)
);
CREATE TABLE IF NOT EXISTS inventory (
    product_name  TEXT PRIMARY KEY,
    stock         INT  NOT NULL DEFAULT 0,
    reorder_point INT  NOT NULL DEFAULT 0,
    reorder_qty   INT  NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS campaigns (
    id          SERIAL PRIMARY KEY,
    date        DATE NOT NULL,
    name        TEXT NOT NULL,
    spend       NUMERIC(10,2),
    clicks      INT,
    conversions INT,
    status      TEXT,
    roas        NUMERIC(6,2),
    UNIQUE (date, name)
);
CREATE TABLE IF NOT EXISTS support_daily (
    date             DATE PRIMARY KEY,
    total_tickets    INT,
    resolved         INT,
    open_tickets     INT,
    response_time    NUMERIC(6,2),
    csat_score       NUMERIC(4,2),
    negative_reviews INT
);
CREATE TABLE IF NOT EXISTS support_complaints (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    complaint_type  TEXT NOT NULL,
    count           INT,
    UNIQUE (date, complaint_type)
);
CREATE TABLE IF NOT EXISTS past_incidents (
    id                   TEXT PRIMARY KEY,
    date                 DATE NOT NULL,
    description          TEXT,
    root_causes          JSONB,
    actions_taken        JSONB,
    outcome              TEXT,
    resolution_time_days INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS chat_threads (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id                SERIAL PRIMARY KEY,
    thread_id         TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role              TEXT NOT NULL,
    content           TEXT NOT NULL,
    structured_output JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS chat_messages_thread_idx ON chat_messages(thread_id, created_at);
"""

SALES_DAILY = [
    {"date": "2026-05-31", "revenue": 24500.00, "orders": 312, "avg_order_value": 78.53, "units_sold": 480, "returns": 14, "refund_amount": 890.00},
    {"date": "2026-06-01", "revenue": 8200.00,  "orders": 104, "avg_order_value": 78.85, "units_sold": 155, "returns": 22, "refund_amount": 1340.00},
    {"date": "2026-06-02", "revenue": 14800.00, "orders": 190, "avg_order_value": 77.89, "units_sold": 290, "returns": 16, "refund_amount": 960.00},
    {"date": "2026-06-03", "revenue": 10100.00, "orders": 128, "avg_order_value": 78.91, "units_sold": 195, "returns": 20, "refund_amount": 1100.00},
]

PRODUCT_SALES = [
    {"date": "2026-05-31", "product_name": "Nike Running Shoes", "units_sold": 95,  "revenue": 9025.00, "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Sony Headphones",    "units_sold": 78,  "revenue": 6240.00, "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Apple Watch",        "units_sold": 52,  "revenue": 5200.00, "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Samsung TV",         "units_sold": 35,  "revenue": 2975.00, "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Levi Jeans",         "units_sold": 220, "revenue": 1760.00, "stock_status": "in_stock"},
    {"date": "2026-06-01", "product_name": "Nike Running Shoes", "units_sold": 0,   "revenue": 0.00,    "stock_status": "out_of_stock"},
    {"date": "2026-06-01", "product_name": "Sony Headphones",    "units_sold": 0,   "revenue": 0.00,    "stock_status": "out_of_stock"},
    {"date": "2026-06-01", "product_name": "Apple Watch",        "units_sold": 44,  "revenue": 4400.00, "stock_status": "in_stock"},
    {"date": "2026-06-01", "product_name": "Samsung TV",         "units_sold": 21,  "revenue": 1785.00, "stock_status": "low_stock"},
    {"date": "2026-06-01", "product_name": "Levi Jeans",         "units_sold": 115, "revenue": 920.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Nike Running Shoes", "units_sold": 40,  "revenue": 3800.00, "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Sony Headphones",    "units_sold": 30,  "revenue": 2400.00, "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Apple Watch",        "units_sold": 50,  "revenue": 5000.00, "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Samsung TV",         "units_sold": 28,  "revenue": 2380.00, "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Levi Jeans",         "units_sold": 140, "revenue": 1120.00, "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Nike Running Shoes", "units_sold": 0,   "revenue": 0.00,    "stock_status": "out_of_stock"},
    {"date": "2026-06-03", "product_name": "Sony Headphones",    "units_sold": 0,   "revenue": 0.00,    "stock_status": "out_of_stock"},
    {"date": "2026-06-03", "product_name": "Apple Watch",        "units_sold": 48,  "revenue": 4800.00, "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Samsung TV",         "units_sold": 25,  "revenue": 2125.00, "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Levi Jeans",         "units_sold": 145, "revenue": 1160.00, "stock_status": "in_stock"},
]

REGIONAL_SALES = [
    {"date": "2026-05-31", "region": "North", "revenue": 6800.00, "orders": 88},
    {"date": "2026-05-31", "region": "South", "revenue": 7200.00, "orders": 92},
    {"date": "2026-05-31", "region": "East",  "revenue": 5500.00, "orders": 70},
    {"date": "2026-05-31", "region": "West",  "revenue": 5000.00, "orders": 62},
    {"date": "2026-06-01", "region": "North", "revenue": 2100.00, "orders": 27},
    {"date": "2026-06-01", "region": "South", "revenue": 2400.00, "orders": 30},
    {"date": "2026-06-01", "region": "East",  "revenue": 2000.00, "orders": 25},
    {"date": "2026-06-01", "region": "West",  "revenue": 1700.00, "orders": 22},
    {"date": "2026-06-02", "region": "North", "revenue": 3900.00, "orders": 50},
    {"date": "2026-06-02", "region": "South", "revenue": 4200.00, "orders": 54},
    {"date": "2026-06-02", "region": "East",  "revenue": 3500.00, "orders": 45},
    {"date": "2026-06-02", "region": "West",  "revenue": 3200.00, "orders": 41},
    {"date": "2026-06-03", "region": "North", "revenue": 2700.00, "orders": 34},
    {"date": "2026-06-03", "region": "South", "revenue": 2900.00, "orders": 37},
    {"date": "2026-06-03", "region": "East",  "revenue": 2400.00, "orders": 30},
    {"date": "2026-06-03", "region": "West",  "revenue": 2100.00, "orders": 27},
]

INVENTORY = [
    {"product_name": "Nike Running Shoes", "stock": 0,   "reorder_point": 50, "reorder_qty": 200},
    {"product_name": "Sony Headphones",    "stock": 0,   "reorder_point": 30, "reorder_qty": 150},
    {"product_name": "Apple Watch",        "stock": 120, "reorder_point": 40, "reorder_qty": 100},
    {"product_name": "Samsung TV",         "stock": 18,  "reorder_point": 20, "reorder_qty": 80},
    {"product_name": "Levi Jeans",         "stock": 340, "reorder_point": 60, "reorder_qty": 200},
]

CAMPAIGNS = [
    {"date": "2026-05-31", "name": "Facebook Summer Sale",  "spend": 1200.00, "clicks": 18000, "conversions": 540, "status": "active", "roas": 3.8},
    {"date": "2026-05-31", "name": "Google Shopping",       "spend": 800.00,  "clicks": 12000, "conversions": 360, "status": "active", "roas": 4.2},
    {"date": "2026-05-31", "name": "Instagram Influencer",  "spend": 500.00,  "clicks": 7500,  "conversions": 210, "status": "active", "roas": 3.5},
    {"date": "2026-06-01", "name": "Facebook Summer Sale",  "spend": 0.00,    "clicks": 0,     "conversions": 0,   "status": "paused", "roas": 0.0},
    {"date": "2026-06-01", "name": "Google Shopping",       "spend": 800.00,  "clicks": 11500, "conversions": 280, "status": "active", "roas": 3.6},
    {"date": "2026-06-01", "name": "Instagram Influencer",  "spend": 500.00,  "clicks": 7200,  "conversions": 190, "status": "active", "roas": 3.2},
    {"date": "2026-06-02", "name": "Facebook Summer Sale",  "spend": 900.00,  "clicks": 13500, "conversions": 400, "status": "active", "roas": 3.6},
    {"date": "2026-06-02", "name": "Google Shopping",       "spend": 800.00,  "clicks": 12000, "conversions": 340, "status": "active", "roas": 4.0},
    {"date": "2026-06-02", "name": "Instagram Influencer",  "spend": 500.00,  "clicks": 7500,  "conversions": 200, "status": "active", "roas": 3.4},
    {"date": "2026-06-03", "name": "Facebook Summer Sale",  "spend": 1100.00, "clicks": 16500, "conversions": 420, "status": "active", "roas": 3.5},
    {"date": "2026-06-03", "name": "Google Shopping",       "spend": 800.00,  "clicks": 11800, "conversions": 300, "status": "active", "roas": 3.8},
    {"date": "2026-06-03", "name": "Instagram Influencer",  "spend": 500.00,  "clicks": 7300,  "conversions": 195, "status": "active", "roas": 3.3},
]

SUPPORT_DAILY = [
    {"date": "2026-05-31", "total_tickets": 45,  "resolved": 40, "open_tickets": 5,  "response_time": 2.1, "csat_score": 4.5, "negative_reviews": 3},
    {"date": "2026-06-01", "total_tickets": 128, "resolved": 70, "open_tickets": 58, "response_time": 5.8, "csat_score": 2.9, "negative_reviews": 34},
    {"date": "2026-06-02", "total_tickets": 88,  "resolved": 72, "open_tickets": 16, "response_time": 3.4, "csat_score": 3.6, "negative_reviews": 18},
    {"date": "2026-06-03", "total_tickets": 102, "resolved": 78, "open_tickets": 24, "response_time": 4.2, "csat_score": 3.1, "negative_reviews": 28},
]

SUPPORT_COMPLAINTS = [
    {"date": "2026-05-31", "complaint_type": "delayed_delivery", "count": 20},
    {"date": "2026-05-31", "complaint_type": "product_quality",  "count": 12},
    {"date": "2026-05-31", "complaint_type": "checkout_error",   "count": 8},
    {"date": "2026-05-31", "complaint_type": "out_of_stock",     "count": 5},
    {"date": "2026-06-01", "complaint_type": "out_of_stock",     "count": 62},
    {"date": "2026-06-01", "complaint_type": "delayed_delivery", "count": 28},
    {"date": "2026-06-01", "complaint_type": "checkout_error",   "count": 22},
    {"date": "2026-06-01", "complaint_type": "product_quality",  "count": 16},
    {"date": "2026-06-02", "complaint_type": "delayed_delivery", "count": 32},
    {"date": "2026-06-02", "complaint_type": "out_of_stock",     "count": 28},
    {"date": "2026-06-02", "complaint_type": "checkout_error",   "count": 15},
    {"date": "2026-06-02", "complaint_type": "product_quality",  "count": 13},
    {"date": "2026-06-03", "complaint_type": "out_of_stock",     "count": 48},
    {"date": "2026-06-03", "complaint_type": "delayed_delivery", "count": 30},
    {"date": "2026-06-03", "complaint_type": "checkout_error",   "count": 14},
    {"date": "2026-06-03", "complaint_type": "product_quality",  "count": 10},
]

PAST_INCIDENTS = [
    {
        "id": "INC-001", "date": "2026-03-15",
        "description": "Nike Air Max stockout caused 35% revenue drop over 3 days.",
        "root_causes": ["Stockout of Nike Air Max", "Insufficient safety stock"],
        "actions_taken": ["Emergency restock ordered", "Safety stock policy updated"],
        "outcome": "Revenue recovered within 5 days after restock arrival.",
        "resolution_time_days": 5,
    },
    {
        "id": "INC-002", "date": "2026-04-10",
        "description": "Facebook campaign budget exhausted mid-day, causing 40% traffic drop.",
        "root_causes": ["Facebook campaign budget exhausted", "No budget alert configured"],
        "actions_taken": ["Budget increased", "Budget alert thresholds configured", "Campaign resumed"],
        "outcome": "Traffic restored within 2 hours after budget top-up.",
        "resolution_time_days": 1,
    },
    {
        "id": "INC-003", "date": "2026-05-05",
        "description": "Payment gateway outage resulted in 60% checkout failure rate for 4 hours.",
        "root_causes": ["Payment gateway downtime", "No fallback gateway configured"],
        "actions_taken": ["Switched to backup gateway", "Incident reported to provider"],
        "outcome": "Full recovery after 4 hours; provider issued SLA credit.",
        "resolution_time_days": 1,
    },
    {
        "id": "INC-004", "date": "2026-05-20",
        "description": "Sony Headphones stock depleted due to viral social media post.",
        "root_causes": ["Viral demand surge for Sony Headphones", "Forecast model not accounting for social signals"],
        "actions_taken": ["Emergency restock", "Social listening tool added to demand forecast"],
        "outcome": "Stock replenished in 4 days; $12k revenue recovered.",
        "resolution_time_days": 4,
    },
]


async def seed():
    print(f"[SEED] Connecting to: {DATABASE_URL}")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(SCHEMA_SQL)
        print("[SEED] Tables created / verified.")

        for row in SALES_DAILY:
            await conn.execute(
                """INSERT INTO sales_daily VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (date) DO UPDATE SET revenue=EXCLUDED.revenue, orders=EXCLUDED.orders,
                   avg_order_value=EXCLUDED.avg_order_value, units_sold=EXCLUDED.units_sold,
                   returns=EXCLUDED.returns, refund_amount=EXCLUDED.refund_amount""",
                row["date"], row["revenue"], row["orders"], row["avg_order_value"],
                row["units_sold"], row["returns"], row["refund_amount"])
        print(f"[SEED] {len(SALES_DAILY)} sales_daily rows.")

        for row in PRODUCT_SALES:
            await conn.execute(
                """INSERT INTO product_sales (date,product_name,units_sold,revenue,stock_status)
                   VALUES ($1,$2,$3,$4,$5)
                   ON CONFLICT (date,product_name) DO UPDATE SET
                   units_sold=EXCLUDED.units_sold, revenue=EXCLUDED.revenue, stock_status=EXCLUDED.stock_status""",
                row["date"], row["product_name"], row["units_sold"], row["revenue"], row["stock_status"])
        print(f"[SEED] {len(PRODUCT_SALES)} product_sales rows.")

        for row in REGIONAL_SALES:
            await conn.execute(
                """INSERT INTO regional_sales (date,region,revenue,orders) VALUES ($1,$2,$3,$4)
                   ON CONFLICT (date,region) DO UPDATE SET revenue=EXCLUDED.revenue, orders=EXCLUDED.orders""",
                row["date"], row["region"], row["revenue"], row["orders"])
        print(f"[SEED] {len(REGIONAL_SALES)} regional_sales rows.")

        for row in INVENTORY:
            await conn.execute(
                """INSERT INTO inventory (product_name,stock,reorder_point,reorder_qty)
                   VALUES ($1,$2,$3,$4)
                   ON CONFLICT (product_name) DO UPDATE SET
                   stock=EXCLUDED.stock, reorder_point=EXCLUDED.reorder_point, reorder_qty=EXCLUDED.reorder_qty""",
                row["product_name"], row["stock"], row["reorder_point"], row["reorder_qty"])
        print(f"[SEED] {len(INVENTORY)} inventory rows.")

        for row in CAMPAIGNS:
            await conn.execute(
                """INSERT INTO campaigns (date,name,spend,clicks,conversions,status,roas)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (date,name) DO UPDATE SET
                   spend=EXCLUDED.spend, clicks=EXCLUDED.clicks, conversions=EXCLUDED.conversions,
                   status=EXCLUDED.status, roas=EXCLUDED.roas""",
                row["date"], row["name"], row["spend"], row["clicks"],
                row["conversions"], row["status"], row["roas"])
        print(f"[SEED] {len(CAMPAIGNS)} campaign rows.")

        for row in SUPPORT_DAILY:
            await conn.execute(
                """INSERT INTO support_daily VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (date) DO UPDATE SET total_tickets=EXCLUDED.total_tickets, resolved=EXCLUDED.resolved,
                   open_tickets=EXCLUDED.open_tickets, response_time=EXCLUDED.response_time,
                   csat_score=EXCLUDED.csat_score, negative_reviews=EXCLUDED.negative_reviews""",
                row["date"], row["total_tickets"], row["resolved"], row["open_tickets"],
                row["response_time"], row["csat_score"], row["negative_reviews"])
        print(f"[SEED] {len(SUPPORT_DAILY)} support_daily rows.")

        for row in SUPPORT_COMPLAINTS:
            await conn.execute(
                """INSERT INTO support_complaints (date,complaint_type,count) VALUES ($1,$2,$3)
                   ON CONFLICT (date,complaint_type) DO UPDATE SET count=EXCLUDED.count""",
                row["date"], row["complaint_type"], row["count"])
        print(f"[SEED] {len(SUPPORT_COMPLAINTS)} support_complaints rows.")

        for row in PAST_INCIDENTS:
            await conn.execute(
                """INSERT INTO past_incidents (id,date,description,root_causes,actions_taken,outcome,resolution_time_days)
                   VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7)
                   ON CONFLICT (id) DO UPDATE SET description=EXCLUDED.description,
                   root_causes=EXCLUDED.root_causes, actions_taken=EXCLUDED.actions_taken,
                   outcome=EXCLUDED.outcome, resolution_time_days=EXCLUDED.resolution_time_days""",
                row["id"], row["date"], row["description"],
                json.dumps(row["root_causes"]), json.dumps(row["actions_taken"]),
                row["outcome"], row["resolution_time_days"])
        print(f"[SEED] {len(PAST_INCIDENTS)} past_incidents rows.")

    finally:
        await conn.close()

    print("[SEED] Done ✓")


if __name__ == "__main__":
    asyncio.run(seed())
