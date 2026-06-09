# Tools that give AI access to customer support and complaint data via PostgreSQL.

from langchain_core.tools import tool
from data.db import fetchone_sync, fetchall_sync


@tool
def get_support_summary(date: str) -> dict:
    """
    Returns customer support metrics for a given date.
    Includes total tickets, resolved vs open, response time,
    complaint breakdown by type, CSAT score and negative reviews.
    Use this to check if customer experience issues caused a sales drop.
    Date must be in YYYY-MM-DD format.
    """
    row = fetchone_sync("SELECT * FROM support_daily WHERE date = $1", date)
    if not row:
        return {"error": f"No support data found for {date}"}
    complaints = fetchall_sync(
        "SELECT complaint_type, count FROM support_complaints "
        "WHERE date = $1 ORDER BY count DESC",
        date,
    )
    data = {k: float(v) if hasattr(v, '__float__') else v
            for k, v in row.items() if k != "date"}
    data["complaints_by_type"] = {r["complaint_type"]: r["count"] for r in complaints}
    return {"date": date, "data": data}


@tool
def get_top_complaints(date: str) -> dict:
    """
    Returns the most common complaint types for a given date, sorted by volume.
    Use this to identify what customers were most frustrated about.
    Date must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT complaint_type, count FROM support_complaints "
        "WHERE date = $1 ORDER BY count DESC",
        date,
    )
    if not rows:
        return {"error": f"No support data found for {date}"}
    return {
        "date": date,
        "complaints": [{"type": r["complaint_type"], "count": r["count"]} for r in rows],
    }
