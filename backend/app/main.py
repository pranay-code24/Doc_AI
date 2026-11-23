import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import (
    BENCHMARK_FILE,
    DEFAULT_LLM_PROVIDER,
    GROQ_API_KEY,
    GROQ_MODEL,
    OLLAMA_MODEL,
    SAMPLE_DOCS_DIR,
    SUPPORTED_LANGUAGES,
    UPLOAD_DOCS_DIR,
)
from app.pipeline import DocumentAIPipeline
from app.verification.guardrails import validate_pdf_upload


pipeline: DocumentAIPipeline | None = None


def ensure_initial_docs():
    existing = list(UPLOAD_DOCS_DIR.glob("*.pdf"))
    if not existing and SAMPLE_DOCS_DIR.exists():
        for pdf in SAMPLE_DOCS_DIR.glob("*.pdf"):
            shutil.copy2(pdf, UPLOAD_DOCS_DIR / pdf.name)


def resolve_pdf_path(doc_name: str) -> Path:
    safe_name = Path(doc_name).name
    for folder in (UPLOAD_DOCS_DIR, SAMPLE_DOCS_DIR):
        candidate = folder / safe_name
        if candidate.exists() and candidate.suffix.lower() == ".pdf":
            return candidate
    raise HTTPException(status_code=404, detail=f"PDF not found: {safe_name}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    ensure_initial_docs()
    print("Initializing Zero-Guessing Document AI Pipeline...")
    pipeline = DocumentAIPipeline()
    if not pipeline.retriever.chunks:
        pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    print(f"Backend Ready on http://localhost:8000 | Default LLM Provider: {DEFAULT_LLM_PROVIDER}")
    yield
    if pipeline:
        pipeline.close()


app = FastAPI(
    title="Zero-Guessing & Contradiction-Checking Document AI",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    language: str = "auto"
    provider: str | None = None
    use_cache: bool = True


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "default_provider": DEFAULT_LLM_PROVIDER,
        "groq_configured": bool(GROQ_API_KEY),
        "groq_model": GROQ_MODEL,
        "ollama_model": OLLAMA_MODEL,
        "languages": SUPPORTED_LANGUAGES,
        "chunks_indexed": len(pipeline.retriever.chunks) if pipeline else 0,
        "documents": list(pipeline.amendment_graph.docs.keys()) if pipeline else [],
    }


@app.get("/api/documents")
def list_documents() -> dict[str, Any]:
    docs_list = []
    for pdf_path in sorted(UPLOAD_DOCS_DIR.glob("*.pdf")):
        doc = pymupdf.open(pdf_path)
        page_count = len(doc)
        doc.close()
        meta = pipeline.amendment_graph.docs.get(pdf_path.name, {}) if pipeline else {}
        docs_list.append(
            {
                "doc_name": pdf_path.name,
                "pages": page_count,
                "doc_id": meta.get("doc_id", pdf_path.name),
                "effective_date": meta.get("effective_date", "Unknown"),
                "amends_doc_ids": meta.get("amends_doc_ids", []),
            }
        )

    return {
        "documents": docs_list,
        "amendment_chains": pipeline.amendment_graph.clause_chains if pipeline else {},
        "default_provider": DEFAULT_LLM_PROVIDER,
        "groq_configured": bool(GROQ_API_KEY),
        "languages": SUPPORTED_LANGUAGES,
    }


@app.post("/api/upload")
async def upload_pdfs(files: list[UploadFile] = File(...)):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    saved_names = []
    for f in files:
        content = await f.read()
        ok, err_msg = validate_pdf_upload(f.filename or "", content)
        if not ok:
            raise HTTPException(status_code=400, detail=err_msg)
        safe_name = Path(f.filename).name
        dest = UPLOAD_DOCS_DIR / safe_name
        dest.write_bytes(content)
        saved_names.append(safe_name)

    stats = pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    return {"uploaded": saved_names, "stats": stats}


@app.delete("/api/documents/{doc_name}")
def delete_document(doc_name: str):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    safe_name = Path(doc_name).name
    target = UPLOAD_DOCS_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {safe_name}")
    target.unlink()

    if list(UPLOAD_DOCS_DIR.glob("*.pdf")):
        stats = pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    else:
        pipeline.clear_cache()
        stats = {"documents_indexed": 0, "pages_parsed": 0, "chunks_indexed": 0}
    return {"deleted": safe_name, "stats": stats}


@app.post("/api/reset-samples")
def reset_samples():
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    for old in UPLOAD_DOCS_DIR.glob("*.pdf"):
        old.unlink()
    ensure_initial_docs()
    stats = pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    return {"message": "Sample documents restored and re-indexed", "stats": stats}


@app.post("/api/query")
def query_documents(req: QueryRequest) -> dict[str, Any]:
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    return pipeline.ask(
        question=q,
        language=req.language,
        provider=req.provider,
        use_cache=req.use_cache,
    )


@app.get("/api/metrics")
def get_benchmark_metrics() -> dict[str, Any]:
    """Saved evaluation benchmark report return karta hai Frontend Metrics Tab ke liye."""
    if BENCHMARK_FILE.exists():
        return json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    return {
        "has_report": False,
        "message": "Run benchmark to generate live accuracy & latency proof.",
    }


@app.post("/api/metrics/run")
def run_live_benchmark(provider: str | None = None) -> dict[str, Any]:
    """Live 9-case evaluation suite run karke real accuracy, guardrail & latency report save karta hai."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    from app.evaluation import evaluate_pipeline
    report = evaluate_pipeline(pipeline, provider=provider)
    BENCHMARK_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


@app.get("/api/pdf-page/{doc_name}/{page_number}")
def render_pdf_page(doc_name: str, page_number: int):
    pdf_path = resolve_pdf_path(doc_name)
    doc = pymupdf.open(pdf_path)
    if page_number < 1 or page_number > len(doc):
        doc.close()
        raise HTTPException(status_code=400, detail=f"Invalid page {page_number} (total {len(doc)})")

    page = doc[page_number - 1]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc.close()

    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/pdf-raw/{doc_name}")
def get_raw_pdf(doc_name: str):
    pdf_path = resolve_pdf_path(doc_name)
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=pdf_path.name)