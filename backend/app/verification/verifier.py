from typing import Any

from app.config import SUPPORTED_LANGUAGES
from app.llm.ollama_client import call_ollama_json
from app.verification.nli_checker import NLIChecker
from app.verification.quote_matcher import (
    QuoteMatcher,
    extract_numbers,
    table_to_readable_prose,
)


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "has_sufficient_evidence": {"type": "boolean"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "english_claim": {"type": "string"},
                    "doc_name": {"type": "string"},
                    "page_number": {"type": "integer"},
                    "verbatim_quote": {"type": "string"},
                },
                "required": [
                    "sentence",
                    "english_claim",
                    "doc_name",
                    "page_number",
                    "verbatim_quote",
                ],
            },
        },
        "missing_info": {"type": "string"},
    },
    "required": ["has_sufficient_evidence", "claims", "missing_info"],
}


BASE_SYSTEM_PROMPT = """You are a strict Zero-Guessing Document Verification Assistant for everyday citizens and auditors.
RULES YOU MUST NEVER BREAK:
1. Answer ONLY using facts explicitly stated in the provided EVIDENCE passages. NEVER guess or use outside knowledge.
2. AMENDMENT PRIORITY RULE: Each evidence header shows a STATUS tag ("ACTIVE" vs "SUPERSEDED"). When asked for the current/applicable rule, base your answer strictly on ACTIVE passages and NEVER state a SUPERSEDED value as currently active.
3. CONTRADICTION RULE: If two ACTIVE passages give conflicting numbers or rules for the same subject, do NOT pick only one side—state BOTH conflicting rules in separate claims, each citing its own document, page, and verbatim quote.
4. NEVER put negative/missing statements (like "X is not mentioned") inside "claims". Put missing gaps ONLY in "missing_info" and leave "claims": [] if nothing can be answered.
5. If the evidence DOES contain the answer (including percentages, rates, or table values), set "has_sufficient_evidence": true and return concise, simple atomic claims.
6. For EVERY claim inside "claims":
   - "sentence": one clear, simple, easy-to-understand factual sentence (avoid heavy legal jargon so even a common village citizen understands easily).
   - "english_claim": the exact English factual statement corresponding to "sentence" (if "sentence" is already English, copy it here).
   - "doc_name": exact filename from the evidence header (e.g., "DocC_Circular_2025.pdf").
   - "page_number": exact integer page number from the evidence header.
   - "verbatim_quote": copy-paste an EXACT verbatim substring directly from that evidence passage (never paraphrase or translate it). For tables, copy the exact table row.
7. Keep "missing_info" as an empty string "" if the question was fully answered by the evidence.
"""


def _language_instruction(language: str) -> str:
    if not language or language == "auto":
        return (
            "LANGUAGE RULE: Detect the user's question language. If the user asked in Hindi/Hinglish, "
            "write 'sentence' in simple everyday Hindi (Devanagari). If asked in Marathi, Bengali, Tamil, "
            "Telugu, Gujarati, Kannada, or Punjabi, write 'sentence' in that language's native script. "
            "Otherwise write 'sentence' in simple English. ALWAYS keep 'english_claim' and 'verbatim_quote' in English."
            "Always keep digits in standard numerals like 30,000 and 11.25%."
        )
    lang_label = SUPPORTED_LANGUAGES.get(language, "English")
    return (
        f"LANGUAGE RULE: You MUST write every 'sentence' and 'missing_info' in simple, everyday {lang_label} "
        f"(using its native script if non-English) so a common citizen can easily read it. "
        f"ALWAYS keep 'english_claim' and 'verbatim_quote' in original English for verification."
    )


class ZeroGuessingVerifier:
    def __init__(
        self,
        quote_matcher: QuoteMatcher | None = None,
        nli_checker: NLIChecker | None = None,
    ):
        self.quote_matcher = quote_matcher or QuoteMatcher()
        self.nli = nli_checker or NLIChecker()

    def _format_evidence(self, chunks: list[dict[str, Any]]) -> str:
        blocks = []
        for idx, ch in enumerate(chunks, start=1):
            status_tag = f" | STATUS: {ch['status']}" if "status" in ch else ""
            blocks.append(
                f"--- EVIDENCE {idx} | doc_name: {ch['doc_name']} | page_number: {ch['page_number']}{status_tag} ---\n"
                f"{ch['text']}"
            )
        return "\n\n".join(blocks)

    def _check_numbers_grounded(self, claim_text: str, source_text: str) -> tuple[bool, list[str]]:
        claim_nums = extract_numbers(claim_text)
        if not claim_nums:
            return True, []
        source_nums = extract_numbers(source_text)
        missing = sorted(claim_nums - source_nums)
        return len(missing) == 0, missing

    def generate_and_verify(
        self,
        question: str,
        retrieved_chunks: list[dict[str, Any]],
        language: str = "auto",
        min_rerank_score: float = -6.0,
    ) -> dict[str, Any]:
        if not retrieved_chunks:
            return self._abstention_response(
                missing_info="No relevant passages were found in the uploaded documents.",
                blocked_claims=[],
                language=language,
            )

        top_score = retrieved_chunks[0].get("rerank_score", 0.0)
        if top_score < min_rerank_score:
            return self._abstention_response(
                missing_info="The uploaded documents do not contain any clauses matching your question.",
                blocked_claims=[],
                language=language,
            )

        evidence_text = self._format_evidence(retrieved_chunks)
        system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n{_language_instruction(language)}"
        user_prompt = (
            f"USER QUESTION:\n{question}\n\n"
            f"EVIDENCE PASSAGES:\n{evidence_text}\n\n"
            f"Return JSON strictly following the schema."
        )

        draft = call_ollama_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=ANSWER_SCHEMA,
        )

        raw_claims = draft.get("claims", [])
        missing_info = (draft.get("missing_info") or "").strip()

        if not draft.get("has_sufficient_evidence", False) and not raw_claims:
            return self._abstention_response(
                missing_info=missing_info
                or "The documents do not contain sufficient evidence to answer this question.",
                blocked_claims=[],
                language=language,
            )

        verified_claims = []
        blocked_claims = []

        for claim in raw_claims:
            sentence = claim.get("sentence", "").strip()
            english_claim = (claim.get("english_claim") or sentence).strip()
            doc_name = claim.get("doc_name", "").strip()
            page_number = int(claim.get("page_number", 0))
            verbatim_quote = claim.get("verbatim_quote", "").strip()

            # Gate 1: Verbatim Quote Match
            q_check = self.quote_matcher.verify_quote(
                doc_name=doc_name,
                page_number=page_number,
                verbatim_quote=verbatim_quote,
            )

            readable_chunk = table_to_readable_prose(q_check["matched_chunk_text"] or verbatim_quote)
            nli_premise = f"Document: {q_check['doc_title']}. {readable_chunk}"

            # Gate 2: Deterministic Numeric Guard (check english_claim digits against source)
            nums_ok, missing_nums = self._check_numbers_grounded(
                claim_text=english_claim,
                source_text=f"{verbatim_quote} {q_check['matched_chunk_text']}",
            )

            # Gate 3: NLI Entailment Check
            if q_check["matched"]:
                entailed_en, scores_en = self.nli.is_entailed(
                    quote=nli_premise,
                    claim=english_claim,
                )
                entailed = entailed_en
                nli_scores = scores_en
            else:
                entailed = False
                nli_scores = {"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0}

            enriched_claim = {
                "sentence": sentence,
                "english_claim": english_claim,
                "doc_name": doc_name,
                "page_number": page_number,
                "verbatim_quote": verbatim_quote,
                "quote_match_score": q_check["score"],
                "nli_scores": nli_scores,
                "bboxes": q_check["bboxes"],
                "page_width": q_check["page_width"],
                "page_height": q_check["page_height"],
            }

            if q_check["matched"] and nums_ok and entailed:
                verified_claims.append(enriched_claim)
            else:
                reasons = []
                if not q_check["matched"]:
                    reasons.append(
                        f"Quote verification failed ({q_check['score']}%): {q_check['reason']}"
                    )
                if not nums_ok:
                    reasons.append(f"Unverified numbers in claim: {missing_nums}")
                if q_check["matched"] and not entailed:
                    reasons.append(
                        f"NLI entailment too low (entail={nli_scores['entailment']}, contra={nli_scores['contradiction']})"
                    )
                enriched_claim["block_reason"] = "; ".join(reasons)
                blocked_claims.append(enriched_claim)

        total_draft_claims = len(raw_claims)
        verified_count = len(verified_claims)

        if verified_count == 0:
            reason = missing_info or (
                "Generated claims could not be verified against exact quotes in the provided documents."
            )
            return self._abstention_response(
                missing_info=reason,
                blocked_claims=blocked_claims,
                language=language,
            )

        faithfulness_pct = round((verified_count / max(total_draft_claims, 1)) * 100.0, 1)
        final_answer = " ".join(c["sentence"] for c in verified_claims)

        return {
            "abstained": False,
            "answer": final_answer,
            "verified_claims": verified_claims,
            "blocked_claims": blocked_claims,
            "missing_info": missing_info,
            "faithfulness": {
                "score_percent": faithfulness_pct,
                "verified_sentences": verified_count,
                "total_draft_sentences": total_draft_claims,
                "displayed_backed_percent": 100.0,
            },
        }

    def _abstention_response(
        self,
        missing_info: str,
        blocked_claims: list[dict],
        language: str = "auto",
    ) -> dict[str, Any]:
        if language == "hi":
            prefix = "मेरे पास अपलोड किए गए दस्तावेज़ों में इसका पक्का सबूत नहीं है। अधूरी जानकारी:"
        elif language == "mr":
            prefix = "अपलोड केलेल्या कागदपत्रांमध्ये याचा पुरेसा पुरावा नाही. गहाळ माहिती:"
        else:
            prefix = "I don't have enough proof in the provided documents to answer this question. Missing evidence:"

        return {
            "abstained": True,
            "answer": f"{prefix} {missing_info}",
            "verified_claims": [],
            "blocked_claims": blocked_claims,
            "missing_info": missing_info,
            "faithfulness": {
                "score_percent": 0.0,
                "verified_sentences": 0,
                "total_draft_sentences": len(blocked_claims),
                "displayed_backed_percent": 100.0,
            },
        }