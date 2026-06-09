# agents/sales_agent.py
# The Sales Agent is responsible for one job only:
# answer questions about revenue, orders, and product performance.
#
# How it works:
#   1. It gets a question + context (e.g., "analyze sales for 2026-06-01")
#   2. It decides which sales tools to call (get_sales_summary, compare_sales, etc.)
#   3. It calls them, reads the results, and writes a structured analysis
#
# The agent is built using `create_react_agent` — a standard pattern where
# the LLM reasons ("Re") and acts ("Act") in a loop until it has enough info.

# agents/sales_agent.py
# Responsible for one job only: answering questions about revenue,
# orders, and product performance.
#
# Pattern used: ReAct (Reason + Act)
#   The LLM reasons about what data it needs → calls a tool → reads result
#   → reasons again → calls another tool → ... → writes final answer

from langgraph.prebuilt import create_react_agent  # builds a ReAct agent as a LangGraph graph
from agents.base import llm                         # shared Azure LLM instance
from tools.sales_tools import (
    get_sales_summary,       # fetches revenue, orders, returns for a date
    compare_sales,           # calculates % change between two dates
    get_product_performance, # shows per-product units and revenue
    get_regional_sales,      # breaks down sales by region
    get_sales_trend,         # returns daily trend over a date range
    get_sales_anomaly,       # z-score vs rolling baseline — answers "is this drop normal?"
)

# Only sales tools are given to this agent.
# Scoping tools per agent keeps reasoning focused and prevents
# the LLM from accidentally calling unrelated tools.
SALES_TOOLS = [
    get_sales_summary,
    compare_sales,
    get_product_performance,
    get_regional_sales,
    get_sales_trend,
    get_sales_anomaly,
]

# System prompt defines the agent's role and what to include in its response.
# This is passed as a persistent system message before every conversation.
SALES_SYSTEM_PROMPT = """
You are the Sales Analysis Agent for an e-commerce operations team.
Your job is to analyze sales data and provide clear, factual insights.
Use the available tools to gather data, then provide a structured analysis
with revenue figures, order counts, comparison to previous period,
which products underperformed, and whether the drop is significant.

Use get_sales_trend when asked about multi-day patterns, week-over-week questions,
or to determine if today's drop is isolated or part of a longer sustained decline.

Use get_sales_anomaly when the user asks whether a drop is "normal", "expected",
"an anomaly", or "significant". It returns a z-score and a verdict
(strong_anomaly / mild_anomaly / normal) against a rolling baseline. If
insufficient_history is True, fall back to compare_sales.

DATA GAPS: If a tool returns {{"error": "No data found"}}, try an adjacent date
(one day earlier or later). If still no data, explicitly state which dates had
no data and continue with what is available. Never fabricate numbers.
"""


def run_sales_agent(question: str) -> str:
    """
    Runs the Sales Agent with a given question.
    Returns a string with the full sales analysis.
    Called by sales_node in agent_nodes.py.
    """
    # create_react_agent builds a mini LangGraph internally:
    # LLM → (tool call?) → tool → LLM → (tool call?) → ... → final message
    agent = create_react_agent(llm, SALES_TOOLS, prompt=SALES_SYSTEM_PROMPT)

    # invoke() runs the full ReAct loop until the LLM stops calling tools
    result = agent.invoke({"messages": [("human", question)]})

    # result["messages"] is the full conversation list
    # [-1] is the last message = the agent's final answer
    return result["messages"][-1].content