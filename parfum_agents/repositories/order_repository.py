import sqlite3
import datetime
import config

class OrderRepository:
    """Repository isolating Order Transaction and Sales History persistence queries."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH

    def insert_sales_history_atomic(
        self,
        conn: sqlite3.Connection,
        tx_id: str,
        perfume_id: str,
        perfume_name: str,
        category: str,
        size_ml: int,
        qty: int,
        unit_price: int,
        total_price: int
    ):
        """Atomic write operation to record sales transaction."""
        today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = conn.cursor()
        c.execute("""
            INSERT INTO sales_history (
                transaction_id, date, perfume_id, perfume_name, category, 
                size_ml, quantity_sold, unit_price_idr, total_revenue_idr, 
                channel, region, customer_segment, campaign_id, return_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_id, today, perfume_id, perfume_name, category, 
            size_ml, qty, unit_price, total_price, 
            "Chatbot", "Online", "Retail", "None", 0
        ))
