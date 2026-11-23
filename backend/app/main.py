import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import SAMPLE_DOCS_DIR, UPLOAD_DOCS_DIR
from app.pipeline import DocumentAIPipeline


pipeline: DocumentAIPipeline | None = None


def ensure_initial_docs():
    """Agar uploaded_docs folder khali hai toh 4 sample PDFs automatically copy kar lo."""
    existing = list(UPLOAD_DOCS_DIR.glob("*.pdf"))
    if not existing and SAMPLE_DOCS_DIR.exists():
        for pdf in SAMPLE_DOCS_DIR.glob("*.pdf"):
            shutil.copy2(pdf, UPLOAD_DOCS_DIR / pdf.name)


def resolve_pdf_path(doc_name: str) -> Path:
    """Safe filename lookup (path traversal block karta hai)."""
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
    # Agar index abhi khali hai toh auto-ingest karo
    if not pipeline.retriever.chunks:
        pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    print("Backend Ready on http://localhost:8000")
    yield
    if pipeline:
        pipeline.close()


app = FastAPI(
    title="Zero-Guessing & Contradiction-Checking Document AI",
    version="1.0.0",
    lifespan=lifespan,
)

# Next.js frontend (localhost:3000) ko allow karo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "chunks_indexed": len(pipeline.retriever.chunks) if pipeline else 0,
        "documents": list(pipeline.amendment_graph.docs.keys()) if pipeline else [],
    }


@app.get("/api/documents")
def list_documents() -> dict[str, Any]:
    """Saare active PDFs, unke page counts, metadata aur amendment chains return karta hai."""
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
    }


@app.post("/api/upload")
async def upload_pdfs(files: list[UploadFile] = File(...)):
    """Multiple PDFs upload karke automatically parse, index aur amendment graph rebuild karta hai."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    saved_names = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Only PDF files are supported: {f.filename}")
        safe_name = Path(f.filename).name
        dest = UPLOAD_DOCS_DIR / safe_name
        content = await f.read()
        dest.write_bytes(content)
        saved_names.append(safe_name)

    stats = pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    return {"uploaded": saved_names, "stats": stats}


@app.delete("/api/documents/{doc_name}")
def delete_document(doc_name: str):
    """Kisi uploaded PDF ko delete karke index rebuild karta hai."""
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
        stats = {"documents_indexed": 0, "pages_parsed": 0, "chunks_indexed": 0}
    return {"deleted": safe_name, "stats": stats}


@app.post("/api/reset-samples")
def reset_samples():
    """Demo ke liye 4 sample PDFs cleanly reload aur re-index karta hai."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    for old in UPLOAD_DOCS_DIR.glob("*.pdf"):
        old.unlink()
    ensure_initial_docs()
    stats = pipeline.ingest_folder(UPLOAD_DOCS_DIR)
    return {"message": "Sample documents restored and re-indexed", "stats": stats}


@app.post("/api/query")
def query_documents(req: QueryRequest) -> dict[str, Any]:
    """Main Zero-Guessing Verification-First Q&A Endpoint."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline still loading")

    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    return pipeline.ask(q)


@app.get("/api/pdf-page/{doc_name}/{page_number}")
def render_pdf_page(doc_name: str, page_number: int):
    """
    Bonus Feature Support: Exact PDF page ko crisp PNG image me render karta hai
    taaki frontend uske upar pixel-accurate yellow passage highlights draw kar sake.
    """
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
    """Download/open original PDF file."""
    pdf_path = resolve_pdf_path(doc_name)
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=pdf_path.name)