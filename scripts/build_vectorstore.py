import os
import sys
import sqlite3
import pandas as pd

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

def build_vectorstore():
    print(f"Initializing embedding model: {config.EMBEDDING_MODEL}...")
    # Initialize embedding model
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    
    documents = []
    
    # 1. Load Perfume Catalog from SQLite
    print(f"Loading perfume catalog from {config.DB_PATH}...")
    try:
        conn = sqlite3.connect(config.DB_PATH)
        df = pd.read_sql("SELECT perfume_id, name, brand, category, gender, top_notes, heart_notes, base_notes, description FROM perfume_catalog", conn)
        conn.close()
        
        print(f"Found {len(df)} perfumes. Creating documents...")
        for _, row in df.iterrows():
            # Create a rich text representation for embedding
            content = f"Parfum {row['name']} oleh {row['brand']}. Kategori: {row['category']}, untuk {row['gender']}. " \
                      f"Top notes: {row['top_notes']}. Heart notes: {row['heart_notes']}. Base notes: {row['base_notes']}. " \
                      f"Deskripsi: {row['description']}"
            
            doc = Document(
                page_content=content,
                metadata={
                    "source": "perfume_catalog",
                    "perfume_id": row['perfume_id'],
                    "name": row['name'],
                    "brand": row['brand'],
                    "category": row['category']
                }
            )
            documents.append(doc)
    except Exception as e:
        print(f"Error loading perfume catalog: {e}")

    # 2. Load FAQ and SOP
    print(f"Loading FAQ and SOP from {config.FAQ_PATH}...")
    try:
        loader = TextLoader(config.FAQ_PATH, encoding='utf-8')
        faq_docs = loader.load()
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        
        split_faq_docs = text_splitter.split_documents(faq_docs)
        
        # Add source metadata explicitly
        for doc in split_faq_docs:
            doc.metadata["source"] = "faq_sop"
            documents.extend([doc])
            
        print(f"Created {len(split_faq_docs)} chunks from FAQ/SOP.")
    except Exception as e:
        print(f"Error loading FAQ/SOP: {e}")

    # 3. Create and persist ChromaDB
    print(f"Total documents to embed: {len(documents)}")
    if documents:
        print(f"Building Chroma vector store at {config.CHROMA_PATH}...")
        
        # This will create and persist the DB
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=config.CHROMA_PATH
        )
        
        print("Vector store built and persisted successfully!")
    else:
        print("No documents found to embed.")

if __name__ == "__main__":
    build_vectorstore()
