import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import Action
from parfum_agents.core.base_agent import BaseSpecialistAgent

class AgentRegistry:
    """
    Object-Oriented Agent Registry with Dependency Injection support.
    Maps abstract Action Enums to concrete BaseSpecialistAgent handlers.
    """

    def __init__(self):
        self._registry: dict[Action, BaseSpecialistAgent] = {}

    def register(self, action: Action, handler: BaseSpecialistAgent):
        self._registry[action] = handler

    def resolve(self, action: Action) -> BaseSpecialistAgent:
        if action not in self._registry:
            raise KeyError(f"No specialist agent registered for action: {action}")
        return self._registry[action]

    def has_action(self, action: Action) -> bool:
        return action in self._registry
