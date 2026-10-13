"""
Agentic RAG with LangGraph — a retriever that can judge and correct itself.

How this differs from traditional RAG
-------------------------------------
Traditional RAG (``src/search.py``) is a straight line executed exactly once:

    query -> embed -> retrieve -> stuff into prompt -> answer

It cannot notice that retrieval failed. If the vector store returns three
irrelevant chunks, they go to the model anyway and the answer is built on sand.

Agentic RAG makes the pipeline a **graph with decisions in it**. The same
retrieval happens, but an LLM then *grades* what came back and the graph
branches on that verdict:

    question
       |
       v
    [route] --- no retrieval needed ---> [answer directly] --> END
       |
       | needs the knowledge base
       v
    [retrieve] --> [grade documents]
                        |         \\
              relevant  |          \\  not relevant
                        v           v
                   [generate]   [rewrite question] --> back to [retrieve]
                        |                                (up to max_rewrites)
                        v
                       END

Three capabilities fall out of that shape, none of which traditional RAG has:

1. **Routing** — a question like "what is 2 + 2" never touches the index.
2. **Self-grading** — the pipeline can tell that retrieval failed.
3. **Query rewriting** — a failed retrieval is retried with a better query
   instead of producing a confident wrong answer.

Ported from the crash-course repo's LangGraph notebook (OpenAI) to Groq plus
this project's local embeddings, so it runs on the free key already in ``.env``.
"""

import os
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv

from src.evaluation import call_with_retry

load_dotenv()


# --------------------------------------------------------------------------- #
# State — the object every node reads from and writes to
# --------------------------------------------------------------------------- #
class AgentState(TypedDict, total=False):
    """Shared state passed along the graph's edges.

    LangGraph merges each node's returned dict into this state, so a node
    only needs to return the keys it changed.

    Keys
    ----
    question:
        The current (possibly rewritten) question driving retrieval.
    original_question:
        The user's untouched question, kept so the final answer addresses
        what was actually asked rather than a rewrite.
    documents:
        Retrieved chunks, each ``{"content", "metadata", "distance"}``.
    answer:
        The generated answer.
    route:
        ``"retrieve"`` or ``"direct"`` — the router's decision.
    grade:
        ``"relevant"`` or ``"irrelevant"`` — the document grader's verdict.
    rewrites:
        How many times the question has been rewritten (loop guard).
    trace:
        Human-readable log of the path taken — the point of the whole
        exercise is being able to see the decisions.
    """
    question: str
    original_question: str
    documents: List[Dict[str, Any]]
    answer: str
    route: str
    grade: str
    rewrites: int
    trace: List[str]


class AgenticRAG:
    """A self-correcting RAG graph built with LangGraph.

    Parameters
    ----------
    vector_store:
        A built or loaded :class:`~src.vector_store.FaissVectorStore`.
    model_name:
        Groq model. ``None`` auto-selects via :func:`src.search.resolve_model`.
    top_k:
        Chunks to retrieve per attempt.
    max_rewrites:
        How many times the graph may rewrite the question before giving up.
        Without this cap a question the knowledge base cannot answer would
        loop forever — the single most important guard in an agentic system.
    """

    def __init__(self, vector_store: Any, model_name: Optional[str] = None,
                 top_k: int = 3, max_rewrites: int = 2):
        self.vector_store = vector_store
        self.top_k = top_k
        self.max_rewrites = max_rewrites

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key == "your_groq_api_key_here":
            raise RuntimeError(
                "AgenticRAG needs a GROQ_API_KEY in RAG/.env — every decision "
                "node is an LLM call."
            )

        from langchain_groq import ChatGroq

        from src.search import resolve_model

        resolved = resolve_model(api_key, model_name)
        self.llm = ChatGroq(api_key=api_key, model=resolved,
                            temperature=0.0, max_tokens=1024)
        print(f"Agentic RAG LLM initialized: {resolved}")
        self.graph = self._build_graph()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str) -> str:
        """One LLM call, retried through rate limits, returned as text."""
        response = call_with_retry(lambda: self.llm.invoke(prompt), label="agent")
        return (response.content or "").strip()

    # ------------------------------------------------------------------ #
    # Nodes
    # ------------------------------------------------------------------ #
    def route_question(self, state: AgentState) -> AgentState:
        """Decide whether this question needs the knowledge base at all.

        Saves a pointless retrieval for questions the model can answer from
        its own weights ("what is 2 + 2"), and keeps unrelated questions from
        dragging in irrelevant context that would only confuse the answer.
        """
        question = state["question"]
        # NOTE: the question to ask here is "is this ON TOPIC for the knowledge
        # base?", NOT "could you answer it yourself?". Asking the latter sends
        # well-known topics like attention straight to DIRECT, defeating the
        # entire point of RAG -- which is to ground answers in *these*
        # documents even when the model already knows the subject.
        verdict = self._ask(
            "Classify whether a QUESTION is on-topic for a knowledge base "
            "covering: transformers and attention, embedding models, RAG "
            "pipelines, chunking, vector databases, machine learning, and "
            "Python.\n"
            "Reply RETRIEVE if the question is about any of those topics, even "
            "if you already know the answer.\n"
            "Reply DIRECT only if it is clearly unrelated to all of them (for "
            "example arithmetic, weather, cooking, or a specific company's "
            "private financials).\n"
            "Answer with exactly one word: RETRIEVE or DIRECT.\n\n"
            f"QUESTION: {question}"
        ).upper()
        # Default to retrieving: a needless retrieval is cheap, while skipping
        # retrieval on an on-topic question loses the grounding entirely.
        route = "direct" if "DIRECT" in verdict and "RETRIEVE" not in verdict else "retrieve"
        return {
            "route": route,
            "trace": state.get("trace", []) + [f"route -> {route}"],
        }

    def retrieve(self, state: AgentState) -> AgentState:
        """Fetch the top-k chunks for the current question."""
        docs = self.vector_store.query(state["question"], top_k=self.top_k)
        sources = sorted({d["metadata"].get("source_file", "?") for d in docs})
        return {
            "documents": docs,
            "trace": state.get("trace", []) + [f"retrieve -> {len(docs)} chunks from {sources}"],
        }

    def grade_documents(self, state: AgentState) -> AgentState:
        """Ask the LLM whether the retrieved chunks can answer the question.

        This is the step traditional RAG lacks. Grading against the
        *original* question matters: after a rewrite, relevance must still be
        judged by what the user actually asked.
        """
        docs = state.get("documents", [])
        if not docs:
            return {"grade": "irrelevant",
                    "trace": state.get("trace", []) + ["grade -> irrelevant (no documents)"]}

        context = "\n\n".join(d["content"][:600] for d in docs)
        verdict = self._ask(
            "You are grading whether retrieved CONTEXT contains the information "
            "needed to answer a QUESTION.\n"
            "Answer with exactly one word: RELEVANT or IRRELEVANT.\n\n"
            f"QUESTION: {state.get('original_question', state['question'])}\n\n"
            f"CONTEXT:\n{context}"
        ).upper()
        grade = "irrelevant" if "IRRELEVANT" in verdict else "relevant"
        return {"grade": grade, "trace": state.get("trace", []) + [f"grade -> {grade}"]}

    def rewrite_question(self, state: AgentState) -> AgentState:
        """Rephrase the question to retrieve better on the next attempt.

        Retrieval failures are often vocabulary mismatches — the user's words
        simply do not embed near the document's words. Rewriting targets that
        directly, which is why it is the standard recovery move.
        """
        rewritten = self._ask(
            "Rewrite the QUESTION to retrieve better from a technical knowledge "
            "base. Use precise domain terminology and keep it to one sentence. "
            "Return ONLY the rewritten question.\n\n"
            f"QUESTION: {state['question']}"
        ).strip().strip('"')
        return {
            "question": rewritten,
            "rewrites": state.get("rewrites", 0) + 1,
            "trace": state.get("trace", []) + [f"rewrite -> {rewritten!r}"],
        }

    def generate(self, state: AgentState) -> AgentState:
        """Answer from the retrieved context (the normal RAG generation step)."""
        context = "\n\n".join(d["content"] for d in state.get("documents", []))
        answer = self._ask(
            "Use the following context to answer the question concisely.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {state.get('original_question', state['question'])}\n\nAnswer:"
        )
        return {"answer": answer, "trace": state.get("trace", []) + ["generate"]}

    def answer_directly(self, state: AgentState) -> AgentState:
        """Answer without retrieval, for questions the router sent here."""
        answer = self._ask(
            "Answer the question concisely from your own knowledge.\n\n"
            f"Question: {state.get('original_question', state['question'])}\n\nAnswer:"
        )
        return {"answer": answer, "trace": state.get("trace", []) + ["answer_directly"]}

    def give_up(self, state: AgentState) -> AgentState:
        """Say so plainly when the knowledge base cannot answer.

        The whole point of grading is to make this outcome reachable. A
        traditional pipeline would instead emit a confident answer built on
        irrelevant context.
        """
        return {
            "answer": ("I could not find relevant information in the knowledge base "
                       "to answer this question."),
            "trace": state.get("trace", []) + ["give_up (rewrite budget exhausted)"],
        }

    # ------------------------------------------------------------------ #
    # Conditional edges
    # ------------------------------------------------------------------ #
    def _after_route(self, state: AgentState) -> str:
        """Send the question to retrieval or straight to a direct answer."""
        return "retrieve" if state.get("route") == "retrieve" else "answer_directly"

    def _after_grade(self, state: AgentState) -> str:
        """Generate if the documents are good; otherwise rewrite, or give up.

        The rewrite budget is checked here — this is what makes the loop
        terminate.
        """
        if state.get("grade") == "relevant":
            return "generate"
        if state.get("rewrites", 0) < self.max_rewrites:
            return "rewrite_question"
        return "give_up"

    # ------------------------------------------------------------------ #
    # Graph
    # ------------------------------------------------------------------ #
    def _build_graph(self):
        """Wire the nodes and edges into a compiled LangGraph state machine."""
        from langgraph.graph import END, StateGraph

        graph = StateGraph(AgentState)

        graph.add_node("route_question", self.route_question)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("grade_documents", self.grade_documents)
        graph.add_node("rewrite_question", self.rewrite_question)
        graph.add_node("generate", self.generate)
        graph.add_node("answer_directly", self.answer_directly)
        graph.add_node("give_up", self.give_up)

        graph.set_entry_point("route_question")

        # routing decision
        graph.add_conditional_edges("route_question", self._after_route,
                                    {"retrieve": "retrieve",
                                     "answer_directly": "answer_directly"})
        # retrieve -> grade
        graph.add_edge("retrieve", "grade_documents")
        # grading decision (this is the self-correcting branch)
        graph.add_conditional_edges("grade_documents", self._after_grade,
                                    {"generate": "generate",
                                     "rewrite_question": "rewrite_question",
                                     "give_up": "give_up"})
        # the loop: a rewritten question goes back through retrieval
        graph.add_edge("rewrite_question", "retrieve")

        graph.add_edge("generate", END)
        graph.add_edge("answer_directly", END)
        graph.add_edge("give_up", END)

        return graph.compile()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self, question: str) -> Dict[str, Any]:
        """Answer a question by executing the graph.

        Parameters
        ----------
        question:
            The user's question.

        Returns
        -------
        dict
            ``answer``, the ``trace`` of decisions taken, ``sources`` for any
            retrieved chunks, and the number of ``rewrites`` used.
        """
        final = self.graph.invoke({
            "question": question,
            "original_question": question,
            "rewrites": 0,
            "trace": [],
        })
        return {
            "answer": final.get("answer", ""),
            "trace": final.get("trace", []),
            "rewrites": final.get("rewrites", 0),
            "sources": sorted({d["metadata"].get("source_file", "?")
                               for d in final.get("documents", [])}),
        }

    def print_run(self, question: str) -> Dict[str, Any]:
        """Run the graph and print the decision trace, then the answer."""
        result = self.run(question)
        print(f"Q: {question}")
        for step in result["trace"]:
            print(f"   -> {step}")
        if result["sources"]:
            print(f"   sources: {result['sources']}")
        print(f"A: {result['answer']}\n")
        return result
