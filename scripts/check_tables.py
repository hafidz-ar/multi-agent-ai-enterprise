import sqlite3, sys
sys.path.insert(0, ".")
import config
conn = sqlite3.connect(config.DB_PATH)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("TABLES:", tables)
# Check sample data
for t in tables:
    c.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t}: {c.fetchone()[0]} rows")
conn.close()
