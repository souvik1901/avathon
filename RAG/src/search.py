"""
Retrieval + Augmentation + Generation component (the query-retrieval pipeline).

Responsibility
--------------
Given a user query, this module performs the three letters of R-A-G:

1. **Retrieval**    — embed the query and pull the most similar chunks out
   of the vector store (delegated to :class:`FaissVectorStore.query`).
2. **Augmentation** — combine the retrieved chunks (the *context*) with a
   prompt that instructs the LLM to answer *from that context only*.
3. **Generation**   — invoke the LLM (an open model hosted on Groq, exactly
   like the crash course) to produce the final summarized answer.

Requires a ``GROQ_API_KEY`` in the environment / ``.env`` file. Get a free
key at https://console.groq.com/keys. Without a key, retrieval still works —
only the final generation step is unavailable.
"""

import os
from typing import Any, Dict

from dotenv import load_dotenv

# Load variables from a .env file at import time so GROQ_API_KEY is available.
load_dotenv()


# Preferred Groq chat models, best first. Groq rotates its catalog regularly
# (the crash course's ``gemma2-9b-it`` and its successor ``llama-3.1-8b-instant``
# have both been decommissioned), so the model is resolved against the models
# the key can actually see instead of being hard-coded.
PREFERRED_MODELS = [
    "openai/gpt-oss-120b",   # open-weights, fast, clean instruction following
    "openai/gpt-oss-20b",    # smaller sibling (needs a generous max_tokens)
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "groq/compound-mini",
]


def resolve_model(api_key: str, preferred: str | None = None) -> str:
    """Pick a chat model that this API key can actually use.

    Asks Groq which models the key can see, then returns the first entry of
    :data:`PREFERRED_MODELS` that is available. This keeps the pipeline
    working across Groq's catalog changes rather than failing with a 404.

    Parameters
    ----------
    api_key:
        The Groq API key to query with.
    preferred:
        An explicit model name. Used as-is when the key can see it;
        otherwise a warning is printed and auto-selection takes over.

    Returns
    -------
    str
        The model name to use. Falls back to the head of
        :data:`PREFERRED_MODELS` if the catalog cannot be listed.
    """
    try:
        from groq import Groq

        available = {m.id for m in Groq(api_key=api_key).models.list().data}
    except Exception as exc:  # network/auth trouble — let the caller try anyway
        print(f"NOTE: could not list Groq models ({type(exc).__name__}); "
              f"using {preferred or PREFERRED_MODELS[0]}")
        return preferred or PREFERRED_MODELS[0]

    if preferred and preferred in available:
        return preferred
    if preferred:
        print(f"NOTE: model '{preferred}' is not available to this key — auto-selecting")

    for candidate in PREFERRED_MODELS:
        if candidate in available:
            return candidate

    # Nothing preferred is available: fall back to any non-audio/guard model.
    for model_id in sorted(available):
        if not any(tag in model_id for tag in ("whisper", "guard", "orpheus", "tts")):
            return model_id
    return PREFERRED_MODELS[0]


class RAGSearch:
    """End-to-end query pipeline: vector-store search + LLM summarization.

    Parameters
    ----------
    vector_store:
        A built or loaded :class:`src.vector_store.FaissVectorStore`.
    model_name:
        Groq-hosted open model to use for generation. Leave as ``None`` to
        auto-select the best model this API key can access (see
        :func:`resolve_model`); pass a name to pin one explicitly.
    temperature:
        Sampling temperature — kept low (0.1) so answers stay grounded in
        the retrieved context instead of getting creative.
    max_tokens:
        Cap on the length of the generated answer. Keep this generous: the
        ``gpt-oss`` models are reasoning models that spend part of the budget
        on hidden reasoning before emitting the answer.
    """

    def __init__(
        self,
        vector_store: Any,
        model_name: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        self.vector_store = vector_store

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key or groq_api_key == "your_groq_api_key_here":
            # Degrade gracefully: retrieval-only mode instead of crashing.
            print(
                "WARNING: GROQ_API_KEY not set — LLM generation disabled. "
                "Add it to RAG/.env to enable answers (retrieval still works)."
            )
            self.llm = None
        else:
            from langchain_groq import ChatGroq

            resolved = resolve_model(groq_api_key, model_name)
            self.llm = ChatGroq(
                api_key=groq_api_key,
                model=resolved,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            print(f"Groq LLM initialized: {resolved}")

    def search_and_summarize(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """Answer a query using retrieved context + the LLM.

        Steps:

        1. ``vector_store.query(...)`` retrieves the ``top_k`` most similar
           chunks (Retrieval).
        2. Chunk texts are joined into a single context block and formatted
           into an instruction prompt (Augmentation).
        3. ``llm.invoke(prompt)`` generates the grounded answer (Generation).

        Parameters
        ----------
        query:
            The user's natural-language question.
        top_k:
            How many chunks to feed the LLM as context (default 3).

        Returns
        -------
        dict
            ``answer``  — the LLM's response text (or the raw context when
            no API key is configured),
            ``sources`` — file name + page for each retrieved chunk, and
            ``results`` — the raw retrieval hits (content/metadata/distance).
        """
        # 1. Retrieval
        results = self.vector_store.query(query, top_k=top_k)
        if not results:
            return {"answer": "No relevant context found.", "sources": [], "results": []}

        # 2. Augmentation — merge chunks and cite where each came from
        context = "\n\n".join(doc["content"] for doc in results)
        sources = [
            {
                "source_file": doc["metadata"].get("source_file", "unknown"),
                "page": doc["metadata"].get("page", "n/a"),
                "distance": doc["distance"],
            }
            for doc in results
        ]

        if self.llm is None:
            return {
                "answer": f"[LLM disabled — showing raw context]\n\n{context}",
                "sources": sources,
                "results": results,
            }

        prompt = (
            "Use the following context to answer the question concisely.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Answer:"
        )

        # 3. Generation
        response = self.llm.invoke(prompt)
        return {"answer": response.content, "sources": sources, "results": results}
