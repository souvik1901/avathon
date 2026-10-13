"""
RAG evaluation (the missing half of every RAG tutorial).

Why this module exists
----------------------
A RAG system has **two halves that fail for different reasons**, and a single
"the answer looked fine" impression cannot tell them apart:

* **Retrieval** — did the right passage reach the model at all? If not, no
  language model can rescue the answer.
* **Generation** — given the right passage, did the model actually use it? An
  answer can be fluent, confident, and completely unsupported.

So this module measures them separately.

Two kinds of metric
-------------------
1. **Retrieval metrics** (:class:`RetrievalEvaluator`) — deterministic,
   free, and instant. They need a *golden set*: questions paired with the
   source files that genuinely contain the answer
   (``eval/golden_qa.json``). No LLM involved, so these are what you run
   on every change to chunking, embeddings, or ``top_k``.

2. **Generation metrics** (:class:`LLMJudge`) — an LLM scores qualities that
   have no formula. Ported from the crash-course repo's LangSmith/OpenAI
   notebook to Groq, so they run on the free key this project already uses:

   * **Correctness**         — is the answer right, vs. a ground-truth answer?
   * **Relevance**           — does the answer address the question?
   * **Groundedness**        — is every claim supported by the retrieved context?
   * **Retrieval relevance** — were the retrieved documents actually useful?

   "LLM as a judge" is a real technique, not a shortcut, but treat its scores
   as *indicative*: judges are biased toward verbose answers and are not
   deterministic. The retrieval metrics are the ones to trust numerically.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

# NOTE: the golden set deliberately lives OUTSIDE data/, because data/ is the
# searchable knowledge base. Keeping it inside data/ would let
# load_all_documents() ingest the questions and reference answers into the
# very index being evaluated - test-set contamination that silently inflates
# every score.
DEFAULT_GOLDEN_SET = Path(__file__).resolve().parent.parent / "eval" / "golden_qa.json"


# --------------------------------------------------------------------------- #
# Rate-limit handling
# --------------------------------------------------------------------------- #
def call_with_retry(fn: Callable[[], Any], max_retries: int = 6,
                    label: str = "LLM call") -> Any:
    """Call ``fn``, retrying through provider rate limits.

    Evaluation is unusually rate-limit prone: judging one question costs four
    LLM calls (one answer + three judges), so a 12-question run issues ~48
    calls in quick succession. Groq's free tier allows 8,000 tokens per
    minute, which that will exceed.

    On a rate-limit error this waits the delay the provider itself suggests
    (parsed from the message, e.g. "try again in 1.14s") plus a small margin,
    falling back to exponential backoff. Any other exception propagates
    immediately -- a broken prompt should fail loudly, not be retried.

    Parameters
    ----------
    fn:
        Zero-argument callable performing the request.
    max_retries:
        Attempts before giving up.
    label:
        Name used in the "waiting" message.

    Returns
    -------
    Any
        Whatever ``fn`` returns.
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - provider classes vary
            is_rate_limit = (
                "RateLimit" in type(exc).__name__
                or "rate_limit" in str(exc)
                or "429" in str(exc)
            )
            if not is_rate_limit or attempt == max_retries - 1:
                raise
            match = re.search(r"try again in ([0-9.]+)s", str(exc))
            wait = float(match.group(1)) + 0.5 if match else 2.0 * (2 ** attempt)
            print(f"  [rate limit] {label}: waiting {wait:.1f}s "
                  f"(attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------- #
# Golden set
# --------------------------------------------------------------------------- #
def load_golden_set(path: str | Path = DEFAULT_GOLDEN_SET) -> List[Dict[str, Any]]:
    """Load the evaluation questions from a JSON file.

    Parameters
    ----------
    path:
        JSON file shaped ``{"items": [{id, question, expected_sources, ...}]}``.

    Returns
    -------
    list[dict]
        One dict per evaluation question.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload["items"]


# --------------------------------------------------------------------------- #
# 1. Retrieval metrics — deterministic, no LLM
# --------------------------------------------------------------------------- #
class RetrievalEvaluator:
    """Scores whether retrieval surfaces the right source documents.

    Every metric compares the ``source_file`` of each retrieved chunk against
    the ``expected_sources`` of the question. A question counts as a *hit* when
    any expected source appears in the results.

    Parameters
    ----------
    vector_store:
        Anything exposing ``query(text, top_k) -> [{"metadata": {...}}, ...]``,
        which both :class:`~src.vector_store.FaissVectorStore` and the
        notebook's ChromaDB wrapper satisfy.
    """

    def __init__(self, vector_store: Any):
        self.vector_store = vector_store

    def _retrieved_sources(self, question: str, top_k: int) -> List[str]:
        """Return the source_file of each hit, best-ranked first."""
        results = self.vector_store.query(question, top_k=top_k)
        return [r["metadata"].get("source_file", "unknown") for r in results]

    def evaluate(self, golden_set: List[Dict[str, Any]], top_k: int = 5) -> Dict[str, Any]:
        """Score retrieval over the whole golden set.

        Metrics returned
        ----------------
        ``hit_rate``
            Fraction of questions where an expected source appeared anywhere in
            the top-k. "Did we find it at all?"
        ``mrr``
            Mean Reciprocal Rank — averages ``1 / rank`` of the *first* correct
            hit (0 when absent). Rewards ranking the right document higher, so
            it separates "found it first" from "found it fifth".
        ``recall_at_k``
            Average fraction of a question's expected sources that were found.
            Matters when several documents are genuinely relevant.
        ``precision_at_k``
            Average fraction of retrieved chunks that came from an expected
            source. Low precision means the model wades through noise.

        Parameters
        ----------
        golden_set:
            Questions from :func:`load_golden_set`.
        top_k:
            How many chunks to retrieve per question.

        Returns
        -------
        dict
            Aggregate metrics plus a ``per_question`` breakdown for debugging.
        """
        per_question: List[Dict[str, Any]] = []

        for item in golden_set:
            expected = set(item["expected_sources"])
            retrieved = self._retrieved_sources(item["question"], top_k)

            # rank (1-based) of the first retrieved chunk from an expected source
            first_hit_rank: Optional[int] = next(
                (i for i, src in enumerate(retrieved, start=1) if src in expected), None
            )
            found = expected & set(retrieved)

            per_question.append({
                "id": item.get("id", ""),
                "question": item["question"],
                "expected": sorted(expected),
                "retrieved": retrieved,
                "hit": first_hit_rank is not None,
                "first_hit_rank": first_hit_rank,
                "reciprocal_rank": (1.0 / first_hit_rank) if first_hit_rank else 0.0,
                "recall": len(found) / len(expected) if expected else 0.0,
                "precision": (sum(1 for s in retrieved if s in expected) / len(retrieved)
                              if retrieved else 0.0),
            })

        n = len(per_question) or 1
        return {
            "top_k": top_k,
            "n_questions": len(per_question),
            "hit_rate": sum(q["hit"] for q in per_question) / n,
            "mrr": sum(q["reciprocal_rank"] for q in per_question) / n,
            "recall_at_k": sum(q["recall"] for q in per_question) / n,
            "precision_at_k": sum(q["precision"] for q in per_question) / n,
            "per_question": per_question,
        }

    def sweep_top_k(self, golden_set: List[Dict[str, Any]],
                    values: List[int] = (1, 3, 5, 10)) -> List[Dict[str, Any]]:
        """Run :meth:`evaluate` at several ``top_k`` values.

        Useful for picking ``top_k``: hit rate only ever rises with k, while
        precision falls, so the sweep shows where the trade-off sits.

        Returns
        -------
        list[dict]
            One summary row per k (``per_question`` omitted).
        """
        rows = []
        for k in values:
            summary = self.evaluate(golden_set, top_k=k)
            summary.pop("per_question")
            rows.append(summary)
        return rows


# --------------------------------------------------------------------------- #
# 2. Generation metrics — LLM as a judge
# --------------------------------------------------------------------------- #
JUDGE_SCHEMA_HINT = (
    'Respond with ONLY a JSON object of the form '
    '{"score": <integer 1-5>, "reasoning": "<one sentence>"}.'
)

# Correctness is graded pass/fail against a ground-truth answer rather than on a
# 1-5 scale, so it has its own schema. The explanation is requested FIRST on
# purpose: generating the reasoning before the verdict makes the model work the
# problem through instead of committing to true/false and rationalising after.
CORRECTNESS_SCHEMA_HINT = (
    'Respond with ONLY a JSON object of the form '
    '{"explanation": "<one sentence of reasoning>", "correct": true or false}. '
    'Give the explanation first, then the verdict.'
)


class LLMJudge:
    """Scores answer quality with an LLM, on Groq.

    Four judges, matching the crash-course repo's LangSmith notebook:

    * :meth:`correctness`         — answer vs. **reference answer** (needs labels)
    * :meth:`relevance`           — answer vs. question
    * :meth:`groundedness`        — answer vs. retrieved context
    * :meth:`retrieval_relevance` — retrieved context vs. question

    Only ``correctness`` requires a ground-truth answer; the other three work
    on unlabelled traffic. Correctness is scored pass/fail, the rest 1-5.

    Each returns a 1-5 score with a one-sentence justification. Scores are
    *indicative*: use them to catch regressions and to compare two pipeline
    variants, not as ground truth.

    Parameters
    ----------
    model_name:
        Groq model for judging. ``None`` auto-selects via
        :func:`src.search.resolve_model`.
    temperature:
        Kept at 0.0 so repeated judgements are as stable as the model allows.
    """

    def __init__(self, model_name: Optional[str] = None, temperature: float = 0.0):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key == "your_groq_api_key_here":
            print("WARNING: GROQ_API_KEY not set — LLM judging disabled. "
                  "Retrieval metrics still work.")
            self.llm = None
            return

        from langchain_groq import ChatGroq

        from src.search import resolve_model

        resolved = resolve_model(api_key, model_name)
        # Generous max_tokens: gpt-oss models spend budget on hidden reasoning
        # before emitting the JSON verdict.
        self.llm = ChatGroq(api_key=api_key, model=resolved,
                            temperature=temperature, max_tokens=1024)
        print(f"LLM judge initialized: {resolved}")

    # ---------------------------------------------------------------- #
    def _ask_json(self, prompt: str) -> Dict[str, Any]:
        """Send a judging prompt and parse its JSON reply defensively.

        Models occasionally wrap JSON in prose or code fences, so the first
        ``{...}`` block is extracted rather than trusting the whole reply.

        Returns
        -------
        dict
            The parsed object, or ``{"_error": "<why>"}`` when the reply could
            not be parsed. Callers decide how a failure maps onto their metric.
        """
        if self.llm is None:
            return {"_error": "judge disabled (no GROQ_API_KEY)"}

        raw = (call_with_retry(lambda: self.llm.invoke(prompt),
                               label="judge").content or "").strip()
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {"_error": f"unparseable judge reply: {raw[:120]}"}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"_error": f"invalid JSON from judge: {raw[:120]}"}

    def _ask(self, prompt: str) -> Dict[str, Any]:
        """Ask for a 1-5 score and return ``{"score", "reasoning"}``.

        Used by the three scale-based judges. An unparseable reply yields
        ``score=None`` so it is excluded from averages rather than silently
        counted as zero.
        """
        verdict = self._ask_json(prompt)
        if "_error" in verdict:
            return {"score": None, "reasoning": verdict["_error"]}

        score = verdict.get("score")
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None
        return {"score": score, "reasoning": str(verdict.get("reasoning", ""))[:300]}

    # ---------------------------------------------------------------- #
    def relevance(self, question: str, answer: str) -> Dict[str, Any]:
        """Does the answer actually address the question that was asked?

        Deliberately ignores whether the answer is *correct* — that is
        groundedness's job. A confidently wrong but on-topic answer scores
        high here and low there, which is exactly how the two separate.
        """
        return self._ask(
            "You are grading whether an ANSWER addresses a QUESTION.\n"
            "Ignore factual accuracy; judge only whether it responds to what was asked.\n"
            "5 = fully addresses the question, 1 = does not address it at all.\n\n"
            f"QUESTION: {question}\n\nANSWER: {answer}\n\n{JUDGE_SCHEMA_HINT}"
        )

    def groundedness(self, answer: str, context: str) -> Dict[str, Any]:
        """Is every claim in the answer supported by the retrieved context?

        This is the hallucination detector. An answer that is true in the real
        world but absent from the context still scores low — and it should,
        because the pipeline got lucky rather than working.
        """
        return self._ask(
            "You are checking whether an ANSWER is fully supported by the CONTEXT.\n"
            "Claims that are true in general but absent from the CONTEXT are NOT supported.\n"
            "5 = every claim is supported by the context, 1 = mostly unsupported.\n\n"
            f"CONTEXT:\n{context}\n\nANSWER: {answer}\n\n{JUDGE_SCHEMA_HINT}"
        )

    def correctness(self, question: str, answer: str,
                    reference_answer: str) -> Dict[str, Any]:
        """Is the answer factually right, judged against a ground-truth answer?

        The only judge of the four that needs **labelled data**: it compares
        the generated answer with the ``reference_answer`` recorded in the
        golden set, the way a teacher marks against a model answer.

        This is a different question from :meth:`groundedness`, and the two can
        disagree in both directions:

        * *grounded but incorrect* — faithfully repeats a passage that does not
          actually answer the question.
        * *correct but ungrounded* — right about the world, but the retrieved
          context never said it, so the pipeline got lucky.

        Graded pass/fail rather than 1-5, because "is this the right answer"
        is a yes/no question. Wording is allowed to differ freely; only the
        substance is marked.

        Parameters
        ----------
        question:
            The original question, for context on what counts as answering it.
        answer:
            What the pipeline produced.
        reference_answer:
            The ground-truth answer from the golden set.

        Returns
        -------
        dict
            ``{"correct": bool | None, "reasoning": str}``. ``None`` means the
            verdict could not be parsed, and is excluded from the aggregate.
        """
        verdict = self._ask_json(
            "You are a teacher grading a quiz. Decide whether the STUDENT ANSWER "
            "is factually correct with respect to the REFERENCE ANSWER.\n"
            "Different wording, extra detail, or a longer explanation is fine — "
            "grade only the substance.\n"
            "It is incorrect if it contradicts the reference answer, or omits the "
            "specific fact the question asked for.\n\n"
            f"QUESTION: {question}\n\n"
            f"REFERENCE ANSWER: {reference_answer}\n\n"
            f"STUDENT ANSWER: {answer}\n\n{CORRECTNESS_SCHEMA_HINT}"
        )
        if "_error" in verdict:
            return {"correct": None, "reasoning": verdict["_error"]}

        raw = verdict.get("correct")
        if isinstance(raw, bool):
            correct = raw
        elif isinstance(raw, str):
            correct = raw.strip().lower() in {"true", "yes", "correct"}
        else:
            correct = None
        return {"correct": correct,
                "reasoning": str(verdict.get("explanation", ""))[:300]}

    def retrieval_relevance(self, question: str, context: str) -> Dict[str, Any]:
        """Were the retrieved documents useful for this question?

        Scores the retriever's output directly, without a golden set — so it
        works on live traffic where you have no labels.
        """
        return self._ask(
            "You are grading whether retrieved CONTEXT is relevant to a QUESTION.\n"
            "5 = context contains the information needed to answer, 1 = irrelevant.\n\n"
            f"QUESTION: {question}\n\nCONTEXT:\n{context}\n\n{JUDGE_SCHEMA_HINT}"
        )


# --------------------------------------------------------------------------- #
# 3. End-to-end evaluation
# --------------------------------------------------------------------------- #
def evaluate_pipeline(
    vector_store: Any,
    answer_fn: Callable[[str, int], Dict[str, Any]],
    golden_set: Optional[List[Dict[str, Any]]] = None,
    top_k: int = 3,
    judge: Optional[LLMJudge] = None,
    limit: Optional[int] = None,
    pause: float = 0.0,
) -> Dict[str, Any]:
    """Score retrieval *and* generation over the golden set in one pass.

    Parameters
    ----------
    vector_store:
        Store used for the deterministic retrieval metrics.
    answer_fn:
        Callable ``(question, top_k) -> {"answer": str, "results": [...]}`` —
        :meth:`src.search.RAGSearch.search_and_summarize` fits directly.
    golden_set:
        Defaults to ``eval/golden_qa.json``.
    top_k:
        Chunks to retrieve per question.
    judge:
        An :class:`LLMJudge`. ``None`` skips generation metrics (retrieval
        metrics still run), which is the right choice for a quick check.
        Correctness is graded only for golden items carrying a
        ``reference_answer``; the other three judges need no labels.
    limit:
        Evaluate only the first N questions — handy while iterating, since
        each judged question costs three LLM calls.
    pause:
        Seconds to sleep between questions. On a rate-limited free tier a
        small pause (2-4s) is faster overall than repeatedly hitting the
        limit and backing off.

    Returns
    -------
    dict
        ``retrieval`` metrics, optional ``generation`` averages, and a
        ``per_question`` list carrying answers and judge verdicts.
    """
    golden_set = golden_set or load_golden_set()
    if limit:
        golden_set = golden_set[:limit]

    retrieval = RetrievalEvaluator(vector_store).evaluate(golden_set, top_k=top_k)

    rows: List[Dict[str, Any]] = []
    for item in golden_set:
        question = item["question"]
        result = call_with_retry(lambda: answer_fn(question, top_k), label="answer")
        answer = result.get("answer", "")
        context = "\n\n".join(r["content"] for r in result.get("results", []))

        row = {"id": item.get("id", ""), "question": question, "answer": answer}
        if judge is not None and judge.llm is not None:
            row["relevance"] = judge.relevance(question, answer)
            row["groundedness"] = judge.groundedness(answer, context)
            row["retrieval_relevance"] = judge.retrieval_relevance(question, context)
            # Correctness is the only judge needing labels, so it is skipped
            # for any golden item that has no reference_answer.
            reference = item.get("reference_answer")
            if reference:
                row["correctness"] = judge.correctness(question, answer, reference)
        rows.append(row)
        if pause:
            time.sleep(pause)

    report: Dict[str, Any] = {"retrieval": retrieval, "per_question": rows}

    if judge is not None and judge.llm is not None:
        def mean(metric: str) -> Optional[float]:
            """Average one 1-5 judge metric across questions, ignoring unparsed scores."""
            scores = [r[metric]["score"] for r in rows
                      if r.get(metric, {}).get("score") is not None]
            return round(sum(scores) / len(scores), 2) if scores else None

        # Correctness is pass/fail, so it aggregates as a percentage rather
        # than a mean score. Unparsed verdicts (None) are excluded from both
        # numerator and denominator.
        graded = [r["correctness"]["correct"] for r in rows
                  if r.get("correctness", {}).get("correct") is not None]

        report["generation"] = {
            "correctness_pct": (round(100 * sum(graded) / len(graded), 1)
                                if graded else None),
            "correctness_n": len(graded),
            "relevance": mean("relevance"),
            "groundedness": mean("groundedness"),
            "retrieval_relevance": mean("retrieval_relevance"),
            "scale": "correctness = % correct (pass/fail); others 1-5, higher is better",
        }
    return report


def print_report(report: Dict[str, Any]) -> None:
    """Print an evaluation report as a readable summary table."""
    r = report["retrieval"]
    print("=" * 66)
    print(f"RETRIEVAL  (top_k={r['top_k']}, {r['n_questions']} questions)")
    print("=" * 66)
    print(f"  hit rate       {r['hit_rate']:.1%}   (expected source found at all)")
    print(f"  MRR            {r['mrr']:.3f}   (1.0 = always ranked first)")
    print(f"  recall@k       {r['recall_at_k']:.1%}")
    print(f"  precision@k    {r['precision_at_k']:.1%}")

    if "generation" in report:
        g = report["generation"]
        print()
        print("=" * 66)
        print("GENERATION  (LLM as judge)")
        print("=" * 66)
        if g.get("correctness_pct") is not None:
            print(f"  correctness          {g['correctness_pct']}%   "
                  f"(pass/fail vs reference answer, n={g['correctness_n']})")
        print(f"  relevance            {g['relevance']}    (1-5)")
        print(f"  groundedness         {g['groundedness']}    (1-5)")
        print(f"  retrieval relevance  {g['retrieval_relevance']}    (1-5)")

        wrong = [r for r in report["per_question"]
                 if r.get("correctness", {}).get("correct") is False]
        if wrong:
            print()
            print(f"  MARKED INCORRECT ({len(wrong)}):")
            for r in wrong:
                print(f"    [{r['id']}] {r['question']}")
                print(f"          {r['correctness']['reasoning'][:150]}")

    misses = [q for q in r["per_question"] if not q["hit"]]
    if misses:
        print()
        print(f"MISSES ({len(misses)}):")
        for q in misses:
            print(f"  [{q['id']}] {q['question']}")
            print(f"        expected  {q['expected']}")
            print(f"        retrieved {q['retrieved']}")
