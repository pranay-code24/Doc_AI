import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import BENCHMARK_FILE, SAMPLE_DOCS_DIR
from app.evaluation import evaluate_pipeline
from app.pipeline import DocumentAIPipeline


def main():
    pipeline = DocumentAIPipeline()
    if not pipeline.retriever.chunks:
        pipeline.ingest_folder(SAMPLE_DOCS_DIR)

    print("Running 9-Case Automated Evaluation & Guardrail Benchmark...\n")
    report = evaluate_pipeline(pipeline)
    BENCHMARK_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")

    s = report["summary"]
    print("=" * 75)
    print(f"PROVIDER: {report['provider'].upper()} ({report['model']})")
    print(f"Overall Benchmark Accuracy : {s['overall_accuracy_percent']}% ({s['tests_passed']}/{s['total_tests']} passed)")
    print(f"Avg Answer Faithfulness    : {s['avg_faithfulness_percent']}%")
    print(f"Hallucination Leak Rate    : {s['hallucination_leak_rate_percent']}%")
    print(f"Abstention Accuracy        : {s['abstention_accuracy_percent']}%")
    print(f"Guardrail Block Rate       : {s['guardrail_block_rate_percent']}%")
    print(f"Avg Full Pipeline Latency  : {s['avg_full_pipeline_latency_ms']} ms (p50: {s['p50_latency_ms']} ms | p95: {s['p95_latency_ms']} ms)")
    print("=" * 75)

    for r in report["cases"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(
            f"[{status}] {r['id']} | {r['category']:28s} | "
            f"{r['latency_ms']:7.1f} ms | Faith: {r['faithfulness_percent']:5.1f}% | {r['notes']}"
        )

    pipeline.close()
    print(f"\nSaved live report to: {BENCHMARK_FILE}")


if __name__ == "__main__":
    main()