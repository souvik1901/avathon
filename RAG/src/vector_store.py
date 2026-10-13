"""
Vector Store component (Step 4 of the data-injection pipeline).

Responsibility
--------------
Persist the chunk embeddings so similarity search can run against them, and
answer queries at retrieval time. This modular version uses **FAISS**
(Facebook AI Similarity Search) — the open-source library used in the
crash course's ``src/`` pipeline — while the notebook version demonstrates
**ChromaDB**. Both are interchangeable at this layer.

Persistence layout (inside ``persist_directory``):

* ``faiss.index``    — the FAISS index holding the raw vectors
* ``metadata.pkl``   — a pickle with each chunk's text + metadata, kept in
  the same order as the index rows so row *i* of the index maps to entry
  *i* of the metadata list.
"""

import pickle
from pathlib import Path
from typing import Any, Dict, List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from src.embedding import EmbeddingPipeline


class FaissVectorStore:
    """FAISS-backed vector store with disk persistence.

    Parameters
    ----------
    persist_directory:
        Folder where ``faiss.index`` and ``metadata.pkl`` are saved/loaded.
    model_name:
        Embedding model used both to build the index and to embed incoming
        queries. **Must be the same model in both phases**, otherwise query
        vectors and document vectors live in different spaces and similarity
        search returns garbage.
    chunk_size / chunk_overlap:
        Forwarded to :class:`EmbeddingPipeline` when building from documents.
    """

    def __init__(
        self,
        persist_directory: str = "faiss_store",
        model_name: str = "all-MiniLM-L6-v2",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self.persist_directory = Path(persist_directory)
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.index: faiss.Index | None = None      # the FAISS vector index
        self.metadata: List[Dict[str, Any]] = []   # row-aligned chunk info

        print(f"Loading embedding model for vector store: {model_name} ...")
        self.model = SentenceTransformer(model_name)

    # ------------------------------------------------------------------ #
    # Build phase (data-injection pipeline)
    # ------------------------------------------------------------------ #
    def build_from_documents(self, documents: List[Any]) -> None:
        """Run the full injection pipeline: chunk -> embed -> index -> save.

        Parameters
        ----------
        documents:
            LangChain Documents from :func:`src.data_loader.load_all_documents`.
        """
        pipeline = EmbeddingPipeline(
            model_name=self.model_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        chunks = pipeline.chunk_documents(documents)
        embeddings = pipeline.embed_chunks(chunks)

        # Keep text + metadata aligned with the index rows for retrieval.
        self.metadata = [
            {"content": chunk.page_content, "metadata": chunk.metadata}
            for chunk in chunks
        ]
        self.add_embeddings(np.asarray(embeddings, dtype=np.float32))
        self.save()

    def add_embeddings(self, embeddings: np.ndarray) -> None:
        """Insert embedding vectors into the FAISS index.

        Creates an ``IndexFlatL2`` (exact L2-distance search) on first use —
        the simplest FAISS index and the one used in the crash course.

        Parameters
        ----------
        embeddings:
            ``float32`` array of shape ``(num_vectors, dim)``.
        """
        if self.index is None:
            dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)
        print(f"Vector store now holds {self.index.ntotal} vectors")

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        """Write the FAISS index and the metadata pickle to disk."""
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.persist_directory / "faiss.index"))
        with open(self.persist_directory / "metadata.pkl", "wb") as f:
            pickle.dump(self.metadata, f)
        print(f"Saved FAISS index + metadata to '{self.persist_directory}'")

    def load(self) -> None:
        """Load a previously saved index + metadata from disk.

        After loading, the store is immediately queryable — no need to
        re-read or re-embed the source documents.
        """
        print(f"Loading FAISS index and metadata from '{self.persist_directory}'")
        self.index = faiss.read_index(str(self.persist_directory / "faiss.index"))
        with open(self.persist_directory / "metadata.pkl", "rb") as f:
            self.metadata = pickle.load(f)
        print(f"Loaded {self.index.ntotal} vectors")

    def exists(self) -> bool:
        """Return ``True`` when a persisted index is already on disk."""
        return (self.persist_directory / "faiss.index").exists()

    # ------------------------------------------------------------------ #
    # Retrieval phase (query pipeline)
    # ------------------------------------------------------------------ #
    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Similarity-search the store for the chunks closest to a query.

        The query text is embedded with the *same* model used at build time,
        then FAISS returns the ``top_k`` nearest vectors by L2 distance.

        Parameters
        ----------
        query_text:
            The user's natural-language question.
        top_k:
            Number of chunks to retrieve (default 3).

        Returns
        -------
        list[dict]
            One dict per hit with keys ``content``, ``metadata`` and
            ``distance`` (smaller distance = more similar).
        """
        query_vector = self.model.encode([query_text]).astype(np.float32)
        distances, indices = self.index.search(query_vector, top_k)

        results: List[Dict[str, Any]] = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1:  # FAISS pads with -1 when fewer than top_k hits exist
                continue
            entry = self.metadata[idx]
            results.append(
                {
                    "content": entry["content"],
                    "metadata": entry["metadata"],
                    "distance": float(distance),
                }
            )
        return results
