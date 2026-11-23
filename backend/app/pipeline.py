import copy
import re
import time
from pathlib import Path
from typing import Any
from rapidfuzz import fuzz

from app.config import GROQ_MODEL, OLLAMA_MODEL
from app.ingestion.pdf_parser import parse_folder
from app.llm.ollama_client import ACTIVE_PROVIDER, get_effective_provider
from app.retrieval.amendment_graph import AmendmentGraph
from app.retrieval.hybrid_search import HybridRetriever
from app.verification.calculator import ClauseCalculator
from app.verification.contradiction_detector import ContradictionDetector
from app.verification.guardrails import check_input_guardrails
from app.verification.nli_checker import NLIChecker
from app.verification.quote_matcher import QuoteMatcher, normalize_text
from app.verification.verifier import ZeroGuessingVerifier


def decompose_query(question: str) -> list[str]:
    queries = [question.strip()]
    parts = re.split(r"\b(?:and|aur|और)\b", question, flags=re.IGNORECASE)
    if len(parts) > 1:
        for p in parts:
            cleaned = p.strip(" ?.,")
            if len(cleaned) >= 8:
                queries.append(cleaned)
    return queries


class DocumentAIPipeline:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.quote_matcher = QuoteMatcher()
        self.nli = NLIChecker()
        self.amendment_graph = AmendmentGraph()
        self.contradiction_detector = ContradictionDetector(
            nli_checker=self.nli,
            quote_matcher=self.quote_matcher,
            amendment_graph=self.amendment_graph,
        )
        self.calculator = ClauseCalculator(quote_matcher=self.quote_matcher)
        self.verifier = ZeroGuessingVerifier(
            quote_matcher=self.quote_matcher,
            nli_checker=self.nli,
        )
        self._query_cache: dict[tuple[str, str, str], dict[str, Any]] = {}

    def clear_cache(self):
        self._query_cache.clear()

    def ingest_folder(self, folder_path: Path) -> dict[str, Any]:
        """Full Ingestion: Parse PDFs -> Index Qdrant+BM25 -> Build Amendment Graph."""
        t0 = time.perf_counter()
        chunks, pages = parse_folder(folder_path)
        self.retriever.index_documents(chunks, pages)
        self.quote_matcher.reload()
        self.amendment_graph.build_graph(chunks, pages)
        self.clear_cache()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "documents_indexed": len(self.amendment_graph.docs),
            "pages_parsed": len(pages),
            "chunks_indexed": len(chunks),
            "amendment_chains": list(self.amendment_graph.clause_chains.keys()),
            "ingestion_ms": elapsed_ms,
        }

    def _multi_query_retrieve(self, question: str, top_k: int = 8) -> list[dict[str, Any]]:
        sub_queries = decompose_query(question)
        best_by_id: dict[str, dict[str, Any]] = {}

        for q in sub_queries:
            hits = self.retriever.search(q, top_k=top_k)
            for h in hits:
                cid = h["chunk_id"]
                if cid not in best_by_id or h["rerank_score"] > best_by_id[cid]["rerank_score"]:
                    best_by_id[cid] = h

        merged = sorted(
            best_by_id.values(),
            key=lambda x: x["rerank_score"],
            reverse=True,
        )
        return merged[:top_k]

    def ask(
        self,
        question: str,
        language: str = "auto",
        provider: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        End-to-End Guardrailed & Verification-First Query Pipeline with Live Telemetry.
        """
        t_start = time.perf_counter()
        effective_provider = get_effective_provider(provider)
        active_model = GROQ_MODEL if effective_provider == "groq" else OLLAMA_MODEL
        cache_key = (question.strip().lower(), language.lower(), effective_provider)

        # Fast Cache Path (< 5ms)
        if use_cache and cache_key in self._query_cache:
            cached = copy.deepcopy(self._query_cache[cache_key])
            cached["telemetry"]["cache_hit"] = True
            cached["telemetry"]["timing_ms"]["total"] = round((time.perf_counter() - t_start) * 1000, 1)
            return cached

        timing_ms: dict[str, float] = {}

        # STAGE 0: Input Guardrails (< 5ms, before any LLM call!)
        t0 = time.perf_counter()
        guard = check_input_guardrails(question, language=language)
        timing_ms["guardrails"] = round((time.perf_counter() - t0) * 1000, 1)

        if not guard["allowed"]:
            timing_ms["total"] = round((time.perf_counter() - t_start) * 1000, 1)
            return {
                "question": question,
                "language": language,
                "abstained": True,
                "answer": guard["message"],
                "faithfulness": {
                    "score_percent": 0.0,
                    "verified_sentences": 0,
                    "total_draft_sentences": 0,
                    "displayed_backed_percent": 100.0,
                },
                "verified_claims": [],
                "blocked_claims": [],
                "missing_info": f"Blocked by Input Guardrail ({guard['block_type']}).",
                "amendment_chains": [],
                "contradictions": [],
                "calculation": None,
                "guardrails": {
                    "status": "BLOCKED",
                    "block_type": guard["block_type"],
                    "warnings": guard["warnings"],
                    "checks": guard["checks"],
                },
                "telemetry": {
                    "provider": effective_provider,
                    "model": active_model,
                    "cache_hit": False,
                    "timing_ms": timing_ms,
                },
            }

        clean_question = guard["sanitized_question"]
        guard_checks = list(guard["checks"])

        # Set active provider context for all downstream open-source LLM calls
        token = ACTIVE_PROVIDER.set(effective_provider)
        try:
            # STAGE 1: Hybrid Multi-Doc Retrieval
            t1 = time.perf_counter()
            raw_chunks = self._multi_query_retrieve(clean_question, top_k=8)
            timing_ms["retrieval"] = round((time.perf_counter() - t1) * 1000, 1)

            # STAGE 2: Amendment Chain Resolution
            t2 = time.perf_counter()
            resolved_chunks, amendment_chains = self.amendment_graph.resolve_chunks(
                retrieved_chunks=raw_chunks,
                all_chunks_by_id=self.retriever.chunk_by_id,
            )
            timing_ms["amendment_graph"] = round((time.perf_counter() - t2) * 1000, 1)
            guard_checks.append({
                "name": "Amendment Lineage Guard",
                "status": "ACTIVE",
                "detail": f"{len(amendment_chains)} chain(s) resolved; superseded clauses tagged",
            })

            # STAGE 3: Active Contradiction Detection
            t3 = time.perf_counter()
            contradictions = self.contradiction_detector.detect(resolved_chunks)
            timing_ms["contradiction_audit"] = round((time.perf_counter() - t3) * 1000, 1)
            guard_checks.append({
                "name": "Contradiction Audit Guard",
                "status": "CONFLICT_FLAGGED" if contradictions else "PASSED",
                "detail": f"{len(contradictions)} active conflict(s) detected",
            })

            # STAGE 4: Deterministic Python Calculator Fast-Path
            t4 = time.perf_counter()
            calculation = self.calculator.try_calculate(clean_question, resolved_chunks)
            timing_ms["calculation"] = round((time.perf_counter() - t4) * 1000, 1)

            if calculation:
                cit = calculation["citation"]
                if language == "hi":
                    calc_sentence = (
                        f"{cit['doc_name']} (पेज {cit['page_number']}) के सक्रिय नियम के अनुसार, "
                        f"आपकी {calculation['operation']} का सटीक मान {calculation['result']} है।"
                    )
                elif language == "mr":
                    calc_sentence = (
                        f"{cit['doc_name']} (पान {cit['page_number']}) मधील सक्रिय नियमानुसार, "
                        f"तुमची {calculation['operation']} अचूक {calculation['result']} आहे."
                    )
                else:
                    calc_sentence = (
                        f"Based on the verified active rule in {cit['doc_name']} (Page {cit['page_number']}), "
                        f"the calculated {calculation['operation']} is {calculation['result']}."
                    )

                guard_checks.append({
                    "name": "Deterministic Math Guard",
                    "status": "PASSED",
                    "detail": "Computed via Python formula engine (zero LLM mental math)",
                })
                timing_ms["total"] = round((time.perf_counter() - t_start) * 1000, 1)

                result = {
                    "question": question,
                    "language": language,
                    "abstained": False,
                    "answer": calc_sentence,
                    "faithfulness": {
                        "score_percent": 100.0,
                        "verified_sentences": 1,
                        "total_draft_sentences": 1,
                        "displayed_backed_percent": 100.0,
                    },
                    "verified_claims": [
                        {
                            "sentence": calc_sentence,
                            "english_claim": calc_sentence,
                            "doc_name": cit["doc_name"],
                            "page_number": cit["page_number"],
                            "verbatim_quote": cit["verbatim_quote"],
                            "quote_match_score": 100.0,
                            "nli_scores": {"entailment": 1.0, "neutral": 0.0, "contradiction": 0.0},
                            "bboxes": cit["bboxes"],
                            "page_width": cit["page_width"],
                            "page_height": cit["page_height"],
                        }
                    ],
                    "blocked_claims": [],
                    "missing_info": "",
                    "amendment_chains": amendment_chains,
                    "contradictions": contradictions,
                    "calculation": calculation,
                    "guardrails": {
                        "status": "PASSED",
                        "block_type": None,
                        "warnings": guard["warnings"],
                        "checks": guard_checks,
                    },
                    "telemetry": {
                        "provider": effective_provider,
                        "model": active_model,
                        "cache_hit": False,
                        "timing_ms": timing_ms,
                    },
                }
                if use_cache:
                    self._query_cache[cache_key] = copy.deepcopy(result)
                return result

            # STAGE 5: LLM Structured Generation + 3-Layer Verification Gate
            t5 = time.perf_counter()
            # Keep context compact (Top 5) for low latency + high precision
            context_for_llm = resolved_chunks[:5]
            verification_result = self.verifier.generate_and_verify(
                question=clean_question,
                retrieved_chunks=context_for_llm,
                language=language,
            )
            timing_ms["llm_and_verification"] = round((time.perf_counter() - t5) * 1000, 1)

            # STAGE 6: Contradiction-Safe Blocking Gate
            if contradictions:
                still_verified = []
                extra_blocked = list(verification_result["blocked_claims"])

                for cl in verification_result["verified_claims"]:
                    is_contradicted = False
                    conflict_note = ""
                    for c in contradictions:
                        sa, sb = c["source_a"], c["source_b"]
                        cl_norm = normalize_text(f"{cl['verbatim_quote']} {cl.get('english_claim', '')}")
                        sa_norm = normalize_text(sa["verbatim_quote"])
                        sb_norm = normalize_text(sb["verbatim_quote"])

                        matches_a = (
                            cl["doc_name"] == sa["doc_name"]
                            and cl["page_number"] == sa["page_number"]
                            and fuzz.partial_ratio(cl_norm, sa_norm) >= 60
                        )
                        matches_b = (
                            cl["doc_name"] == sb["doc_name"]
                            and cl["page_number"] == sb["page_number"]
                            and fuzz.partial_ratio(cl_norm, sb_norm) >= 60
                        )
                        if matches_a or matches_b:
                            is_contradicted = True
                            conflict_note = (
                                f"Contradicted by active conflict on '{c['subject']}' "
                                f"({sa['doc_name']} p.{sa['page_number']} vs {sb['doc_name']} p.{sb['page_number']})"
                            )
                            break

                    if is_contradicted:
                        blocked_copy = dict(cl)
                        blocked_copy["block_reason"] = conflict_note
                        extra_blocked.append(blocked_copy)
                    else:
                        still_verified.append(cl)

                verification_result["verified_claims"] = still_verified
                verification_result["blocked_claims"] = extra_blocked

                total_claims = len(still_verified) + len(extra_blocked)
                if not still_verified:
                    verification_result["abstained"] = True
                    if language == "hi":
                        verification_result["answer"] = (
                            "सावधान! दो सक्रिय दस्तावेज़ों में एक ही नियम पर अलग-अलग जानकारी लिखी है, "
                            "इसलिए कोई एक उत्तर नहीं माना जा सकता। नीचे दोनों दस्तावेज़ों के सबूत आमने-सामने देखें।"
                        )
                    elif language == "mr":
                        verification_result["answer"] = (
                            "सावधान! दोन सक्रिय कागदपत्रांमध्ये एकाच नियमाबाबत वेगळी माहिती आहे, "
                            "त्यामुळे एकच उत्तर देता येणार नाही. खाली दोन्ही पुरावे समोरासमोर पहा."
                        )
                    else:
                        verification_result["answer"] = (
                            "Cannot state a single definitive rule because active documents contradict each other. "
                            "Conflicting claims were blocked—review the side-by-side Contradiction Alerts below."
                        )
                    verification_result["missing_info"] = (
                        "A governing precedence clause or amendment circular is missing to resolve which active document overrides the other."
                    )
                    verification_result["faithfulness"] = {
                        "score_percent": 0.0,
                        "verified_sentences": 0,
                        "total_draft_sentences": total_claims,
                        "displayed_backed_percent": 100.0,
                    }
                else:
                    verification_result["answer"] = " ".join(c["sentence"] for c in still_verified)
                    verification_result["faithfulness"] = {
                        "score_percent": round((len(still_verified) / max(total_claims, 1)) * 100.0, 1),
                        "verified_sentences": len(still_verified),
                        "total_draft_sentences": total_claims,
                        "displayed_backed_percent": 100.0,
                    }

            guard_checks.append({
                "name": "3-Layer Output Verification Gate",
                "status": "ABSTAINED" if verification_result["abstained"] else "VERIFIED",
                "detail": (
                    f"Verified {verification_result['faithfulness']['verified_sentences']} | "
                    f"Blocked {len(verification_result['blocked_claims'])} claim(s)"
                ),
            })

            timing_ms["total"] = round((time.perf_counter() - t_start) * 1000, 1)

            result = {
                "question": question,
                "language": language,
                "abstained": verification_result["abstained"],
                "answer": verification_result["answer"],
                "faithfulness": verification_result["faithfulness"],
                "verified_claims": verification_result["verified_claims"],
                "blocked_claims": verification_result["blocked_claims"],
                "missing_info": verification_result["missing_info"],
                "amendment_chains": amendment_chains,
                "contradictions": contradictions,
                "calculation": None,
                "guardrails": {
                    "status": "ABSTAINED" if verification_result["abstained"] else "PASSED",
                    "block_type": "contradiction_blocked" if (contradictions and verification_result["abstained"]) else None,
                    "warnings": guard["warnings"],
                    "checks": guard_checks,
                },
                "telemetry": {
                    "provider": effective_provider,
                    "model": active_model,
                    "cache_hit": False,
                    "timing_ms": timing_ms,
                },
            }

            if use_cache:
                self._query_cache[cache_key] = copy.deepcopy(result)
            return result
        finally:
            ACTIVE_PROVIDER.reset(token)

    def close(self):
        self.retriever.close()