from typing import TypedDict, List, Annotated
import operator

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
    event_payload: dict
    execution_strategy: str

    # Execution
    planner_status: str
    execution_plan: list
    executed_plan: list

    # Contexts & Memory
    conversation_context: dict
    business_context: dict
    transaction_context: dict
    session_context: dict
    user_context: dict
    user_preferences: dict
    workflow_state: str

    # Multi-turn Conversation Memory
    conversation_history: list

    # Cross-turn entity memory
    resolved_entities: dict

    # Slot currently awaiting user input
    pending_slot: str

    # Services Outputs
    services_results: Annotated[list, operator.add]

    final_response: str
