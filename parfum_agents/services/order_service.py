import os
import sys
import time
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import AgentState, ResultType, Severity

def run(state: AgentState) -> dict:
    start_time = time.time()
    exec_id = str(uuid.uuid4())
    
    tx_context = state.get("transaction_context", {})
    
    payment_method = tx_context.get("payment_method")
    if not payment_method:
        return _error_response(exec_id, start_time, tx_context, "Metode pembayaran belum dipilih.")
    
    if tx_context.get("status") != "PROCESSING_ORDER":
        return _error_response(exec_id, start_time, tx_context, "Status transaksi tidak valid untuk memproses pesanan.")
    
    import sqlite3
    import datetime
    import config
    
    remaining_stock = 0
    unit_price = 0
    total_price = 0
    invoice_no = f"INV-{datetime.datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4().hex[:4]).upper()}"
    p_name = tx_context.get("product", "Parfum")
    
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        
        product_name = tx_context.get("product")
        size_ml = tx_context.get("size_ml", 50)
        qty = tx_context.get("qty", 1)
        
        c.execute("SELECT perfume_id, name, category, price_idr FROM perfume_catalog WHERE name LIKE ?", (f"%{product_name}%",))
        prod = c.fetchone()
        
        if prod:
            perfume_id, p_name, category, price = prod
            
            if size_ml == 100:
                unit_price = price
            elif size_ml == 50:
                unit_price = int(price * 0.65)
            elif size_ml == 30:
                unit_price = int(price * 0.45)
            else:
                unit_price = int(price * (size_ml / 100.0))
                
            total_price = unit_price * qty
            
            tx_id = tx_context.get("transaction_id", invoice_no)
            today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO sales_history (
                    transaction_id, date, perfume_id, perfume_name, category, 
                    size_ml, quantity_sold, unit_price_idr, total_revenue_idr, 
                    channel, region, customer_segment, campaign_id, return_flag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx_id, today, perfume_id, p_name, category, 
                size_ml, qty, unit_price, total_price, 
                "Chatbot", "Online", "Retail", "None", 0
            ))
            
            c.execute("""
                SELECT quantity_available FROM inventory 
                WHERE perfume_id = ? AND size_ml = ?
            """, (perfume_id, size_ml))
            current_stock_row = c.fetchone()
            current_stock = current_stock_row[0] if current_stock_row else 0
            
            if current_stock < qty:
                conn.rollback()
                conn.close()
                return _error_response(exec_id, start_time, tx_context, 
                    f"Stok {p_name} {size_ml}ml tidak mencukupi (tersisa {current_stock} pcs, diminta {qty} pcs).")
            
            remaining_stock = current_stock - qty
            c.execute("""
                UPDATE inventory 
                SET quantity_available = quantity_available - ? 
                WHERE perfume_id = ? AND size_ml = ?
            """, (qty, perfume_id, size_ml))
            
            conn.commit()
            
    except Exception as e:
        if 'conn' in locals(): conn.rollback()
        return _error_response(exec_id, start_time, tx_context, f"Database Error: {str(e)}")
    finally:
        if 'conn' in locals(): conn.close()
    
    tx_context["status"] = "COMPLETED"
    tx_context["invoice_no"] = invoice_no
    tx_context["unit_price"] = unit_price
    tx_context["subtotal"] = total_price
    tx_context["remaining_stock"] = remaining_stock
    
    res = {
        "execution_id": exec_id,
        "service_name": "OrderService",
        "result_type": ResultType.SUCCESS,
        "severity": Severity.INFO,
        "user_message": f"Pesanan Anda untuk {p_name} ({tx_context.get('size_ml')}ml) sebanyak {tx_context.get('qty', 1)} botol telah berhasil dibuat dengan nomor transaksi {invoice_no}.",
        "developer_message": "Order created and payment recorded successfully.",
        "payload": {
            "transaction_id": invoice_no,
            "product": p_name,
            "size_ml": tx_context.get("size_ml"),
            "qty": tx_context.get("qty"),
            "unit_price": unit_price,
            "total_price": total_price,
            "payment_method": payment_method,
            "remaining_stock": remaining_stock,
            "status": "COMPLETED"
        }
    }
    
    metrics = {
        "agent": "OrderService",
        "latency_ms": (time.time() - start_time) * 1000,
        "decision": "ORDER_CREATED",
        "status": "OK",
        "execution_id": exec_id
    }
    
    return {
        "services_results": [res],
        "transaction_context": tx_context,
        "workflow_state": "COMPLETED",
        "_metrics": metrics
    }

def _error_response(exec_id, start_time, tx_context, msg):
    res = {
        "execution_id": exec_id,
        "service_name": "OrderService",
        "result_type": ResultType.ERROR,
        "severity": Severity.ERROR,
        "user_message": f"Mohon maaf, pesanan gagal diproses: {msg}",
        "developer_message": msg,
        "payload": {}
    }
    
    return {
        "services_results": [res],
        "transaction_context": tx_context,
        "workflow_state": "FAILED",
        "_metrics": {
            "agent": "OrderService",
            "latency_ms": (time.time() - start_time) * 1000,
            "decision": "ERROR",
            "status": "ERROR",
            "execution_id": exec_id
        }
    }
