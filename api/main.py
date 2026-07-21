import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio
import traceback

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config
from workflow.graph import run_workflow

app = FastAPI(title="Parfum Enterprise API")

# Enable CORS for the dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Static files will be mounted at the bottom to avoid overriding /api routes

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    client_timestamp: str = ""
    dashboard_version: str = ""

SESSION_LOCKS = {}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if req.session_id not in SESSION_LOCKS:
        SESSION_LOCKS[req.session_id] = asyncio.Lock()
        
    async with SESSION_LOCKS[req.session_id]:
        try:
            # Menggunakan asyncio.sleep agar tidak memblokir threadpool utama FastAPI
            await asyncio.sleep(5)
            # Menjalankan workflow sinkron di thread terpisah (non-blocking)
            response = await asyncio.to_thread(run_workflow, req.message, session_id=req.session_id)
            return {"status": "success", "response": response}
        except Exception as e:
            traceback.print_exc()
            return {"status": "error", "response": f"Terjadi kesalahan pada sistem: {str(e)}"}

@app.get("/api/analytics/sales")
def get_sales_analytics():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT perfume_name, SUM(quantity_sold) as total_sold
            FROM sales_history 
            GROUP BY perfume_name 
            ORDER BY total_sold DESC 
            LIMIT 5
        """)
        data = c.fetchall()
        conn.close()
        return {"status": "success", "data": [{"name": row[0], "sold": row[1]} for row in data]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/revenue")
def get_revenue_analytics(months: int = 1):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        if months == 1:
            c.execute("""
                SELECT strftime('%Y-%m-%d', date) as period, SUM(total_revenue_idr) as revenue
                FROM sales_history 
                GROUP BY period 
                ORDER BY period DESC
                LIMIT 30
            """)
            data = c.fetchall()
            data.reverse()
        else:
            c.execute("""
                SELECT strftime('%Y-%m', date) as month, SUM(total_revenue_idr) as revenue
                FROM sales_history 
                GROUP BY month 
                ORDER BY month DESC
                LIMIT ?
            """, (months,))
            data = c.fetchall()
            data.reverse()
        conn.close()
        return {"status": "success", "data": [{"month": row[0], "revenue": row[1]} for row in data]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory/status")
def get_inventory_status():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM inventory WHERE quantity_available > reorder_point")
        available = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM inventory WHERE quantity_available <= reorder_point AND quantity_available > 0")
        low_stock = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM inventory WHERE quantity_available = 0")
        out_of_stock = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM inventory")
        total_products = c.fetchone()[0]
        
        c.execute("SELECT SUM(total_revenue_idr) FROM sales_history")
        total_revenue = c.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "success",
            "data": {
                "total_products": total_products,
                "total_revenue": total_revenue,
                "available": available,
                "low_stock": low_stock,
                "out_of_stock": out_of_stock
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
def get_logs():
    try:
        logs = []
        if os.path.exists(config.LOG_PATH):
            with open(config.LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # Ambil 10 log terakhir
                for line in reversed(lines[-10:]):
                    logs.append(line.strip())
        return {"status": "success", "data": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory/list")
def get_inventory_list():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT i.perfume_id, i.perfume_name, i.size_ml, i.quantity_available, i.reorder_point, p.price_idr, i.status, i.warehouse_location, i.stock_id
            FROM inventory i
            JOIN perfume_catalog p ON i.perfume_id = p.perfume_id
            ORDER BY i.perfume_id ASC, i.size_ml ASC
        """)
        data = c.fetchall()
        conn.close()

        formatted_data = []
        for r in data:
            size = r[2]
            base_price = r[5]
            if size == 100:
                unit_price = base_price
            elif size == 50:
                unit_price = int(base_price * 0.65)
            elif size == 30:
                unit_price = int(base_price * 0.45)
            else:
                unit_price = int(base_price * (size / 100.0))
                
            formatted_data.append({
                "perfume_id": r[0],
                "perfume_name": r[1],
                "size_ml": r[2],
                "quantity_available": r[3],
                "reorder_point": r[4],
                "unit_price_idr": unit_price,
                "db_status": r[6],
                "warehouse_location": r[7],
                "stock_id": r[8]
            })

        return {
            "status": "success",
            "data": formatted_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ingredients/list")
def get_ingredients_list():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT ingredient_id, ingredient_name, category, unit, stock_available, reorder_point, cost_per_unit_idr, origin_country, status
            FROM ingredients
            ORDER BY ingredient_id ASC
        """)
        data = c.fetchall()
        conn.close()

        formatted_data = []
        for r in data:
            stock = r[4] or 0.0
            reorder = r[5] or 0.0
            status = r[8]
            if not status or status == "NULL":
                if stock <= 0:
                    status = "OUT_OF_STOCK"
                elif stock <= reorder:
                    status = "LOW_STOCK"
                else:
                    status = "AVAILABLE"

            formatted_data.append({
                "ingredient_id": r[0],
                "ingredient_name": r[1],
                "category": r[2] or "Bahan Baku",
                "unit": r[3] or "ml",
                "stock_available": stock,
                "reorder_point": reorder,
                "cost_per_unit_idr": r[6] or 0,
                "origin_country": r[7] or "Lokal",
                "db_status": status
            })

        return {
            "status": "success",
            "data": formatted_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sales/list")
def get_sales_list():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT transaction_id, date, perfume_name, quantity_sold, total_revenue_idr, region, channel
            FROM sales_history
            ORDER BY date DESC
            LIMIT 500
        """)
        data = c.fetchall()
        conn.close()
        return {
            "status": "success",
            "data": [{
                "transaction_id": r[0],
                "date": r[1],
                "perfume_name": r[2],
                "quantity": r[3],
                "total_revenue_idr": r[4],
                "customer_city": r[5],
                "sales_channel": r[6]
            } for r in data]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/procurement/orders")
def get_procurement_orders(page: int = 1, page_size: int = 20, status: str = "", supplier: str = "", sort: str = "created_at_desc"):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        
        where_clauses = []
        params = []
        if status:
            where_clauses.append("po.status = ?")
            params.append(status)
        if supplier:
            where_clauses.append("s.supplier_name LIKE ?")
            params.append(f"%{supplier}%")
            
        where_str = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        order_str = "ORDER BY po.created_at DESC" if sort == "created_at_desc" else "ORDER BY po.created_at ASC"

        count_sql = f"SELECT COUNT(*) FROM purchase_orders po JOIN supplier s ON po.supplier_id = s.supplier_id {where_str}"
        c.execute(count_sql, params)
        total = c.fetchone()[0]

        offset = (page - 1) * page_size
        sql = f"""
            SELECT po.id, po.po_number, s.supplier_name, po.status, po.created_at, po.expected_arrival, po.remarks
            FROM purchase_orders po
            JOIN supplier s ON po.supplier_id = s.supplier_id
            {where_str}
            {order_str}
            LIMIT ? OFFSET ?
        """
        c.execute(sql, params + [page_size, offset])
        rows = c.fetchall()

        orders = []
        for r in rows:
            po_id = r[0]
            c.execute("""
                SELECT poi.ingredient_id, i.ingredient_name, poi.order_qty, poi.estimated_cost, poi.unit
                FROM purchase_order_items poi
                LEFT JOIN ingredients i ON poi.ingredient_id = i.ingredient_id
                WHERE poi.purchase_order_id = ?
            """, (po_id,))
            items = c.fetchall()
            item_list = []
            total_cost = 0
            for item in items:
                cost = item[3] or 0
                total_cost += cost
                item_list.append({
                    "ingredient_id": item[0],
                    "ingredient_name": item[1] or item[0],
                    "order_qty": item[2],
                    "estimated_cost": cost,
                    "unit": item[4]
                })

            orders.append({
                "id": r[0],
                "po_number": r[1],
                "supplier_name": r[2],
                "status": r[3],
                "created_at": r[4],
                "expected_arrival": r[5],
                "remarks": r[6],
                "total_items": len(item_list),
                "estimated_cost": total_cost,
                "items": item_list
            })

        conn.close()
        return {"status": "success", "total": total, "page": page, "page_size": page_size, "data": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/procurement/orders/{po_id}/progress")
def progress_procurement_order(po_id: str):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("SELECT status FROM purchase_orders WHERE id = ? OR po_number = ?", (po_id, po_id))
        row = c.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
            
        current_status = row[0]
        new_status = current_status
        message = ""
        
        if current_status == 'PENDING':
            new_status = 'APPROVED'
            message = f"Purchase Order {po_id} berhasil di-approve."
        elif current_status == 'APPROVED':
            new_status = 'ORDERED'
            message = f"Purchase Order {po_id} telah dipesan ke supplier."
        elif current_status == 'ORDERED':
            new_status = 'RECEIVED'
            message = f"Purchase Order {po_id} telah diterima, stok bahan baku diperbarui."
            
            # Update Ingredient Stock
            c.execute("""
                SELECT ingredient_id, order_qty 
                FROM purchase_order_items 
                WHERE purchase_order_id = ? OR purchase_order_id = (SELECT id FROM purchase_orders WHERE po_number = ?)
            """, (po_id, po_id))
            items = c.fetchall()
            
            for item in items:
                ing_id = item[0]
                qty = item[1]
                c.execute("UPDATE ingredients SET stock_available = stock_available + ? WHERE ingredient_id = ?", (qty, ing_id))
                
                # Insert Ledger
                import uuid
                c.execute("""
                    INSERT INTO ingredient_transactions (
                        id, ingredient_id, movement_type, qty_before, qty_change, qty_after, 
                        reference_type, reference_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), ing_id, 'PURCHASE', 0, qty, 0, 'PROCUREMENT', po_id, now)) # Note: qty_before/after ideally calculated, but simplified here
        else:
            conn.close()
            return {"status": "info", "message": f"Purchase Order sudah mencapai status {current_status}", "new_status": current_status}
            
        c.execute("UPDATE purchase_orders SET status = ?, updated_at = ? WHERE id = ? OR po_number = ?", (new_status, now, po_id, po_id))
        
        # Check if we should trigger pending production
        # In a real system, there might be a queue. For now, the user can just restock again.
        
        conn.commit()
        conn.close()
        return {"status": "success", "message": message, "new_status": new_status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/production/orders")
def get_production_orders(page: int = 1, page_size: int = 20, status: str = "", product: str = "", date_from: str = "", date_to: str = ""):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()

        where_clauses = []
        params = []
        if status:
            where_clauses.append("p.status = ?")
            params.append(status)
        if product:
            where_clauses.append("cat.name LIKE ?")
            params.append(f"%{product}%")
        if date_from:
            where_clauses.append("DATE(p.created_at) >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("DATE(p.created_at) <= ?")
            params.append(date_to)

        where_str = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        count_sql = f"SELECT COUNT(*) FROM production_orders p LEFT JOIN perfume_catalog cat ON p.perfume_id = cat.perfume_id {where_str}"
        c.execute(count_sql, params)
        total = c.fetchone()[0]

        offset = (page - 1) * page_size
        sql = f"""
            SELECT p.id, p.production_no, p.perfume_id, cat.name, p.variant_id, p.qty_requested, p.qty_produced, p.status, p.created_at, p.completed_at
            FROM production_orders p
            LEFT JOIN perfume_catalog cat ON p.perfume_id = cat.perfume_id
            {where_str}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        """
        c.execute(sql, params + [page_size, offset])
        rows = c.fetchall()

        orders = []
        for r in rows:
            created_at = r[8]
            completed_at = r[9]
            duration_str = "-"
            if completed_at and created_at:
                try:
                    from datetime import datetime
                    fmt = "%Y-%m-%d %H:%M:%S"
                    t1 = datetime.strptime(created_at[:19], fmt)
                    t2 = datetime.strptime(completed_at[:19], fmt)
                    diff_sec = int((t2 - t1).total_seconds())
                    if diff_sec < 60:
                        duration_str = f"{diff_sec} detik"
                    elif diff_sec < 3600:
                        duration_str = f"{diff_sec // 60} menit"
                    elif diff_sec < 86400:
                        duration_str = f"{diff_sec // 3600} jam"
                    else:
                        duration_str = f"{diff_sec // 86400} hari"
                except Exception:
                    duration_str = "-"

            orders.append({
                "id": r[0],
                "production_no": r[1],
                "perfume_id": r[2],
                "perfume_name": r[3] or r[2],
                "variant_id": r[4],
                "qty_requested": r[5],
                "qty_produced": r[6],
                "status": r[7],
                "created_at": r[8],
                "completed_at": r[9],
                "duration": duration_str
            })

        conn.close()
        return {"status": "success", "total": total, "page": page, "page_size": page_size, "data": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/metrics")
def get_agents_metrics():
    try:
        metrics = {}
        if os.path.exists(config.LOG_PATH):
            with open(config.LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            import re
            agent_data = {}
            for line in lines[-150:]:
                agent_match = re.search(r'AGENT=(.*?)(?:\s*\||$)', line)
                latency_match = re.search(r'LATENCY_MS=(.*?)(?:\s*\||$)', line)
                status_match = re.search(r'STATUS=(.*?)(?:\s*\||$)', line)
                time_match = re.search(r'^\[(.*?)\]', line)

                if agent_match:
                    ag = agent_match[1].strip()
                    lat = float(latency_match[1].strip()) if latency_match else 0.0
                    st = status_match[1].strip() if status_match else "OK"
                    ts_str = time_match[1].strip() if time_match else ""

                    if ag not in agent_data:
                        agent_data[ag] = {"latencies": [], "statuses": [], "last_ts": ts_str}
                    agent_data[ag]["latencies"].append(lat)
                    agent_data[ag]["statuses"].append(st)
                    if ts_str:
                        agent_data[ag]["last_ts"] = ts_str

            now_ts = time.time()
            for ag, data in agent_data.items():
                lats = data["latencies"]
                stats = data["statuses"]
                avg_lat = round(sum(lats) / len(lats), 1) if lats else 0.0
                errors = sum(1 for s in stats if 'ERROR' in s or 'FAIL' in s)
                err_rate = round((errors / len(stats)) * 100, 1) if stats else 0.0

                ago_sec = None
                if data["last_ts"]:
                    try:
                        from datetime import datetime
                        t_fmt = "%Y-%m-%d %H:%M:%S"
                        parsed_t = datetime.strptime(data["last_ts"][:19], t_fmt)
                        ago_sec = int(now_ts - parsed_t.timestamp())
                    except Exception:
                        ago_sec = None

                metrics[ag] = {
                    "avg_latency_ms": avg_lat,
                    "total_calls": len(lats),
                    "last_call_ago_seconds": ago_sec,
                    "error_rate": err_rate
                }

        return {"status": "success", "data": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount Dashboard Static Files at the root
# MUST be placed after all /api routes to prevent overriding them
dashboard_path = BASE_DIR / "dashboard"
app.mount("/", StaticFiles(directory=str(dashboard_path), html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
