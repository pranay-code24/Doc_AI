import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import SAMPLE_DOCS_DIR
from app.pipeline import DocumentAIPipeline


TESTS = [
    (
        "TEST 1: Amendment Chain (A -> B -> C)",
        "What is the currently applicable interest rate for a Retail Personal Loan?",
    ),
    (
        "TEST 2: Contradiction Detection (Side-by-Side Conflicts)",
        "What is the maximum repayment tenure and minimum applicant age?",
    ),
    (
        "TEST 3: Calculation - Late Payment Penalty",
        "If my overdue EMI is INR 20,000 for 2 months past the grace period, what is the total late payment penalty?",
    ),
    (
        "TEST 4: Calculation - Monthly EMI at Current Rate",
        "Calculate the monthly EMI for a Retail Personal Loan of INR 5,00,000 for 24 months at the current interest rate.",
    ),
]


def main():
    pipeline = DocumentAIPipeline()

    print("--- Step 1: Running Full Ingestion + Amendment Graph Build ---")
    stats = pipeline.ingest_folder(SAMPLE_DOCS_DIR)
    print(f"[OK] Ingestion Stats: {stats}")

    for title, question in TESTS:
        print("\n" + "=" * 72)
        print(f"{title}")
        print(f"Question: {question}")
        print("=" * 72)

        res = pipeline.ask(question)
        f = res["faithfulness"]

        print(f"Abstained   : {res['abstained']}")
        print(f"Answer      : {res['answer']}")
        print(
            f"Faithfulness: {f['score_percent']}% "
            f"({f['verified_sentences']}/{f['total_draft_sentences']} claims verified)"
        )

        # 1. Print Amendment Chains
        if res["amendment_chains"]:
            print("\n  [Amendment Chain Detected]")
            for chain in res["amendment_chains"]:
                print(f"   Clause: {chain['clause_ref']} ({chain['subject']}) -> Active: {chain['active_doc_id']}")
                for step in chain["steps"]:
                    tag = "ACTIVE" if step["status"] == "ACTIVE" else f"SUPERSEDED by {step.get('superseded_by')}"
                    print(
                        f"     -> [{step['effective_date']}] {step['doc_id']} ({step['doc_name']}) "
                        f"| {tag} | {step['summary']}"
                    )

        # 2. Print Contradictions
        if res["contradictions"]:
            print("\n  [CONTRADICTION ALERTS - SIDE BY SIDE]")
            for idx, c in enumerate(res["contradictions"], start=1):
                print(f"   Conflict #{idx}: {c['subject']} ({c['conflict_type']}) | {c['explanation']}")
                print(
                    f"     Side A [{c['source_a']['doc_name']} p.{c['source_a']['page_number']}]: "
                    f"\"{c['source_a']['verbatim_quote']}\""
                )
                print(
                    f"     Side B [{c['source_b']['doc_name']} p.{c['source_b']['page_number']}]: "
                    f"\"{c['source_b']['verbatim_quote']}\""
                )

        # 3. Print Calculation Working
        if res["calculation"]:
            calc = res["calculation"]
            print(f"\n  [CALCULATION WORKING - {calc['operation']}]")
            print(f"   Formula: {calc['formula']}")
            for k, v in calc["inputs"].items():
                print(f"   - {k}: {v}")
            for s in calc["steps"]:
                print(f"   {s}")
            print(f"   => FINAL RESULT: {calc['result']}")

        # 4. Print Verified Citations
        if res["verified_claims"]:
            print("\n  [Verified Claims]")
            for idx, cl in enumerate(res["verified_claims"], start=1):
                print(
                    f"   {idx}. {cl['sentence']} "
                    f"[{cl['doc_name']} p.{cl['page_number']} | match={cl['quote_match_score']}% | "
                    f"entail={cl['nli_scores']['entailment']}]"
                )

    pipeline.close()
    print("\nPhase 4 COMPLETE!")


if __name__ == "__main__":
    main()