import re
from pathlib import Path
from typing import Any
import pdfplumber
import pymupdf


HEADING_PATTERN = re.compile(
    r"^(Section\s+\d+|Clause\s+\d+(\.\d+)?|Amendment\s+to|Subject:|Unchanged\s+Provisions|Retention\s+of)",
    re.IGNORECASE,
)


def table_to_markdown(rows: list[list[Any]]) -> str:
    """Extracted PDF table rows ko clean Markdown table me convert karta hai."""
    if not rows:
        return ""

    cleaned_rows = []
    for row in rows:
        cleaned = [
            " ".join(str(cell).split()) if cell is not None else ""
            for cell in row
        ]
        if any(cleaned):
            cleaned_rows.append(cleaned)

    if not cleaned_rows:
        return ""

    header = cleaned_rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for row in cleaned_rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
    return "\n".join(lines)


def is_inside_any_box(block_bbox: tuple, table_bboxes: list[tuple]) -> bool:
    """Check karta hai ki kya ye text block kisi already-extracted table ke andar hai."""
    b_rect = pymupdf.Rect(block_bbox)
    b_area = b_rect.get_area()
    if b_area <= 0:
        return False

    for t_bbox in table_bboxes:
        t_rect = pymupdf.Rect(t_bbox)
        inter = b_rect & t_rect
        if inter.get_area() / b_area > 0.5:
            return True
    return False


def is_heading(text: str) -> bool:
    """Detect karta hai ki text block ek clause/section heading hai ya normal paragraph."""
    single_line = " ".join(text.split())
    if HEADING_PATTERN.match(single_line):
        return True
    if len(single_line) < 85 and not single_line.endswith(".") and "Document ID:" not in single_line:
        return True
    return False


def parse_pdf(pdf_path: Path) -> tuple[list[dict], list[dict]]:
    """
    Single PDF ko parse karta hai:
      - Tables: pdfplumber (exact decimals, commas aur spaces preserve karne ke liye)
      - Text + BBoxes: PyMuPDF
    """
    doc = pymupdf.open(pdf_path)
    plumber_doc = pdfplumber.open(pdf_path)
    doc_name = pdf_path.name
    chunks: list[dict] = []
    pages: list[dict] = []
    chunk_counter = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        p_page = plumber_doc.pages[page_index]
        page_num = page_index + 1
        page_w = round(page.rect.width, 2)
        page_h = round(page.rect.height, 2)

        # Raw page text (pdfplumber ka text spacing zyada clean hota hai)
        raw_page_text = (p_page.extract_text() or page.get_text("text")).strip()
        pages.append(
            {
                "doc_name": doc_name,
                "page_number": page_num,
                "page_width": page_w,
                "page_height": page_h,
                "raw_text": raw_page_text,
            }
        )

        # 1. pdfplumber se exact tables + unke bounding boxes nikalo
        table_items = []
        table_bboxes = []
        for tbl in p_page.find_tables():
            md = table_to_markdown(tbl.extract())
            if md:
                bbox = [round(v, 2) for v in tbl.bbox]
                table_bboxes.append(tbl.bbox)
                table_items.append(
                    {
                        "type": "table",
                        "y0": tbl.bbox[1],
                        "bbox": bbox,
                        "text": md,
                    }
                )

        # 2. Non-table text blocks nikalo (PyMuPDF words se clean spaces ke saath)
        text_items = []
        for b in page.get_text("blocks", sort=True):
            x0, y0, x1, y1, text, _, block_type = b
            if block_type != 0:
                continue
            clean_text = " ".join(text.split())
            if not clean_text:
                continue
            if is_inside_any_box((x0, y0, x1, y1), table_bboxes):
                continue
            text_items.append(
                {
                    "type": "text",
                    "y0": y0,
                    "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    "text": clean_text,
                }
            )

        # 3. Top-to-bottom reading order me sort karo
        all_items = sorted(text_items + table_items, key=lambda item: item["y0"])

        # 4. Clause-aware chunking
        current_title = "Document Header"
        current_texts: list[str] = []
        current_bboxes: list[list[float]] = []

        def flush_text_chunk():
            nonlocal chunk_counter, current_texts, current_bboxes
            if not current_texts:
                return
            combined = "\n".join(current_texts).strip()
            chunks.append(
                {
                    "chunk_id": f"{doc_name}::p{page_num}::c{chunk_counter}",
                    "doc_name": doc_name,
                    "page_number": page_num,
                    "page_width": page_w,
                    "page_height": page_h,
                    "section_title": current_title,
                    "chunk_type": "text",
                    "text": combined,
                    "bboxes": current_bboxes,
                }
            )
            chunk_counter += 1
            current_texts = []
            current_bboxes = []

        for item in all_items:
            if item["type"] == "table":
                if len(current_texts) > 1 or (
                    len(current_texts) == 1 and not is_heading(current_texts[0])
                ):
                    flush_text_chunk()
                    table_text = f"{current_title}\n{item['text']}"
                    table_bboxes_list = [item["bbox"]]
                else:
                    prefix = "\n".join(current_texts)
                    table_text = f"{prefix}\n{item['text']}".strip()
                    table_bboxes_list = current_bboxes + [item["bbox"]]
                    current_texts = []
                    current_bboxes = []

                chunks.append(
                    {
                        "chunk_id": f"{doc_name}::p{page_num}::c{chunk_counter}",
                        "doc_name": doc_name,
                        "page_number": page_num,
                        "page_width": page_w,
                        "page_height": page_h,
                        "section_title": current_title,
                        "chunk_type": "table",
                        "text": table_text,
                        "bboxes": table_bboxes_list,
                    }
                )
                chunk_counter += 1
            else:
                text = item["text"]
                if is_heading(text) and current_texts:
                    flush_text_chunk()
                    current_title = text
                    current_texts = [text]
                    current_bboxes = [item["bbox"]]
                else:
                    if not current_texts and is_heading(text):
                        current_title = text
                    current_texts.append(text)
                    current_bboxes.append(item["bbox"])

        flush_text_chunk()

    plumber_doc.close()
    doc.close()
    return chunks, pages


def parse_folder(folder_path: Path) -> tuple[list[dict], list[dict]]:
    all_chunks: list[dict] = []
    all_pages: list[dict] = []
    for pdf_path in sorted(folder_path.glob("*.pdf")):
        chunks, pages = parse_pdf(pdf_path)
        all_chunks.extend(chunks)
        all_pages.extend(pages)
    return all_chunks, all_pages