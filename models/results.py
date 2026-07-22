from typing import TypedDict, List
from .events import ResultType, Severity

class ServiceResult(TypedDict):
    execution_id: str
    service_name: str
    result_type: ResultType
    severity: Severity
    user_message: str
    developer_message: str
    payload: dict

class AgentResult(TypedDict):
    """Standardized schema across all specialist agents for Enterprise Observability."""
    success: bool
    execution_id: str
    service_name: str
    data: dict
    errors: List[str]
    warnings: List[str]
    user_message: str
    latency_ms: float
