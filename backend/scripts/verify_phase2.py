import sys
from pathlib import Path

# Ensure 'backend/' is in Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import SAMPLE_DOCS_DIR
from app.ingestion.pdf_parser import parse_folder
from app.retrieval.hybrid_search import HybridRetriever


TEST_QUERIES = [
    ("1. Amendment Chain Query", "What is the currently applicable interest rate for a Retail Personal Loan?"),
    ("2. Contradiction Query", "What is the maximum repayment tenure and minimum applicant age?"),
    ("3. Fee Table Query", "What is the processing fee and foreclosure fee?"),
    ("4. Hindi Cross-Lingual Query", "Abhi personal loan par late payment penalty kitni lagti hai?"),
]


def main():
    print("--- Step 1: Parsing all PDFs in sample_docs/ ---")
    chunks, pages = parse_folder(SAMPLE_DOCS_DIR)
    table_count = sum(1 for c in chunks if c["chunk_type"] == "table")
    text_count = sum(1 for c in chunks if c["chunk_type"] == "text")
    print(f"[OK] Parsed {len(pages)} pages -> {text_count} text chunks + {table_count} table chunks")

    # Quick preview of one table chunk to verify Markdown extraction
    for c in chunks:
        if c["chunk_type"] == "table":
            print(f"\n[Table Preview from {c['doc_name']} p.{c['page_number']}]")
            print(c["text"])
            print(f"BBox: {c['bboxes'][0]}")
            break

    print("\n--- Step 2: Indexing into Local Qdrant + BM25 ---")
    print("(First run pe HuggingFace se ~900MB lightweight models download honge, thoda wait karna...)")
    retriever = HybridRetriever()
    retriever.index_documents(chunks, pages)

    print("\n--- Step 3: Testing Hybrid Multi-Document Search ---")
    for label, query in TEST_QUERIES:
        print(f"\n==========================================")
        print(f"{label}: {query}")
        print(f"==========================================")
        hits = retriever.search(query, top_k=3)
        for rank, h in enumerate(hits, start=1):
            snippet = h["text"].replace("\n", " ")[:150]
            print(
                f"  #{rank} [{h['doc_name']} | p.{h['page_number']} | {h['chunk_type']} | "
                f"score={h['rerank_score']}]"
            )
            print(f"     {snippet}...")

    retriever.close()
    print("\nPhase 2 COMPLETE! Agar saare queries me sahi PDFs aur tables upar aaye, toh Phase 3 start karein.")


if __name__ == "__main__":
    main()