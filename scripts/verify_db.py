import sqlite3
import pandas as pd

db = sqlite3.connect(r'd:\Amikom\Semester 6\Proyek Data Mining\UAS\data\database\parfum_enterprise.db')

# 1. Cek semua tabel
print('=== DAFTAR TABEL ===')
tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", db)
print(tables.to_string(index=False))

# 2. Cek jumlah baris per tabel
print('\n=== JUMLAH BARIS PER TABEL ===')
for t in tables['name']:
    count = pd.read_sql(f'SELECT COUNT(*) as total FROM {t}', db)
    print(f'  {t}: {count.iloc[0,0]} baris')

# 3. Sample perfume_catalog
print('\n=== SAMPLE: perfume_catalog (5 baris) ===')
df = pd.read_sql('SELECT perfume_id, name, brand, category, price_idr FROM perfume_catalog LIMIT 5', db)
print(df.to_string(index=False))

# 4. Sample ingredients
print('\n=== SAMPLE: ingredients (5 baris) ===')
df = pd.read_sql('SELECT ingredient_id, ingredient_name, category, stock_available, status FROM ingredients LIMIT 5', db)
print(df.to_string(index=False))

# 5. Sample inventory
print('\n=== SAMPLE: inventory (5 baris) ===')
df = pd.read_sql('SELECT stock_id, perfume_name, size_ml, quantity_available, status FROM inventory LIMIT 5', db)
print(df.to_string(index=False))

# 6. Sample sales_history
print('\n=== SAMPLE: sales_history (5 baris) ===')
df = pd.read_sql('SELECT transaction_id, date, perfume_name, quantity_sold, total_revenue_idr, channel FROM sales_history LIMIT 5', db)
print(df.to_string(index=False))

# 7. Validasi FK
print('\n=== VALIDASI FOREIGN KEY ===')
orphan_sales = pd.read_sql("""
    SELECT COUNT(*) as orphan FROM sales_history 
    WHERE perfume_id NOT IN (SELECT perfume_id FROM perfume_catalog)
""", db)
print(f'  Sales tanpa perfume_id valid: {orphan_sales.iloc[0,0]}')

orphan_formula = pd.read_sql("""
    SELECT COUNT(*) as orphan FROM formula 
    WHERE ingredient_id NOT IN (SELECT ingredient_id FROM ingredients)
""", db)
print(f'  Formula tanpa ingredient_id valid: {orphan_formula.iloc[0,0]}')

orphan_inv = pd.read_sql("""
    SELECT COUNT(*) as orphan FROM inventory 
    WHERE perfume_id NOT IN (SELECT perfume_id FROM perfume_catalog)
""", db)
print(f'  Inventory tanpa perfume_id valid: {orphan_inv.iloc[0,0]}')

# 8. Distribusi status inventory
print('\n=== DISTRIBUSI STATUS INVENTORY ===')
df = pd.read_sql('SELECT status, COUNT(*) as jumlah FROM inventory GROUP BY status', db)
print(df.to_string(index=False))

# 9. Distribusi brand
print('\n=== DISTRIBUSI BRAND ===')
df = pd.read_sql('SELECT brand, COUNT(*) as jumlah FROM perfume_catalog GROUP BY brand ORDER BY jumlah DESC', db)
print(df.to_string(index=False))

# 10. Sample deskripsi Bahasa Indonesia
print('\n=== SAMPLE DESKRIPSI (Bahasa Indonesia) ===')
df = pd.read_sql('SELECT name, description FROM perfume_catalog LIMIT 3', db)
for _, row in df.iterrows():
    print(f'  [{row["name"]}]: {row["description"]}')
    print()

db.close()
print('=== VERIFIKASI SELESAI ===')
