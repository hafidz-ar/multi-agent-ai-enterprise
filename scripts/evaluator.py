import os
import sys
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def get_evaluator_llm():
    return ChatGroq(
        groq_api_key=config.GROQ_API_KEY,
        model_name=config.LLM_MODEL,
        temperature=0.0, # Gunakan temperature 0 untuk evaluasi yang konsisten
        max_tokens=512
    )

evaluator_prompt = PromptTemplate(
    input_variables=["question", "context", "answer"],
    template="""Kamu adalah seorang Juri Evaluator AI tingkat lanjut.
Tugas kamu adalah mengevaluasi respon dari sebuah sistem Multi-Agent berdasarkan metrik berikut:

1. ACCURACY (Akurasi): Apakah jawaban yang diberikan menjawab pertanyaan secara relevan dan benar berdasarkan konteks? (Skor 0-10)
2. EXPLAINABILITY (Kemampuan Menjelaskan): Seberapa baik sistem menjelaskan alasannya atau detail tambahan yang relevan? (Skor 0-10)
3. HALLUCINATION (Halusinasi): Apakah sistem mengarang informasi yang tidak ada dalam konteks? (Skor 0-10, di mana 10 = TIDAK ADA HALUSINASI sama sekali, 0 = HALUSINASI PENUH)

Berikut adalah data yang perlu dievaluasi:
---
PERTANYAAN: {question}
---
KONTEKS / REFERENSI: {context}
---
JAWABAN SISTEM: {answer}
---

Berikan penilaianmu dalam format JSON ketat (strict JSON) berikut tanpa teks tambahan:
{{
    "accuracy_score": <int>,
    "explainability_score": <int>,
    "hallucination_score": <int>,
    "reasoning": "<penjelasan singkat tentang penilaianmu>"
}}
"""
)

def evaluate_response(question: str, context: str, answer: str, latency_ms: float = 0):
    llm = get_evaluator_llm()
    chain = evaluator_prompt | llm
    
    print("Mengevaluasi respons menggunakan LLM-as-a-Judge...")
    try:
        result = chain.invoke({"question": question, "context": context, "answer": answer})
        
        # Ekstrak konten JSON dari output LLM
        response_text = result.content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()
            
        evaluation = json.loads(response_text)
        
        # Tambahkan Efficiency metric (dihitung secara deterministik)
        # Misal: < 2000ms = 10, < 4000ms = 8, dst.
        efficiency_score = 10
        if latency_ms > 5000:
            efficiency_score = 4
        elif latency_ms > 3000:
            efficiency_score = 6
        elif latency_ms > 1500:
            efficiency_score = 8
            
        evaluation["efficiency_score"] = efficiency_score
        evaluation["latency_ms"] = latency_ms
        
        return evaluation
    except Exception as e:
        print(f"Error dalam evaluasi: {e}")
        return {
            "accuracy_score": 0,
            "explainability_score": 0,
            "hallucination_score": 0,
            "efficiency_score": 0,
            "reasoning": f"Gagal mengevaluasi: {str(e)}",
            "latency_ms": latency_ms
        }

if __name__ == "__main__":
    print("=== Demo Evaluator Multi-Agent (Accuracy, Explainability, Hallucination, Efficiency) ===")
    
    # Skenario 1: Jawaban yang Sempurna
    q1 = "Berapa stok YSL Est Aqua saat ini?"
    ctx1 = "Database Inventory: YSL Est Aqua stok 25, Gudang A."
    ans1 = "Stok parfum YSL Est Aqua saat ini adalah 25 botol yang berada di Gudang A."
    
    print(f"\nSkenario 1 - Pertanyaan: {q1}")
    res1 = evaluate_response(q1, ctx1, ans1, latency_ms=1200)
    print(json.dumps(res1, indent=2))
    
    # Skenario 2: Halusinasi
    q2 = "Siapa CEO Parfum Enterprise?"
    ctx2 = "Visi Misi Perusahaan Parfum Enterprise: Menjadi perusahaan parfum nomor 1 di Indonesia."
    ans2 = "CEO Parfum Enterprise adalah Bapak Budi Santoso dan didirikan pada tahun 2010."
    
    print(f"\nSkenario 2 (Contoh Halusinasi) - Pertanyaan: {q2}")
    res2 = evaluate_response(q2, ctx2, ans2, latency_ms=2500)
    print(json.dumps(res2, indent=2))
