import os
import sys
import time
import json
import sqlite3
from langchain_groq import ChatGroq

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from parfum_agents.tools.utils import log_evaluation
from models import AgentState

def _load_prompt_template(filename: str) -> str:
    prompt_path = os.path.join(config.BASE_DIR, "prompts", filename)
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def intent_validator(request_json: dict) -> dict:
    """Validator deterministik untuk memvalidasi output JSON LLM"""
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    
    product_name = request_json.get("product", "")
    if product_name:
        c.execute("SELECT perfume_id, name FROM perfume_catalog WHERE name LIKE ?", (f"%{product_name}%",))
        result = c.fetchone()
        
        if result:
            request_json["perfume_id"] = result[0]
            request_json["product_valid"] = True
            request_json["product"] = result[1]
        else:
            request_json["product_valid"] = False
            request_json["error"] = "PRODUCT_NOT_FOUND"
    
    conn.close()
    
    qty = request_json.get("qty", 1)
    if not isinstance(qty, int) or qty <= 0:
        request_json["qty"] = 1
        
    size_str = str(request_json.get("size", "")).lower().replace("ml", "").strip()
    if size_str:
        try:
            request_json["size_ml"] = int(size_str)
        except ValueError:
            request_json["size_ml"] = None
    else:
        request_json["size_ml"] = None
        
    return request_json

def run(state: AgentState) -> dict:
    start_time = time.time()
    input_text = state["input"]
    
    try:
        llm = ChatGroq(
            model=config.LLM_MODEL, 
            api_key=config.GROQ_API_KEY,
            temperature=0.1
        ).bind(response_format={"type": "json_object"})
        
        template = _load_prompt_template("sales.txt") or "Kamu adalah Asisten Penjualan Senior di Parfum Enterprise."
        system_prompt = f"""{template}
Tugasmu hanya satu: baca kalimat pengguna dan ekstrak entitas produk yang ingin ia beli.
Jika user tidak ingin membeli (misalnya tanya FAQ atau analitik), isi intent dengan "OTHER".

Input user: "{input_text}"

Hasilkan JSON dengan struktur berikut persis:
{{
  "intent": "BUY" atau "OTHER",
  "product": "nama produk parfum (string)",
  "size": "ukuran misalnya 50ml, 100ml (string) atau kosongkan",
  "qty": jumlah botol (integer)
}}

Berikan HANYA JSON yang valid, tanpa tambahan teks apapun."""

        response = llm.invoke(system_prompt)
        parsed = json.loads(response.content)
        
        validated_request = intent_validator(parsed)
        
        latency = (time.time() - start_time) * 1000
        decision = "Parse Intent" if validated_request.get("intent") == "BUY" else "OTHER"
        status = "NOT_FOUND" if not validated_request.get("product_valid", True) else "OK"
        
        validated_request["_metrics"] = {
            "agent": "SalesAI",
            "latency_ms": latency,
            "decision": decision,
            "status": status
        }
        
        return validated_request
        
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return {
            "intent": "ERROR",
            "error": str(e),
            "_metrics": {
                "agent": "SalesAI",
                "latency_ms": latency,
                "decision": "Error",
                "status": "ERROR"
            }
        }
