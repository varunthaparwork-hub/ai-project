# The Memory Node runs BEFORE synthesis.
# It searches Qdrant for past incidents similar to what the agents found,
# then writes those results into state so synthesis can reference them.
#
# This enables questions like:
#   "Has this happened before?"
#   "What did we do last time?"
#   "Did discounts help previously?"

from graph.state import OpsState
from memory.long_term import search_similar


def memory_node(state: OpsState) -> OpsState:
    """
    Searches long-term memory for incidents similar to the current situation.
    Builds a search query from available agent analyses.
    Writes found incidents into state["past_incidents"].
    """
    print("\n[MEMORY] Searching long-term memory for similar past incidents...")

    # Build a rich search query from whatever agent analyses are available.
    # The more context we include, the better the semantic match.
    # Prepend user question to anchor semantic search to user intent.
    query_parts = []

    # Always include the full user question first, no truncation — highest priority for intent anchoring
    user_question = state.get("user_question", "")
    if user_question:
        query_parts.append(user_question)

    if state.get("sales_analysis"):
        query_parts.append(state["sales_analysis"][:1000])  # increased from 600 to 1000

    if state.get("inventory_analysis"):
        query_parts.append(state["inventory_analysis"][:1000])  # increased from 600 to 1000

    if state.get("marketing_analysis"):
        query_parts.append(state["marketing_analysis"][:1000])  # increased from 600 to 1000

    if state.get("support_analysis"):
        query_parts.append(state["support_analysis"][:1000])  # also include support for completeness

    # If no agent ran yet (e.g. pure memory question), use the raw user question
    if not query_parts:
        query_parts.append(state.get("user_question", ""))

    query = " ".join(query_parts)

    # Search Qdrant — only returns incidents above the similarity threshold (0.50)
    similar_incidents = search_similar(query, top_k=3)

    if similar_incidents:
        print(f"[MEMORY] Found {len(similar_incidents)} relevant past incident(s) (score >= 0.50).")
        for inc in similar_incidents:
            print(f"  - {inc['date']}: {inc['description'][:80]}... (score: {inc['similarity_score']})")
    else:
        print("[MEMORY] No sufficiently similar past incidents found (threshold: 0.50).")

    return {**state, "past_incidents": similar_incidents}