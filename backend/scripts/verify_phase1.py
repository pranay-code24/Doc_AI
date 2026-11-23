from pathlib import Path
import fitz  # PyMuPDF
import requests

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample_docs"
MODEL_NAME = "qwen2.5:3b"


def check_pdfs():
    print("--- 1. Checking Sample PDFs ---")
    pdfs = sorted(SAMPLE_DIR.glob("*.pdf"))
    if len(pdfs) != 4:
        print(f"ERROR: Expected 4 PDFs, found {len(pdfs)}")
        return False

    for pdf_path in pdfs:
        doc = fitz.open(pdf_path)
        first_line = doc[0].get_text("text").strip().splitlines()[0]
        print(f"[OK] {pdf_path.name} | Pages: {len(doc)} | Title: {first_line}")
        doc.close()
    return True


def check_ollama():
    print("\n--- 2. Checking Local Ollama Connection ---")
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": "Say only: LOCAL_LLM_OK",
                "stream": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        reply = resp.json().get("response", "").strip()
        print(f"[OK] Ollama ({MODEL_NAME}) responded: {reply}")
        return True
    except Exception as e:
        print(f"[FAIL] Ollama check failed: {e}")
        print("Tip: Check karo ki 'ollama serve' chal raha hai aur model pull ho chuka hai.")
        return False


if __name__ == "__main__":
    ok_pdfs = check_pdfs()
    ok_llm = check_ollama()
    if ok_pdfs and ok_llm:
        print("\nPhase 1 COMPLETE! Ab tum Phase 2 ke liye ready ho.")