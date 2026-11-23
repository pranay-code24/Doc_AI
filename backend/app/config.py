import os
from pathlib import Path

# Folder paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
SAMPLE_DOCS_DIR = PROJECT_ROOT / "sample_docs"
STORAGE_DIR = BACKEND_DIR / "storage"
QDRANT_DIR = STORAGE_DIR / "qdrant_db"
CHUNKS_FILE = STORAGE_DIR / "chunks.json"
PAGES_FILE = STORAGE_DIR / "pages.json"
AMENDMENT_GRAPH_FILE = STORAGE_DIR / "amendment_graph.json"
BENCHMARK_FILE = STORAGE_DIR / "benchmark_report.json"
UPLOAD_DOCS_DIR = STORAGE_DIR / "uploaded_docs"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DOCS_DIR.mkdir(parents=True, exist_ok=True)


def _load_dotenv(env_path: Path):
    """Lightweight .env loader (no extra dependency needed)."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")
_load_dotenv(PROJECT_ROOT / ".env")

# Open-Source Inference Providers (Groq Free Open-Source API + Offline Local Ollama)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b").strip()

# Default provider: agar GROQ_API_KEY set hai toh fast 'groq', warna offline 'ollama'
DEFAULT_LLM_PROVIDER = os.environ.get(
    "LLM_PROVIDER",
    "groq" if GROQ_API_KEY else "ollama",
).strip().lower()

# Local Open-Source Retrieval & Verification Models
EMBED_MODEL_NAME = "intfloat/multilingual-e5-small"
RERANK_MODEL_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
NLI_MODEL_NAME = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
QDRANT_COLLECTION = "doc_ai_chunks"

# Supported Languages (Citizen-Friendly Multilingual Support)
SUPPORTED_LANGUAGES = {
    "auto": "Auto-Detect (Match User Language)",
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "gu": "Gujarati (ગુજરાતી)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
}