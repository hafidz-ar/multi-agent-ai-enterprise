import os
import sys
import time
import sqlite3
from langchain_groq import ChatGroq

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from parfum_agents.tools.db_tools import query_sales
from parfum_agents.tools.utils import log_evaluation

def get_business_context():
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT SUM(total_revenue_idr) FROM sales_history")
    total_revenue = c.fetchone()[0] or 0
    
    c.execute("SELECT perfume_name, SUM(quantity_sold) as total_qty FROM sales_history GROUP BY perfume_name ORDER BY total_qty DESC LIMIT 3")
    top_products = c.fetchall()
    
    c.execute("SELECT region, SUM(total_revenue_idr) as rev FROM sales_history GROUP BY region ORDER BY rev DESC LIMIT 3")
    top_regions = c.fetchall()
    conn.close()
    
    context = f"Total Revenue Keseluruhan: Rp {total_revenue:,}\n\n"
    context += "Top 3 Produk Terlaris:\n"
    for r in top_products:
        context += f"- {r[0]}: {r[1]} pcs terjual\n"
        
    context += "\nTop 3 Region Penjualan:\n"
    for r in top_regions:
        context += f"- {r[0]}: Rp {r[1]:,}\n"
    return context

def run(input_text: str) -> str:
    start_time = time.time()
    try:
        biz_context = get_business_context()
        llm = ChatGroq(
            model=config.LLM_MODEL, 
            api_key=config.GROQ_API_KEY,
            temperature=0.2
        )
        
        system_prompt = f"""Kamu adalah Business Insight Agent untuk perusahaan parfum.
Berikut adalah rangkuman data penjualan dari database:
{biz_context}

Pertanyaan Manager / User:
"{input_text}"

Tugasmu:
Berikan jawaban analitis dan wawasan bisnis yang ringkas, jelas, dan profesional berdasarkan data di atas.
Jangan mengarang data yang tidak ada di konteks."""

        response = llm.invoke(system_prompt)
        output = response.content
        
        duration = time.time() - start_time
        log_evaluation("BusinessInsightAgent", input_text, output, duration, "SUCCESS")
        return output
    except Exception as e:
        duration = time.time() - start_time
        err_msg = f"Error in BusinessInsightAgent: {str(e)}"
        log_evaluation("BusinessInsightAgent", input_text, err_msg, duration, "ERROR")
        return err_msg
