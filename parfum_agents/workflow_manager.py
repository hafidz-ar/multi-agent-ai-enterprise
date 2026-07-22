import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from parfum_agents.models import AgentState, WorkflowStatus, WorkflowEvent
from parfum_agents.tools.utils import generate_transaction_id
from parfum_agents.event_bus import EventBus

TRANSITIONS = {
    # (Current Tx Status, Event) -> (Next Tx Status, Next Wf State, Exec Plan, Decision)
    ("DRAFT", WorkflowEvent.PURCHASE_INTENT): ("DRAFT", WorkflowStatus.EXECUTING_SERVICE, [["CHECK_PRICE", "CHECK_STOCK"], "CoordinatorAI"], "START_PURCHASE"),
    (None, WorkflowEvent.PURCHASE_INTENT): ("DRAFT", WorkflowStatus.EXECUTING_SERVICE, [["CHECK_PRICE", "CHECK_STOCK"], "CoordinatorAI"], "START_PURCHASE"),
    
    ("WAITING_CONFIRMATION", WorkflowEvent.CONFIRM): ("WAITING_PAYMENT", WorkflowStatus.WAITING_USER_INPUT, ["CoordinatorAI"], "PROCEED_TO_PAYMENT"),
    ("WAITING_CONFIRMATION", WorkflowEvent.REJECT): ("CANCELLED", WorkflowStatus.CANCELLED, ["CoordinatorAI"], "CANCEL_ORDER"),
    ("WAITING_CONFIRMATION", WorkflowEvent.CHANGE_QTY): ("DRAFT", WorkflowStatus.EXECUTING_SERVICE, [["CHECK_PRICE", "CHECK_STOCK"], "CoordinatorAI"], "REVALIDATE_STOCK_QTY"),
    ("WAITING_CONFIRMATION", WorkflowEvent.CHANGE_VARIANT): ("DRAFT", WorkflowStatus.EXECUTING_SERVICE, [["CHECK_PRICE", "CHECK_STOCK"], "CoordinatorAI"], "REVALIDATE_STOCK_VARIANT"),
    
    ("WAITING_PAYMENT", WorkflowEvent.PAYMENT_SELECTED): ("PROCESSING_ORDER", WorkflowStatus.EXECUTING_SERVICE, ["CREATE_ORDER", "CoordinatorAI"], "PROCESS_ORDER"),
    ("WAITING_PAYMENT", WorkflowEvent.REJECT): ("CANCELLED", WorkflowStatus.CANCELLED, ["CoordinatorAI"], "CANCEL_ORDER"),
    ("WAITING_PAYMENT", WorkflowEvent.CHANGE_QTY): ("DRAFT", WorkflowStatus.EXECUTING_SERVICE, [["CHECK_PRICE", "CHECK_STOCK"], "CoordinatorAI"], "REVALIDATE_STOCK_QTY"),
    ("WAITING_PAYMENT", WorkflowEvent.CHANGE_VARIANT): ("DRAFT", WorkflowStatus.EXECUTING_SERVICE, [["CHECK_PRICE", "CHECK_STOCK"], "CoordinatorAI"], "REVALIDATE_STOCK_VARIANT"),
}

RESTOCK_PLAN = ["CHECK_STOCK", "PRODUCE_ITEM", "CoordinatorAI"]
RESTOCK_PROCUREMENT_PLAN = ["PROCURE_ITEM", "CoordinatorAI"]

# Circuit Breaker & Retry State Tracker
_CIRCUIT_BREAKER_FAILURES = {}
_MAX_FAILURES_THRESHOLD = 3

def run(state: AgentState) -> dict:
    start_time = time.time()
    
    wf_state = state.get("workflow_state", WorkflowStatus.START)
    event = state.get("workflow_event", WorkflowEvent.UNKNOWN)
    transaction = state.get("transaction_context", {}).copy()
    exec_plan = state.get("execution_plan", [])
    trace_id = state.get("trace_context", {}).get("trace_id", "N/A")
    
    decision_log = "NO_CHANGE"
    tx_status = transaction.get("status")
    
    # 0. Clean up terminal transactions before processing new intents
    is_new_intent = event in [WorkflowEvent.PURCHASE_INTENT, WorkflowEvent.RESTOCK_INTENT]
    if (tx_status in ["COMPLETED", "CANCELLED", "FAILED"] or is_new_intent) and event != WorkflowEvent.TIMEOUT:
        transaction = {}
        tx_status = None
        state["transaction_context"] = transaction

    # 1. Rollback & Circuit Breaker Checking
    if event == WorkflowEvent.ROLLBACK or tx_status == "FAILED":
        decision_log = "TRIGGER_ROLLBACK"
        wf_state = WorkflowStatus.FAILED
        transaction["status"] = "FAILED"
        exec_plan = ["CoordinatorAI"]
        EventBus.publish("ROLLBACK_EVENT", {"tx_id": transaction.get("transaction_id")}, trace_id=trace_id)

    # 2. Timeout Checking
    last_updated = transaction.get("updated_at", 0)
    if tx_status not in [None, "COMPLETED", "CANCELLED", "FAILED"] and (start_time - last_updated > config.WORKFLOW_TIMEOUT):
        event = WorkflowEvent.TIMEOUT
        transaction["status"] = "CANCELLED"
        wf_state = WorkflowStatus.CANCELLED
        exec_plan = ["CoordinatorAI"]
        decision_log = "TIMEOUT_RESET"
    else:
        if transaction.get("workflow") == "RESTOCK" and tx_status == "WAITING_PROCUREMENT_CONFIRMATION" and event == WorkflowEvent.CONFIRM:
            transaction["status"] = "PROCUREMENT_APPROVED"
            transaction["updated_at"] = start_time
            wf_state = WorkflowStatus.EXECUTING_SERVICE
            exec_plan = RESTOCK_PROCUREMENT_PLAN.copy()
            decision_log = "RESTOCK_PROCUREMENT_APPROVED"
        elif transaction.get("workflow") == "RESTOCK" and tx_status == "WAITING_PROCUREMENT_CONFIRMATION" and event == WorkflowEvent.REJECT:
            transaction["status"] = "CANCELLED"
            transaction["updated_at"] = start_time
            wf_state = WorkflowStatus.CANCELLED
            exec_plan = ["CoordinatorAI"]
            decision_log = "RESTOCK_PROCUREMENT_REJECTED"
        elif event == WorkflowEvent.RESTOCK_INTENT:
            transaction = _handle_restock_event(state, transaction, start_time)
            if transaction.get("status") == "WAITING_QTY":
                wf_state = WorkflowStatus.COLLECTING_INFORMATION
                exec_plan = ["CoordinatorAI"]
                decision_log = "RESTOCK_WAITING_QTY"
            elif transaction.get("status") == "READY":
                wf_state = WorkflowStatus.EXECUTING_SERVICE
                exec_plan = RESTOCK_PLAN.copy()
                decision_log = "START_RESTOCK"
            else:
                wf_state = WorkflowStatus.COLLECTING_INFORMATION
                exec_plan = ["CoordinatorAI"]
                decision_log = "RESTOCK_COLLECTING_INFO"
        else:
        # 3. State Transition Lookup
            transition = TRANSITIONS.get((tx_status, event))
            if transition:
                next_tx_status, next_wf_state, next_exec_plan, decision = transition
                
                planner_status = state.get("planner_status", "")
                if planner_status == "CLARIFICATION_REQUIRED":
                    # Abort the state transition and just ask for clarification
                    next_tx_status = tx_status
                    next_wf_state = wf_state
                    next_exec_plan = ["CoordinatorAI"]
                    decision = "CLARIFY_FIRST"
                else:
                    # Additional custom logic based on event
                    if event == WorkflowEvent.PURCHASE_INTENT and tx_status is None:
                        transaction["transaction_id"] = generate_transaction_id()
                        transaction["version"] = 1
                        
                    elif event in [WorkflowEvent.CHANGE_QTY, WorkflowEvent.CHANGE_VARIANT]:
                        transaction["version"] = transaction.get("version", 1) + 1
                        
                    elif event == WorkflowEvent.PAYMENT_SELECTED:
                        payment_method = state.get("event_payload", {}).get("payment_method")
                        if payment_method:
                            transaction["payment_method"] = payment_method
                        else:
                            # Invalid payment
                            next_tx_status = tx_status
                            next_wf_state = wf_state
                            next_exec_plan = ["CoordinatorAI"]
                            decision = "INVALID_PAYMENT"
                        
                transaction["status"] = next_tx_status
                wf_state = next_wf_state
                exec_plan = next_exec_plan
                decision_log = decision
                transaction["updated_at"] = start_time

    # Publish EventBus Event
    EventBus.publish("WORKFLOW_STATE_CHANGED", {
        "wf_state": str(wf_state),
        "tx_status": str(transaction.get("status")),
        "decision": decision_log
    }, trace_id=trace_id)

    latency = (time.time() - start_time) * 1000
    
    return {
        "workflow_state": wf_state,
        "transaction_context": transaction,
        "execution_plan": exec_plan,
        "_metrics": {
            "agent": "WorkflowManagerFSM",
            "latency_ms": latency,
            "decision": decision_log,
            "status": "OK"
        }
    }

def _handle_restock_event(state: AgentState, transaction: dict, now: float) -> dict:
    semantic_frame = state.get("semantic_frame", {})
    entities = semantic_frame.get("entities", {})
    ambiguities = set(semantic_frame.get("ambiguities", []))

    if transaction.get("workflow") != "RESTOCK":
        transaction = {}

    transaction.setdefault("transaction_id", generate_transaction_id())
    transaction.setdefault("version", 1)
    transaction.setdefault("created_at", now)
    transaction["workflow"] = "RESTOCK"

    if entities.get("product"):
        transaction["product"] = entities["product"]
    if entities.get("size_ml"):
        transaction["size_ml"] = entities["size_ml"]
    if entities.get("quantity"):
        transaction["qty"] = entities["quantity"]

    missing = {
        slot for slot in ["product", "size_ml", "quantity"]
        if slot in ambiguities or (slot == "quantity" and not transaction.get("qty")) or (slot != "quantity" and not transaction.get(slot))
    }

    if missing == {"quantity"} and transaction.get("product") and transaction.get("size_ml"):
        transaction["status"] = "WAITING_QTY"
        transaction["locked_slots"] = ["product", "size_ml"]
    elif missing:
        transaction["status"] = "COLLECTING_INFORMATION"
        transaction["locked_slots"] = [
            slot for slot in ["product", "size_ml"]
            if transaction.get(slot)
        ]
    else:
        transaction["status"] = "READY"
        transaction["locked_slots"] = ["product", "size_ml", "qty"]

    transaction["updated_at"] = now
    return transaction
