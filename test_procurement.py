import sys
import os

from workflow.graph import run_workflow

print("Testing RESTOCK flow...")
response = run_workflow("saya ingin restok ysl possimus 50ml 50botol", session_id="test_session")
print(f"Agent: {response}")

print("\n" + "="*50 + "\n")
response2 = run_workflow("lanjutkan", session_id="test_session")
print(f"Agent: {response2}")
