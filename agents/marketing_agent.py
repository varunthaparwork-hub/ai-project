# agents/marketing_agent.py
# Responsible for one job only: analyzing campaign and ad performance
# to identify whether paused or underperforming campaigns reduced traffic.

from langgraph.prebuilt import create_react_agent  # builds the ReAct agent graph
from agents.base import llm                         # shared Azure LLM
from tools.marketing_tools import (
    get_campaign_status,           # returns all campaigns and their status for a date
    get_paused_campaign,           # returns only the paused campaigns (quick check)
    compare_campaign_performance,  # compares spend/clicks/conversions across two dates
)

# Marketing-only tools — scoped to prevent cross-domain confusion
MARKETING_TOOLS = [
    get_campaign_status,
    get_paused_campaign,
    compare_campaign_performance,
]

# Tells the LLM its role and what to include in the response
MARKETING_SYSTEM_PROMPT = """
You are the Marketing Analysis Agent for an e-commerce operations team.
Your job is to analyze campaign performance and identify marketing issues
that may have reduced traffic or conversions.
Use the available tools to gather data, then provide a clear summary
of which campaigns were active vs paused, spend and conversion comparisons
to the previous period, and which channel caused the most impact.
"""


def run_marketing_agent(question: str) -> str:
    """
    Runs the Marketing Agent with a given question.
    Returns a string with campaign analysis.
    Called by marketing_node in agent_nodes.py.
    """
    agent = create_react_agent(llm, MARKETING_TOOLS, prompt=MARKETING_SYSTEM_PROMPT)
    result = agent.invoke({"messages": [("human", question)]})
    return result["messages"][-1].content  # last message = final answer from LLM
