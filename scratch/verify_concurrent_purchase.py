import os
import sys
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.graph import run_workflow

def test_concurrent_purchase_flow():
    session_id = f"test-session-{uuid.uuid4().hex[:6]}"
    print(f"=== Starting Test Multi-turn Purchase Flow (Session: {session_id}) ===")

    # Turn 1: Specify product
    print("\n--- Turn 1: 'saya ingin beli ysl possimus' ---")
    resp1 = run_workflow("saya ingin beli ysl possimus", session_id=session_id)
    print(resp1)

    # Turn 2: Specify size_ml
    print("\n--- Turn 2: '50 ml' ---")
    resp2 = run_workflow("50 ml", session_id=session_id)
    print(resp2)

    # Turn 3: Specify quantity (Triggers MULTI_AGENT_PARALLEL Pricing + Inventory)
    print("\n--- Turn 3: '50' ---")
    try:
        resp3 = run_workflow("50", session_id=session_id)
        print(resp3)
        print("\nSUCCESS: Parallel graph execution completed without error!")
    except Exception as e:
        print(f"\nFAILED with Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_concurrent_purchase_flow()
