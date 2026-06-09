# agents/inventory_agent.py
# Responsible for one job only: checking stock levels and identifying
# whether out-of-stock or low-stock products caused lost sales.

from langgraph.prebuilt import create_react_agent  # builds the ReAct agent graph
from agents.base import llm                         # shared Azure LLM
from tools.inventory_tools import (
    get_all_inventory,        # returns stock levels for ALL products at once
    get_inventory_status,     # returns stock level for a single specific product
    get_stockout_products,    # returns only products with zero stock (quickest check)
    get_overstocked_products, # returns only products with stock > 2x reorder point
    get_stock_status_on_date, # returns historical stock_status per product for a past date
)

# Inventory-only tools — agent cannot call sales or campaign tools
INVENTORY_TOOLS = [
    get_all_inventory,
    get_inventory_status,
    get_stockout_products,
    get_overstocked_products,
    get_stock_status_on_date,
]

# Tells the LLM its role and what a good response looks like
INVENTORY_SYSTEM_PROMPT = """
You are the Inventory Analysis Agent for an e-commerce operations team.
Your job is to check stock levels and identify ALL inventory problems:
  - OUT OF STOCK: products with zero stock (stock == 0)
  - LOW STOCK: products at or below their reorder point
  - OVERSTOCKED: products with stock > 2x their reorder point (overstock_ratio > 2)

When asked about overstocked products, call get_overstocked_products or get_all_inventory
and report every product where is_overstocked is True, sorted by overstock_ratio descending.

HISTORICAL STOCKOUT QUESTIONS (e.g. "did stockouts cause the June 1 drop?"):
  Use get_stock_status_on_date(date) — NOT get_all_inventory or get_stockout_products.
  Those tools show CURRENT stock; get_stock_status_on_date shows what was out-of-stock
  on the specific past date. Always use the target date from the question for this tool.

Always provide: product name, current stock, reorder point, overstock_ratio,
estimated financial impact of holding excess inventory, and recommended action
(discount, return-to-supplier, or demand stimulation).

If sales agent findings are provided in the question, cross-reference them:
confirm whether products with zero sales also have zero stock (stockout = lost revenue).

DATA GAPS: If a tool returns an error, state it explicitly in your report.
Never assume or estimate stock levels — only report what the tools return.
"""


def run_inventory_agent(question: str) -> str:
    """
    Runs the Inventory Agent with a given question.
    Returns a string with inventory analysis and restock recommendations.
    Called by inventory_node in agent_nodes.py.
    """
    agent = create_react_agent(llm, INVENTORY_TOOLS, prompt=INVENTORY_SYSTEM_PROMPT)
    result = agent.invoke({"messages": [("human", question)]})
    return result["messages"][-1].content  # last message = final answer from LLM