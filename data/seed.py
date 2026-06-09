# data/seed.py
# Seeds the PostgreSQL database with all tables + initial data.
# Called by Docker compose "seed" service on first startup.
# Safe to re-run — uses ON CONFLICT DO NOTHING / DO UPDATE.
#
# Run manually:  python -m data.seed

import json
import random
import asyncio
import asyncpg
from datetime import date, timedelta
from data.db import DATABASE_URL


def _to_date(s):
    """asyncpg's DATE binding refuses strings — coerce ISO strings to date."""
    return s if isinstance(s, date) else date.fromisoformat(s)

# ── Catalogue ────────────────────────────────────────────────────────────────
# Single source of truth for products used by the generator below.
# Each entry: (name, unit_price, baseline_daily_units, weekend_units, supply_floor)
_CATALOGUE = [
    ("Nike Running Shoes", 95.00,  90, 110, 0),
    ("Sony Headphones",    80.00,  75, 95,  0),
    ("Apple Watch",       100.00,  50, 65,  120),
    ("Samsung TV",         85.00,  35, 50,  18),
    ("Levi Jeans",          8.00, 200, 260, 340),
    ("Adidas Ultraboost",  120.00, 60, 80,  150),
    ("Bose Speakers",      150.00, 40, 55,  90),
    ("iPad Pro",           650.00, 25, 35,  60),
    ("Dell Laptop",        850.00, 18, 28,  45),
    ("Kindle Paperwhite",  130.00, 70, 90,  200),
]

_REGIONS = ["North", "South", "East", "West"]

_CAMPAIGN_DEFAULTS = [
    # name, daily_spend, daily_clicks, daily_conversions, baseline_roas
    ("Facebook Summer Sale",  1200, 18000, 540, 3.8),
    ("Google Shopping",        800, 12000, 360, 4.2),
    ("Instagram Influencer",   500,  7500, 210, 3.5),
]

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
    product_name        TEXT PRIMARY KEY,
    stock               INT  NOT NULL DEFAULT 0,
    reorder_point       INT  NOT NULL DEFAULT 0,
    reorder_qty         INT  NOT NULL DEFAULT 0,
    discount_pct        NUMERIC(5,2) NOT NULL DEFAULT 0,
    discount_expires_at TIMESTAMPTZ
);
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS discount_pct        NUMERIC(5,2) NOT NULL DEFAULT 0;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS discount_expires_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS support_tickets (
    id          TEXT PRIMARY KEY,
    issue_type  TEXT NOT NULL,
    description TEXT,
    priority    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

# ── Generated historical baseline ────────────────────────────────────────────
# We generate 28 days of "normal" history (2026-05-04 → 2026-05-30) so the
# anomaly detector has a real baseline. Then 2026-05-31 onward are kept as
# hand-tuned anchors so the well-known revenue-drop incidents on 2026-06-01
# and 2026-06-03 remain visible against that baseline.
#
# Generation is deterministic (random.seed=42) so re-running the seed produces
# identical numbers — required for ON CONFLICT idempotency to be meaningful.

_RNG = random.Random(42)
_HISTORY_START = date(2026, 5, 4)    # Monday
_HISTORY_END   = date(2026, 5, 30)   # Saturday — last generated day before anchors


def _history_dates():
    d = _HISTORY_START
    while d <= _HISTORY_END:
        yield d
        d += timedelta(days=1)


def _gen_product_sales_for_day(d: date) -> list[dict]:
    """Returns one product_sales row per catalogue entry for date d."""
    is_weekend = d.weekday() >= 5
    rows = []
    for name, price, base_units, weekend_units, _floor in _CATALOGUE:
        units = weekend_units if is_weekend else base_units
        # ±15% jitter — feels organic, baseline std for anomaly detector ≈ small
        units = max(0, int(units * _RNG.uniform(0.85, 1.15)))
        revenue = round(units * price, 2)
        rows.append({
            "date": d.isoformat(),
            "product_name": name,
            "units_sold": units,
            "revenue": revenue,
            "stock_status": "in_stock",
        })
    return rows


def _gen_regional_sales_for_day(d: date, total_revenue: float, total_orders: int) -> list[dict]:
    """Splits a day's totals across the four regions with mild variance."""
    weights = [0.27, 0.29, 0.23, 0.21]   # North, South, East, West — North/South lead
    weights = [w * _RNG.uniform(0.92, 1.08) for w in weights]
    s = sum(weights)
    weights = [w / s for w in weights]
    return [
        {
            "date":    d.isoformat(),
            "region":  region,
            "revenue": round(total_revenue * w, 2),
            "orders":  max(1, int(total_orders * w)),
        }
        for region, w in zip(_REGIONS, weights)
    ]


# Generate 28 days of product_sales, then derive sales_daily totals from them.
_GENERATED_PRODUCT_SALES: list[dict] = []
_GENERATED_SALES_DAILY:   list[dict] = []
_GENERATED_REGIONAL:      list[dict] = []

for _d in _history_dates():
    day_rows = _gen_product_sales_for_day(_d)
    _GENERATED_PRODUCT_SALES.extend(day_rows)
    units  = sum(r["units_sold"] for r in day_rows)
    rev    = round(sum(r["revenue"] for r in day_rows), 2)
    # Realistic order count: about 1 order per 1.5 units (mixed basket sizes)
    orders = max(1, int(units / 1.5))
    aov    = round(rev / orders, 2) if orders else 0.0
    returns       = int(orders * _RNG.uniform(0.03, 0.06))
    refund_amount = round(returns * aov * _RNG.uniform(0.7, 1.1), 2)
    _GENERATED_SALES_DAILY.append({
        "date": _d.isoformat(),
        "revenue": rev, "orders": orders, "avg_order_value": aov,
        "units_sold": units, "returns": returns, "refund_amount": refund_amount,
    })
    _GENERATED_REGIONAL.extend(_gen_regional_sales_for_day(_d, rev, orders))

# Hand-tuned anchor days — scaled to match the 10-product generated baseline
# (~$78k/day mean) so the June 1 incident remains a clear anomaly against history,
# not just an artifact of catalogue-size mismatch. Original ratios preserved:
# May 31 strong, June 1 deep drop, June 2 partial recovery, June 3 relapse.
_ANCHOR_SALES_DAILY = [
    {"date": "2026-05-31", "revenue": 85000.00, "orders": 1080, "avg_order_value": 78.70, "units_sold": 1620, "returns": 48, "refund_amount": 3080.00},
    {"date": "2026-06-01", "revenue": 28500.00, "orders": 360,  "avg_order_value": 79.17, "units_sold": 540,  "returns": 76, "refund_amount": 4640.00},
    {"date": "2026-06-02", "revenue": 51500.00, "orders": 660,  "avg_order_value": 78.03, "units_sold": 1010, "returns": 56, "refund_amount": 3340.00},
    {"date": "2026-06-03", "revenue": 35000.00, "orders": 444,  "avg_order_value": 78.83, "units_sold": 680,  "returns": 70, "refund_amount": 3820.00},
]
SALES_DAILY = _GENERATED_SALES_DAILY + _ANCHOR_SALES_DAILY

_ANCHOR_PRODUCT_SALES = [
    # 2026-05-31 — strong day, all 10 products in stock
    {"date": "2026-05-31", "product_name": "Nike Running Shoes", "units_sold": 95,  "revenue": 9025.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Sony Headphones",    "units_sold": 78,  "revenue": 6240.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Apple Watch",        "units_sold": 52,  "revenue": 5200.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Samsung TV",         "units_sold": 35,  "revenue": 2975.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Levi Jeans",         "units_sold": 220, "revenue": 1760.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Adidas Ultraboost",  "units_sold": 70,  "revenue": 8400.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Bose Speakers",      "units_sold": 45,  "revenue": 6750.00,  "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "iPad Pro",           "units_sold": 28,  "revenue": 18200.00, "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Dell Laptop",        "units_sold": 20,  "revenue": 17000.00, "stock_status": "in_stock"},
    {"date": "2026-05-31", "product_name": "Kindle Paperwhite",  "units_sold": 80,  "revenue": 10400.00, "stock_status": "in_stock"},
    # 2026-06-01 — incident day: Nike/Sony stockouts + checkout errors hit premium SKUs
    {"date": "2026-06-01", "product_name": "Nike Running Shoes", "units_sold": 0,   "revenue": 0.00,     "stock_status": "out_of_stock"},
    {"date": "2026-06-01", "product_name": "Sony Headphones",    "units_sold": 0,   "revenue": 0.00,     "stock_status": "out_of_stock"},
    {"date": "2026-06-01", "product_name": "Apple Watch",        "units_sold": 44,  "revenue": 4400.00,  "stock_status": "in_stock"},
    {"date": "2026-06-01", "product_name": "Samsung TV",         "units_sold": 21,  "revenue": 1785.00,  "stock_status": "low_stock"},
    {"date": "2026-06-01", "product_name": "Levi Jeans",         "units_sold": 115, "revenue": 920.00,   "stock_status": "in_stock"},
    {"date": "2026-06-01", "product_name": "Adidas Ultraboost",  "units_sold": 22,  "revenue": 2640.00,  "stock_status": "in_stock"},
    {"date": "2026-06-01", "product_name": "Bose Speakers",      "units_sold": 8,   "revenue": 1200.00,  "stock_status": "low_stock"},
    {"date": "2026-06-01", "product_name": "iPad Pro",           "units_sold": 6,   "revenue": 3900.00,  "stock_status": "in_stock"},
    {"date": "2026-06-01", "product_name": "Dell Laptop",        "units_sold": 4,   "revenue": 3400.00,  "stock_status": "low_stock"},
    {"date": "2026-06-01", "product_name": "Kindle Paperwhite",  "units_sold": 38,  "revenue": 4940.00,  "stock_status": "in_stock"},
    # 2026-06-02 — partial recovery
    {"date": "2026-06-02", "product_name": "Nike Running Shoes", "units_sold": 40,  "revenue": 3800.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Sony Headphones",    "units_sold": 30,  "revenue": 2400.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Apple Watch",        "units_sold": 50,  "revenue": 5000.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Samsung TV",         "units_sold": 28,  "revenue": 2380.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Levi Jeans",         "units_sold": 140, "revenue": 1120.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Adidas Ultraboost",  "units_sold": 48,  "revenue": 5760.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Bose Speakers",      "units_sold": 25,  "revenue": 3750.00,  "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "iPad Pro",           "units_sold": 18,  "revenue": 11700.00, "stock_status": "in_stock"},
    {"date": "2026-06-02", "product_name": "Dell Laptop",        "units_sold": 12,  "revenue": 10200.00, "stock_status": "low_stock"},
    {"date": "2026-06-02", "product_name": "Kindle Paperwhite",  "units_sold": 60,  "revenue": 7800.00,  "stock_status": "in_stock"},
    # 2026-06-03 — relapse: Nike/Sony out again
    {"date": "2026-06-03", "product_name": "Nike Running Shoes", "units_sold": 0,   "revenue": 0.00,     "stock_status": "out_of_stock"},
    {"date": "2026-06-03", "product_name": "Sony Headphones",    "units_sold": 0,   "revenue": 0.00,     "stock_status": "out_of_stock"},
    {"date": "2026-06-03", "product_name": "Apple Watch",        "units_sold": 48,  "revenue": 4800.00,  "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Samsung TV",         "units_sold": 25,  "revenue": 2125.00,  "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Levi Jeans",         "units_sold": 145, "revenue": 1160.00,  "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Adidas Ultraboost",  "units_sold": 30,  "revenue": 3600.00,  "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Bose Speakers",      "units_sold": 12,  "revenue": 1800.00,  "stock_status": "low_stock"},
    {"date": "2026-06-03", "product_name": "iPad Pro",           "units_sold": 10,  "revenue": 6500.00,  "stock_status": "in_stock"},
    {"date": "2026-06-03", "product_name": "Dell Laptop",        "units_sold": 6,   "revenue": 5100.00,  "stock_status": "low_stock"},
    {"date": "2026-06-03", "product_name": "Kindle Paperwhite",  "units_sold": 45,  "revenue": 5850.00,  "stock_status": "in_stock"},
]
PRODUCT_SALES = _GENERATED_PRODUCT_SALES + _ANCHOR_PRODUCT_SALES

_ANCHOR_REGIONAL_SALES = [
    # Scaled ~3.5× to match new $85k/$28.5k/$51.5k/$35k daily totals.
    {"date": "2026-05-31", "region": "North", "revenue": 23600.00, "orders": 305},
    {"date": "2026-05-31", "region": "South", "revenue": 24900.00, "orders": 318},
    {"date": "2026-05-31", "region": "East",  "revenue": 19000.00, "orders": 242},
    {"date": "2026-05-31", "region": "West",  "revenue": 17500.00, "orders": 215},
    {"date": "2026-06-01", "region": "North", "revenue": 7300.00,  "orders": 94},
    {"date": "2026-06-01", "region": "South", "revenue": 8400.00,  "orders": 105},
    {"date": "2026-06-01", "region": "East",  "revenue": 6900.00,  "orders": 87},
    {"date": "2026-06-01", "region": "West",  "revenue": 5900.00,  "orders": 74},
    {"date": "2026-06-02", "region": "North", "revenue": 13600.00, "orders": 174},
    {"date": "2026-06-02", "region": "South", "revenue": 14600.00, "orders": 188},
    {"date": "2026-06-02", "region": "East",  "revenue": 12200.00, "orders": 157},
    {"date": "2026-06-02", "region": "West",  "revenue": 11100.00, "orders": 141},
    {"date": "2026-06-03", "region": "North", "revenue": 9400.00,  "orders": 119},
    {"date": "2026-06-03", "region": "South", "revenue": 10100.00, "orders": 129},
    {"date": "2026-06-03", "region": "East",  "revenue": 8400.00,  "orders": 105},
    {"date": "2026-06-03", "region": "West",  "revenue": 7100.00,  "orders": 91},
]
REGIONAL_SALES = _GENERATED_REGIONAL + _ANCHOR_REGIONAL_SALES

INVENTORY = [
    {"product_name": "Nike Running Shoes", "stock": 0,   "reorder_point": 50, "reorder_qty": 200},
    {"product_name": "Sony Headphones",    "stock": 0,   "reorder_point": 30, "reorder_qty": 150},
    {"product_name": "Apple Watch",        "stock": 120, "reorder_point": 40, "reorder_qty": 100},
    {"product_name": "Samsung TV",         "stock": 18,  "reorder_point": 20, "reorder_qty": 80},
    {"product_name": "Levi Jeans",         "stock": 340, "reorder_point": 60, "reorder_qty": 200},
    {"product_name": "Adidas Ultraboost",  "stock": 150, "reorder_point": 45, "reorder_qty": 150},
    {"product_name": "Bose Speakers",      "stock": 12,  "reorder_point": 25, "reorder_qty": 80},   # below reorder point
    {"product_name": "iPad Pro",           "stock": 60,  "reorder_point": 20, "reorder_qty": 60},
    {"product_name": "Dell Laptop",        "stock": 8,   "reorder_point": 15, "reorder_qty": 40},   # below reorder point
    {"product_name": "Kindle Paperwhite",  "stock": 200, "reorder_point": 50, "reorder_qty": 200},
]

def _gen_campaigns_for_day(d: date) -> list[dict]:
    is_weekend = d.weekday() >= 5
    rows = []
    for name, spend, clicks, conv, base_roas in _CAMPAIGN_DEFAULTS:
        # Weekend lift on clicks/conversions, mild jitter on all metrics
        lift   = 1.10 if is_weekend else 1.0
        jitter = _RNG.uniform(0.92, 1.08)
        s = round(spend  * jitter, 2)
        c = int(clicks * lift * jitter)
        v = int(conv   * lift * jitter)
        rows.append({
            "date":        d.isoformat(),
            "name":        name,
            "spend":       s,
            "clicks":      c,
            "conversions": v,
            "status":      "active",
            "roas":        round(base_roas * _RNG.uniform(0.92, 1.08), 2),
        })
    return rows


_GENERATED_CAMPAIGNS: list[dict] = []
for _d in _history_dates():
    _GENERATED_CAMPAIGNS.extend(_gen_campaigns_for_day(_d))

_ANCHOR_CAMPAIGNS = [
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
CAMPAIGNS = _GENERATED_CAMPAIGNS + _ANCHOR_CAMPAIGNS

# Generate 28 days of "calm" support baseline so the support agent can see
# what normal looks like before the 2026-06-01 incident spike.
def _gen_support_daily_for_day(d: date) -> dict:
    is_weekend = d.weekday() >= 5
    base = 38 if is_weekend else 42
    total = max(20, int(base * _RNG.uniform(0.85, 1.15)))
    resolved = int(total * _RNG.uniform(0.85, 0.95))
    return {
        "date": d.isoformat(),
        "total_tickets":    total,
        "resolved":         resolved,
        "open_tickets":     total - resolved,
        "response_time":    round(_RNG.uniform(1.8, 2.6), 2),
        "csat_score":       round(_RNG.uniform(4.2, 4.6), 2),
        "negative_reviews": max(0, int(_RNG.uniform(2, 6))),
    }


_GENERATED_SUPPORT_DAILY = [_gen_support_daily_for_day(_d) for _d in _history_dates()]

_ANCHOR_SUPPORT_DAILY = [
    {"date": "2026-05-31", "total_tickets": 45,  "resolved": 40, "open_tickets": 5,  "response_time": 2.1, "csat_score": 4.5, "negative_reviews": 3},
    {"date": "2026-06-01", "total_tickets": 128, "resolved": 70, "open_tickets": 58, "response_time": 5.8, "csat_score": 2.9, "negative_reviews": 34},
    {"date": "2026-06-02", "total_tickets": 88,  "resolved": 72, "open_tickets": 16, "response_time": 3.4, "csat_score": 3.6, "negative_reviews": 18},
    {"date": "2026-06-03", "total_tickets": 102, "resolved": 78, "open_tickets": 24, "response_time": 4.2, "csat_score": 3.1, "negative_reviews": 28},
]
SUPPORT_DAILY = _GENERATED_SUPPORT_DAILY + _ANCHOR_SUPPORT_DAILY


_COMPLAINT_BASELINE = [
    # complaint_type, mean_per_day
    ("delayed_delivery", 8),
    ("product_quality",  6),
    ("checkout_error",   3),
    ("out_of_stock",     4),
]


def _gen_complaints_for_day(d: date) -> list[dict]:
    return [
        {
            "date": d.isoformat(),
            "complaint_type": ct,
            "count": max(1, int(mean * _RNG.uniform(0.7, 1.3))),
        }
        for ct, mean in _COMPLAINT_BASELINE
    ]


_GENERATED_COMPLAINTS: list[dict] = []
for _d in _history_dates():
    _GENERATED_COMPLAINTS.extend(_gen_complaints_for_day(_d))

_ANCHOR_COMPLAINTS = [
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
SUPPORT_COMPLAINTS = _GENERATED_COMPLAINTS + _ANCHOR_COMPLAINTS

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
    {
        "id": "INC-005", "date": "2025-11-29",
        "description": "Black Friday CDN provider outage caused 90-minute storefront blackout, ~$48k revenue lost.",
        "root_causes": ["CDN provider regional outage", "No multi-CDN failover", "Static asset origin not directly reachable"],
        "actions_taken": ["Failed over to secondary CDN", "Multi-CDN routing implemented", "Runbook updated for CDN incidents"],
        "outcome": "Restored within 90 minutes; provider issued credit; multi-CDN now standard.",
        "resolution_time_days": 1,
    },
    {
        "id": "INC-006", "date": "2026-02-08",
        "description": "Mobile checkout regression dropped mobile conversion 38% for 6 days before being detected.",
        "root_causes": ["Front-end deploy broke Apple Pay button on iOS Safari", "No conversion-rate alerting on mobile funnel"],
        "actions_taken": ["Hotfix deployed to restore Apple Pay", "Conversion-rate alerts added per device class", "QA matrix expanded to cover iOS Safari"],
        "outcome": "Mobile conversion recovered within 24h of hotfix; ~$22k estimated lost revenue not recoverable.",
        "resolution_time_days": 6,
    },
    {
        "id": "INC-007", "date": "2026-04-22",
        "description": "Marketing email campaign sent to wrong segment, triggering 18% unsubscribe spike and 110 angry tickets.",
        "root_causes": ["Segment ID swapped during campaign rebuild", "No second-pair-of-eyes review before send"],
        "actions_taken": ["Apology email sent", "Segment-ID validation step added to campaign tooling", "Review checklist enforced"],
        "outcome": "Unsubscribe rate normalised within 5 days; ticket queue drained in 2 days.",
        "resolution_time_days": 2,
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
                _to_date(row["date"]), row["revenue"], row["orders"], row["avg_order_value"],
                row["units_sold"], row["returns"], row["refund_amount"])
        print(f"[SEED] {len(SALES_DAILY)} sales_daily rows.")

        for row in PRODUCT_SALES:
            await conn.execute(
                """INSERT INTO product_sales (date,product_name,units_sold,revenue,stock_status)
                   VALUES ($1,$2,$3,$4,$5)
                   ON CONFLICT (date,product_name) DO UPDATE SET
                   units_sold=EXCLUDED.units_sold, revenue=EXCLUDED.revenue, stock_status=EXCLUDED.stock_status""",
                _to_date(row["date"]), row["product_name"], row["units_sold"], row["revenue"], row["stock_status"])
        print(f"[SEED] {len(PRODUCT_SALES)} product_sales rows.")

        for row in REGIONAL_SALES:
            await conn.execute(
                """INSERT INTO regional_sales (date,region,revenue,orders) VALUES ($1,$2,$3,$4)
                   ON CONFLICT (date,region) DO UPDATE SET revenue=EXCLUDED.revenue, orders=EXCLUDED.orders""",
                _to_date(row["date"]), row["region"], row["revenue"], row["orders"])
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
                _to_date(row["date"]), row["name"], row["spend"], row["clicks"],
                row["conversions"], row["status"], row["roas"])
        print(f"[SEED] {len(CAMPAIGNS)} campaign rows.")

        for row in SUPPORT_DAILY:
            await conn.execute(
                """INSERT INTO support_daily VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (date) DO UPDATE SET total_tickets=EXCLUDED.total_tickets, resolved=EXCLUDED.resolved,
                   open_tickets=EXCLUDED.open_tickets, response_time=EXCLUDED.response_time,
                   csat_score=EXCLUDED.csat_score, negative_reviews=EXCLUDED.negative_reviews""",
                _to_date(row["date"]), row["total_tickets"], row["resolved"], row["open_tickets"],
                row["response_time"], row["csat_score"], row["negative_reviews"])
        print(f"[SEED] {len(SUPPORT_DAILY)} support_daily rows.")

        for row in SUPPORT_COMPLAINTS:
            await conn.execute(
                """INSERT INTO support_complaints (date,complaint_type,count) VALUES ($1,$2,$3)
                   ON CONFLICT (date,complaint_type) DO UPDATE SET count=EXCLUDED.count""",
                _to_date(row["date"]), row["complaint_type"], row["count"])
        print(f"[SEED] {len(SUPPORT_COMPLAINTS)} support_complaints rows.")

        for row in PAST_INCIDENTS:
            await conn.execute(
                """INSERT INTO past_incidents (id,date,description,root_causes,actions_taken,outcome,resolution_time_days)
                   VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7)
                   ON CONFLICT (id) DO UPDATE SET description=EXCLUDED.description,
                   root_causes=EXCLUDED.root_causes, actions_taken=EXCLUDED.actions_taken,
                   outcome=EXCLUDED.outcome, resolution_time_days=EXCLUDED.resolution_time_days""",
                row["id"], _to_date(row["date"]), row["description"],
                json.dumps(row["root_causes"]), json.dumps(row["actions_taken"]),
                row["outcome"], row["resolution_time_days"])
        print(f"[SEED] {len(PAST_INCIDENTS)} past_incidents rows.")

    finally:
        await conn.close()

    print("[SEED] Done.")


if __name__ == "__main__":
    asyncio.run(seed())
