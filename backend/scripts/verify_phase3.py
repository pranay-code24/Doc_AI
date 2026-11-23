import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.retrieval.hybrid_search import HybridRetriever
from app.verification.verifier import ZeroGuessingVerifier


TEST_CASES = [
    (
        "TEST 1: Table Evidence + Exact Citations",
        "What are the processing fee and foreclosure fee for a Retail Personal Loan?",
    ),
    (
        "TEST 2: Zero-Guessing Abstention (Missing Info)",
        "What is the loan policy for NRI applicants or cryptocurrency collateral?",
    ),
    (
        "TEST 3: Hindi Cross-Lingual Q&A + Verification",
        "Personal loan ke liye minimum monthly income kitni honi chahiye?",
    ),
]


def main():
    retriever = HybridRetriever()
    verifier = ZeroGuessingVerifier()

    for title, question in TEST_CASES:
        print("\n" + "=" * 65)
        print(f"{title}")
        print(f"Question: {question}")
        print("=" * 65)

        chunks = retriever.search(question, top_k=5)
        result = verifier.generate_and_verify(question, chunks)

        print(f"Abstained   : {result['abstained']}")
        print(f"Answer      : {result['answer']}")
        f = result["faithfulness"]
        print(
            f"Faithfulness: {f['score_percent']}% "
            f"({f['verified_sentences']}/{f['total_draft_sentences']} claims verified)"
        )

        if result["verified_claims"]:
            print("\n  [Verified Citations]")
            for i, c in enumerate(result["verified_claims"], start=1):
                print(f"   {i}. Claim : {c['sentence']}")
                print(f"      Source: {c['doc_name']} | Page {c['page_number']}")
                print(f"      Quote : \"{c['verbatim_quote']}\"")
                print(
                    f"      Checks: quote_match={c['quote_match_score']}% | "
                    f"nli_entail={c['nli_scores']['entailment']} | "
                    f"bboxes={len(c['bboxes'])}"
                )

        if result["blocked_claims"]:
            print("\n  [Blocked / Rejected Claims]")
            for b in result["blocked_claims"]:
                print(f"   - Claim : {b['sentence']}")
                print(f"     Source: {b['doc_name']} p.{b['page_number']} | Quote: \"{b['verbatim_quote']}\"")
                print(f"     REASON: {b['block_reason']}")

        if result["missing_info"]:
            print(f"\n  [Missing Info Note]: {result['missing_info']}")

    retriever.close()
    print("\nPhase 3 COMPLETE!")


if __name__ == "__main__":
    main()