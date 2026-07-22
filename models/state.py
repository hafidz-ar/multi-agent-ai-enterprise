from typing import TypedDict, List, Annotated
import operator

def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Merge dictionary states from parallel nodes (right overwrites left)."""
    if not left and not right:
        return {}
    if not left:
        return dict(right) if right else {}
    if not right:
        return dict(left) if left else {}
    res = dict(left)
    res.update(right)
    return res

def merge_lists(left: list | None, right: list | None) -> list:
    """Merge list states from parallel nodes while preserving order and deduplicating."""
    if not left and not right:
        return []
    if not left:
        return list(right) if right else []
    if not right:
        return list(left) if left else []
    combined = list(left)
    for item in right:
        if item not in combined:
            combined.append(item)
    return combined

def take_last(left, right):
    """Take the latest non-None value from parallel steps."""
    return right if right is not None else left

class TransactionContext(TypedDict, total=False):
    transaction_id: str
    product_id: str
    product: str
    variant_id: str
    size_ml: int
    qty: int
    unit_price: float
    subtotal: float
    payment_method: str
    customer_id: str
    created_at: float
    updated_at: float
    status: str
    version: int

class SessionContext(TypedDict, total=False):
    language: str
    timezone: str
    device: str
    channel: str
    session_started: float
    last_activity: float

class UserContext(TypedDict, total=False):
    name: str
    role: str
    preferences: dict

class AgentState(TypedDict):
    input: str
    request_id: str
    trace_context: dict

    # Front-door System Command
    system_command_triggered: bool
    system_command: str

    # NLU Semantic Frame & Event
    semantic_frame: dict
    workflow_event: str
    event_payload: Annotated[dict, merge_dicts]
    execution_strategy: str

    # Execution
    planner_status: Annotated[str, take_last]
    execution_plan: Annotated[list, take_last]
    executed_plan: Annotated[list, merge_lists]

    # Contexts & Memory
    conversation_context: Annotated[dict, merge_dicts]
    business_context: Annotated[dict, merge_dicts]
    transaction_context: Annotated[dict, merge_dicts]
    session_context: Annotated[dict, merge_dicts]
    user_context: Annotated[dict, merge_dicts]
    user_preferences: Annotated[dict, merge_dicts]
    workflow_state: Annotated[str, take_last]

    # Multi-turn Conversation Memory
    conversation_history: Annotated[list, operator.add]

    # Cross-turn entity memory
    resolved_entities: Annotated[dict, merge_dicts]

    # Slot currently awaiting user input
    pending_slot: Annotated[str, take_last]

    # Services Outputs
    services_results: Annotated[list, operator.add]

    final_response: Annotated[str, take_last]
