import time
import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger("event_bus")

class EventBus:
    """
    In-Memory Pub/Sub Event Bus Architecture.
    Allows decoupled specialist agents to subscribe to system events
    and publish async/sync events across the enterprise system.
    """
    _subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
    _event_history: List[Dict[str, Any]] = []

    @classmethod
    def subscribe(cls, topic: str, handler: Callable[[Dict[str, Any]], None]):
        """Subscribe a handler function to a specific event topic."""
        if topic not in cls._subscribers:
            cls._subscribers[topic] = []
        if handler not in cls._subscribers[topic]:
            cls._subscribers[topic].append(handler)

    @classmethod
    def unsubscribe(cls, topic: str, handler: Callable[[Dict[str, Any]], None]):
        """Unsubscribe a handler function from a topic."""
        if topic in cls._subscribers and handler in cls._subscribers[topic]:
            cls._subscribers[topic].remove(handler)

    @classmethod
    def publish(cls, topic: str, payload: Dict[str, Any], trace_id: str = "N/A"):
        """Publish an event to a topic, notifying all registered subscribers."""
        event_record = {
            "topic": topic,
            "trace_id": trace_id,
            "timestamp": time.time(),
            "payload": payload
        }
        cls._event_history.append(event_record)
        # Keep history capped at 200 items
        if len(cls._event_history) > 200:
            cls._event_history = cls._event_history[-200:]

        subscribers = cls._subscribers.get(topic, [])
        for handler in subscribers:
            try:
                handler(event_record)
            except Exception as e:
                logger.error(f"[EventBus] Error handling event on topic '{topic}': {e}")

    @classmethod
    def get_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent event bus audit logs."""
        return cls._event_history[-limit:]

    @classmethod
    def clear(cls):
        """Clear all subscribers and history."""
        cls._subscribers.clear()
        cls._event_history.clear()
