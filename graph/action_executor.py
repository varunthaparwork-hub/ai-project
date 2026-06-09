# Executes only the actions the human approved in the HITL node.
# Looks up each tool by name from a registry, calls it with the
# exact args the action planner specified, and collects results.
# One failed action never crashes the others — each is try/except wrapped.

from graph.state import OpsState

# Actions Tools
from tools.action_tools import (
    restock_product,
    apply_discount,
    resume_campaign,
    pause_campaign,
    create_support_ticket,
)

# Registry maps the string tool name from action planner → actual callable tool
TOOL_REGISTRY = {
    "restock_product":       restock_product,
    "apply_discount":        apply_discount,
    "resume_campaign":       resume_campaign,
    "pause_campaign":        pause_campaign,
    "create_support_ticket": create_support_ticket,
}

def action_executor_node(state: OpsState) -> OpsState:
    """
    Executes each approved action by looking up and calling the correct tool.
    Builds a human-readable execution report summarising success and failures.
    """
    approved = state.get("approved_actions", [])

    # No actions to execute 
    if not approved or state.get("skip_execution"):
        print("\n[EXECUTOR] No actions to execute.")
        return {**state, "execution_report": "No actions were approved for execution."}

    print(f"\n[EXECUTOR] Executing {len(approved)} approved action(s)...")

    results = []

    for action in approved:
        tool_name = action.get("tool_name")
        tool_args = action.get("tool_args", {})
        tool_fn   = TOOL_REGISTRY.get(tool_name)

        if not tool_fn:
            # Unknown tool name — log it and continue rather than crashing
            msg = f"Unknown tool: '{tool_name}'"
            results.append({"action_id": action["action_id"], "tool": tool_name, "success": False, "result": msg})
            print(f" Failed Action {action['action_id']}: {msg}")
            continue

        try:
            # Call the real tool function with args from the planner
            result  = tool_fn.invoke(tool_args)
            success = result.get("success", True)
            msg     = result.get("message", str(result))
            results.append({"action_id": action["action_id"], "tool": tool_name, "success": success, "result": msg})
            print(f"  {'Passed' if success else 'Failed'} Action {action['action_id']}: {msg}")

        except Exception as e:
            # Catch runtime errors so one bad action doesn't stop the rest
            msg = f"Error: {str(e)}"
            results.append({"action_id": action["action_id"], "tool": tool_name, "success": False, "result": msg})
            print(f" Failed Action {action['action_id']} failed: {e}")

    # Build a clean text report
    succeeded = [r for r in results if r["success"]]
    failed    = [r for r in results if not r["success"]]

    lines = [f"Execution Summary: {len(succeeded)}/{len(results)} succeeded.\n"]
    for r in results:
        icon = "✅" if r["success"] else "❌"
        lines.append(f"{icon} Action {r['action_id']} ({r['tool']}): {r['result']}")

    execution_report = "\n".join(lines)
    print(f"\n[EXECUTOR] Done. {len(succeeded)}/{len(results)} succeeded.")

    return {
        **state,
        "execution_report":  execution_report,
        "execution_results": results,
    }