from pathlib import Path

# Folder paths (automatically detect honge)
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
SAMPLE_DOCS_DIR = PROJECT_ROOT / "sample_docs"
STORAGE_DIR = BACKEND_DIR / "storage"
QDRANT_DIR = STORAGE_DIR / "qdrant_db"
CHUNKS_FILE = STORAGE_DIR / "chunks.json"
PAGES_FILE = STORAGE_DIR / "pages.json"

# Ensure storage folder exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Open-Source Models (MacBook Air friendly + English/Hindi multilingual)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-small"
RERANK_MODEL_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
QDRANT_COLLECTION = "doc_ai_chunks"
NLI_MODEL_NAME = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"