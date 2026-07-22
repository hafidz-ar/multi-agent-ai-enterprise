import os
import sys
import time
import uuid
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, ProductionStatus, ResultType, Severity

def run(state: AgentState) -> dict:
    start_time = time.time()
    exec_id = str(uuid.uuid4())
    
    business_context = state.get("business_context", {})
    perfume_id = business_context.get("perfume_id") 
    
    if not perfume_id:
        p_name = (
            business_context.get("product_name") 
            or state.get("transaction_context", {}).get("product") 
            or state.get("semantic_frame", {}).get("entities", {}).get("product")
        )
        if p_name:
            conn = sqlite3.connect(config.DB_PATH)
            c = conn.cursor()
            c.execute("SELECT perfume_id FROM perfume_catalog WHERE name LIKE ?", (f"%{p_name}%",))
            r = c.fetchone()
            conn.close()
            if r:
                perfume_id = r[0]
                business_context["perfume_id"] = perfume_id

    if not perfume_id:
        res = {
            "execution_id": exec_id,
            "service_name": "ProductionService",
            "result_type": ResultType.ERROR,
            "severity": Severity.WARNING,
            "user_message": "Mohon maaf, sistem tidak dapat memproses produksi karena ID parfum tidak diketahui.",
            "developer_message": "Missing perfume_id in business_context",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "ProductionService",
                "latency_ms": (time.time() - start_time) * 1000,
                "decision": "NO_PERFUME_ID",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }

    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT ingredient_id, ingredient_name, quantity_per_100ml FROM formula WHERE perfume_id = ?", (perfume_id,))
        formulas = c.fetchall()
        
        if not formulas:
            conn.close()
            res = {
                "execution_id": exec_id,
                "service_name": "ProductionService",
                "result_type": ResultType.ERROR,
                "severity": Severity.WARNING,
                "user_message": "Mohon maaf, formula untuk parfum ini tidak ditemukan.",
                "developer_message": f"FORMULA_NOT_FOUND for perfume_id {perfume_id}",
                "payload": {}
            }
            return {
                "services_results": [res],
                "_metrics": {
                    "agent": "ProductionService",
                    "latency_ms": (time.time() - start_time) * 1000,
                    "decision": "FORMULA_NOT_FOUND",
                    "status": "ERROR",
                    "execution_id": exec_id
                }
            }
            
        c.execute("SELECT ingredient_id, stock_available FROM ingredients")
        ingredients_stock = {row[0]: row[1] for row in c.fetchall()}
        
        size_ml = (
            business_context.get("size_ml") 
            or state.get("transaction_context", {}).get("size_ml") 
            or state.get("semantic_frame", {}).get("entities", {}).get("size_ml") 
            or 50
        )
        requested_qty = (
            business_context.get("requested_qty") 
            or state.get("transaction_context", {}).get("qty") 
            or state.get("semantic_frame", {}).get("entities", {}).get("quantity") 
            or 100
        )
        
        c.execute("SELECT quantity_available, reorder_point FROM inventory WHERE perfume_id = ? AND size_ml = ?", (perfume_id, size_ml))
        inv_row = c.fetchone()
        if inv_row:
            current_stock, reorder_point = inv_row
        else:
            current_stock, reorder_point = 0, 10
            
        requested_qty = max(1, requested_qty)
        qty_to_produce = max(requested_qty, max(0, reorder_point - current_stock))
        
        multiplier = (size_ml / 100.0) * qty_to_produce
        
        missing_ingredients = []
        production_items = []
        
        for f in formulas:
            ing_id, ing_name, qty_per_100ml = f
            dibutuhkan = qty_per_100ml * multiplier
            tersedia = ingredients_stock.get(ing_id, 0)
            
            production_items.append({
                "ingredient_id": ing_id,
                "required": dibutuhkan
            })
            
            if round(tersedia, 2) < round(dibutuhkan, 2):
                missing_ingredients.append({
                    "ingredient_id": ing_id,
                    "ingredient_name": ing_name,
                    "required":   round(dibutuhkan, 2),
                    "available":  round(tersedia, 2),
                    "shortage":   round(dibutuhkan - tersedia, 2)
                })

                
        if missing_ingredients:
            status = ProductionStatus.INSUFFICIENT_INGREDIENTS
            decision_log = "INSUFFICIENT_INGREDIENTS"
            conn.close()
        else:
            status = ProductionStatus.READY
            decision_log = "PRODUCTION_EXECUTED"
            
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            po_id = str(uuid.uuid4())
            po_no = f"PRD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            c.execute("""
                INSERT INTO production_orders (
                    id, production_no, perfume_id, variant_id, qty_requested, 
                    qty_produced, status, formula_version, request_source, 
                    created_by, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (po_id, po_no, perfume_id, str(size_ml), qty_to_produce, 
                  qty_to_produce, 'COMPLETED', 'v1', 'AUTO', 'AI Agent', now, now))
                  
            for item in production_items:
                item_id = str(uuid.uuid4())
                c.execute("""
                    INSERT INTO production_order_items (
                        id, production_order_id, ingredient_id, required_qty, used_qty, unit
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (item_id, po_id, item["ingredient_id"], item["required"], item["required"], 'ml'))
                
                c.execute("""
                    UPDATE ingredients SET stock_available = stock_available - ? WHERE ingredient_id = ?
                """, (item["required"], item["ingredient_id"]))
                
                qty_before = ingredients_stock.get(item["ingredient_id"], 0)
                qty_after = qty_before - item["required"]
                c.execute("""
                    INSERT INTO ingredient_transactions (
                        id, ingredient_id, movement_type, qty_before, qty_change, qty_after, 
                        reference_type, reference_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), item["ingredient_id"], 'CONSUMPTION', qty_before, -item["required"], qty_after, 'PRODUCTION', po_id, now))
                ingredients_stock[item["ingredient_id"]] = qty_after
                
            c.execute("""
                UPDATE inventory SET quantity_available = quantity_available + ? WHERE perfume_id = ? AND size_ml = ?
            """, (qty_to_produce, perfume_id, size_ml))
            
            c.execute("""
                INSERT INTO inventory_transactions (
                    id, product_id, size_ml, movement_type, qty_before, qty_change, qty_after,
                    reference_type, reference_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), perfume_id, size_ml, 'PRODUCTION', current_stock, qty_to_produce, current_stock + qty_to_produce, 'PRODUCTION', po_id, now))
            
            conn.commit()
            conn.close()
            
        latency = (time.time() - start_time) * 1000
        
        user_message = f"Produksi berhasil dilakukan untuk {qty_to_produce} pcs {business_context.get('product_name')} {size_ml}ml." if status == ProductionStatus.READY else f"Produksi tidak dapat dilakukan karena kekurangan {len(missing_ingredients)} bahan baku."
        
        res = {
            "execution_id": exec_id,
            "service_name": "ProductionService",
            "result_type": ResultType.SUCCESS if status == ProductionStatus.READY else ResultType.WARNING,
            "severity": Severity.INFO if status == ProductionStatus.READY else Severity.WARNING,
            "user_message": user_message,
            "developer_message": f"Production status: {status}",
            "payload": {
                "status": status,
                "missing_ingredients": missing_ingredients,
                "produced_qty": qty_to_produce if status == ProductionStatus.READY else 0
            }
        }

        tx_context = state.get("transaction_context", {})
        if tx_context.get("workflow") == "RESTOCK":
            tx_context = {**tx_context, "updated_at": time.time()}
            if status == ProductionStatus.INSUFFICIENT_INGREDIENTS:
                tx_context["status"] = "WAITING_PROCUREMENT_CONFIRMATION"
                tx_context["pending_procurement"] = missing_ingredients
                tx_context["production_status"] = status
            else:
                tx_context["status"] = "COMPLETED"
                tx_context.pop("pending_procurement", None)
                tx_context["production_status"] = status
        
        return {
            "services_results": [res],
            "business_context": {
                "production_status": status,
                "missing_ingredients": missing_ingredients
            },
            "transaction_context": tx_context,
            "workflow_state": "WAITING_USER_INPUT" if tx_context.get("status") == "WAITING_PROCUREMENT_CONFIRMATION" else state.get("workflow_state"),
            "_metrics": {
                "agent": "ProductionService",
                "latency_ms": latency,
                "decision": decision_log,
                "status": "OK",
                "execution_id": exec_id
            }
        }

    except Exception as e:
        if 'conn' in locals():
            try: conn.rollback()
            except: pass
        if 'conn' in locals():
            try: conn.close()
            except: pass
            
        latency = (time.time() - start_time) * 1000
        res = {
            "execution_id": exec_id,
            "service_name": "ProductionService",
            "result_type": ResultType.ERROR,
            "severity": Severity.ERROR,
            "user_message": "Mohon maaf, saat ini sistem gagal mengeksekusi data produksi.",
            "developer_message": f"SQLite Error: {str(e)}",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "ProductionService",
                "latency_ms": latency,
                "decision": "Error",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }
