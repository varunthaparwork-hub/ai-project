# Tools that give AI access to sales and product data via PostgreSQL.

from langchain_core.tools import tool
from data.db import fetchone_sync, fetchall_sync


@tool
def get_sales_summary(date: str) -> dict:
    """
    Returns a sale summary for the given date.
    Use this to get revenue, order count, average order value, units sold,
    returns, and refund amounts.
    Date must be in YYYY-MM-DD format.
    """
    row = fetchone_sync("SELECT * FROM sales_daily WHERE date = $1", date)
    if not row:
        return {"error": f"No sales data found for {date}"}
    return {"date": date, "data": {k: float(v) if hasattr(v, '__float__') else v
                                   for k, v in row.items() if k != "date"}}


@tool
def compare_sales(date1: str, date2: str) -> dict:
    """
    Compares sales metrics between two dates.
    Returns the absolute and percentage change for revenue and orders.
    Use this to detect drops or improvements.
    Date must be in YYYY-MM-DD format.
    """
    d1 = fetchone_sync("SELECT * FROM sales_daily WHERE date = $1", date1)
    d2 = fetchone_sync("SELECT * FROM sales_daily WHERE date = $1", date2)
    if not d1 or not d2:
        return {"error": "One or both dates not found in sales data"}

    rev1, rev2 = float(d1["revenue"]), float(d2["revenue"])
    ord1, ord2 = int(d1["orders"]), int(d2["orders"])
    revenue_change = rev1 - rev2
    revenue_pct = round((revenue_change / rev2) * 100, 1) if rev2 else 0
    orders_change = ord1 - ord2
    orders_pct = round((orders_change / ord2) * 100, 1) if ord2 else 0

    return {
        "date1": date1,
        "date2": date2,
        "revenue_change": revenue_change,
        "revenue_pct_change": revenue_pct,
        "orders_change": orders_change,
        "orders_pct_change": orders_pct,
        "is_drop": revenue_change < 0,
    }


@tool
def get_product_performance(date: str) -> dict:
    """
    Returns per-product sales data for a given date including
    units sold, revenue per product, and stock status.
    Use this to identify which products caused a sales drop.
    Date must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT product_name, units_sold, revenue, stock_status "
        "FROM product_sales WHERE date = $1 ORDER BY revenue DESC",
        date,
    )
    if not rows:
        return {"error": f"No product data for {date}"}
    return {
        "date": date,
        "products": [{"product": r["product_name"], "units_sold": r["units_sold"],
                      "revenue": float(r["revenue"]), "stock_status": r["stock_status"]}
                     for r in rows],
    }


@tool
def get_regional_sales(date: str) -> dict:
    """
    Returns sales broken down by region (North, South, East, West)
    for a given date. Use this to check if a drop is region-specific.
    Date must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT region, revenue, orders FROM regional_sales WHERE date = $1",
        date,
    )
    if not rows:
        return {"error": f"No regional data for {date}"}
    return {
        "date": date,
        "regions": {r["region"]: {"revenue": float(r["revenue"]), "orders": r["orders"]}
                    for r in rows},
    }


@tool
def get_sales_trend(start_date: str, end_date: str) -> dict:
    """
    Returns daily revenue and orders for a date range to identify trends.
    Use this for week-over-week questions, sustained drops, or to check whether
    today's issue is isolated or part of a longer pattern.
    Both dates must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT date, revenue, orders FROM sales_daily "
        "WHERE date BETWEEN $1 AND $2 ORDER BY date ASC",
        start_date, end_date,
    )
    if not rows:
        return {"error": f"No sales data found between {start_date} and {end_date}"}

    revenues = [float(r["revenue"]) for r in rows]
    avg_rev  = round(sum(revenues) / len(revenues), 2)
    peak_row   = max(rows, key=lambda r: float(r["revenue"]))
    lowest_row = min(rows, key=lambda r: float(r["revenue"]))

    return {
        "start_date":            start_date,
        "end_date":              end_date,
        "days_analyzed":         len(rows),
        "average_daily_revenue": avg_rev,
        "peak_day":              str(peak_row["date"]),
        "peak_revenue":          float(peak_row["revenue"]),
        "lowest_day":            str(lowest_row["date"]),
        "lowest_revenue":        float(lowest_row["revenue"]),
        "trend": (
            "declining" if revenues[-1] < revenues[0]
            else "growing" if revenues[-1] > revenues[0]
            else "flat"
        ),
        "daily_data": [
            {"date": str(r["date"]), "revenue": float(r["revenue"]), "orders": int(r["orders"])}
            for r in rows
        ],
    }
