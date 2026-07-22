from dataclasses import dataclass, field
from typing import List
from models.actions import Action

@dataclass
class Stage:
    actions: List[Action]
    parallel: bool = False

@dataclass
class ExecutionPlan:
    stages: List[Stage] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.stages) == 0

    def peek_next_action(self) -> Action | None:
        if self.stages and self.stages[0].actions:
            return self.stages[0].actions[0]
        return None
