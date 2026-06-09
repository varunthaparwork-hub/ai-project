# Exports all tools in one place so agents can import them easily

from tools.sales_tools import (
    get_sales_summary,
    compare_sales,
    get_product_performance,
    get_regional_sales
)

from tools.inventory_tools import(
    get_all_inventory,
    get_inventory_status,
    get_stockout_products
)

from tools.marketing_tools import(
    get_campaign_status,
    get_paused_campaign,
    compare_campaign_performance
)

from tools.support_tools import(
    get_support_summary,
    get_top_complaints
)

ALL_TOOLS = [
    get_sales_summary , compare_sales , get_product_performance, get_regional_sales,
    get_all_inventory , get_inventory_status , get_stockout_products,
    get_campaign_status, get_paused_campaign , compare_campaign_performance,
    get_support_summary , get_top_complaints
]