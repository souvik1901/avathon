"""Evaluate the RAG pipeline from the command line.

Retrieval metrics are free and instant, so they always run. LLM-as-a-judge
metrics cost four calls per question, so they are opt-in via ``--judge``.

Examples
--------
    python scripts/run_evaluation.py                  # retrieval metrics + top_k sweep
    python scripts/run_evaluation.py --judge          # add LLM judges (slower, uses quota)
    python scripts/run_evaluation.py --judge --limit 4
    python scripts/run_evaluation.py --top-k 5
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_all_documents  # noqa: E402
from src.evaluation import (  # noqa: E402
    LLMJudge,
    RetrievalEvaluator,
    evaluate_pipeline,
    load_golden_set,
    print_report,
)
from src.search import RAGSearch  # noqa: E402
from src.vector_store import FaissVectorStore  # noqa: E402


def main() -> None:
    """Parse CLI arguments, build or load the store, and print an evaluation report."""
    parser = argparse.ArgumentParser(description="Evaluate the RAG pipeline.")
    parser.add_argument("--top-k", type=int, default=3, help="chunks to retrieve (default 3)")
    parser.add_argument("--judge", action="store_true", help="also run LLM-as-a-judge metrics")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N questions")
    parser.add_argument("--pause", type=float, default=3.0, help="seconds between judged questions")
    parser.add_argument("--store", default="faiss_store", help="FAISS persist directory")
    args = parser.parse_args()

    store = FaissVectorStore(persist_directory=str(PROJECT_ROOT / args.store))
    if store.exists():
        store.load()
    else:
        store.build_from_documents(load_all_documents(str(PROJECT_ROOT / "data")))

    golden = load_golden_set()
    if args.limit:
        golden = golden[: args.limit]

    if not args.judge:
        evaluator = RetrievalEvaluator(store)
        print_report({"retrieval": evaluator.evaluate(golden, top_k=args.top_k)})
        print("\ntop_k sweep")
        print(f"{'k':>3}  {'hit rate':>9}  {'MRR':>6}  {'recall':>7}  {'precision':>10}")
        for row in evaluator.sweep_top_k(golden, values=[1, 3, 5, 10]):
            print(f"{row['top_k']:>3}  {row['hit_rate']:>8.1%}  {row['mrr']:>6.3f}  "
                  f"{row['recall_at_k']:>6.1%}  {row['precision_at_k']:>9.1%}")
        return

    rag = RAGSearch(store)
    report = evaluate_pipeline(
        vector_store=store,
        answer_fn=lambda q, k: rag.search_and_summarize(q, top_k=k),
        golden_set=golden,
        top_k=args.top_k,
        judge=LLMJudge(),
        pause=args.pause,
    )
    print_report(report)

    out_path = PROJECT_ROOT / "eval" / "last_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report saved to {out_path}")


if __name__ == "__main__":
    main()
