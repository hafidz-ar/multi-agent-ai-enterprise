import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parfum_agents.planner_service import run

class TestPlannerService(unittest.TestCase):
    def test_planner_check_price(self):
        state = {
            "semantic_frame": {
                "goal": "CHECK_PRICE",
                "confidence": 0.9,
                "requested_operations": ["CHECK_PRICE"]
            },
            "conversation_context": {}
        }
        res = run(state)
        execution_plan = res.get("execution_plan", [])
        
        # User expects it to route to PricingService eventually,
        # but the planner puts "CHECK_PRICE" in the execution plan
        self.assertIn("CHECK_PRICE", execution_plan)
        
    def test_planner_purchase(self):
        # Without ambiguities, it should add CHECK_STOCK
        state = {
            "semantic_frame": {
                "goal": "PURCHASE",
                "confidence": 0.9,
                "ambiguities": [],
                "requested_operations": ["CHECK_STOCK"]
            },
            "conversation_context": {}
        }
        res = run(state)
        execution_plan = res.get("execution_plan", [])
        self.assertIn("CHECK_STOCK", execution_plan)

    def test_planner_restock_locks_known_slots_when_waiting_quantity(self):
        state = {
            "semantic_frame": {
                "goal": "RESTOCK",
                "confidence": 0.95,
                "ambiguities": ["quantity"],
                "entities": {
                    "product": "YSL Possimus",
                    "size_ml": 50,
                    "quantity": None
                },
                "requested_operations": ["CHECK_STOCK", "PRODUCE_ITEM", "PROCURE_ITEM"]
            },
            "conversation_context": {},
            "transaction_context": {}
        }
        res = run(state)
        tx = res.get("transaction_context", {})

        self.assertEqual(res.get("planner_status"), "CLARIFICATION_REQUIRED")
        self.assertEqual(tx.get("workflow"), "RESTOCK")
        self.assertEqual(tx.get("status"), "WAITING_QTY")
        self.assertEqual(tx.get("product"), "YSL Possimus")
        self.assertEqual(tx.get("size_ml"), 50)
        self.assertEqual(tx.get("locked_slots"), ["product", "size_ml"])

if __name__ == '__main__':
    unittest.main()
