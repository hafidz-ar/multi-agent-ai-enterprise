import sqlite3
import config

class InventoryRepository:
    """Repository isolating Inventory persistence queries from business agents."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH

    def get_stock_by_perfume_id(self, perfume_id: str) -> list[tuple]:
        """Read-only query for inventory stock sizes."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT size_ml, quantity_available, reorder_point, warehouse_location
                FROM inventory
                WHERE perfume_id = ?
            """, (perfume_id,))
            rows = c.fetchall()
            conn.close()
            return rows
        except Exception:
            return []

    def get_available_quantity(self, perfume_id: str, size_ml: int) -> int:
        """Read-only query for available quantity of a specific size."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT quantity_available FROM inventory 
                WHERE perfume_id = ? AND size_ml = ?
            """, (perfume_id, size_ml))
            row = c.fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    def update_stock_atomic(self, conn: sqlite3.Connection, perfume_id: str, size_ml: int, qty: int) -> bool:
        """Atomic write operation to deduct stock inside an open transaction."""
        c = conn.cursor()
        c.execute("""
            UPDATE inventory 
            SET quantity_available = quantity_available - ? 
            WHERE perfume_id = ? AND size_ml = ? AND quantity_available >= ?
        """, (qty, perfume_id, size_ml, qty))
        return c.rowcount > 0
