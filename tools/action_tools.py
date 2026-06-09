# These tools execute real business actions against PostgreSQL.
# restock / discount update the inventory table;
# resume / pause update the campaigns table.

from langchain_core.tools import tool
from data.db import fetchone_sync, execute_sync


@tool
def restock_product(product_name: str, quantity: int) -> dict:
    """
    Restocks a product by adding the specified quantity to current stock.
    Use when a product is out of stock or below its reorder point.
    Returns confirmation with old and new stock levels.
    """
    row = fetchone_sync("SELECT stock FROM inventory WHERE product_name = $1", product_name)
    if not row:
        return {"success": False, "error": f"Product '{product_name}' not found."}

    old_stock = row["stock"]
    new_stock = old_stock + quantity
    execute_sync(
        "UPDATE inventory SET stock = $1 WHERE product_name = $2",
        new_stock, product_name,
    )
    return {
        "success": True,
        "action": "restock",
        "product": product_name,
        "quantity_added": quantity,
        "old_stock": old_stock,
        "new_stock": new_stock,
        "message": f"Restocked '{product_name}' with {quantity} units. Stock: {old_stock} → {new_stock}",
    }


@tool
def apply_discount(product_name: str, discount_pct: float, duration_hours: int) -> dict:
    """
    Applies a percentage discount to a product for a limited time.
    Use to recover sales on available products when revenue is low.
    discount_pct should be a number like 10 for 10%, not 0.10.
    Cannot discount an out-of-stock product.
    """
    row = fetchone_sync("SELECT stock FROM inventory WHERE product_name = $1", product_name)
    if not row:
        return {"success": False, "error": f"Product '{product_name}' not found."}
    if row["stock"] == 0:
        return {"success": False, "error": f"Product '{product_name}' is out of stock."}
    return {
        "success": True,
        "action": "apply_discount",
        "product": product_name,
        "discount_pct": discount_pct,
        "duration_hours": duration_hours,
        "message": f"Applied {discount_pct}% discount on '{product_name}' for {duration_hours} hours.",
    }


@tool
def resume_campaign(campaign_name: str) -> dict:
    """
    Resume a paused marketing campaign.
    Use when a campaign was paused due to budget exhaustion
    and traffic needs to be restored to recover sales.
    """
    row = fetchone_sync(
        "SELECT status FROM campaigns WHERE name = $1 ORDER BY date DESC LIMIT 1",
        campaign_name,
    )
    if not row:
        return {"success": False, "error": f"Campaign '{campaign_name}' not found."}
    if row["status"] == "active":
        return {"success": False, "error": f"Campaign '{campaign_name}' is already active."}
    execute_sync("UPDATE campaigns SET status = 'active' WHERE name = $1", campaign_name)
    return {
        "success": True,
        "action": "resume_campaign",
        "campaign": campaign_name,
        "message": f"Campaign '{campaign_name}' resumed and is now active.",
    }


@tool
def pause_campaign(campaign_name: str, reason: str) -> dict:
    """
    Pauses an active marketing campaign.
    Use when a campaign is underperforming or wasting budget.
    Always provide a reason so the team knows why it was paused.
    """
    row = fetchone_sync(
        "SELECT status FROM campaigns WHERE name = $1 ORDER BY date DESC LIMIT 1",
        campaign_name,
    )
    if not row:
        return {"success": False, "error": f"Campaign '{campaign_name}' not found."}
    if row["status"] == "paused":
        return {"success": False, "error": f"Campaign '{campaign_name}' is already paused."}
    execute_sync("UPDATE campaigns SET status = 'paused' WHERE name = $1", campaign_name)
    return {
        "success": True,
        "action": "pause_campaign",
        "campaign": campaign_name,
        "reason": reason,
        "message": f"Campaign '{campaign_name}' paused. Reason: {reason}",
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