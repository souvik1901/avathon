"""
End-to-end RAG pipeline runner — wires all the modular components together.

Flow (matches the crash-course app.py):

    load_all_documents  ->  FaissVectorStore.build_from_documents  (first run)
                            FaissVectorStore.load                  (later runs)
                        ->  RAGSearch.search_and_summarize         (query time)

* First run:  reads data/, chunks + embeds everything, persists the FAISS
  index to faiss_store/.
* Later runs: skips ingestion entirely and loads the persisted index — this
  is the whole point of the persistent vector store.

Run from the RAG folder:

    python app.py                      # uses the default demo query
    python app.py "your question"      # ask your own question
"""

import sys

from src.data_loader import load_all_documents
from src.search import RAGSearch
from src.vector_store import FaissVectorStore

DATA_DIR = "data"
PERSIST_DIR = "faiss_store"


def main(query: str) -> None:
    """Build (or load) the vector store, then answer ``query`` through RAG."""
    store = FaissVectorStore(persist_directory=PERSIST_DIR)

    if store.exists():
        # Injection already done on a previous run — just load the index.
        store.load()
    else:
        # First run: full data-injection pipeline (load -> chunk -> embed -> save).
        documents = load_all_documents(DATA_DIR)
        store.build_from_documents(documents)

    # --- Retrieval only (no LLM): raw similarity search --------------------
    print("\n=== Raw retrieval results ===")
    for i, hit in enumerate(store.query(query, top_k=3), start=1):
        source = hit["metadata"].get("source_file", "unknown")
        page = hit["metadata"].get("page", "n/a")
        print(f"[{i}] {source} (page {page}, distance {hit['distance']:.4f})")
        print(f"    {hit['content'][:200]}...\n")

    # --- Full RAG: retrieval + augmentation + generation --------------------
    print("=== RAG answer (Groq LLM) ===")
    rag_search = RAGSearch(store)
    result = rag_search.search_and_summarize(query, top_k=3)
    print(f"\nQ: {query}")
    print(f"A: {result['answer']}\n")
    print("Sources:")
    for src in result["sources"]:
        print(f"  - {src['source_file']} (page {src['page']})")


if __name__ == "__main__":
    user_query = sys.argv[1] if len(sys.argv) > 1 else "What is the attention mechanism?"
    main(user_query)
