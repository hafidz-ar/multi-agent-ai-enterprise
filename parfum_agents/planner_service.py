import time
from parfum_agents.tools.utils import generate_transaction_id
from parfum_agents.models import AgentState

# Pemetaan deterministik: goal → service operation
# Ini adalah fallback jika NLU tidak menyertakan requested_operations
GOAL_TO_OPERATIONS = {
    "PURCHASE":     ["CHECK_STOCK"],
    "PRICE_CHECK":  ["CHECK_PRICE"],
    "STOCK_CHECK":  ["CHECK_STOCK"],
    "REPORT_CHECK": ["CHECK_REPORT"],
    "RESTOCK":      ["CHECK_STOCK", "PRODUCE_ITEM"],
}

# Priority order for slot clarification
_SLOT_PRIORITY = ["product", "size_ml", "quantity", "period"]


def run(state: AgentState) -> dict:
    start_time = time.time()

    semantic_frame = state.get("semantic_frame", {})
    goal           = semantic_frame.get("goal", "UNKNOWN")
    ambiguities    = semantic_frame.get("ambiguities", [])
    confidence     = semantic_frame.get("confidence", 1.0)
    req_ops        = semantic_frame.get("requested_operations", [])
    entities       = semantic_frame.get("entities", {})

    execution_plan = []
    planner_status = "READY"
    transaction    = state.get("transaction_context", {}).copy()

    # ── Determine pending_slot (next missing slot in priority order) ──────
    pending_slot = ""
    if ambiguities:
        for slot in _SLOT_PRIORITY:
            if slot in ambiguities:
                pending_slot = slot
                break

    # ── Execution routing ─────────────────────────────────────────────────
    if confidence < 0.6:
        planner_status = "CLARIFICATION_REQUIRED"
        execution_plan = ["CoordinatorAI"]
    elif goal in ["PURCHASE", "RESTOCK"] and ambiguities:
        planner_status = "CLARIFICATION_REQUIRED"
        execution_plan = ["CoordinatorAI"]
    elif goal in ["UNKNOWN", "GREETING", "CONFIRM", "REJECT", "GRATITUDE", "HELP", "RECOMMENDATION", "CATALOG_CHECK"]:
        execution_plan = ["CoordinatorAI"]
        pending_slot   = ""  # clear any stale pending slot on terminal intents
    else:
        # Use req_ops from NLU if available, else deterministic fallback
        if req_ops:
            execution_plan = req_ops.copy()
        else:
            execution_plan = GOAL_TO_OPERATIONS.get(goal, []).copy()

        if not execution_plan:
            execution_plan = ["CoordinatorAI"]
        elif "CoordinatorAI" not in execution_plan:
            execution_plan.append("CoordinatorAI")

    # ── Update structured conversation context ────────────────────────────
    context = state.get("conversation_context", {})
    if entities.get("product") and entities["product"] != "UNKNOWN_PRODUCT":
        context["current_product"] = entities["product"]
    if entities.get("size_ml"):
        context["current_variant"] = entities["size_ml"]
    if entities.get("quantity"):
        context["current_quantity"] = entities["quantity"]

    # Track whether user has been greeted (suppress future greetings)
    if goal == "GREETING":
        context["has_greeted"] = True

    if goal == "RESTOCK":
        context["active_workflow"] = "RESTOCK"
        transaction = _merge_restock_transaction(transaction, entities)
        if planner_status == "CLARIFICATION_REQUIRED":
            missing = set(ambiguities)
            if missing <= {"quantity"} and transaction.get("product") and transaction.get("size_ml"):
                transaction["status"] = "WAITING_QTY"
                transaction["locked_slots"] = ["product", "size_ml"]
    elif goal not in ["UNKNOWN", "GREETING"]:
        context.pop("active_workflow", None)

    context["conversation_goal"] = goal
    context["updated_at"]        = time.time()

    latency = (time.time() - start_time) * 1000

    return {
        "planner_status":     planner_status,
        "execution_plan":     execution_plan,
        "conversation_context": context,
        "transaction_context": transaction,
        "pending_slot":       pending_slot,
        "_metrics": {
            "agent":      "PlannerService",
            "latency_ms": latency,
            "decision":   planner_status,
            "status":     "OK"
        }
    }

def _merge_restock_transaction(transaction: dict, entities: dict) -> dict:
    if transaction.get("workflow") != "RESTOCK":
        transaction = {}

    transaction.setdefault("transaction_id", generate_transaction_id())
    transaction.setdefault("version", 1)
    transaction["workflow"] = "RESTOCK"
    transaction.setdefault("status", "DRAFT")
    transaction.setdefault("created_at", time.time())

    if entities.get("product"):
        transaction["product"] = entities["product"]
    if entities.get("size_ml"):
        transaction["size_ml"] = entities["size_ml"]
    if entities.get("quantity"):
        transaction["qty"] = entities["quantity"]

    transaction["updated_at"] = time.time()
    return transaction
