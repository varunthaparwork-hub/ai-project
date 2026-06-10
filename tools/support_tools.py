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


@tool
def compare_support(date1: str, date2: str) -> dict:
    """
    Compares support metrics and complaints between two dates.
    Returns ticket volume, CSAT score, and per-complaint-type changes.
    Use this to detect whether support issues spiked or subsided.
    Date must be in YYYY-MM-DD format.
    """
    d1_daily = fetchone_sync("SELECT * FROM support_daily WHERE date = $1", date1)
    d2_daily = fetchone_sync("SELECT * FROM support_daily WHERE date = $1", date2)

    if not d1_daily and not d2_daily:
        return {"error": f"No support data found for {date1} or {date2}"}

    # Fetch complaint breakdowns for both dates
    d1_complaints = fetchall_sync(
        "SELECT complaint_type, count FROM support_complaints WHERE date = $1",
        date1,
    )
    d2_complaints = fetchall_sync(
        "SELECT complaint_type, count FROM support_complaints WHERE date = $1",
        date2,
    )

    # Build lookup maps for complaint types
    d1_complaint_map = {r["complaint_type"]: r["count"] for r in d1_complaints}
    d2_complaint_map = {r["complaint_type"]: r["count"] for r in d2_complaints}

    # Compare daily metrics if both exist
    tickets_d1, tickets_d2, csat_d1, csat_d2 = 0, 0, 0, 0
    if d1_daily:
        tickets_d1 = int(d1_daily.get("total_tickets", 0))
        csat_d1 = float(d1_daily.get("csat_score", 0))
    if d2_daily:
        tickets_d2 = int(d2_daily.get("total_tickets", 0))
        csat_d2 = float(d2_daily.get("csat_score", 0))

    tickets_change = tickets_d1 - tickets_d2
    tickets_pct = round((tickets_change / tickets_d2) * 100, 1) if tickets_d2 else 0
    csat_change = round(csat_d1 - csat_d2, 2)

    # Build complaint comparisons
    all_complaint_types = set(d1_complaint_map.keys()) | set(d2_complaint_map.keys())
    complaint_changes = []
    for complaint_type in sorted(all_complaint_types):
        count_d1 = d1_complaint_map.get(complaint_type, 0)
        count_d2 = d2_complaint_map.get(complaint_type, 0)
        change = count_d1 - count_d2
        pct_change = round((change / count_d2) * 100, 1) if count_d2 else 0
        complaint_changes.append({
            "complaint_type": complaint_type,
            f"count_{date1}": count_d1,
            f"count_{date2}": count_d2,
            "change": change,
            "pct_change": pct_change,
        })

    return {
        "date1": date1,
        "date2": date2,
        f"tickets_{date1}": tickets_d1,
        f"tickets_{date2}": tickets_d2,
        "tickets_change": tickets_change,
        "tickets_pct_change": tickets_pct,
        f"csat_{date1}": csat_d1,
        f"csat_{date2}": csat_d2,
        "csat_change": csat_change,
        "complaints": complaint_changes,
    }
