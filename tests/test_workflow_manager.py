import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parfum_agents.workflow_manager import run
from parfum_agents.models import WorkflowEvent, WorkflowStatus


class TestWorkflowManager(unittest.TestCase):
    def test_restock_waits_for_quantity_without_losing_slots(self):
        state = {
            "workflow_event": WorkflowEvent.RESTOCK_INTENT,
            "workflow_state": WorkflowStatus.START,
            "planner_status": "CLARIFICATION_REQUIRED",
            "execution_plan": ["CoordinatorAI"],
            "semantic_frame": {
                "goal": "RESTOCK",
                "ambiguities": ["quantity"],
                "entities": {
                    "product": "YSL Possimus",
                    "size_ml": 50,
                    "quantity": None
                }
            },
            "transaction_context": {
                "workflow": "RESTOCK",
                "status": "WAITING_QTY",
                "product": "YSL Possimus",
                "size_ml": 50,
                "locked_slots": ["product", "size_ml"]
            }
        }

        res = run(state)
        tx = res.get("transaction_context", {})

        self.assertEqual(res.get("workflow_state"), WorkflowStatus.COLLECTING_INFORMATION)
        self.assertEqual(res.get("execution_plan"), ["CoordinatorAI"])
        self.assertEqual(tx.get("status"), "WAITING_QTY")
        self.assertEqual(tx.get("product"), "YSL Possimus")
        self.assertEqual(tx.get("size_ml"), 50)

    def test_restock_quantity_completes_slot_filling_and_runs_services(self):
        state = {
            "workflow_event": WorkflowEvent.RESTOCK_INTENT,
            "workflow_state": WorkflowStatus.COLLECTING_INFORMATION,
            "planner_status": "READY",
            "execution_plan": ["CHECK_STOCK", "PRODUCE_ITEM", "CoordinatorAI"],
            "semantic_frame": {
                "goal": "RESTOCK",
                "ambiguities": [],
                "entities": {
                    "product": "YSL Possimus",
                    "size_ml": 50,
                    "quantity": 50
                }
            },
            "transaction_context": {
                "workflow": "RESTOCK",
                "status": "WAITING_QTY",
                "product": "YSL Possimus",
                "size_ml": 50,
                "locked_slots": ["product", "size_ml"]
            }
        }

        res = run(state)
        tx = res.get("transaction_context", {})

        self.assertEqual(res.get("workflow_state"), WorkflowStatus.EXECUTING_SERVICE)
        self.assertEqual(res.get("execution_plan"), ["CHECK_STOCK", "PRODUCE_ITEM", "CoordinatorAI"])
        self.assertEqual(tx.get("status"), "READY")
        self.assertEqual(tx.get("qty"), 50)

    def test_restock_procurement_requires_confirmation(self):
        state = {
            "workflow_event": WorkflowEvent.CONFIRM,
            "workflow_state": WorkflowStatus.WAITING_USER_INPUT,
            "planner_status": "READY",
            "execution_plan": ["CoordinatorAI"],
            "semantic_frame": {
                "goal": "CONFIRM",
                "ambiguities": [],
                "entities": {}
            },
            "transaction_context": {
                "workflow": "RESTOCK",
                "status": "WAITING_PROCUREMENT_CONFIRMATION",
                "product": "YSL Possimus",
                "size_ml": 50,
                "qty": 50,
                "pending_procurement": [
                    {
                        "ingredient_id": "ING-001",
                        "ingredient_name": "Lemon Extract",
                        "shortage": 269
                    }
                ]
            }
        }

        res = run(state)
        tx = res.get("transaction_context", {})

        self.assertEqual(res.get("workflow_state"), WorkflowStatus.EXECUTING_SERVICE)
        self.assertEqual(res.get("execution_plan"), ["PROCURE_ITEM", "CoordinatorAI"])
        self.assertEqual(tx.get("status"), "PROCUREMENT_APPROVED")


if __name__ == "__main__":
    unittest.main()
