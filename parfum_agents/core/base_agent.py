from abc import ABC, abstractmethod
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import AgentState, AgentResult

class BaseSpecialistAgent(ABC):
    """Abstract Base Class interface for all Enterprise Specialist Agents."""

    @abstractmethod
    def execute(self, state: AgentState) -> AgentResult:
        """Execute agent business logic and return an immutable AgentResult."""
        pass
