# agents/support_agent.py
# Responsible for one job only: analyzing customer support data
# to identify complaints or friction points that hurt conversions.

from langgraph.prebuilt import create_react_agent  # builds the ReAct agent graph
from agents.base import llm                         # shared Azure LLM
from tools.support_tools import (
    get_support_summary,  # returns total tickets, CSAT score, open vs resolved counts
    get_top_complaints,   # returns complaint types ranked by volume
)

# Support-only tools — scoped to customer experience domain
SUPPORT_TOOLS = [
    get_support_summary,
    get_top_complaints,
]

# Tells the LLM its role and what to include in the response
SUPPORT_SYSTEM_PROMPT = """
You are the Customer Support Analysis Agent for an e-commerce operations team.
Your job is to analyze support tickets, complaints, and customer satisfaction
data to identify experience issues that may have hurt sales or reputation.
Use the available tools to gather data, then provide a clear summary
of ticket volume vs normal, top complaint categories, CSAT score,
and whether any complaints correlate with sales issues.

If prior findings from other agents are provided in the question, check alignment:
for example, if inventory found a stockout, verify whether "out of stock" complaints
spiked on the same date — this confirms the stockout had customer-visible impact.

DATA GAPS: If a tool returns no data for a date, note this explicitly in your report.
Do not assume complaint volumes — only report confirmed numbers from tool results.
"""


def run_support_agent(question: str) -> str:
    """
    Runs the Support Agent with a given question.
    Returns a string with customer experience analysis.
    Called by support_node in agent_nodes.py.
    """
    agent = create_react_agent(llm, SUPPORT_TOOLS, prompt=SUPPORT_SYSTEM_PROMPT)
    result = agent.invoke({"messages": [("human", question)]})
    return result["messages"][-1].content  # last message = final answer from LLM
