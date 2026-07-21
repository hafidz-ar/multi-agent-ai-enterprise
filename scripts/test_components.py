"""
Script Pengujian Komponen Mandiri (Tanpa Full Agent Workflow)
============================================================
Script ini menguji setiap komponen sistem secara terpisah:
1. Koneksi Database (SQLite)
2. Tools Database (db_tools)
3. Vector Store (ChromaDB / vector_tools)
4. Percakapan langsung ke LLM (tanpa tool calling yang bermasalah)

Hasil pengujian dicatat ke logs/evaluation.log
"""
import os
import sys
import time
import json

# Tambahkan path root ke sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from parfum_agents.tools.utils import log_evaluation

SEPARATOR = "=" * 60

def print_section(title):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)

def test_database_connection():
    """Tes 1: Koneksi langsung ke database SQLite"""
    print_section("TES 1: Koneksi Database SQLite")
    import sqlite3
    start = time.time()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        tables = ["perfume_catalog", "inventory", "formula", "ingredients", "supplier", "sales_history"]
        results = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            results[table] = count
            print(f"  ✅ Tabel '{table}': {count} baris")
        
        conn.close()
        duration = time.time() - start
        log_evaluation("DB_Connection_Test", "check_all_tables", json.dumps(results), duration, "SUCCESS")
        print(f"\n  STATUS: LULUS ✅ ({duration:.2f}s)")
        return True
    except Exception as e:
        duration = time.time() - start
        print(f"  STATUS: GAGAL ❌ - {e}")
        log_evaluation("DB_Connection_Test", "check_all_tables", str(e), duration, "ERROR")
        return False

def test_db_tools():
    """Tes 2: Uji setiap DB Tool secara langsung"""
    print_section("TES 2: DB Tools (check_stock, get_formula, check_ingredients, search_suppliers, query_sales)")
    from parfum_agents.tools import db_tools
    
    all_pass = True
    
    # Test check_stock
    start = time.time()
    try:
        result = db_tools.check_stock.invoke({"perfume_id": "PF001", "size_ml": 50})
        duration = time.time() - start
        print(f"  ✅ check_stock('PF001', 50ml): {str(result)[:80]}...")
        log_evaluation("Tool_check_stock", "PF001 | 50ml", str(result)[:200], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ check_stock Error: {e}")
        log_evaluation("Tool_check_stock", "PF001 | 50ml", str(e), duration, "ERROR")
        all_pass = False

    # Test get_formula
    start = time.time()
    try:
        result = db_tools.get_formula.invoke({"perfume_id": "PF001"})
        duration = time.time() - start
        print(f"  ✅ get_formula('PF001'): {str(result)[:80]}...")
        log_evaluation("Tool_get_formula", "PF001", str(result)[:200], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ get_formula Error: {e}")
        log_evaluation("Tool_get_formula", "PF001", str(e), duration, "ERROR")
        all_pass = False

    # Test check_ingredients
    start = time.time()
    try:
        result = db_tools.check_ingredients.invoke({"ingredient_ids": ["ING001", "ING002", "ING003"]})
        duration = time.time() - start
        print(f"  ✅ check_ingredients(['ING001','ING002','ING003']): {str(result)[:80]}...")
        log_evaluation("Tool_check_ingredients", "ING001|ING002|ING003", str(result)[:200], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ check_ingredients Error: {e}")
        log_evaluation("Tool_check_ingredients", "ING001|ING002|ING003", str(e), duration, "ERROR")
        all_pass = False

    # Test search_suppliers
    start = time.time()
    try:
        result = db_tools.search_suppliers.invoke({"ingredient_id": "ING001"})
        duration = time.time() - start
        print(f"  ✅ search_suppliers('ING001'): {str(result)[:80]}...")
        log_evaluation("Tool_search_suppliers", "ING001", str(result)[:200], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ search_suppliers Error: {e}")
        log_evaluation("Tool_search_suppliers", "ING001", str(e), duration, "ERROR")
        all_pass = False

    # Test query_sales
    start = time.time()
    try:
        result = db_tools.query_sales.invoke({"sql_query": "SELECT perfume_name, SUM(total_revenue_idr) as total FROM sales_history GROUP BY perfume_name ORDER BY total DESC LIMIT 3"})
        duration = time.time() - start
        print(f"  ✅ query_sales(top 3 best sellers): {str(result)[:80]}...")
        log_evaluation("Tool_query_sales", "top 3 best sellers", str(result)[:200], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ query_sales Error: {e}")
        log_evaluation("Tool_query_sales", "top 3 best sellers", str(e), duration, "ERROR")
        all_pass = False

    print(f"\n  STATUS: {'LULUS ✅' if all_pass else 'SEBAGIAN GAGAL ⚠️'}")
    return all_pass

def test_vector_tools():
    """Tes 3: Uji Vector Store (ChromaDB)"""
    print_section("TES 3: Vector Tools (search_perfume, search_faq)")
    from parfum_agents.tools import vector_tools
    
    all_pass = True

    # Test search_perfume
    start = time.time()
    try:
        result = vector_tools.search_perfume.invoke({"query": "parfum woody maskulin untuk pria"})
        duration = time.time() - start
        print(f"  ✅ search_perfume('woody maskulin'): {str(result)[:100]}...")
        log_evaluation("Tool_search_perfume", "woody maskulin untuk pria", str(result)[:300], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ search_perfume Error: {e}")
        log_evaluation("Tool_search_perfume", "woody maskulin untuk pria", str(e), duration, "ERROR")
        all_pass = False

    # Test search_faq
    start = time.time()
    try:
        result = vector_tools.search_faq.invoke({"query": "apa itu EDP dan EDT?"})
        duration = time.time() - start
        print(f"  ✅ search_faq('apa itu EDP dan EDT?'): {str(result)[:100]}...")
        log_evaluation("Tool_search_faq", "apa itu EDP dan EDT?", str(result)[:300], duration, "SUCCESS")
    except Exception as e:
        duration = time.time() - start
        print(f"  ❌ search_faq Error: {e}")
        log_evaluation("Tool_search_faq", "apa itu EDP dan EDT?", str(e), duration, "ERROR")
        all_pass = False

    print(f"\n  STATUS: {'LULUS ✅' if all_pass else 'SEBAGIAN GAGAL ⚠️'}")
    return all_pass

def test_llm_direct():
    """Tes 4: Percakapan langsung ke LLM (tanpa Tool Calling)"""
    print_section("TES 4: Percakapan Langsung ke LLM (Groq)")
    from langchain_groq import ChatGroq

    questions = [
        "Apa itu parfum EDP dan EDT? Jelaskan singkat dalam Bahasa Indonesia.",
        "Berikan rekomendasi singkat parfum dengan aroma woody yang cocok untuk pria profesional.",
    ]

    all_pass = True
    for q in questions:
        start = time.time()
        try:
            llm = ChatGroq(
                model=config.LLM_MODEL,
                api_key=config.GROQ_API_KEY,
                temperature=0.5
            )
            response = llm.invoke(q)
            output_text = str(response.content)
            
            duration = time.time() - start
            print(f"  ✅ Q: {q[:50]}...")
            print(f"     A: {output_text[:100]}...")
            log_evaluation("LLM_Direct_Test", q, output_text[:300], duration, "SUCCESS")
            time.sleep(15)  # Jeda 15 detik antar pertanyaan untuk menghindari rate limit
        except Exception as e:
            duration = time.time() - start
            print(f"  ❌ Error: {e}")
            log_evaluation("LLM_Direct_Test", q, str(e), duration, "ERROR")
            all_pass = False

    print(f"\n  STATUS: {'LULUS ✅' if all_pass else 'SEBAGIAN GAGAL ⚠️'}")
    return all_pass

if __name__ == "__main__":
    print(f"\n{'#'*60}")
    print(f"  PENGUJIAN KOMPONEN SISTEM PARFUM ENTERPRISE")
    print(f"  Model LLM: {config.LLM_MODEL}")
    print(f"  Database : {config.DB_PATH}")
    print(f"  Log File : {config.LOG_PATH}")
    print(f"{'#'*60}")

    results = {}
    results["db_connection"] = test_database_connection()
    results["db_tools"]      = test_db_tools()
    results["vector_tools"]  = test_vector_tools()
    results["llm_direct"]    = test_llm_direct()

    print_section("RINGKASAN HASIL PENGUJIAN")
    for name, passed in results.items():
        status = "✅ LULUS" if passed else "❌ GAGAL"
        print(f"  {status}  - {name}")

    total = sum(results.values())
    print(f"\n  TOTAL: {total}/{len(results)} pengujian berhasil")
    print(f"  Log tersimpan di: {config.LOG_PATH}")
    print(SEPARATOR)
