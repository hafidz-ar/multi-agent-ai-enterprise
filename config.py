import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database & File Paths
DB_PATH = os.path.join(BASE_DIR, "data", "database", "parfum_enterprise.db")
CHROMA_PATH = os.path.join(BASE_DIR, "data", "vectorstore", "chroma_db")
FAQ_PATH = os.path.join(BASE_DIR, "data", "raw", "faq_sop.txt")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "evaluation.log")

# Ensure directories exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(CHROMA_PATH), exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Optional: Redis configuration (Jika nanti ingin beralih dari SQLite/In-memory)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# FSM Configuration
WORKFLOW_TIMEOUT = int(os.getenv("WORKFLOW_TIMEOUT", 900)) # 15 minutes

# Konfigurasi LLM (Groq API)
# Gunakan llama-3.1-8b-instant untuk Tool Calling yang sangat cepat dan gratis
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY or GROQ_API_KEY == "ISI_API_KEY_ANDA_DISINI":
    print("WARNING: GROQ_API_KEY belum diset dengan benar di file .env")

LLM_MODEL = "llama-3.1-8b-instant"

# Embedding (tetap lokal)
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

# Feature Flags
DEVELOPER_MODE = True
