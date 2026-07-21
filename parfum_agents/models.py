from enum import Enum
from typing import TypedDict, List, Optional, Any, Annotated
import operator
import time

class ResultType(str, Enum):
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    CLARIFICATION = "CLARIFICATION"
    ERROR = "ERROR"

class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class ServiceResult(TypedDict):
    execution_id: str
    service_name: str
    result_type: ResultType
    severity: Severity
    user_message: str
    developer_message: str
    payload: dict

class InventoryStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"

class ProductionStatus(str, Enum):
    READY = "READY"
    INSUFFICIENT_INGREDIENTS = "INSUFFICIENT_INGREDIENTS"
    FORMULA_NOT_FOUND = "FORMULA_NOT_FOUND"
    NOT_REQUIRED = "NOT_REQUIRED"

class WorkflowStatus(str, Enum):
    START = "START"
    COLLECTING_INFORMATION = "COLLECTING_INFORMATION"
    PROCESSING = "PROCESSING"
    WAITING_USER_INPUT = "WAITING_USER_INPUT"
    EXECUTING_SERVICE = "EXECUTING_SERVICE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class WorkflowEvent(str, Enum):
    PURCHASE_INTENT = "PURCHASE_INTENT"
    RESTOCK_INTENT = "RESTOCK_INTENT"
    INFO_PROVIDED = "INFO_PROVIDED"
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    PAYMENT_SELECTED = "PAYMENT_SELECTED"
    CHANGE_VARIANT = "CHANGE_VARIANT"
    CHANGE_QTY = "CHANGE_QTY"
    ROLLBACK = "ROLLBACK"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"

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

    # NLU Semantic Frame & Event
    semantic_frame: dict
    workflow_event: str
    event_payload: dict

    # Execution
    planner_status: str
    execution_plan: list
    executed_plan: list

    # Contexts
    conversation_context: dict
    business_context: dict
    transaction_context: dict
    session_context: dict
    user_context: dict
    workflow_state: str

    # Multi-turn Conversation Memory
    # conversation_history: list of dicts with keys:
    #   role ("user" | "assistant"), content, timestamp, intent (optional)
    # Stored as a plain list (serializable); graph.py manages maxlen=20 via deque.
    conversation_history: list

    # Cross-turn entity memory: last known product, variant, period, etc.
    resolved_entities: dict

    # Slot currently awaiting user input (e.g. "size_ml", "quantity", "period")
    pending_slot: str

    # Services Outputs (Uniform payload structure)
    services_results: Annotated[list, operator.add]

    final_response: str
