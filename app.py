import os
import uvicorn
from api.main import app

# Ini adalah trik agar FastAPI kita bisa berjalan di atas infrastruktur Gradio Hugging Face yang GRATIS
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
