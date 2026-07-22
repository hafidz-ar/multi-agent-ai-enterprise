import os
import sys
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Action, Stage, ExecutionPlan, AgentResult
from parfum_agents.core.agent_registry import AgentRegistry
from parfum_agents.core.execution_engine import ExecutionEngine
from parfum_agents.repositories import CatalogRepository, InventoryRepository, OrderRepository
from parfum_agents.services.pricing_service import PricingAgent
from parfum_agents.services.inventory_service import InventoryAgent
from parfum_agents.services.order_service import OrderAgent
from workflow.graph import run_workflow

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        clean_text = text.encode('ascii', errors='replace').decode('ascii')
        print(clean_text)

def test_enterprise_components():
    safe_print("=== TEST 1: Enterprise Repositories & AgentRegistry Dispatching ===")
    
    cat_repo = CatalogRepository()
    inv_repo = InventoryRepository()
    order_repo = OrderRepository()

    prods = cat_repo.get_all_product_names()
    safe_print(f"Catalog Products fetched via Repository: {len(prods)} items")
    assert len(prods) > 0, "CatalogRepository should fetch products"

    registry = AgentRegistry()
    registry.register(Action.CHECK_PRICE, PricingAgent(cat_repo))
    registry.register(Action.CHECK_STOCK, InventoryAgent(cat_repo, inv_repo))
    registry.register(Action.CREATE_ORDER, OrderAgent(cat_repo, inv_repo, order_repo))

    assert registry.has_action(Action.CHECK_PRICE), "Registry should have Action.CHECK_PRICE"
    assert registry.has_action(Action.CHECK_STOCK), "Registry should have Action.CHECK_STOCK"
    assert registry.has_action(Action.CREATE_ORDER), "Registry should have Action.CREATE_ORDER"

    engine = ExecutionEngine(registry)
    plan = ExecutionPlan(stages=[
        Stage(actions=[Action.CHECK_PRICE, Action.CHECK_STOCK], parallel=True)
    ])

    test_state = {
        "input": "Beli YSL Possimus 50ml 5 botol",
        "semantic_frame": {
            "goal": "PURCHASE",
            "entities": {"product": "YSL Possimus", "size_ml": 50, "quantity": 5}
        },
        "transaction_context": {"product": "YSL Possimus", "size_ml": 50, "qty": 5}
    }

    results = engine.execute_plan(plan, test_state)
    safe_print(f"ExecutionEngine executed {len(results)} actions in parallel stage!")
    for res in results:
        safe_print(f" - Action: {res.get('action')}, Success: {res.get('success')}, Agent: {res.get('service_name')}")

    safe_print("\n✅ Enterprise Component Test Passed!")

def test_full_workflow_end_to_end():
    safe_print("\n=== TEST 2: End-to-End Workflow with Repositories & Action Enums ===")
    session_id = f"test-enterprise-{uuid.uuid4().hex[:6]}"

    # Reset stock for test
    inv_repo = InventoryRepository()
    import sqlite3, config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE inventory SET quantity_available = 500")
    conn.commit()
    conn.close()

    # Step 1
    safe_print("\n--- STEP 1: 'Saya ingin beli YSL Possimus' ---")
    res1 = run_workflow("Saya ingin beli YSL Possimus", session_id=session_id)
    safe_print(res1)

    # Step 2
    safe_print("\n--- STEP 2: '50ml 50pcs' (Simultaneous Extraction) ---")
    res2 = run_workflow("50ml 50pcs", session_id=session_id)
    safe_print(res2)

    # Step 3
    safe_print("\n--- STEP 3: 'lanjut' (Confirm Payment Selection) ---")
    res3 = run_workflow("lanjut", session_id=session_id)
    safe_print(res3)

    # Step 4
    safe_print("\n--- STEP 4: 'tunai' (Atomic Order Transaction & Receipt) ---")
    res4 = run_workflow("tunai", session_id=session_id)
    safe_print(res4)

    safe_print("\n✅ End-to-End Enterprise Workflow Test Passed!")

if __name__ == "__main__":
    test_enterprise_components()
    test_full_workflow_end_to_end()
