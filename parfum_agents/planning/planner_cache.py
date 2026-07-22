import time
import hashlib
import json
from typing import Dict, Any, List, Optional

class PlannerCache:
    """
    In-Memory Planner Execution Cache.
    Caches DAG execution plans for semantic frames & goals to avoid redundant planning overhead.
    """
    _cache: Dict[str, Dict[str, Any]] = {}
    _TTL_SECONDS: int = 600  # 10 minutes cache TTL

    @classmethod
    def _generate_cache_key(cls, goal: str, strategy: str, req_ops: List[Any], ambiguities: List[str]) -> str:
        raw_key = f"{goal}:{strategy}:{json.dumps(req_ops)}:{json.dumps(sorted(ambiguities))}"
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def get(cls, goal: str, strategy: str, req_ops: List[Any], ambiguities: List[str]) -> Optional[List[Any]]:
        """Retrieve cached execution plan if valid and not expired."""
        key = cls._generate_cache_key(goal, strategy, req_ops, ambiguities)
        entry = cls._cache.get(key)
        if not entry:
            return None
            
        if time.time() - entry["timestamp"] > cls._TTL_SECONDS:
            cls._cache.pop(key, None)
            return None
            
        return entry["execution_plan"].copy()

    @classmethod
    def set(cls, goal: str, strategy: str, req_ops: List[Any], ambiguities: List[str], plan: List[Any]):
        """Cache an execution plan."""
        key = cls._generate_cache_key(goal, strategy, req_ops, ambiguities)
        cls._cache[key] = {
            "execution_plan": plan.copy(),
            "timestamp": time.time()
        }

    @classmethod
    def clear(cls):
        """Clear the planner cache."""
        cls._cache.clear()
