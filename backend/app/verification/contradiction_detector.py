import re
from itertools import combinations
from typing import Any

from app.llm.ollama_client import call_ollama_json
from app.retrieval.amendment_graph import AmendmentGraph
from app.verification.nli_checker import NLIChecker
from app.verification.quote_matcher import QuoteMatcher, extract_numbers


CONTRADICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "has_contradiction": {"type": "boolean"},
        "subject": {"type": "string"},
        "conflict_type": {
            "type": "string",
            "enum": ["numeric", "date", "eligibility", "rule", "none"],
        },
        "explanation": {"type": "string"},
        "quote_a": {"type": "string"},
        "quote_b": {"type": "string"},
    },
    "required": [
        "has_contradiction",
        "subject",
        "conflict_type",
        "explanation",
        "quote_a",
        "quote_b",
    ],
}


CONTRADICTION_SYSTEM_PROMPT = """You are a strict compliance auditor detecting contradictions between two ACTIVE policy clauses.
A TRUE CONTRADICTION exists ONLY when Passage A and Passage B state INCOMPATIBLE numbers, limits, eligibility conditions, or rules for the EXACT SAME specific rule (e.g., maximum tenure = 60 months vs maximum tenure = 48 months; OR minimum age = 21 years vs minimum age = 25 years).

STRICTLY NOT A CONTRADICTION (set has_contradiction = false):
- Comparing a circular's effective date (e.g., "April 1, 2025") with a loan tenure or fee rule.
- Comparing two different policy rules (e.g., interest rate vs repayment tenure, or age vs income).
- Two passages stating the exact same value (e.g., both say INR 30,000).
- One passage providing general scope/preamble while another gives a specific limit.

If a true contradiction exists:
- Set "has_contradiction": true
- Provide exact verbatim substrings from Passage A in "quote_a" and Passage B in "quote_b" showing the direct conflict.
If NO true contradiction exists:
- Set "has_contradiction": false, "conflict_type": "none", "quote_a": "", "quote_b": "".
"""


SKIP_TITLES_RE = re.compile(
    r"^(Document Header|Subject:|Section\s+1|Unchanged\s+Provisions|Note:)",
    re.IGNORECASE,
)

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "have", "shall", "must",
    "under", "loan", "loans", "retail", "personal", "policy", "applicant", "applicants",
    "bank", "apex", "national", "clause", "section", "document", "effective",
    "date", "dates", "all", "any", "not", "are", "was", "were", "per", "inr",
    "circular", "amends", "amended", "amendment", "first", "second", "below",
    "changes", "effect", "take", "takes", "applicable", "standard", "provisions",
    "terms", "guidelines", "basis", "hereby", "superseded", "previously",
}


def content_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


class ContradictionDetector:
    def __init__(
        self,
        nli_checker: NLIChecker,
        quote_matcher: QuoteMatcher,
        amendment_graph: AmendmentGraph,
    ):
        self.nli = nli_checker
        self.quote_matcher = quote_matcher
        self.amendment_graph = amendment_graph

    def _is_candidate_pair(self, c1: dict[str, Any], c2: dict[str, Any]) -> tuple[bool, float]:
        """Fast pre-filter: sirf genuine same-topic active clause pairs ko LLM tak bhejo."""
        if len(c1["text"]) < 45 or len(c2["text"]) < 45:
            return False, 0.0

        # Skip headers, preamble, subject summaries
        if SKIP_TITLES_RE.match(c1.get("section_title", "")) or SKIP_TITLES_RE.match(
            c2.get("section_title", "")
        ):
            return False, 0.0

        # Formal amendment relationship wale docs ko skip karo
        if self.amendment_graph.are_amendment_related(c1["doc_name"], c2["doc_name"]):
            return False, 0.0

        # Topic overlap check (at least 2 specific domain keywords common hone chahiye)
        kw1 = content_keywords(c1["text"])
        kw2 = content_keywords(c2["text"])
        shared_kw = kw1 & kw2
        if len(shared_kw) < 2:
            return False, 0.0

        nums1 = extract_numbers(c1["text"])
        nums2 = extract_numbers(c2["text"])
        has_numeric_diff = bool(nums1 and nums2 and nums1 != nums2)

        # Bidirectional NLI contradiction check
        nli_ab = self.nli.predict(premise=c1["text"], hypothesis=c2["text"])
        nli_ba = self.nli.predict(premise=c2["text"], hypothesis=c1["text"])
        max_contra = max(nli_ab["contradiction"], nli_ba["contradiction"])

        if max_contra >= 0.50 or (has_numeric_diff and (max_contra >= 0.12 or len(shared_kw) >= 3)):
            return True, max_contra
        return False, max_contra

    def detect(self, resolved_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Sirf top relevant ACTIVE chunks ke beech contradictions detect karta hai.
        """
        active_chunks = [
            c
            for c in resolved_chunks
            if c.get("is_active", True) and c.get("rerank_score", 0.0) >= -2.5
        ][:6]

        if len(active_chunks) < 2:
            return []

        contradictions: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for c1, c2 in combinations(active_chunks, 2):
            if c1["doc_name"] == c2["doc_name"] and c1["page_number"] == c2["page_number"]:
                continue

            pair_key = tuple(sorted([c1["chunk_id"], c2["chunk_id"]]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            is_cand, nli_contra_score = self._is_candidate_pair(c1, c2)
            if not is_cand:
                continue

            user_prompt = (
                f"PASSAGE A ({c1['doc_name']}, Page {c1['page_number']}):\n{c1['text']}\n\n"
                f"PASSAGE B ({c2['doc_name']}, Page {c2['page_number']}):\n{c2['text']}\n\n"
                f"Do Passage A and Passage B state incompatible rules/numbers for the EXACT SAME policy rule?"
            )

            verdict = call_ollama_json(
                system_prompt=CONTRADICTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                json_schema=CONTRADICTION_SCHEMA,
            )

            if not verdict.get("has_contradiction"):
                continue

            quote_a = (verdict.get("quote_a") or "").strip()
            quote_b = (verdict.get("quote_b") or "").strip()

            check_a = self.quote_matcher.verify_quote(c1["doc_name"], c1["page_number"], quote_a)
            check_b = self.quote_matcher.verify_quote(c2["doc_name"], c2["page_number"], quote_b)

            if not check_a["matched"]:
                quote_a = c1["text"]
                check_a = self.quote_matcher.verify_quote(c1["doc_name"], c1["page_number"], quote_a)
            if not check_b["matched"]:
                quote_b = c2["text"]
                check_b = self.quote_matcher.verify_quote(c2["doc_name"], c2["page_number"], quote_b)

            if check_a["matched"] and check_b["matched"]:
                contradictions.append(
                    {
                        "subject": verdict.get("subject", "Conflicting Rule"),
                        "conflict_type": verdict.get("conflict_type", "rule"),
                        "explanation": verdict.get("explanation", ""),
                        "nli_contradiction_score": round(nli_contra_score, 4),
                        "source_a": {
                            "doc_name": c1["doc_name"],
                            "page_number": c1["page_number"],
                            "verbatim_quote": quote_a,
                            "bboxes": check_a["bboxes"],
                            "page_width": check_a["page_width"],
                            "page_height": check_a["page_height"],
                        },
                        "source_b": {
                            "doc_name": c2["doc_name"],
                            "page_number": c2["page_number"],
                            "verbatim_quote": quote_b,
                            "bboxes": check_b["bboxes"],
                            "page_width": check_b["page_width"],
                            "page_height": check_b["page_height"],
                        },
                    }
                )

        return contradictions