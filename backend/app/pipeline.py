import re
from pathlib import Path
from typing import Any

from app.ingestion.pdf_parser import parse_folder
from app.retrieval.amendment_graph import AmendmentGraph
from app.retrieval.hybrid_search import HybridRetriever
from app.verification.calculator import ClauseCalculator
from app.verification.contradiction_detector import ContradictionDetector
from app.verification.nli_checker import NLIChecker
from app.verification.quote_matcher import QuoteMatcher
from app.verification.verifier import ZeroGuessingVerifier


def decompose_query(question: str) -> list[str]:
    """
    Agar question me 'and' / 'aur' se do topics jude hain, toh sub-queries banao
    taaki dono topics ke saare multi-document chunks retrieve hon.
    """
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

    def ingest_folder(self, folder_path: Path) -> dict[str, Any]:
        """Full Ingestion: Parse PDFs -> Index Qdrant+BM25 -> Build Amendment Graph."""
        chunks, pages = parse_folder(folder_path)
        self.retriever.index_documents(chunks, pages)
        self.quote_matcher.reload()
        self.amendment_graph.build_graph(chunks, pages)
        return {
            "documents_indexed": len(self.amendment_graph.docs),
            "pages_parsed": len(pages),
            "chunks_indexed": len(chunks),
            "amendment_chains": list(self.amendment_graph.clause_chains.keys()),
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

    def ask(self, question: str) -> dict[str, Any]:
        """
        End-to-End Verification-First Query Pipeline:
        1. Hybrid Multi-Doc Retrieval (with sub-query decomposition)
        2. Amendment Chain Resolution (A -> B -> C, ACTIVE vs SUPERSEDED)
        3. Active Contradiction Detection (side-by-side verified quotes)
        4. Deterministic Clause Calculation (EMI / Penalty / Fees)
        5. Zero-Guessing Claim Verification & Faithfulness Score
        """
        # 1. Retrieve
        raw_chunks = self._multi_query_retrieve(question, top_k=8)

        # 2. Resolve Amendment Chains
        resolved_chunks, amendment_chains = self.amendment_graph.resolve_chunks(
            retrieved_chunks=raw_chunks,
            all_chunks_by_id=self.retriever.chunk_by_id,
        )

        # 3. Detect Contradictions among ACTIVE chunks
        contradictions = self.contradiction_detector.detect(resolved_chunks)

        # 4. Try Deterministic Calculation (if applicable)
        calculation = self.calculator.try_calculate(question, resolved_chunks)
        if calculation:
            cit = calculation["citation"]
            calc_sentence = (
                f"Based on the verified active rule in {cit['doc_name']} (Page {cit['page_number']}), "
                f"the calculated {calculation['operation']} is {calculation['result']}."
            )
            return {
                "question": question,
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
            }

        # 5. Generate & Verify Claims
        context_for_llm = resolved_chunks[:6]
        verification_result = self.verifier.generate_and_verify(
            question=question,
            retrieved_chunks=context_for_llm,
        )

        # 6. Contradiction-Safe Blocking Gate:
        # Problem Statement rule: If a claim is contradicted by another active clause, BLOCK it!
        if contradictions:
            still_verified = []
            extra_blocked = list(verification_result["blocked_claims"])

            for cl in verification_result["verified_claims"]:
                is_contradicted = False
                conflict_note = ""
                for c in contradictions:
                    sa, sb = c["source_a"], c["source_b"]
                    same_doc_page = (
                        (cl["doc_name"] == sa["doc_name"] and cl["page_number"] == sa["page_number"])
                        or (cl["doc_name"] == sb["doc_name"] and cl["page_number"] == sb["page_number"])
                    )
                    if same_doc_page:
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

        return {
            "question": question,
            "abstained": verification_result["abstained"],
            "answer": verification_result["answer"],
            "faithfulness": verification_result["faithfulness"],
            "verified_claims": verification_result["verified_claims"],
            "blocked_claims": verification_result["blocked_claims"],
            "missing_info": verification_result["missing_info"],
            "amendment_chains": amendment_chains,
            "contradictions": contradictions,
            "calculation": None,
        }

    def close(self):
        self.retriever.close()