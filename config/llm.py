import os
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi LLM (Groq API)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY or GROQ_API_KEY == "ISI_API_KEY_ANDA_DISINI":
    print("WARNING: GROQ_API_KEY belum diset dengan benar di file .env")

LLM_MODEL = "llama-3.1-8b-instant"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"
