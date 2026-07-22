import sys
import os
import concurrent.futures

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import AgentState, AgentResult, Action, Stage, ExecutionPlan
from parfum_agents.core.agent_registry import AgentRegistry
from parfum_agents.services.pricing_service import PricingAgent
from parfum_agents.services.inventory_service import InventoryAgent
from parfum_agents.services.order_service import OrderAgent

def get_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(Action.CHECK_PRICE, PricingAgent())
    registry.register(Action.CHECK_STOCK, InventoryAgent())
    registry.register(Action.CREATE_ORDER, OrderAgent())
    return registry

class ExecutionEngine:
    """
    Execution Engine responsible for:
    - Stage-based action dispatching via AgentRegistry
    - Parallel execution of independent stages
    - Error isolation & result aggregation
    """

    def __init__(self, registry: AgentRegistry = None):
        self.registry = registry or get_default_registry()

    def execute_action(self, action: Action, state: AgentState) -> dict:
        handler = self.registry.resolve(action)
        result = handler.execute(state)
        return result.to_dict()

    def execute_stage(self, stage: Stage, state: AgentState) -> list[dict]:
        results = []
        if stage.parallel and len(stage.actions) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(stage.actions)) as executor:
                future_to_action = {
                    executor.submit(self.execute_action, act, state): act 
                    for act in stage.actions if self.registry.has_action(act)
                }
                for future in concurrent.futures.as_completed(future_to_action):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        act = future_to_action[future]
                        results.append({
                            "action": act.value if hasattr(act, "value") else str(act),
                            "success": False,
                            "user_message": f"Execution error: {str(e)}",
                            "payload": {}
                        })
        else:
            for act in stage.actions:
                if self.registry.has_action(act):
                    results.append(self.execute_action(act, state))
        return results

    def execute_plan(self, plan: ExecutionPlan, state: AgentState) -> list[dict]:
        all_results = []
        for stage in plan.stages:
            stage_results = self.execute_stage(stage, state)
            all_results.extend(stage_results)
        return all_results
