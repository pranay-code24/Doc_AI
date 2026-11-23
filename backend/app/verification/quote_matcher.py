import json
import re
from typing import Any
from rapidfuzz import fuzz

from app.config import CHUNKS_FILE, PAGES_FILE


def normalize_text(text: str) -> str:
    """Matching ke liye pipes, commas, colons aur extra symbols normalize karta hai."""
    text = text.lower()
    # Numbers ke beech ka comma hatao (e.g., 30,000 -> 30000)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    # Baaki punctuation ko space banao (decimal dot aur % bachake rakho)
    text = re.sub(r"[^a-z0-9.%]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def table_to_readable_prose(chunk_text: str) -> str:
    """
    Markdown table rows ko clean readable sentences me convert karta hai
    taaki NLI model (mDeBERTa-v3) tables ko 100% accurately verify kar sake.
    """
    lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
    output_parts: list[str] = []
    headers: list[str] = []

    for line in lines:
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Separator row (| --- | --- |) skip karo
            if all(re.fullmatch(r"-+", c.replace(" ", "")) for c in cells if c):
                continue
            if not headers:
                headers = cells
            else:
                pairs = [
                    f"{h}: {v}"
                    for h, v in zip(headers, cells)
                    if v
                ]
                if pairs:
                    output_parts.append("; ".join(pairs) + ".")
        else:
            headers = []
            output_parts.append(line)

    return " ".join(output_parts)


def extract_numbers(text: str) -> set[str]:
    """Text se saare numeric tokens nikalkar normalize karta hai (e.g., 3.0% -> 3%, 30,000 -> 30000)."""
    cleaned = re.sub(r"(?<=\d),(?=\d)", "", text)
    raw_nums = re.findall(r"\d+(?:\.\d+)?%?", cleaned)
    normalized = set()
    for token in raw_nums:
        is_pct = token.endswith("%")
        num_str = token[:-1] if is_pct else token
        try:
            val = float(num_str)
            # 3.0 -> "3", 1.5 -> "1.5", 11.25 -> "11.25"
            canonical = f"{val:g}"
            normalized.add(f"{canonical}%" if is_pct else canonical)
        except ValueError:
            normalized.add(token)
    return normalized


class QuoteMatcher:
    def __init__(self):
        self.pages_map: dict[tuple[str, int], dict] = {}
        self.chunks_by_page: dict[tuple[str, int], list[dict]] = {}
        self.doc_titles: dict[str, str] = {}
        self.reload()

    def reload(self):
        self.pages_map = {}
        self.chunks_by_page = {}
        self.doc_titles = {}

        if PAGES_FILE.exists():
            pages = json.loads(PAGES_FILE.read_text(encoding="utf-8"))
            for p in pages:
                key = (p["doc_name"], int(p["page_number"]))
                self.pages_map[key] = p
                if int(p["page_number"]) == 1:
                    first_line = p["raw_text"].strip().splitlines()[0] if p["raw_text"].strip() else p["doc_name"]
                    self.doc_titles[p["doc_name"]] = first_line

        if CHUNKS_FILE.exists():
            chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
            for c in chunks:
                key = (c["doc_name"], int(c["page_number"]))
                self.chunks_by_page.setdefault(key, []).append(c)

    def verify_quote(
        self,
        doc_name: str,
        page_number: int,
        verbatim_quote: str,
        threshold: float = 82.0,
    ) -> dict[str, Any]:
        """
        Verify karta hai ki verbatim_quote sach me (doc_name, page_number) par exist karta hai.
        Saath hi matched chunk text aur document title return karta hai NLI check ke liye.
        """
        quote_clean = normalize_text(verbatim_quote)
        if len(quote_clean) < 6:
            return {
                "matched": False,
                "score": 0.0,
                "reason": "Quote too short or empty",
                "bboxes": [],
                "page_width": 0,
                "page_height": 0,
                "matched_chunk_text": "",
                "doc_title": "",
            }

        key = (doc_name, int(page_number))
        page_info = self.pages_map.get(key)
        page_chunks = self.chunks_by_page.get(key, [])

        if not page_info and not page_chunks:
            return {
                "matched": False,
                "score": 0.0,
                "reason": f"Document/page not found: {doc_name} p.{page_number}",
                "bboxes": [],
                "page_width": 0,
                "page_height": 0,
                "matched_chunk_text": "",
                "doc_title": "",
            }

        best_score = 0.0
        best_bboxes: list[list[float]] = []
        best_chunk_text = ""

        # 1. Raw page text check
        if page_info:
            raw_norm = normalize_text(page_info["raw_text"])
            if quote_clean in raw_norm:
                best_score = 100.0
            else:
                best_score = max(best_score, float(fuzz.partial_ratio(quote_clean, raw_norm)))

        # 2. Best matching chunk dhundho (exact bboxes + NLI premise context ke liye)
        best_chunk_score = 0.0
        for ch in page_chunks:
            ch_norm = normalize_text(ch["text"])
            if quote_clean in ch_norm:
                score = 100.0
            else:
                score = max(
                    float(fuzz.partial_ratio(quote_clean, ch_norm)),
                    float(fuzz.token_set_ratio(quote_clean, ch_norm)) if len(quote_clean) >= 15 else 0.0,
                )
            if score > best_chunk_score:
                best_chunk_score = score
                best_bboxes = ch.get("bboxes", [])
                best_chunk_text = ch["text"]

        best_score = max(best_score, best_chunk_score)
        matched = best_score >= threshold

        return {
            "matched": matched,
            "score": round(best_score, 2),
            "reason": "Exact/fuzzy match verified" if matched else "Quote not found verbatim on cited page",
            "bboxes": best_bboxes if matched else [],
            "page_width": page_info["page_width"] if page_info else 0,
            "page_height": page_info["page_height"] if page_info else 0,
            "matched_chunk_text": best_chunk_text if matched else "",
            "doc_title": self.doc_titles.get(doc_name, doc_name),
        }