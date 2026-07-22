import os
import sys
import time
import uuid
import json
from datetime import datetime
from typing import TypedDict, List, Dict
from langgraph.graph import StateGraph, END

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import AgentState
from parfum_agents.core import conversation_manager, workflow_manager, coordinator_ai
from parfum_agents.memory import memory_service
from parfum_agents.nlu import nlu_service
from parfum_agents.planning import event_mapper, planner_service
from parfum_agents.services import (
    inventory_service,
    production_service,
    procurement_service,
    pricing_service,
    reporting_service,
    order_service
)

from parfum_agents.tools.utils import log_evaluation

def _log_metrics(state: AgentState, metrics: dict):
    req_id = state.get("request_id", "UNKNOWN")
    agent = metrics.get("agent", "Unknown")
    latency = metrics.get("latency_ms", 0)
    decision = metrics.get("decision", "")
    status = metrics.get("status", "OK")
    exec_id = metrics.get("execution_id", "N/A")
    trace_id = state.get("trace_context", {}).get("trace_id", "N/A")
    
    planner_status = state.get("planner_status", "-")
    plan = state.get("execution_plan", [])
    executed = state.get("executed_plan", [])
    
    status_str = "SUCCESS" if status == "OK" else "ERROR"
    output_str = f"Trace: {trace_id[:8]} | Dec: {decision} | Plan: {plan} | Executed: {executed} | Planner: {planner_status}"
    log_evaluation(agent, f"Req: {req_id[:8]}", output_str, latency / 1000, status_str, exec_id=exec_id)

def _advance_plan(state: AgentState, service_name: str, res: dict):
    plan = state.get("execution_plan", [])
    executed = state.get("executed_plan", [])

    # Merge business_context — new values overwrite old keys
    existing_ctx = state.get("business_context", {})
    new_ctx = res.pop("business_context", {})
    res["business_context"] = {**existing_ctx, **new_ctx}

    if plan:
        next_item = plan[0]
        if isinstance(next_item, list):
            # Parallel stage: remove operation if present
            # We map node name back to op
            op_map = {
                "PricingService": "CHECK_PRICE",
                "InventoryService": "CHECK_STOCK",
                "ReportingService": "CHECK_REPORT",
                "OrderService": "CREATE_ORDER"
            }
            op = op_map.get(service_name)
            if op in next_item:
                next_item.remove(op)
            if not next_item:
                plan = plan[1:]
        else:
            plan = plan[1:]

    res["execution_plan"] = plan
    res["executed_plan"] = executed + [service_name]
    return res

# --- Nodes ---

def conversation_manager_node(state: AgentState):
    user_input = state.get("input", "")
    cmd_res = conversation_manager.handle_system_command(user_input, state)
    if cmd_res:
        if "_metrics" in cmd_res:
            _log_metrics(state, cmd_res.pop("_metrics"))
        return cmd_res
    return {"system_command_triggered": False}

def nlu_node(state: AgentState):
    if state.get("system_command_triggered"):
        return {}
    res = nlu_service.run(state)
    sf = res.get("semantic_frame", {})
    
    # Update Preference Memory in background
    user_prefs = state.get("user_preferences", {})
    updated_prefs = memory_service.MemoryService.update_user_preferences(user_prefs, sf.get("entities", {}))
    res["user_preferences"] = updated_prefs
    
    if "_metrics" in sf:
        _log_metrics(state, sf.pop("_metrics"))
    return res

def event_mapper_node(state: AgentState):
    if state.get("system_command_triggered"):
        return {}
    res = event_mapper.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return res

def planner_node(state: AgentState):
    if state.get("system_command_triggered"):
        return {}
    res = planner_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return res

def workflow_manager_node(state: AgentState):
    if state.get("system_command_triggered"):
        return {}
    res = workflow_manager.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return res

def inventory_node(state: AgentState):
    res = inventory_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "InventoryService", res)

def production_node(state: AgentState):
    res = production_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "ProductionService", res)

def procurement_node(state: AgentState):
    res = procurement_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "ProcurementService", res)

def pricing_node(state: AgentState):
    res = pricing_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "PricingService", res)
    
def reporting_node(state: AgentState):
    res = reporting_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "ReportingService", res)

def order_node(state: AgentState):
    res = order_service.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "OrderService", res)

def coordinator_node(state: AgentState):
    if state.get("system_command_triggered"):
        return {"execution_plan": []}
    res = coordinator_ai.run(state)
    if "_metrics" in res:
        _log_metrics(state, res.pop("_metrics"))
    return _advance_plan(state, "CoordinatorAI", {"final_response": res.get("final_response", "")})

# --- Service Registry ---
SERVICE_REGISTRY = {
    "CHECK_PRICE": "pricing",
    "CHECK_STOCK": "inventory",
    "PRODUCE_ITEM": "production",
    "PROCURE_ITEM": "procurement",
    "CHECK_REPORT": "reporting",
    "CREATE_ORDER": "order",
    "CoordinatorAI": "coordinator"
}

def route_front_door(state: AgentState):
    if state.get("system_command_triggered"):
        return END
    return "nlu"

def route_execution(state: AgentState):
    if state.get("system_command_triggered"):
        return END

    plan = state.get("execution_plan", [])
    if not plan:
        return END
    
    next_item = plan[0]
    if isinstance(next_item, list):
        # Parallel stage in LangGraph! Return list of node names to run concurrently
        nodes = [SERVICE_REGISTRY.get(op, "coordinator") for op in next_item if op in SERVICE_REGISTRY]
        return nodes if nodes else "coordinator"
    
    return SERVICE_REGISTRY.get(next_item, "coordinator")

# --- Build Graph ---

def build_workflow():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("conversation_manager", conversation_manager_node)
    workflow.add_node("nlu", nlu_node)
    workflow.add_node("event_mapper", event_mapper_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("workflow_manager", workflow_manager_node)
    
    workflow.add_node("inventory", inventory_node)
    workflow.add_node("production", production_node)
    workflow.add_node("procurement", procurement_node)
    workflow.add_node("pricing", pricing_node)
    workflow.add_node("reporting", reporting_node)
    workflow.add_node("order", order_node)
    workflow.add_node("coordinator", coordinator_node)
    
    workflow.set_entry_point("conversation_manager")
    workflow.add_conditional_edges("conversation_manager", route_front_door, {"nlu": "nlu", END: END})
    
    workflow.add_edge("nlu", "event_mapper")
    workflow.add_edge("event_mapper", "planner")
    workflow.add_edge("planner", "workflow_manager")
    
    # Dynamic Routing hub from workflow_manager
    nodes = list(set(SERVICE_REGISTRY.values()))
    route_map = {n: n for n in nodes}
    route_map[END] = END
    
    workflow.add_conditional_edges("workflow_manager", route_execution, route_map)
    
    # All services loop back to the dynamic router to execute the NEXT step in the plan
    for n in ["inventory", "production", "procurement", "pricing", "reporting", "order"]:
        workflow.add_conditional_edges(n, route_execution, route_map)
        
    workflow.add_edge("coordinator", END)
    
    return workflow.compile()

# Global memory for session & preferences
GLOBAL_CONTEXT_MEMORY = {}
_HISTORY_MAXLEN = 20

def _trim_history(history: list, maxlen: int = _HISTORY_MAXLEN) -> list:
    return history[-maxlen:] if len(history) > maxlen else history

_COMPILED_WORKFLOW = None

def run_workflow(user_input: str, session_id: str = "default_session", trace_id: str = None) -> str:
    global _COMPILED_WORKFLOW
    if _COMPILED_WORKFLOW is None:
        _COMPILED_WORKFLOW = build_workflow()
    app = _COMPILED_WORKFLOW
    
    req_id = str(uuid.uuid4())
    trace_id = trace_id or str(uuid.uuid4())

    # ── Retrieve session ────────────────────────────────────────────────────
    old_ctx = GLOBAL_CONTEXT_MEMORY.get(session_id, {})

    # Context Expiration (10 mins)
    last_updated = old_ctx.get("updated_at", 0)
    if time.time() - last_updated > 600:
        old_ctx = {}

    # Handle system reset / terminal transactions
    tx_ctx = old_ctx.get("tx", {})
    conv_ctx = old_ctx.get("conv", {})
    
    if user_input.strip().lower() in ["reset", "/reset"]:
        # Reset session memory but keep preferences
        old_ctx = memory_service.MemoryService.reset_session_memory(old_ctx)
        tx_ctx = {}
        conv_ctx = {}
    elif tx_ctx.get("status") in ["COMPLETED", "CANCELLED", "FAILED"]:
        tx_ctx = {}
        conv_ctx.pop("active_workflow", None)
        conv_ctx.pop("conversation_goal", None)
        old_ctx["tx"] = tx_ctx
        old_ctx["conv"] = conv_ctx
        old_ctx["resolved"] = {}
        old_ctx["pending_slot"] = ""

    conv_history = _trim_history(old_ctx.get("history", []))

    # ── Build initial state ─────────────────────────────────────────────────
    initial_state = {
        "input":                    user_input,
        "request_id":               req_id,
        "trace_context":            {"trace_id": trace_id, "session_id": session_id, "workflow_id": tx_ctx.get("transaction_id", "N/A")},
        "system_command_triggered": False,
        "system_command":           "",
        "semantic_frame":           {},
        "workflow_event":           "UNKNOWN",
        "event_payload":            {},
        "execution_strategy":       "SINGLE_AGENT",
        "planner_status":           "",
        "execution_plan":           [],
        "executed_plan":            [],
        "conversation_context":     old_ctx.get("conv", {}),
        "business_context":         {},
        "transaction_context":      tx_ctx,
        "session_context":          old_ctx.get("ses", {}),
        "user_context":             old_ctx.get("usr", {}),
        "user_preferences":         old_ctx.get("user_preferences", {}),
        "workflow_state":           old_ctx.get("wf", "START"),
        "conversation_history":     conv_history,
        "resolved_entities":        old_ctx.get("resolved", {}),
        "pending_slot":             old_ctx.get("pending_slot", ""),
        "services_results":         [],
        "final_response":           ""
    }

    result = app.invoke(initial_state)

    # ── Append conversation turns to history (if not system command) ───────
    if not result.get("system_command_triggered"):
        intent = result.get("semantic_frame", {}).get("goal", "")
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        conv_history = _trim_history(result.get("conversation_history", conv_history))
        conv_history.append({
            "role":      "user",
            "content":   user_input,
            "timestamp": now_iso,
            "intent":    intent
        })
        bot_response = result.get("final_response", "")
        if bot_response:
            conv_history.append({
                "role":      "assistant",
                "content":   bot_response,
                "timestamp": now_iso
            })
        conv_history = _trim_history(conv_history)

    # ── Persist session context ─────────────────────────────────────────────
    GLOBAL_CONTEXT_MEMORY[session_id] = {
        "conv":             result.get("conversation_context", {}),
        "tx":               result.get("transaction_context", {}),
        "wf":               result.get("workflow_state", "START"),
        "ses":              result.get("session_context", {}),
        "usr":              result.get("user_context", {}),
        "user_preferences": result.get("user_preferences", {}),
        "resolved":         result.get("resolved_entities", {}),
        "pending_slot":     result.get("pending_slot", ""),
        "history":          conv_history,
        "updated_at":       time.time()
    }

    return f"--- System Coordinator ---\n{result['final_response']}"

if __name__ == "__main__":
    print("Testing System Command (reset)...")
    print(run_workflow("reset"))

    print("\nTesting System Command (help)...")
    print(run_workflow("help"))

    print("\nTesting Parallel Query (Beli YSL Est Aqua 50ml)...")
    print(run_workflow("Beli YSL Est Aqua 50ml"))
