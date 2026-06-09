# Tools that give AI access to stock level data via PostgreSQL.

from langchain_core.tools import tool
from data.db import fetchone_sync, fetchall_sync


@tool
def get_inventory_status(product_name: str) -> dict:
    """
    Returns the current stock level for a specific product.
    Includes stock quantity, reorder point, and reorder quantity.
    Use this to check if a specific product is out of stock.
    """
    row = fetchone_sync("SELECT * FROM inventory WHERE product_name = $1", product_name)
    if not row:
        return {"error": f"Product '{product_name}' not found in inventory"}
    stock = row["stock"]
    rp    = row["reorder_point"]
    return {
        "product":         row["product_name"],
        "stock":           stock,
        "reorder_point":   rp,
        "reorder_qty":     row["reorder_qty"],
        "is_out_of_stock": stock == 0,
        "is_low_stock":    0 < stock <= rp,
        "is_overstocked":  stock > rp * 2,
        "overstock_ratio": round(stock / max(rp, 1), 1),
    }


@tool
def get_all_inventory() -> dict:
    """
    Returns stock levels for all products at once.
    Use this to get a full picture of inventory health and identify
    out-of-stock, low-stock, OR overstocked items.
    overstock_ratio = stock / reorder_point.  Values > 2 indicate overstock.
    """
    rows = fetchall_sync("SELECT * FROM inventory ORDER BY product_name")
    return {
        r["product_name"]: {
            "stock":           r["stock"],
            "reorder_point":   r["reorder_point"],
            "reorder_qty":     r["reorder_qty"],
            "is_out_of_stock": r["stock"] == 0,
            "is_low_stock":    0 < r["stock"] <= r["reorder_point"],
            "is_overstocked":  r["stock"] > r["reorder_point"] * 2,
            "overstock_ratio": round(r["stock"] / max(r["reorder_point"], 1), 1),
        }
        for r in rows
    }


@tool
def get_overstocked_products() -> dict:
    """
    Returns only the products that are overstocked (stock > 2x their reorder point).
    Use this when the user asks about excess inventory, overstocking, or slow-moving stock.
    overstock_ratio shows how many times above the reorder point the stock is.
    """
    rows = fetchall_sync(
        "SELECT * FROM inventory WHERE stock > reorder_point * 2 ORDER BY stock DESC"
    )
    return {
        "overstocked_count": len(rows),
        "products": [
            {
                "product":         r["product_name"],
                "stock":           r["stock"],
                "reorder_point":   r["reorder_point"],
                "reorder_qty":     r["reorder_qty"],
                "overstock_ratio": round(r["stock"] / max(r["reorder_point"], 1), 1),
            }
            for r in rows
        ],
    }


@tool
def get_stockout_products() -> dict:
    """
    Returns only the products that are currently out of stock (stock == 0).
    Use this as a quick check to find the most critical inventory problems.
    """
    rows = fetchall_sync(
        "SELECT product_name, reorder_qty FROM inventory WHERE stock = 0"
    )
    return {
        "out_of_stock_count": len(rows),
        "products": [{"product": r["product_name"], "reorder_qty": r["reorder_qty"]}
                     for r in rows],
    }


@tool
def get_stock_status_on_date(date: str) -> dict:
    """
    Returns the stock status of every product on a specific past date.
    Use this to check HISTORICAL stockout conditions — e.g. which products were
    out-of-stock on June 1 when revenue dropped. This is different from current
    inventory: it reads from the product_sales table which records stock_status
    per product per day.
    Date must be in YYYY-MM-DD format.
    """
    rows = fetchall_sync(
        "SELECT product_name, units_sold, revenue, stock_status "
        "FROM product_sales WHERE date = $1 ORDER BY revenue DESC",
        date,
    )
    if not rows:
        return {"error": f"No product sales data found for {date}"}

    out_of_stock  = [r for r in rows if r["stock_status"] == "out_of_stock"]
    low_stock     = [r for r in rows if r["stock_status"] == "low_stock"]
    in_stock      = [r for r in rows if r["stock_status"] == "in_stock"]

    return {
        "date": date,
        "summary": {
            "out_of_stock_count": len(out_of_stock),
            "low_stock_count":    len(low_stock),
            "in_stock_count":     len(in_stock),
        },
        "out_of_stock_products": [
            {"product": r["product_name"], "units_sold": r["units_sold"], "revenue": float(r["revenue"])}
            for r in out_of_stock
        ],
        "low_stock_products": [
            {"product": r["product_name"], "units_sold": r["units_sold"], "revenue": float(r["revenue"])}
            for r in low_stock
        ],
        "in_stock_products": [
            {"product": r["product_name"], "units_sold": r["units_sold"], "revenue": float(r["revenue"])}
            for r in in_stock
        ],
    }
