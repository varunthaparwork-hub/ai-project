# main.py
# Entry point for the entire AI E-Commerce Operations Manager.
# Run this file directly: `python main.py`
# The ask() function can also be imported by Streamlit or FastAPI later.

from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", encoding="utf-8-sig")


def ask(question: str, target_date: str = "", comparison_date: str = "",
        thread_id: str = "default", history: list = None):
    """
    Main function to run the AI system.
    - question        : the business question from the user
    - target_date     : the date to analyze (leave empty → planner infers it)
    - comparison_date : the date to compare against (leave empty → planner infers it)
    - thread_id       : groups messages into the same conversation for MemorySaver
                        same thread_id = AI remembers previous turns in this session
    - history         : running list of past messages, passed in and updated each turn
    """
    from graph.workflow import ops_app  # lazy: keeps import safe when main.py is imported by FastAPI
    from graph.state import OpsState

    # Default mutable argument fix — never use [] as default in Python function signatures
    if history is None:
        history = []

    # Cap history to last 20 turns (40 messages) to prevent token explosion
    if len(history) > 40:
        history = history[-40:]

    # Add the new user question to the conversation history
    history = history + [{"role": "user", "content": question}]

    # Print a visual separator so output is easy to read in terminal
    print("\n" + "=" * 60)
    print(f"QUESTION: {question}")

    # Only print dates if the user explicitly provided them
    if target_date:
        print(f"TARGET DATE: {target_date}")
    if comparison_date:
        print(f"COMPARISON DATE: {comparison_date}")
    print("=" * 60)

    # Build the initial state — this is the starting snapshot of the shared whiteboard.
    # Every field is set to a safe default. Nodes will fill them in as the graph runs.
    initial_state: OpsState = {
        "user_question": question,       # the raw question — every node can read this
        "needs_sales": False,            # planner will set to True if sales analysis needed
        "needs_inventory": False,        # planner will set to True if inventory check needed
        "needs_marketing": False,        # planner will set to True if campaign check needed
        "needs_support": False,          # planner will set to True if support check needed
        "sales_analysis": None,          # sales_node writes its findings here
        "inventory_analysis": None,      # inventory_node writes its findings here
        "marketing_analysis": None,      # marketing_node writes its findings here
        "support_analysis": None,        # support_node writes its findings here
        "synthesis_draft": None,         # synthesis_node writes the combined draft here
        "critic_feedback": None,         # critic_node writes its feedback here if revision needed
        "needs_revision": False,         # critic sets this True to send draft back to synthesis
        "revision_count": 0,             # tracks how many times critic has sent for revision
        "final_answer": None,            # critic promotes synthesis_draft here when approved
        "target_date": target_date,      # empty string = planner will infer from the question
        "comparison_date": comparison_date,  # empty string = planner will infer from the question
        "conversation_history": history,  # running history passed in from previous turns
        "proposed_actions": None,         # action_planner fills this with proposed actions
        "action_plan_reasoning": None,    # action_planner fills this with overall reasoning
        "approved_actions": None,         # hitl fills this with user-approved subset
        "skip_execution": False,          # hitl sets True if user rejects all actions
        "execution_report": None,         # executor fills this after running actions
        "execution_results": None,        # executor fills this with per-action result list
        "past_incidents": None,           # memory_node fills this from Qdrant search
        "structured_output": None,         # formatter_node writes OpsResponse dict here
    }

    # config tells MemorySaver which conversation thread this belongs to.
    # Same thread_id = checkpointer restores previous state automatically.
    # Different thread_id = fresh conversation with no memory of the past.
    config = {"configurable": {"thread_id": thread_id}}

    # ops_app.invoke() runs the full LangGraph graph from START to END
    # It processes every node in order and returns the final state
    result = ops_app.invoke(initial_state, config=config)

    # Safely get final answer — fall back to draft if critic didn't set final_answer
    final = result.get("final_answer") or result.get("synthesis_draft") or "No answer generated."

    # Add the assistant's answer to history so next turn has full context
    history = history + [{"role": "assistant", "content": final}]

    # Print the final answer
    print("\n" + "=" * 60)
    print("FINAL ANSWER:")
    print("=" * 60)
    print(final)

    # If actions were executed, print the execution report as well
    if result.get("execution_report"):
        print("\n" + "=" * 60)
        print("EXECUTION REPORT:")
        print("=" * 60)
        print(result["execution_report"])

    # Print structured output summary (severity + top root cause)
    structured = result.get("structured_output")
    if structured:
        print("\n" + "-" * 60)
        print(f"[STRUCTURED] Severity : {structured.get('severity', 'N/A').upper()}")
        print(f"[STRUCTURED] One-liner: {structured.get('one_liner', 'N/A')}")
        causes = structured.get('root_causes') or []
        if causes:
            top = causes[0]
            print(f"[STRUCTURED] Top cause: #{top.get('rank',1)} {top.get('description','N/A')} ({top.get('domain','?')})")
        actions = structured.get('recommended_actions') or []
        executable = [a for a in actions if a.get('is_executable')]
        print(f"[STRUCTURED] Actions  : {len(actions)} recommended, {len(executable)} executable")
        print("-" * 60)

    # If actions were executed, save this incident to long-term memory
    # so future questions like "what did we do last time?" can find it
    if result.get("execution_results"):
        from memory.long_term import save_incident  # lazy import
        executed_tools = [r["tool"] for r in result["execution_results"] if r["success"]]
        if executed_tools:
            save_incident(
                date         = result.get("target_date", date.today().isoformat()),
                description  = final[:400],           # first 400 chars of final answer
                root_causes  = [],                    # could extract from state in future
                actions_taken= executed_tools,
                outcome      = "Actions executed — outcome pending.",
            )
            print("[MEMORY] Incident saved to long-term memory.")

    return {
        "final_answer": final,
        "history": history,
        "structured_output": result.get("structured_output"),
        "proposed_actions": result.get("proposed_actions"),
        "execution_report": result.get("execution_report"),
        "execution_results": result.get("execution_results"),
        "sales_analysis": result.get("sales_analysis"),
        "inventory_analysis": result.get("inventory_analysis"),
        "marketing_analysis": result.get("marketing_analysis"),
        "support_analysis": result.get("support_analysis"),
        "revision_count": result.get("revision_count", 0),
        "target_date": result.get("target_date"),
        "comparison_date": result.get("comparison_date"),
    }


if __name__ == "__main__":
    from memory.long_term import seed_memory_from_db  # lazy: avoid import at module level
    import asyncio

    # This block only runs when you execute `python main.py` directly
    print("=" * 60)
    print("  AI E-Commerce Operations Manager")
    print("  Today: " + date.today().isoformat())
    print("=" * 60)

    # Seed long-term memory with past incidents from the database
    asyncio.run(seed_memory_from_db())

    thread_id    = "session-1"  # groups all turns into one conversation for MemorySaver
    history      = []           # running conversation history passed between turns
    turn_count   = 0            # tracks how many questions have been asked this session

    # Read the business question from the user
    # Type 'quit' or 'exit' to stop, or press Ctrl+C at any time
    print("\nType 'quit' or 'exit' to stop the session.")
    while True:
        try:
            question = input("\nAsk a business question: ").strip()
        except KeyboardInterrupt:
            # Handles Ctrl+C gracefully instead of showing a traceback
            print("\n\nSession ended. Goodbye!")
            exit()

        # Allow user to cleanly exit by typing a keyword
        if question.lower() in ("quit", "exit", "q", "bye"):
            print("\nSession ended. Goodbye!")
            exit()

        if not question:
            print("Please type a question or 'quit' to exit.")
            continue  # loop back and ask again instead of exiting

        # Only ask for dates on the FIRST question in a session.
        # Follow-up questions ("Fix it", "What happened?") don't need dates —
        # the planner already has context from the thread history.
        if turn_count == 0:
            print("\nDates are optional — press Enter to let the AI infer them.")
            target_date     = input("Target date     (YYYY-MM-DD) or Enter to skip: ").strip()
            comparison_date = input("Comparison date (YYYY-MM-DD) or Enter to skip: ").strip()
        else:
            # Reuse the dates from the first question for all follow-ups
            target_date     = ""
            comparison_date = ""

        turn_count += 1  # increment after each successful question

        # Run the full pipeline — pass thread_id and history so memory works across turns
        response = ask(question, target_date, comparison_date, thread_id, history)
        history = response["history"]
