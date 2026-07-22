import sqlite3
import config

class CatalogRepository:
    """Repository isolating Catalog & Pricing persistence queries from business agents."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH

    def get_all_product_names(self) -> list[str]:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT name FROM perfume_catalog")
            names = [r[0] for r in c.fetchall()]
            conn.close()
            return names
        except Exception:
            return []

    def find_product_by_name(self, product_name: str) -> tuple | None:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT perfume_id, name, category, price_idr FROM perfume_catalog WHERE name LIKE ?", (f"%{product_name}%",))
            prod = c.fetchone()
            conn.close()
            return prod
        except Exception:
            return None

    def get_variant_prices(self, perfume_id: str) -> list[tuple]:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT i.size_ml, p.price_idr 
                FROM inventory i 
                JOIN perfume_catalog p ON i.perfume_id = p.perfume_id 
                WHERE i.perfume_id = ?
            """, (perfume_id,))
            rows = c.fetchall()
            conn.close()
            return rows
        except Exception:
            return []

    def get_catalog_summary(self) -> list[dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT name, brand, category, gender, price_idr, top_notes, heart_notes, base_notes FROM perfume_catalog LIMIT 25")
            rows = c.fetchall()
            conn.close()
            return [
                {
                    "name": r[0], "brand": r[1], "category": r[2],
                    "gender": r[3], "price_idr": r[4],
                    "top_notes": r[5], "heart_notes": r[6], "base_notes": r[7]
                }
                for r in rows
            ]
        except Exception:
            return []
