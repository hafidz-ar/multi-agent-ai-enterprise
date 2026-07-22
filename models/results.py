from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any
from .events import ResultType, Severity
from .actions import Action

class ServiceResult:
    """Legacy dict representation for backward compatibility."""
    pass

@dataclass(frozen=True)
class AgentResult:
    """Frozen immutable AgentResult dataclass for Enterprise Observability & Safety."""
    execution_id: str
    action: Action
    service_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    errors: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    user_message: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "action": self.action.value if hasattr(self.action, "value") else str(self.action),
            "service_name": self.service_name,
            "success": self.success,
            "data": dict(self.data),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "user_message": self.user_message,
            "latency_ms": self.latency_ms,
            "result_type": ResultType.SUCCESS if self.success else ResultType.ERROR,
            "severity": Severity.INFO if self.success else Severity.ERROR,
            "payload": dict(self.data)
        }
