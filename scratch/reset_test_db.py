import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def reset_inventory():
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE inventory SET quantity_available = 50")
    conn.commit()
    conn.close()
    print("Database inventory stock reset to 500 pcs for all items.")

if __name__ == "__main__":
    reset_inventory()
