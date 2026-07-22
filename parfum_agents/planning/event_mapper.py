import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import AgentState, WorkflowEvent

def run(state: AgentState) -> dict:
    start_time = time.time()
    
    semantic_frame = state.get("semantic_frame", {})
    goal = semantic_frame.get("goal", "UNKNOWN")
    entities = semantic_frame.get("entities", {})
    
    event = WorkflowEvent.UNKNOWN
    payload = {}
    strategy = "SINGLE_AGENT"
    priority = "NORMAL"
    required_agents = []
    
    if goal == "PURCHASE":
        event = WorkflowEvent.PURCHASE_INTENT
        strategy = "MULTI_AGENT_PARALLEL"
        required_agents = ["PricingService", "InventoryService"]
    elif goal == "RESTOCK":
        event = WorkflowEvent.RESTOCK_INTENT
        strategy = "SEQUENTIAL_PIPELINE"
        required_agents = ["InventoryService", "ProductionService"]
    elif goal == "CONFIRM":
        event = WorkflowEvent.CONFIRM
        strategy = "SINGLE_AGENT"
    elif goal == "REJECT":
        event = WorkflowEvent.REJECT
        strategy = "SINGLE_AGENT"
    elif goal == "PAYMENT_METHOD":
        event = WorkflowEvent.PAYMENT_SELECTED
        payload["payment_method"] = entities.get("payment_method")
        strategy = "SINGLE_AGENT"
        required_agents = ["OrderService"]
    elif goal == "PRICE_CHECK":
        event = WorkflowEvent.UNKNOWN
        strategy = "SINGLE_AGENT"
        required_agents = ["PricingService"]
    elif goal == "STOCK_CHECK":
        event = WorkflowEvent.UNKNOWN
        strategy = "SINGLE_AGENT"
        required_agents = ["InventoryService"]
    elif goal == "REPORT_CHECK":
        event = WorkflowEvent.UNKNOWN
        strategy = "SINGLE_AGENT"
        required_agents = ["ReportingService"]
    
    latency = (time.time() - start_time) * 1000
    
    event_payload = {
        "event_type": event.value,
        "priority": priority,
        "strategy": strategy,
        "required_agents": required_agents,
        "entities": entities,
        **payload
    }
    
    return {
        "workflow_event": event,
        "event_payload": event_payload,
        "execution_strategy": strategy,
        "_metrics": {
            "agent": "EventMapper",
            "latency_ms": latency,
            "decision": f"{event.value}:{strategy}",
            "status": "OK"
        }
    }
