import os

# Base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

# Redis configuration (Optional)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
