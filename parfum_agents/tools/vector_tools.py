import os
import sys
from langchain_core.tools import tool
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

# Global instances for vector store
_embeddings = None
_vectorstore = None

def get_vectorstore():
    global _embeddings, _vectorstore
    if _vectorstore is None:
        if not os.path.exists(config.CHROMA_PATH):
            raise FileNotFoundError(f"ChromaDB not found at {config.CHROMA_PATH}. Tolong jalankan scripts/build_vectorstore.py dulu.")
            
        _embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
        _vectorstore = Chroma(
            persist_directory=config.CHROMA_PATH, 
            embedding_function=_embeddings
        )
    return _vectorstore

@tool
def search_perfume(query: str, k: int = 3) -> str:
    """
    Melakukan pencarian parfum yang relevan berdasarkan deskripsi dan preferensi pelanggan.
    Gunakan tool ini untuk mencari rekomendasi parfum.
    """
    try:
        vs = get_vectorstore()
        # Filter only perfume catalog
        docs = vs.similarity_search(
            query, 
            k=k, 
            filter={"source": "perfume_catalog"}
        )
        
        if not docs:
            return "Tidak ditemukan parfum yang cocok dengan kriteria tersebut."
            
        res_str = f"Rekomendasi parfum untuk '{query}':\n\n"
        for i, doc in enumerate(docs):
            res_str += f"{i+1}. {doc.metadata['name']} (ID: {doc.metadata['perfume_id']})\n"
            res_str += f"   Info: {doc.page_content}\n\n"
        return res_str
    except Exception as e:
        return f"Error searching perfume: {str(e)}"

@tool
def search_faq(query: str, k: int = 2) -> str:
    """
    Mencari jawaban di FAQ atau Panduan SOP untuk pertanyaan pelanggan tentang parfum (misalnya perbedaan EDT dan EDP).
    """
    try:
        vs = get_vectorstore()
        # Filter only FAQ
        docs = vs.similarity_search(
            query, 
            k=k, 
            filter={"source": "faq_sop"}
        )
        
        if not docs:
            return "Tidak ditemukan panduan atau FAQ yang relevan."
            
        res_str = f"Panduan relevan untuk '{query}':\n\n"
        for i, doc in enumerate(docs):
            res_str += f"- {doc.page_content}\n\n"
        return res_str
    except Exception as e:
        return f"Error searching FAQ: {str(e)}"
