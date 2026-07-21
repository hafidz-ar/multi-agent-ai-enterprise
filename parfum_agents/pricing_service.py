import os
import sys
import time
import uuid
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from parfum_agents.models import AgentState, ResultType, Severity

def run(state: AgentState) -> dict:
    start_time = time.time()
    exec_id = str(uuid.uuid4())
    
    # Pricing bisa memakai entity dari semantic frame atau conversation_context
    semantic_frame = state.get("semantic_frame", {})
    entities = semantic_frame.get("entities", {})
    context = state.get("conversation_context", {})
    resolved = state.get("resolved_entities", {})
    
    product_name = entities.get("product") or context.get("current_product") or resolved.get("last_product")
    requested_size = entities.get("size_ml") or context.get("current_variant") or resolved.get("last_variant")
    
    if not product_name or product_name == "UNKNOWN_PRODUCT":
        res = {
            "execution_id": exec_id,
            "service_name": "PricingService",
            "result_type": ResultType.ERROR,
            "severity": Severity.WARNING,
            "user_message": "Mohon maaf, saya belum menangkap produk apa yang ingin Anda cek harganya.",
            "developer_message": "Missing product_name in semantic_frame and context",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "PricingService",
                "latency_ms": (time.time() - start_time) * 1000,
                "decision": "PRODUCT_NOT_FOUND",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }
        
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        
        # Pertama, dapatkan perfume_id dari nama
        c.execute("SELECT perfume_id, name FROM perfume_catalog WHERE name LIKE ?", (f"%{product_name}%",))
        prod = c.fetchone()
        
        if not prod:
            conn.close()
            res = {
                "execution_id": exec_id,
                "service_name": "PricingService",
                "result_type": ResultType.ERROR,
                "severity": Severity.WARNING,
                "user_message": f"Mohon maaf, produk {product_name} tidak ditemukan dalam katalog kami.",
                "developer_message": f"Product '{product_name}' not found in perfume_catalog",
                "payload": {}
            }
            return {
                "services_results": [res],
                "_metrics": {
                    "agent": "PricingService",
                    "latency_ms": (time.time() - start_time) * 1000,
                    "decision": "NOT_IN_CATALOG",
                    "status": "ERROR",
                    "execution_id": exec_id
                }
            }
            
        perfume_id = prod[0]
        actual_name = prod[1]
        
        # Cari harga dengan JOIN antara inventory dan perfume_catalog
        if requested_size:
            c.execute("""
                SELECT i.size_ml, p.price_idr 
                FROM inventory i 
                JOIN perfume_catalog p ON i.perfume_id = p.perfume_id 
                WHERE i.perfume_id = ? AND i.size_ml = ?
            """, (perfume_id, requested_size))
        else:
            c.execute("""
                SELECT i.size_ml, p.price_idr 
                FROM inventory i 
                JOIN perfume_catalog p ON i.perfume_id = p.perfume_id 
                WHERE i.perfume_id = ?
            """, (perfume_id,))
        rows = c.fetchall()
        conn.close()
        
        prices = {}
        for r in rows:
            size = r[0]
            base_price = r[1]
            if size == 100:
                calc_price = base_price
            elif size == 50:
                calc_price = int(base_price * 0.65)
            elif size == 30:
                calc_price = int(base_price * 0.45)
            else:
                calc_price = int(base_price * (size / 100.0))
            prices[f"{size}ml"] = calc_price
            
        latency = (time.time() - start_time) * 1000
        
        res = {
            "execution_id": exec_id,
            "service_name": "PricingService",
            "result_type": ResultType.SUCCESS,
            "severity": Severity.INFO,
            "user_message": f"Harga untuk {actual_name} berhasil ditemukan.",
            "developer_message": "Prices fetched successfully via JOIN.",
            "payload": {
                "product": actual_name,
                "prices": prices
            }
        }
        
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "PricingService",
                "latency_ms": latency,
                "decision": "PRICE_FETCHED",
                "status": "OK",
                "execution_id": exec_id
            }
        }
        
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        res = {
            "execution_id": exec_id,
            "service_name": "PricingService",
            "result_type": ResultType.ERROR,
            "severity": Severity.ERROR,
            "user_message": "Mohon maaf, saat ini sistem gagal mengambil data harga. Silakan coba beberapa saat lagi.",
            "developer_message": f"SQLite Error: {str(e)}",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "PricingService",
                "latency_ms": latency,
                "decision": "Error",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }
