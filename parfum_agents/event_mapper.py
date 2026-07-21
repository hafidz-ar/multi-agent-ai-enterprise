import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parfum_agents.models import AgentState, WorkflowEvent

def run(state: AgentState) -> dict:
    start_time = time.time()
    
    semantic_frame = state.get("semantic_frame", {})
    goal = semantic_frame.get("goal", "UNKNOWN")
    entities = semantic_frame.get("entities", {})
    
    event = WorkflowEvent.UNKNOWN
    payload = {}
    
    if goal == "PURCHASE":
        event = WorkflowEvent.PURCHASE_INTENT
    elif goal == "RESTOCK":
        event = WorkflowEvent.RESTOCK_INTENT
    elif goal == "CONFIRM":
        event = WorkflowEvent.CONFIRM
    elif goal == "REJECT":
        event = WorkflowEvent.REJECT
    elif goal == "PAYMENT_METHOD":
        event = WorkflowEvent.PAYMENT_SELECTED
        payload["payment_method"] = entities.get("payment_method")
    elif goal in ["PRICE_CHECK", "STOCK_CHECK", "REPORT_CHECK", "GREETING", "UNKNOWN"]:
        event = WorkflowEvent.UNKNOWN
    
    # We pass the event so FSM can consume it
    latency = (time.time() - start_time) * 1000
    
    return {
        "workflow_event": event,
        "event_payload": payload,
        "_metrics": {
            "agent": "EventMapper",
            "latency_ms": latency,
            "decision": event.value,
            "status": "OK"
        }
    }
