# graph/agent_nodes.py
# These are thin wrapper nodes that sit between the LangGraph state
# and the individual specialist agents.
#
# Why wrappers instead of calling agents directly?
#   - Nodes read from and write to OpsState
#   - Agents just take a string question and return a string answer
#   - Wrappers translate between the two worlds
#
# Each node follows the same 4-step pattern:
#   1. Check the flag — if planner said skip, return state unchanged
#   2. Build a focused question from dates stored in state
#   3. Call the agent
#   4. Write the result back into state and return it

from graph.state import OpsState                        # shared state TypedDict
from agents.sales_agent import run_sales_agent          # sales analysis function
from agents.marketing_agent import run_marketing_agent  # marketing analysis function
from agents.inventory_agent import run_inventory_agent  # inventory analysis function
from agents.support_agent import run_support_agent      # support analysis function


def sales_node(state: OpsState) -> OpsState:
    # Check if planner activated this node — if not, skip it entirely
    if not state.get("needs_sales"):
        print("[SALES] Skipped")
        return state  # return state unchanged so graph can continue to next node

    # Build a specific question using the dates from state
    # Including the original question gives the agent full context
    question = (
        f"Analyze sales performance for {state['target_date']} "
        f"and compare with {state['comparison_date']}. "
        f"Original user question: {state['user_question']}"
    )

    print("\n[SALES] Running...")
    analysis = run_sales_agent(question)  # agent returns a string with its findings

    # {**state} copies all existing fields, then overwrites just sales_analysis
    # This pattern ensures we never lose data from other fields
    return {**state, "sales_analysis": analysis}


def inventory_node(state: OpsState) -> OpsState:
    if not state.get("needs_inventory"):
        print("[INVENTORY] Skipped.")
        return state

    # Pass sales findings so inventory can confirm which stockouts caused lost revenue
    sales_context = ""
    if state.get("sales_analysis"):
        sales_context = (
            "\n\nSALES AGENT FINDINGS (cross-reference these with your stock data):\n"
            + state["sales_analysis"][:600]
        )

    question = (
        f"Check all inventory levels. Identify out-of-stock and low stock products. "
        f"Assess impact on sales for {state['target_date']}. "
        f"Original user question: {state['user_question']}"
        f"{sales_context}"
    )

    print("\n[INVENTORY] Running...")
    analysis = run_inventory_agent(question)
    return {**state, "inventory_analysis": analysis}


def marketing_node(state: OpsState) -> OpsState:
    if not state.get("needs_marketing"):
        print("[MARKETING] Skipped.")
        return state

    # Provide prior findings so marketing can correlate campaign drops with revenue/stock issues
    prior_context = ""
    if state.get("sales_analysis"):
        prior_context += f"\n\nSALES FINDINGS:\n{state['sales_analysis'][:400]}"
    if state.get("inventory_analysis"):
        prior_context += f"\n\nINVENTORY FINDINGS:\n{state['inventory_analysis'][:400]}"
    if prior_context:
        prior_context = "\n\nPRIOR AGENT FINDINGS (use to guide your campaign analysis):" + prior_context

    question = (
        f"Analyze all campaigns on {state['target_date']} "
        f"compared to {state['comparison_date']}. "
        f"Identify paused or underperforming campaigns. "
        f"Original user question: {state['user_question']}"
        f"{prior_context}"
    )

    print("\n[MARKETING] Running...")
    analysis = run_marketing_agent(question)
    return {**state, "marketing_analysis": analysis}


def support_node(state: OpsState) -> OpsState:
    if not state.get("needs_support"):
        print("[SUPPORT] Skipped.")
        return state

    # Provide full cross-domain context so support can confirm if complaints match other signals
    prior_context = ""
    for label, key in [("SALES", "sales_analysis"), ("INVENTORY", "inventory_analysis"), ("MARKETING", "marketing_analysis")]:
        if state.get(key):
            prior_context += f"\n\n{label} FINDINGS:\n{state[key][:300]}"
    if prior_context:
        prior_context = "\n\nPRIOR AGENT FINDINGS (check if complaints correlate with these):" + prior_context

    question = (
        f"Analyze customer support tickets and complaints for {state['target_date']}. "
        f"Compare with {state['comparison_date']} if possible. "
        f"Original user question: {state['user_question']}"
        f"{prior_context}"
    )

    print("\n[SUPPORT] Running...")
    analysis = run_support_agent(question)
    return {**state, "support_analysis": analysis}
