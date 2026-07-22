import time
import os
import sys
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

class MemoryService:
    """
    3-Tier Memory Architecture:
    1. Session Memory: Active workflow, pending slot, current product, transaction context.
       - Cleared on reset / command / completed transaction.
    2. Preference Memory: User profile, favorite brands, notes, size preferences.
       - Preserved across resets.
    3. Knowledge Cache: In-memory lookup cache for frequent queries (catalog, prices, ingredients).
    """
    _KNOWLEDGE_CACHE = {
        "catalog": [],
        "catalog_timestamp": 0,
        "ttl_seconds": 300  # 5 minutes cache TTL
    }

    @classmethod
    def get_catalog_cached(cls) -> list:
        now = time.time()
        if (now - cls._KNOWLEDGE_CACHE["catalog_timestamp"] < cls._KNOWLEDGE_CACHE["ttl_seconds"]) and cls._KNOWLEDGE_CACHE["catalog"]:
            return cls._KNOWLEDGE_CACHE["catalog"]
            
        try:
            conn = sqlite3.connect(config.DB_PATH)
            c = conn.cursor()
            c.execute("SELECT name FROM perfume_catalog")
            names = [r[0] for r in c.fetchall()]
            conn.close()
            cls._KNOWLEDGE_CACHE["catalog"] = names
            cls._KNOWLEDGE_CACHE["catalog_timestamp"] = now
            return names
        except Exception:
            return cls._KNOWLEDGE_CACHE.get("catalog", [])

    @classmethod
    def update_user_preferences(cls, user_preferences: dict, entities: dict) -> dict:
        """Extract and persist long-term user preferences from semantic entities."""
        prefs = dict(user_preferences or {})
        
        product = entities.get("product")
        if product and product != "UNKNOWN_PRODUCT":
            # Extract brand from product (e.g. "Tom Ford" from "Tom Ford Itaque Intense")
            parts = product.split()
            if len(parts) >= 2:
                brand = " ".join(parts[:2]) if parts[0] in ["Tom", "Le", "Jo"] else parts[0]
                prefs["favorite_brand"] = brand
                
        size_ml = entities.get("size_ml")
        if size_ml:
            prefs["favorite_size_ml"] = size_ml
            
        return prefs

    @classmethod
    def reset_session_memory(cls, session_memory: dict) -> dict:
        """Clear active session/working memory while preserving container structure."""
        return {
            "conv": {},
            "tx": {},
            "wf": "START",
            "resolved": {},
            "pending_slot": "",
            "history": []
        }
