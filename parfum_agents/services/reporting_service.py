import os
import sys
import time
import uuid
import sqlite3
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from models import AgentState, ResultType, Severity

def _get_data_date_range(conn):
    c = conn.cursor()
    c.execute("SELECT MIN(date), MAX(date) FROM sales_history")
    row = c.fetchone()
    if not row or not row[0]:
        return None, None
    min_date = datetime.strptime(row[0][:10], "%Y-%m-%d")
    max_date = datetime.strptime(row[1][:10], "%Y-%m-%d")
    return min_date, max_date

def _resolve_period(period: str, conn=None):
    today = datetime.now()

    if not period or period in ("all", None):
        return "Semua Waktu", None, ()

    p = period.lower()

    ref_year = today.year
    ref_date = today
    if conn:
        min_d, max_d = _get_data_date_range(conn)
        if max_d and max_d.year != today.year:
            ref_date = max_d
            ref_year = max_d.year

    if "hari ini" in p or "today" in p:
        date_str = ref_date.strftime("%Y-%m-%d")
        return f"Hari Ini ({date_str})", "DATE(date) = ?", (date_str,)

    if "kemarin" in p or "yesterday" in p:
        date_str = (ref_date - timedelta(days=1)).strftime("%Y-%m-%d")
        return f"Kemarin ({date_str})", "DATE(date) = ?", (date_str,)

    if "minggu ini" in p or "week" in p or "pekan ini" in p:
        start = (ref_date - timedelta(days=ref_date.weekday())).strftime("%Y-%m-%d")
        end = ref_date.strftime("%Y-%m-%d")
        return f"Minggu Ini ({start} s/d {end})", "DATE(date) BETWEEN ? AND ?", (start, end)

    if "bulan ini" in p or "month" in p:
        start = ref_date.replace(day=1).strftime("%Y-%m-%d")
        end = ref_date.strftime("%Y-%m-%d")
        return f"Bulan Ini ({start} s/d {end})", "DATE(date) BETWEEN ? AND ?", (start, end)

    if "tahun ini" in p or "year" in p:
        start = ref_date.replace(month=1, day=1).strftime("%Y-%m-%d")
        end = ref_date.strftime("%Y-%m-%d")
        return f"Tahun Ini ({ref_year})", "DATE(date) BETWEEN ? AND ?", (start, end)

    return period, None, ()

def run(state: AgentState) -> dict:
    start_time = time.time()
    exec_id = str(uuid.uuid4())

    semantic_frame = state.get("semantic_frame", {})
    entities       = semantic_frame.get("entities", {})
    period_raw     = entities.get("period", "all")

    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()

        start_date = entities.get("start_date")
        end_date   = entities.get("end_date")
        if start_date and end_date:
            period_label = entities.get("period", period_raw)
            date_clause  = "DATE(date) BETWEEN ? AND ?"
            date_params  = (start_date, end_date)
        else:
            period_label, date_clause, date_params = _resolve_period(period_raw, conn)

        if date_clause:
            c.execute(
                f"SELECT COUNT(*), COALESCE(SUM(quantity_sold), 0), COALESCE(SUM(total_revenue_idr), 0) "
                f"FROM sales_history WHERE {date_clause}",
                date_params
            )
        else:
            c.execute(
                "SELECT COUNT(*), COALESCE(SUM(quantity_sold), 0), COALESCE(SUM(total_revenue_idr), 0) "
                "FROM sales_history"
            )
        row = c.fetchone()
        total_transactions  = row[0] or 0
        total_qty_sold      = row[1] or 0
        total_sales_revenue = row[2] or 0

        if date_clause:
            c.execute(
                f"SELECT perfume_name, SUM(quantity_sold) as qty FROM sales_history "
                f"WHERE {date_clause} GROUP BY perfume_name ORDER BY qty DESC LIMIT 3",
                date_params
            )
        else:
            c.execute(
                "SELECT perfume_name, SUM(quantity_sold) as qty FROM sales_history "
                "GROUP BY perfume_name ORDER BY qty DESC LIMIT 3"
            )
        top_products = [{"name": r[0], "qty_sold": r[1]} for r in c.fetchall()]

        c.execute("""
            SELECT COALESCE(sum(i.quantity_available * p.price_idr), 0)
            FROM inventory i
            JOIN perfume_catalog p ON i.perfume_id = p.perfume_id
        """)
        total_inventory_value = c.fetchone()[0] or 0

        c.execute("SELECT COALESCE(sum(quantity_available), 0) FROM inventory")
        total_stock = c.fetchone()[0] or 0

        c.execute(
            "SELECT count(*) FROM inventory WHERE quantity_available <= reorder_point AND quantity_available > 0"
        )
        low_stock_items = c.fetchone()[0] or 0

        conn.close()

        payload = {
            "period": period_label,
            "sales": {
                "total_transactions": total_transactions,
                "total_qty_sold": total_qty_sold,
                "total_revenue_idr": total_sales_revenue,
                "top_products": top_products
            },
            "inventory_snapshot": {
                "total_inventory_value": total_inventory_value,
                "total_stock_items": total_stock,
                "low_stock_warnings": low_stock_items
            }
        }

        latency = (time.time() - start_time) * 1000
        res = {
            "execution_id": exec_id,
            "service_name": "ReportingService",
            "result_type": ResultType.SUCCESS,
            "severity": Severity.INFO,
            "user_message": f"Laporan periode '{period_label}' berhasil dihasilkan.",
            "developer_message": "SQL aggregations executed with period filter.",
            "payload": payload
        }

        return {
            "services_results": [res],
            "_metrics": {
                "agent": "ReportingService",
                "latency_ms": latency,
                "decision": "REPORT_GENERATED",
                "status": "OK",
                "execution_id": exec_id
            }
        }

    except Exception as e:
        latency = (time.time() - start_time) * 1000
        res = {
            "execution_id": exec_id,
            "service_name": "ReportingService",
            "result_type": ResultType.ERROR,
            "severity": Severity.ERROR,
            "user_message": "Maaf, saat ini laporan belum dapat ditampilkan karena terjadi kendala pada sistem.",
            "developer_message": f"SQLite Error: {str(e)}",
            "payload": {}
        }
        return {
            "services_results": [res],
            "_metrics": {
                "agent": "ReportingService",
                "latency_ms": latency,
                "decision": "Error",
                "status": "ERROR",
                "execution_id": exec_id
            }
        }
