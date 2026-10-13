"""
Vectorless RAG — retrieval by LLM reasoning over a document tree.

The idea
--------
Everything else in this project retrieves by **similarity**: embed the corpus,
embed the query, compare vectors. Vectorless RAG (the approach behind
PageIndex) throws that out. There are **no embeddings, no vector database, and
no fixed-size chunking**. Instead the documents are organised into a tree, and
an LLM *navigates* it the way a person uses a table of contents:

    root
     |-- attention_is_all_you_need.pdf
     |     |-- section 1: "Attention Is All You Need - An Overview..."
     |     |-- section 2: "Scaled Dot-Product Attention..."
     |     '-- section 3: "Why Self-Attention..."
     |-- embedding_models_report.pdf
     |     '-- ...
     '-- ...

Retrieval becomes two reasoning steps:

1. **Which documents look relevant?**  The LLM sees the file names and a short
   preview of each section, and picks the files worth opening.
2. **Which sections inside them?**  The LLM sees the previews from just those
   files and picks the sections to read in full.

Then the selected section text is used to answer, exactly as in normal RAG.

Why it can beat similarity search
---------------------------------
* **No chunk-size tuning, and no severed context** — sections stay whole.
* **It reasons instead of matching.** A question needing a *comparison*
  ("which of these is managed?") or *multi-hop* logic has no single passage
  that is "similar" to it; an LLM reading a table of contents can still work
  out where to look.
* **The retrieval decision is explainable** — the model can state why it
  opened a document, which a cosine score cannot.

What it costs
-------------
* **LLM calls per query** instead of a vector lookup: slower and not free.
* **It does not scale like a vector index.** Previews for the whole corpus
  must fit in the navigation prompt, so this suits tens or hundreds of
  documents, not millions. (PageIndex's hosted service adds hierarchy and
  caching to push that further.)

This is a local, self-contained port of the crash-course repo's PageIndex
notebook: same mechanism, but running on Groq with no external service or
extra API key.
"""

import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.evaluation import call_with_retry

load_dotenv()


class VectorlessRAG:
    """Answers questions by having an LLM search a document tree.

    Parameters
    ----------
    documents:
        LangChain Documents from :func:`src.data_loader.load_all_documents`.
        They are grouped by ``source_file`` into a two-level tree; no
        chunking, embedding or indexing happens.
    model_name:
        Groq model. ``None`` auto-selects via :func:`src.search.resolve_model`.
    preview_chars:
        How much of each section to show during navigation. Larger previews
        mean better decisions and a bigger navigation prompt.
    """

    def __init__(self, documents: List[Any], model_name: Optional[str] = None,
                 preview_chars: int = 160):
        self.preview_chars = preview_chars
        self.tree = self._build_tree(documents)

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key == "your_groq_api_key_here":
            raise RuntimeError(
                "VectorlessRAG needs a GROQ_API_KEY in RAG/.env — retrieval "
                "itself is done by the LLM here, so there is no offline mode."
            )

        from langchain_groq import ChatGroq

        from src.search import resolve_model

        resolved = resolve_model(api_key, model_name)
        self.llm = ChatGroq(api_key=api_key, model=resolved,
                            temperature=0.0, max_tokens=1024)
        print(f"Vectorless RAG LLM initialized: {resolved}")
        print(f"Tree: {len(self.tree)} documents, "
              f"{sum(len(v) for v in self.tree.values())} sections, 0 embeddings")

    # ------------------------------------------------------------------ #
    # Tree construction — the only "indexing" that happens
    # ------------------------------------------------------------------ #
    def _build_tree(self, documents: List[Any]) -> "OrderedDict[str, List[Dict[str, Any]]]":
        """Group Documents by source file into ``{file: [section, ...]}``.

        Each source Document becomes one section, kept **whole** — this is the
        step where a similarity pipeline would instead chunk and embed.
        """
        tree: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        for doc in documents:
            source = doc.metadata.get("source_file", "unknown")
            tree.setdefault(source, []).append({
                "index": len(tree.get(source, [])),
                "text": doc.page_content,
                "metadata": doc.metadata,
            })
        return tree

    def table_of_contents(self) -> str:
        """Render the tree as a compact table of contents for the LLM.

        This string *is* the index — the entire retrieval mechanism is the
        model reading this and deciding where to look.
        """
        lines = []
        for source, sections in self.tree.items():
            lines.append(f"DOCUMENT: {source}")
            for section in sections:
                preview = " ".join(section["text"][: self.preview_chars].split())
                lines.append(f"  [{section['index']}] {preview}...")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str) -> str:
        """One LLM call, retried through rate limits."""
        response = call_with_retry(lambda: self.llm.invoke(prompt), label="vectorless")
        return (response.content or "").strip()

    # ------------------------------------------------------------------ #
    # Step 1 — pick documents
    # ------------------------------------------------------------------ #
    def select_documents(self, question: str) -> List[str]:
        """Ask the LLM which documents are worth opening.

        Returns
        -------
        list[str]
            Source file names the model chose. Falls back to every document
            if the reply cannot be matched, so a parsing failure degrades to
            "read everything" rather than to an empty answer.
        """
        names = list(self.tree.keys())
        reply = self._ask(
            "You are searching a document collection to answer a QUESTION.\n"
            "Below is the table of contents. Choose the documents most likely "
            "to contain the answer.\n"
            "Reply with ONLY a comma-separated list of exact document names, "
            "at most three.\n\n"
            f"QUESTION: {question}\n\n"
            f"TABLE OF CONTENTS:\n{self.table_of_contents()}"
        )
        chosen = [n for n in names if n.lower() in reply.lower()]
        return chosen or names

    # ------------------------------------------------------------------ #
    # Step 2 — pick sections inside those documents
    # ------------------------------------------------------------------ #
    def select_sections(self, question: str, doc_names: List[str]) -> List[Dict[str, Any]]:
        """Ask the LLM which sections of the chosen documents to read in full.

        Returns
        -------
        list[dict]
            The selected sections, each with ``source``, ``index`` and
            ``text``. Falls back to the first section of each chosen document
            when nothing parses.
        """
        listing = []
        for name in doc_names:
            listing.append(f"DOCUMENT: {name}")
            for section in self.tree[name]:
                preview = " ".join(section["text"][: self.preview_chars * 2].split())
                listing.append(f"  {name} #{section['index']}: {preview}...")

        reply = self._ask(
            "Choose the sections that contain the information needed to answer "
            "the QUESTION.\n"
            "Reply with ONLY a comma-separated list in the form "
            "filename#index (for example report.pdf#2), at most four.\n\n"
            f"QUESTION: {question}\n\n"
            f"SECTIONS:\n{chr(10).join(listing)}"
        )

        selected: List[Dict[str, Any]] = []
        for name, idx in re.findall(r"([\w\-. ]+?)\s*#\s*(\d+)", reply):
            name = name.strip()
            if name in self.tree and int(idx) < len(self.tree[name]):
                section = self.tree[name][int(idx)]
                selected.append({"source": name, "index": section["index"],
                                 "text": section["text"]})

        if not selected:
            for name in doc_names:
                if self.tree[name]:
                    section = self.tree[name][0]
                    selected.append({"source": name, "index": section["index"],
                                     "text": section["text"]})
        return selected

    # ------------------------------------------------------------------ #
    # Step 3 — answer
    # ------------------------------------------------------------------ #
    def query(self, question: str, verbose: bool = True) -> Dict[str, Any]:
        """Answer a question by navigating the tree, with no vector search.

        Parameters
        ----------
        question:
            The user's question.
        verbose:
            Print each navigation decision as it is made.

        Returns
        -------
        dict
            ``answer``, the ``documents_selected``, the ``sections_selected``,
            and the number of ``llm_calls`` the query cost.
        """
        doc_names = self.select_documents(question)
        if verbose:
            print(f"   step 1 · opened documents: {doc_names}")

        sections = self.select_sections(question, doc_names)
        if verbose:
            labels = [f"{s['source']}#{s['index']}" for s in sections]
            print(f"   step 2 · selected sections: {labels}")

        context = "\n\n".join(
            f"[{s['source']} #{s['index']}]\n{s['text']}" for s in sections
        )
        answer = self._ask(
            "Use the following sections to answer the question concisely.\n\n"
            f"SECTIONS:\n{context}\n\n"
            f"QUESTION: {question}\n\nANSWER:"
        )
        return {
            "answer": answer,
            "documents_selected": doc_names,
            "sections_selected": [f"{s['source']}#{s['index']}" for s in sections],
            "llm_calls": 3,
        }

    def print_query(self, question: str) -> Dict[str, Any]:
        """Run :meth:`query` and print the navigation path and answer."""
        print(f"Q: {question}")
        result = self.query(question)
        print(f"A: {result['answer']}\n")
        return result
