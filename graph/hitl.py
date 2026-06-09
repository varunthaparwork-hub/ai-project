# The Human-in-the-Loop approval gate.
# NOTHING gets executed without explicit human approval here.
#
# The node:
#   1. Prints all proposed actions clearly with full details
#   2. Waits for user to type their decision
#   3. Parses "yes", "no", or "1,3" style selective approval
#   4. Writes only the approved subset into state
#   5. Sets skip_execution=True if nothing was approved

from graph.state import OpsState

# Human in the loop Node
def hitl_node(state: OpsState) -> OpsState:
    """
    Pauses the graph and asks the human to approve or reject proposed actions.
    Only approved actions get passed to the executor node.
    """
    proposed = state.get("proposed_actions", [])

    # If action planner found no actions needed, pass straight through
    if not proposed or state.get("skip_execution"):
        return {**state, "approved_actions": [], "skip_execution": True}

    # ── Print the full action plan ─────────────────────────────────
    print("\n" + "=" * 60)
    print("  ⚠️  ACTION APPROVAL REQUIRED")
    print("=" * 60)
    print(f"\nReasoning: {state.get('action_plan_reasoning', '')}\n")
    print("Proposed Actions:")

    for action in proposed:
        print(f"\n  [{action['action_id']}] {action['description']}")
        print(f"       Tool     : {action['tool_name']}")
        print(f"       Args     : {action['tool_args']}")
        print(f"       Priority : {action['priority']}")
        print(f"       Impact   : {action['estimated_impact']}")

    # ── Show approval options ──────────────────────────────────────
    print("\n" + "-" * 60)
    print("  Options:")
    print("    yes / all   → approve ALL actions")
    print("    no          → reject ALL actions")
    print("    1           → approve only action 1")
    print("    1,3         → approve actions 1 and 3 only")
    print("-" * 60)

    try:
        response = input("\n  Your decision: ").strip().lower()
    except KeyboardInterrupt:
        print("\n  Approval cancelled.")
        return {**state, "approved_actions": [], "skip_execution": True}

    # ── Parse the response ─────────────────────────────────────────
    if response in ("yes", "all", "y"):
        approved = proposed
        print(f"\n  ✅ All {len(approved)} action(s) approved.")

    elif response in ("no", "skip", "n", ""):
        print("\n  ❌ All actions rejected. No changes will be made.")
        return {**state, "approved_actions": [], "skip_execution": True}

    else:
        # Selective approval — parse comma-separated IDs like "1,3"
        try:
            ids = {int(x.strip()) for x in response.split(",")}
            approved = [a for a in proposed if a["action_id"] in ids]
            rejected = [a for a in proposed if a["action_id"] not in ids]

            if not approved:
                print("\n  ❌ No valid action IDs entered. Nothing approved.")
                return {**state, "approved_actions": [], "skip_execution": True}

            print(f"\n  ✅ Approved: {[a['action_id'] for a in approved]}")
            if rejected:
                print(f"  ❌ Rejected: {[a['action_id'] for a in rejected]}")

        except ValueError:
            print("\n  ❌ Invalid input. Nothing approved.")
            return {**state, "approved_actions": [], "skip_execution": True}

    return {
        **state,
        "approved_actions": approved,
        "skip_execution": False,
    }