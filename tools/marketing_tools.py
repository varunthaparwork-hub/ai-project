# Tools that give the AI access to campaign and promotion data via PostgreSQL.

from langchain_core.tools import tool
from data.db import fetchall_sync


@tool
def get_campaign_status(date: str) -> dict:
    """
    Returns all marketing campaigns and their status for a given date.
    Includes spend, clicks, conversions, and ROAS(Return on Ad spend).
    Use this to check if any campaign was paused or underperforming.
    Date must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT name, spend, clicks, conversions, status, roas "
        "FROM campaigns WHERE date = $1 ORDER BY spend DESC",
        date,
    )
    if not rows:
        return {"error": f"No campaign data found for {date}"}
    return {
        "date": date,
        "campaigns": [{**r, "spend": float(r["spend"]), "roas": float(r["roas"])} for r in rows],
    }


@tool
def get_paused_campaign(date: str) -> dict:
    """
    Returns only the campaigns that were paused on a given date.
    Use this as a quick check to identify marketing gaps.
    Date must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT name, spend, clicks, conversions, status, roas "
        "FROM campaigns WHERE date = $1 AND status = 'paused'",
        date,
    )
    return {
        "date": date,
        "paused_count": len(rows),
        "paused_campaigns": [{**r, "spend": float(r["spend"]), "roas": float(r["roas"])} for r in rows],
    }


@tool
def compare_campaign_performance(date1: str, date2: str) -> dict:
    """
    Compares total campaign spend, clicks and conversions between two dates.
    Use this to measure how much marketing performance dropped.
    Date must be in YYYY-MM-DD format.
    """
    def totals(date):
        rows = fetchall_sync(
            "SELECT SUM(spend) AS spend, SUM(clicks) AS clicks, SUM(conversions) AS conversions "
            "FROM campaigns WHERE date = $1",
            date,
        )
        r = rows[0] if rows else {}
        return {
            "spend": float(r.get("spend") or 0),
            "clicks": int(r.get("clicks") or 0),
            "conversions": int(r.get("conversions") or 0),
        }

    t1, t2 = totals(date1), totals(date2)
    if not t1["clicks"] and not t2["clicks"]:
        return {"error": "No campaign data found for one or both dates"}
    return {
        "date1": date1, "totals_date1": t1,
        "date2": date2, "totals_date2": t2,
        "spend_drop": t1["spend"] - t2["spend"],
        "clicks_drop": t1["clicks"] - t2["clicks"],
        "conversion_drop": t1["conversions"] - t2["conversions"],
    }
