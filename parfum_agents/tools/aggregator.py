import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import AgentResult, Action

class AgentResultAggregator:
    """
    Utility helper that merges individual AgentResult objects into an Action-indexed dictionary.
    Called directly inside CoordinatorAI node (NOT as a separate LangGraph node).
    """

    @staticmethod
    def merge_results(services_results: list) -> dict[Action, dict]:
        aggregated = {}
        for res in services_results or []:
            if isinstance(res, AgentResult):
                action = res.action
                aggregated[action] = res.data
                aggregated[action]["user_message"] = res.user_message
                aggregated[action]["success"] = res.success
            elif isinstance(res, dict):
                action_str = res.get("action") or res.get("service_name")
                if action_str:
                    try:
                        action = Action(action_str)
                    except ValueError:
                        action = action_str
                    data = res.get("data") or res.get("payload", {})
                    aggregated[action] = dict(data)
                    aggregated[action]["user_message"] = res.get("user_message", "")
                    aggregated[action]["success"] = res.get("result_type") == "SUCCESS" or res.get("success", True)
        return aggregated
