import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from parfum_agents.tools.utils import generate_transaction_id
from models import AgentState
from parfum_agents.planning.planner_cache import PlannerCache

# Pemetaan deterministik: goal → service operation
GOAL_TO_OPERATIONS = {
    "PURCHASE":     [["CHECK_PRICE", "CHECK_STOCK"]], # Stage 1: Parallel Check
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
    event_payload  = state.get("event_payload", {})
    strategy       = event_payload.get("strategy", "SINGLE_AGENT")

    execution_plan = []
    planner_status = "READY"
    transaction    = state.get("transaction_context", {}).copy()
    cache_hit      = False

    # ── Determine pending_slot (next missing slot in priority order) ──────
    pending_slot = ""
    if ambiguities:
        for slot in _SLOT_PRIORITY:
            if slot in ambiguities:
                pending_slot = slot
                break

    # ── Check Planner Cache ────────────────────────────────────────────────
    cached_plan = PlannerCache.get(goal, strategy, req_ops, ambiguities)
    if cached_plan and confidence >= 0.6 and not (goal in ["PURCHASE", "RESTOCK"] and ambiguities):
        execution_plan = cached_plan
        cache_hit = True
    else:
        # ── Execution routing ─────────────────────────────────────────────
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
            # Check strategy from EventMapper
            required_agents = event_payload.get("required_agents", [])
            if strategy == "MULTI_AGENT_PARALLEL" and len(required_agents) > 1:
                # Map required_agents to operations
                agent_op_map = {
                    "PricingService": "CHECK_PRICE",
                    "InventoryService": "CHECK_STOCK",
                    "ReportingService": "CHECK_REPORT",
                    "OrderService": "CREATE_ORDER"
                }
                parallel_ops = [agent_op_map[ag] for ag in required_agents if ag in agent_op_map]
                if parallel_ops:
                    execution_plan = [parallel_ops, "CoordinatorAI"]
                else:
                    execution_plan = GOAL_TO_OPERATIONS.get(goal, ["CoordinatorAI"]).copy()
            elif req_ops:
                execution_plan = req_ops.copy()
            else:
                execution_plan = GOAL_TO_OPERATIONS.get(goal, ["CoordinatorAI"]).copy()

            if not execution_plan:
                execution_plan = ["CoordinatorAI"]
            elif isinstance(execution_plan[-1], str) and execution_plan[-1] != "CoordinatorAI":
                execution_plan.append("CoordinatorAI")

        # Save to cache if ready and not clarification required
        if planner_status == "READY":
            PlannerCache.set(goal, strategy, req_ops, ambiguities, execution_plan)

    # ── Update structured conversation context ────────────────────────────
    context = state.get("conversation_context", {})
    if entities.get("product") and entities["product"] != "UNKNOWN_PRODUCT":
        context["current_product"] = entities["product"]
    if entities.get("size_ml"):
        context["current_variant"] = entities["size_ml"]
    if entities.get("quantity"):
        context["current_quantity"] = entities["quantity"]

    # Track whether user has been greeted
    if goal == "GREETING":
        context["has_greeted"] = True

    if goal == "RECOMMENDATION":
        context["active_recommendation"] = True
    elif goal in ["PURCHASE", "RESTOCK", "RESET", "CANCEL"]:
        context.pop("active_recommendation", None)

    if goal == "RESTOCK":
        context["active_workflow"] = "RESTOCK"
        transaction = _merge_restock_transaction(transaction, entities)
        if planner_status == "CLARIFICATION_REQUIRED":
            missing = set(ambiguities)
            if missing <= {"quantity"} and transaction.get("product") and transaction.get("size_ml"):
                transaction["status"] = "WAITING_QTY"
                transaction["locked_slots"] = ["product", "size_ml"]
    elif goal not in ["UNKNOWN", "GREETING", "CONFIRM", "RECOMMENDATION"]:
        context.pop("active_workflow", None)

    context["conversation_goal"] = goal
    context["updated_at"]        = time.time()

    latency = (time.time() - start_time) * 1000

    decision_str = f"{planner_status}:{strategy}{':CACHE_HIT' if cache_hit else ''}"

    return {
        "planner_status":     planner_status,
        "execution_plan":     execution_plan,
        "conversation_context": context,
        "transaction_context": transaction,
        "pending_slot":       pending_slot,
        "_metrics": {
            "agent":      "PlannerService",
            "latency_ms": latency,
            "decision":   decision_str,
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
