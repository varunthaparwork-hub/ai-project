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
            + state["sales_analysis"][:2000]
        )

    # Determine whether this is a HISTORICAL question (past date) or a CURRENT inventory check.
    # Historical questions must use get_stock_status_on_date — not get_all_inventory.
    # get_all_inventory only shows today's stock; get_stock_status_on_date shows what was
    # actually in/out of stock on the specific date being investigated.
    from datetime import date as _date
    target = state.get("target_date") or ""
    user_q  = state.get("user_question", "").lower()
    is_historical = False
    try:
        is_historical = bool(target) and _date.fromisoformat(target) < _date.today()
    except ValueError:
        pass

    historical_keywords = ("stockout", "cause", "did", "why", "drop", "revenue", "june 1", "what happened")
    looks_like_stockout_question = any(kw in user_q for kw in historical_keywords)

    # DIRECT ACTION MODE — user is issuing a command, not asking for analysis.
    # e.g. "restock samsung tv by 20 units" — no need to run deep inventory analysis.
    # Just confirm the current stock level of the named product so the action planner
    # has the data it needs; skip the full overstock/stockout report that would confuse it.
    direct_action_keywords = ("restock", "apply discount", "add stock", "add units", "order more")
    looks_like_direct_command = any(kw in user_q for kw in direct_action_keywords)

    if looks_like_direct_command:
        # Extract the product if mentioned (agent will figure it out from the question)
        question = (
            f"The user has issued a direct inventory action command. "
            f"Use get_all_inventory() to retrieve current stock levels, then confirm "
            f"the current stock of any products mentioned in the request. "
            f"Do NOT produce an overstock/understock analysis — just report current stock "
            f"of the relevant product(s) so the action can be executed. "
            f"User command: {state['user_question']}"
            f"{sales_context}"
        )
        mode = "direct-command"
    elif is_historical and looks_like_stockout_question:
        # HISTORICAL MODE — check what was actually in/out of stock on that specific past date
        question = (
            f"Use get_stock_status_on_date('{target}') to check which products were "
            f"out-of-stock or low-stock on {target}. "
            f"This is a historical investigation — do NOT call get_all_inventory or "
            f"get_overstocked_products as those show current stock, not {target} stock. "
            f"Confirm whether stockouts on {target} caused lost revenue and which products were affected. "
            f"Original user question: {state['user_question']}"
            f"{sales_context}"
        )
        mode = "historical:" + target
    else:
        # CURRENT MODE — check today's stock levels for overstock / stockout / low stock
        question = (
            f"Check current inventory levels. Identify any out-of-stock, low-stock, "
            f"or overstocked products right now. "
            f"Assess how current stock levels may affect upcoming sales. "
            f"Original user question: {state['user_question']}"
            f"{sales_context}"
        )
        mode = "current"

    print(f"\n[INVENTORY] Running... (mode={mode})")
    analysis = run_inventory_agent(question)
    return {**state, "inventory_analysis": analysis}


def marketing_node(state: OpsState) -> OpsState:
    if not state.get("needs_marketing"):
        print("[MARKETING] Skipped.")
        return state

    # Provide prior findings so marketing can correlate campaign drops with revenue/stock issues
    prior_context = ""
    if state.get("sales_analysis"):
        prior_context += f"\n\nSALES FINDINGS:\n{state['sales_analysis'][:2000]}"
    if state.get("inventory_analysis"):
        prior_context += f"\n\nINVENTORY FINDINGS:\n{state['inventory_analysis'][:2000]}"
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
            prior_context += f"\n\n{label} FINDINGS:\n{state[key][:2000]}"
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
