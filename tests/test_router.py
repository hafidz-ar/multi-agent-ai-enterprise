import unittest
import os
import sys
from langgraph.graph import END

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workflow.graph import route_execution

class TestRouter(unittest.TestCase):
    def test_router_pricing(self):
        state = {
            "execution_plan": ["CHECK_PRICE", "CoordinatorAI"]
        }
        # Based on SERVICE_REGISTRY, CHECK_PRICE should route to "pricing"
        next_node = route_execution(state)
        self.assertEqual(next_node, "pricing")

    def test_router_reporting(self):
        state = {
            "execution_plan": ["CHECK_REPORT", "CoordinatorAI"]
        }
        next_node = route_execution(state)
        self.assertEqual(next_node, "reporting")
        
    def test_router_end(self):
        state = {
            "execution_plan": []
        }
        next_node = route_execution(state)
        self.assertEqual(next_node, END)

if __name__ == '__main__':
    unittest.main()
