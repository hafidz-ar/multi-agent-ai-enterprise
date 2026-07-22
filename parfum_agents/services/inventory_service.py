import os
import sys
import time
import uuid
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, InventoryStatus, ResultType, Severity

def run(state: AgentState) -> dict:
    start_time = time.time()
    exec_id = str(uuid.uuid4())

    semantic_frame  = state.get("semantic_frame", {})
    entities        = semantic_frame.get("entities", {})
    context         = state.get("conversation_context", {})
    tx_context      = state.get("transaction_context", {})

    product_name    = entities.get("product") or tx_context.get("product") or context.get("current_product")
    size_ml         = entities.get("size_ml") or tx_context.get("size_ml") or context.get("current_variant")
    if size_ml and isinstance(size_ml, str):
        import re
        match = re.search(r'\d+', size_ml)
        size_ml = int(match.group()) if match else size_ml
        
    qty_requested   = entities.get("quantity") or tx_context.get("qty") or context.get("current_quantity") or 1

    if not product_name or product_name == "UNKNOWN_PRODUCT":
        res = {
            "execution_id": exec_id,
            "service_name": "InventoryService",
            "result_type": ResultType.ERROR,
            "severity": Severity.WARNING,
            "user_message": "Mohon maaf, saya belum menangkap produk apa yang ingin Anda cek stoknya.",
            "developer_message": "Missing product_name in semantic_frame and context",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "InventoryService",
                "latency_ms": (time.time() - start_time) * 1000,
                "decision": "PRODUCT_NOT_FOUND",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }

    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()

        c.execute("SELECT perfume_id, name FROM perfume_catalog WHERE name LIKE ?", (f"%{product_name}%",))
        prod = c.fetchone()

        if not prod:
            conn.close()
            res = {
                "execution_id": exec_id,
                "service_name": "InventoryService",
                "result_type": ResultType.ERROR,
                "severity": Severity.WARNING,
                "user_message": f"Mohon maaf, produk {product_name} tidak ditemukan dalam katalog kami.",
                "developer_message": f"Product '{product_name}' not found in perfume_catalog",
                "payload": {}
            }
            return {
                "services_results": [res],
                "_metrics": {
                    "agent": "InventoryService",
                    "latency_ms": (time.time() - start_time) * 1000,
                    "decision": "NOT_IN_CATALOG",
                    "status": "ERROR",
                    "execution_id": exec_id
                }
            }

        perfume_id  = prod[0]

        if size_ml:
            c.execute("SELECT size_ml, quantity_available, reorder_point FROM inventory WHERE perfume_id = ? AND size_ml = ?", (perfume_id, size_ml))
        else:
            c.execute("SELECT size_ml, quantity_available, reorder_point FROM inventory WHERE perfume_id = ?", (perfume_id,))
            
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            res = {
                "execution_id": exec_id,
                "service_name": "InventoryService",
                "result_type": ResultType.ERROR,
                "severity": Severity.WARNING,
                "user_message": f"Maaf, varian {product_name} ukuran {size_ml}ml tidak ditemukan dalam stok kami.",
                "developer_message": f"Variant size_ml={size_ml} not found for perfume_id={perfume_id}",
                "payload": {}
            }
            return {
                "services_results": [res],
                "_metrics": {
                    "agent": "InventoryService",
                    "latency_ms": (time.time() - start_time) * 1000,
                    "decision": "VARIANT_NOT_FOUND",
                    "status": "ERROR",
                    "execution_id": exec_id
                }
            }
            
        total_available = 0
        min_reorder_point = 999999
        stock_sizes = {}
        
        for r in rows:
            s_ml, q_avail, r_point = r
            stock_sizes[f"stock_{s_ml}ml"] = q_avail
            total_available += q_avail
            if r_point < min_reorder_point:
                min_reorder_point = r_point
                
        need_production = False
        status = InventoryStatus.AVAILABLE
        decision_log = "AVAILABLE"
        
        if total_available == 0:
            status = InventoryStatus.OUT_OF_STOCK
            need_production = True
            decision_log = "OUT_OF_STOCK"
        elif total_available <= min_reorder_point:
            status = InventoryStatus.LOW_STOCK
            need_production = True
            decision_log = "LOW_STOCK"
            
        latency = (time.time() - start_time) * 1000
            
        can_fulfill = total_available >= qty_requested
        variant_details = ", ".join([f"{k.replace('stock_', '')}: {v} pcs" for k, v in stock_sizes.items()])
            
        res = {
            "execution_id": exec_id,
            "service_name": "InventoryService",
            "result_type": ResultType.SUCCESS if can_fulfill else ResultType.WARNING,
            "severity": Severity.INFO if can_fulfill else Severity.WARNING,
            "user_message": f"Stok {product_name} {'tersedia' if can_fulfill else 'menipis/habis'} ({variant_details} - Total: {total_available} pcs).",
            "developer_message": f"Stock Check. Status: {status}. Needs production: {need_production}",
            "payload": {
                "status": status,
                "total_available": total_available,
                "can_fulfill": can_fulfill,
                "need_production": need_production,
                "stock_sizes": stock_sizes
            }
        }
        
        metrics = {
            "agent": "InventoryService",
            "latency_ms": latency,
            "decision": decision_log,
            "status": "OK",
            "execution_id": exec_id
        }
        
        wf_state = state.get("workflow_state")
        tx_context = state.get("transaction_context", {})
        
        if tx_context and tx_context.get("status") == "DRAFT" and tx_context.get("workflow") != "RESTOCK":
            if can_fulfill:
                tx_context["status"] = "WAITING_CONFIRMATION"
                tx_context["product"] = product_name
                tx_context["size_ml"] = size_ml
                tx_context["qty"] = qty_requested
                wf_state = "WAITING_USER_INPUT"
            else:
                tx_context["status"] = "CANCELLED"
                wf_state = "CANCELLED"
        
        return {
            "services_results": [res],
            "business_context": {
                "perfume_id": perfume_id,
                "product_name": product_name,
                "size_ml": size_ml,
                "requested_qty": qty_requested,
                "inventory_status": status,
                "need_production": need_production
            },
            "workflow_state": wf_state or state.get("workflow_state"),
            "transaction_context": tx_context,
            "_metrics": metrics
        }
        
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        res = {
            "execution_id": exec_id,
            "service_name": "InventoryService",
            "result_type": ResultType.ERROR,
            "severity": Severity.ERROR,
            "user_message": "Mohon maaf, saat ini sistem gagal mengambil data stok. Silakan coba beberapa saat lagi.",
            "developer_message": f"SQLite Error: {str(e)}",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "InventoryService",
                "latency_ms": latency,
                "decision": "Error",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }
