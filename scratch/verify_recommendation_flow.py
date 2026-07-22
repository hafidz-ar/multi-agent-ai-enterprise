import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

from workflow.graph import build_workflow

graph = build_workflow()

conversation_turns = [
    "aku butuh rekomendasi",
    "harga yang terjangkau",
    "boleh"
]

state = {
    "request_id": "test_rec_001",
    "input": "",
    "conversation_context": {},
    "transaction_context": {},
    "resolved_entities": {},
    "pending_slot": "",
    "conversation_history": [],
    "user_preferences": {}
}

print("=== VERIFYING RECOMMENDATION CONVERSATION FLOW ===")
for turn in conversation_turns:
    print(f"\n--- User: '{turn}' ---")
    state["input"] = turn
    
    output = graph.invoke(state)
    
    final_response = output.get("final_response", "")
    print(f"Assistant:\n{final_response}")
    
    state["conversation_context"] = output.get("conversation_context", {})
    state["transaction_context"] = output.get("transaction_context", {})
    state["resolved_entities"] = output.get("resolved_entities", {})
    state["pending_slot"] = output.get("pending_slot", "")
    
    history = list(state.get("conversation_history", []))
    history.append({"role": "user", "content": turn})
    history.append({"role": "assistant", "content": final_response})
    state["conversation_history"] = history

print("\n=== VERIFICATION FINISHED ===")
