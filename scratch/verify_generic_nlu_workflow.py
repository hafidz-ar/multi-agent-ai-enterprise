import os
import sys
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.graph import run_workflow

def safe_print(text):
    """Safely print text replacing emojis if Windows CP1252 stdout fails."""
    try:
        print(text)
    except UnicodeEncodeError:
        clean_text = text.encode('ascii', errors='replace').decode('ascii')
        print(clean_text)

def test_full_4step_purchase_flow():
    session_id = f"test-session-{uuid.uuid4().hex[:6]}"
    safe_print(f"=== TEST 1: Full 4-Step Purchase Flow (Session: {session_id}) ===")

    # Step 1
    safe_print("\n--- STEP 1: 'Saya ingin beli YSL Possimus' ---")
    res1 = run_workflow("Saya ingin beli YSL Possimus", session_id=session_id)
    safe_print(res1)

    # Step 2
    safe_print("\n--- STEP 2: '50ml 50pcs' (Simultaneous Extraction) ---")
    res2 = run_workflow("50ml 50pcs", session_id=session_id)
    safe_print(res2)

    # Step 3
    safe_print("\n--- STEP 3: 'lanjut' (Confirm to Payment) ---")
    res3 = run_workflow("lanjut", session_id=session_id)
    safe_print(res3)

    # Step 4
    safe_print("\n--- STEP 4: 'tunai' (Execute Order & Produce Receipt) ---")
    res4 = run_workflow("tunai", session_id=session_id)
    safe_print(res4)

    safe_print("\nSUCCESS: 4-Step Conversation Flow Executed Completely!")

def test_direct_single_turn_purchase():
    session_id = f"test-session-direct-{uuid.uuid4().hex[:6]}"
    safe_print(f"\n=== TEST 2: Single-Turn Direct Purchase Flow (Session: {session_id}) ===")

    safe_print("\n--- Input: 'Beli YSL Possimus 50ml 5 botol tunai' ---")
    res = run_workflow("Beli YSL Possimus 50ml 5 botol tunai", session_id=session_id)
    safe_print(res)
    safe_print("\nSUCCESS: Single-Turn Direct Purchase Executed Completely!")

if __name__ == "__main__":
    test_full_4step_purchase_flow()
    test_direct_single_turn_purchase()
