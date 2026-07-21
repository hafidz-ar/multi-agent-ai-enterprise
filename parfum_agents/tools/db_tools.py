import os
import sys
import sqlite3
import pandas as pd
from langchain_core.tools import tool

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

def get_db_connection():
    return sqlite3.connect(config.DB_PATH)

@tool
def check_stock(perfume_id: str, size_ml: int = None) -> str:
    """
    Mengecek stok parfum berdasarkan perfume_id. Parameter size_ml opsional (misal: 50 atau 100).
    Gunakan tool ini untuk mengecek ketersediaan barang.
    """
    try:
        conn = get_db_connection()
        if size_ml:
            query = "SELECT perfume_name, size_ml, quantity_available, status FROM inventory WHERE perfume_id = ? AND size_ml = ?"
            df = pd.read_sql(query, conn, params=(perfume_id, size_ml))
        else:
            query = "SELECT perfume_name, size_ml, quantity_available, status FROM inventory WHERE perfume_id = ?"
            df = pd.read_sql(query, conn, params=(perfume_id,))
        conn.close()
        
        if df.empty:
            size_str = f"ukuran {size_ml}ml " if size_ml else ""
            return f"Parfum dengan ID {perfume_id} {size_str}tidak ditemukan di sistem."
        
        res = []
        for _, row in df.iterrows():
            res.append(f"Status {row['perfume_name']} ({row['size_ml']}ml): {row['status']}. Sisa stok: {row['quantity_available']} botol.")
        return "\n".join(res)
    except Exception as e:
        return f"Error checking stock: {str(e)}"

@tool
def get_formula(perfume_id: str) -> str:
    """
    Mengambil formula lengkap dari parfum berdasarkan perfume_id.
    Gunakan tool ini untuk Formulation Agent.
    """
    try:
        conn = get_db_connection()
        query = "SELECT ingredient_id, ingredient_name, percentage, note_type FROM formula WHERE perfume_id = ?"
        df = pd.read_sql(query, conn, params=(perfume_id,))
        conn.close()
        
        if df.empty:
            return f"Formula untuk parfum ID {perfume_id} tidak ditemukan."
            
        formula_str = f"Formula untuk {perfume_id}:\n"
        for _, row in df.iterrows():
            formula_str += f"- {row['ingredient_name']} (ID: {row['ingredient_id']}): {row['percentage']}% ({row['note_type']})\n"
        return formula_str
    except Exception as e:
        return f"Error getting formula: {str(e)}"

@tool
def check_ingredients(ingredient_ids: list[str]) -> str:
    """
    Mengecek ketersediaan bahan baku di gudang.
    Menerima list of ingredient_id.
    Gunakan tool ini untuk Formulation Agent.
    """
    if not ingredient_ids:
        return "Tidak ada bahan baku yang dicek."
        
    try:
        conn = get_db_connection()
        placeholders = ','.join('?' for _ in ingredient_ids)
        query = f"SELECT ingredient_id, ingredient_name, stock_available, status FROM ingredients WHERE ingredient_id IN ({placeholders})"
        df = pd.read_sql(query, conn, params=ingredient_ids)
        conn.close()
        
        if df.empty:
            return "Bahan baku tidak ditemukan."
            
        res_str = "Status Bahan Baku:\n"
        for _, row in df.iterrows():
            res_str += f"- {row['ingredient_name']} ({row['ingredient_id']}): {row['status']} (Stok: {row['stock_available']})\n"
        return res_str
    except Exception as e:
        return f"Error checking ingredients: {str(e)}"

@tool
def search_suppliers(ingredient_id: str) -> str:
    """
    Mencari supplier untuk bahan baku tertentu berdasarkan ingredient_id.
    Gunakan tool ini untuk Procurement Agent.
    """
    try:
        conn = get_db_connection()
        query = "SELECT supplier_name, price_per_unit_idr, lead_time_days, reliability_score FROM supplier WHERE ingredient_id = ? ORDER BY reliability_score DESC"
        df = pd.read_sql(query, conn, params=(ingredient_id,))
        conn.close()
        
        if df.empty:
            return f"Tidak ada supplier yang menyediakan bahan baku dengan ID {ingredient_id}."
            
        res_str = f"Rekomendasi Supplier untuk bahan {ingredient_id}:\n"
        for i, row in df.iterrows():
            res_str += f"{i+1}. {row['supplier_name']} - Harga: Rp{row['price_per_unit_idr']}/unit, Pengiriman: {row['lead_time_days']} hari, Reputasi: {row['reliability_score']}/10\n"
        return res_str
    except Exception as e:
        return f"Error searching suppliers: {str(e)}"

@tool
def query_sales(sql_query: str) -> str:
    """
    Mengeksekusi SQL query ke tabel sales_history, perfume_catalog, dll.
    Input harus berupa query SQL SELECT yang valid untuk SQLite.
    Gunakan tool ini untuk Business Insight Agent.
    """
    # Keamanan: pastikan hanya query SELECT (read-only) dan cegah stacked queries
    clean_query = sql_query.strip().upper()
    if not clean_query.startswith("SELECT"):
        return "Error: Hanya diperbolehkan query SELECT untuk analisa."
        
    if ";" in clean_query:
        return "Error: Karakter ';' tidak diperbolehkan untuk keamanan query."

    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "EXEC", "TRUNCATE"]
    if any(kw in clean_query.split() for kw in forbidden):
        return "Error: Query mengandung kata kunci SQL yang dilarang."
        
    try:
        conn = get_db_connection()
        df = pd.read_sql(sql_query, conn)
        conn.close()
        
        if df.empty:
            return "Hasil query kosong (tidak ada data yang cocok)."
            
        # Batasi output jika terlalu banyak baris
        if len(df) > 20:
            return f"Hasil terlalu banyak ({len(df)} baris). Menampilkan 10 baris pertama:\n{df.head(10).to_string(index=False)}"
            
        return f"Hasil Query:\n{df.to_string(index=False)}"
    except Exception as e:
        return f"Error executing SQL: {str(e)}"
