# These tools execute real business actions against PostgreSQL.
# restock / discount update the inventory table;
# resume / pause update the campaigns table.

import random
import string
from langchain_core.tools import tool
from data.db import fetchone_sync, execute_sync


@tool
def restock_product(product_name: str, quantity: int) -> dict:
    """
    Restocks a product by adding the specified quantity to current stock.
    Use when a product is out of stock or below its reorder point.
    Returns confirmation with old and new stock levels.
    """
    # Case-insensitive lookup — LLM may pass lowercase/mixed-case names
    row = fetchone_sync(
        "SELECT product_name, stock FROM inventory WHERE LOWER(product_name) = LOWER($1)",
        product_name,
    )
    if not row:
        from data.db import fetchall_sync as _fa
        available = ", ".join(r["product_name"] for r in _fa("SELECT product_name FROM inventory ORDER BY product_name"))
        return {"success": False, "error": f"Product '{product_name}' not found. Available products: {available}"}

    canonical  = row["product_name"]   # always use DB's exact casing for UPDATE
    old_stock  = row["stock"]
    new_stock  = old_stock + quantity
    execute_sync(
        "UPDATE inventory SET stock = $1 WHERE product_name = $2",
        new_stock, canonical,
    )
    return {
        "success": True,
        "action": "restock",
        "product": canonical,
        "quantity_added": quantity,
        "old_stock": old_stock,
        "new_stock": new_stock,
        "message": f"Restocked '{canonical}' with {quantity} units. Stock: {old_stock} to {new_stock}",
    }


@tool
def apply_discount(product_name: str, discount_pct: float, duration_hours: int) -> dict:
    """
    Applies a percentage discount to a product for a limited time.
    Use to recover sales on available products when revenue is low.
    discount_pct should be a number like 10 for 10%, not 0.10.
    Cannot discount an out-of-stock product.
    """
    row = fetchone_sync(
        "SELECT product_name, stock FROM inventory WHERE LOWER(product_name) = LOWER($1)",
        product_name,
    )
    if not row:
        from data.db import fetchall_sync as _fa
        available = ", ".join(r["product_name"] for r in _fa("SELECT product_name FROM inventory ORDER BY product_name"))
        return {"success": False, "error": f"Product '{product_name}' not found. Available products: {available}"}
    canonical = row["product_name"]
    if row["stock"] == 0:
        return {"success": False, "error": f"Product '{canonical}' is out of stock — cannot apply discount."}
    execute_sync(
        "UPDATE inventory SET discount_pct = $1, "
        "discount_expires_at = NOW() + ($2 * INTERVAL '1 hour') "
        "WHERE product_name = $3",
        discount_pct, duration_hours, canonical,
    )
    return {
        "success": True,
        "action": "apply_discount",
        "product": canonical,
        "discount_pct": discount_pct,
        "duration_hours": duration_hours,
        "message": f"Applied {discount_pct}% discount on '{canonical}' for {duration_hours} hours.",
    }


@tool
def resume_campaign(campaign_name: str) -> dict:
    """
    Resume a paused marketing campaign.
    Use when a campaign was paused due to budget exhaustion
    and traffic needs to be restored to recover sales.
    """
    row = fetchone_sync(
        "SELECT name, status FROM campaigns WHERE LOWER(name) = LOWER($1) ORDER BY date DESC LIMIT 1",
        campaign_name,
    )
    if not row:
        from data.db import fetchall_sync as _fa
        available = ", ".join(r["name"] for r in _fa("SELECT DISTINCT name FROM campaigns ORDER BY name"))
        return {"success": False, "error": f"Campaign '{campaign_name}' not found. Available: {available}"}
    canonical = row["name"]
    if row["status"] == "active":
        return {"success": False, "error": f"Campaign '{canonical}' is already active."}
    execute_sync("UPDATE campaigns SET status = 'active' WHERE LOWER(name) = LOWER($1)", campaign_name)
    return {
        "success": True,
        "action": "resume_campaign",
        "campaign": canonical,
        "message": f"Campaign '{canonical}' resumed and is now active.",
    }


@tool
def pause_campaign(campaign_name: str, reason: str) -> dict:
    """
    Pauses an active marketing campaign.
    Use when a campaign is underperforming or wasting budget.
    Always provide a reason so the team knows why it was paused.
    """
    row = fetchone_sync(
        "SELECT name, status FROM campaigns WHERE LOWER(name) = LOWER($1) ORDER BY date DESC LIMIT 1",
        campaign_name,
    )
    if not row:
        from data.db import fetchall_sync as _fa
        available = ", ".join(r["name"] for r in _fa("SELECT DISTINCT name FROM campaigns ORDER BY name"))
        return {"success": False, "error": f"Campaign '{campaign_name}' not found. Available: {available}"}
    canonical = row["name"]
    if row["status"] == "paused":
        return {"success": False, "error": f"Campaign '{canonical}' is already paused."}
    execute_sync("UPDATE campaigns SET status = 'paused' WHERE LOWER(name) = LOWER($1)", campaign_name)
    return {
        "success": True,
        "action": "pause_campaign",
        "campaign": canonical,
        "reason": reason,
        "message": f"Campaign '{canonical}' paused. Reason: {reason}",
    }



@tool
def create_support_ticket(issue_type: str, description: str, priority: str) -> dict:
    """
    Creates a support ticket for a reported customer or technical issue.
    Use for checkout errors, delivery problems, or product quality issues.
    priority must be one of: low, medium, high, critical.
    """
    # Generate a realistic-looking ticket ID
    ticket_id = "TKT-" + "".join(random.choices(string.digits, k=6))
    execute_sync(
        "INSERT INTO support_tickets (id, issue_type, description, priority, status) "
        "VALUES ($1, $2, $3, $4, 'open')",
        ticket_id, issue_type, description, priority,
    )
    return {
        "success": True,
        "action": "create_support_ticket",
        "ticket_id": ticket_id,
        "issue_type": issue_type,
        "description": description,
        "priority": priority,
        "status": "open",
        "message": f"Ticket {ticket_id} created. Priority: {priority}. Issue: {issue_type}",
    }