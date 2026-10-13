"""
Typesense vector store — the open-source search engine option.

Where this fits
---------------
This project already has two vector stores:

* **ChromaDB** (notebook 02) — embedded, zero setup, great for prototyping.
* **FAISS** (``src/vector_store.py``) — an in-process index saved to a file.

Both live *inside* your Python process. **Typesense** is different: it is a
standalone search **server** you talk to over HTTP, which is what you actually
want once more than one application needs the same index. It also does
keyword search natively, so it can run the sparse and dense halves of hybrid
retrieval in one engine.

    ChromaDB / FAISS                    Typesense
    ------------------------            ------------------------
    a library in your process           a server you connect to
    index lives in a local file         index lives in the server
    one process at a time               many clients, concurrently
    vector search                       vector + keyword + filters

The crash course demonstrates Typesense in ``typesense.ipynb``; this module is
the same idea as a reusable component matching the interface of
:class:`~src.vector_store.FaissVectorStore`, so it is a drop-in swap.

Running a server first
----------------------
Typesense is not embedded — nothing here works without a server. The quickest
way is Docker::

    docker run -p 8108:8108 -v "$(pwd)/typesense-data:/data" \\
      typesense/typesense:27.1 \\
      --data-dir /data --api-key=devkey --enable-cors

Then point this class at it (``api_key="devkey"``).

.. warning::
   **Unverified against a live server.** Docker was unavailable in the
   environment where this project was built, so unlike every other module here
   this one has *not* been run end-to-end — only its API usage was checked
   against the installed ``typesense`` 2.0 client. Treat it as a reviewed
   starting point rather than tested code, and expect to adjust details on
   first run. :meth:`ping` exists to tell you immediately whether the server
   is reachable.
"""

import os
from typing import Any, Dict, List, Optional

import numpy as np


class TypesenseVectorStore:
    """A vector store backed by a Typesense server.

    Mirrors :class:`~src.vector_store.FaissVectorStore`
    (:meth:`build_from_documents`, :meth:`query`) so the rest of the pipeline
    does not care which store it is talking to.

    Parameters
    ----------
    collection_name:
        Typesense collection to create/use — the equivalent of a table.
    host, port, protocol:
        Where the server is. Defaults match the Docker command above.
    api_key:
        Server API key. Falls back to the ``TYPESENSE_API_KEY`` environment
        variable, then to ``"devkey"``.
    model_name:
        Embedding model, kept identical to the rest of the project so query
        and document vectors share one space.
    embedding_dim:
        Vector width, which Typesense needs **declared up front** in the
        schema (``num_dim``) — unlike FAISS, which infers it on first insert.
    """

    def __init__(
        self,
        collection_name: str = "rag_chunks",
        host: str = "localhost",
        port: str = "8108",
        protocol: str = "http",
        api_key: Optional[str] = None,
        model_name: str = "all-MiniLM-L6-v2",
        embedding_dim: int = 384,
    ):
        import typesense
        from sentence_transformers import SentenceTransformer

        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.client = typesense.Client({
            "nodes": [{"host": host, "port": port, "protocol": protocol}],
            "api_key": api_key or os.getenv("TYPESENSE_API_KEY", "devkey"),
            "connection_timeout_seconds": 5,
        })
        print(f"Loading embedding model for Typesense store: {model_name} ...")
        self.model = SentenceTransformer(model_name)

    # ------------------------------------------------------------------ #
    def ping(self) -> bool:
        """Return ``True`` if the server answers, printing guidance if not.

        Call this first. Every other method fails with a connection error
        when no server is running, and that error is far less clear than this.
        """
        try:
            self.client.operations.is_healthy()
            print("Typesense server is reachable")
            return True
        except Exception as exc:  # noqa: BLE001 - surface any connection problem
            print(f"Typesense server NOT reachable ({type(exc).__name__}). "
                  "Start one with:\n"
                  "  docker run -p 8108:8108 -v \"$(pwd)/typesense-data:/data\" \\\n"
                  "    typesense/typesense:27.1 --data-dir /data "
                  "--api-key=devkey --enable-cors")
            return False

    # ------------------------------------------------------------------ #
    def create_collection(self, drop_existing: bool = False) -> None:
        """Create the collection schema.

        The schema declares a ``float[]`` field with ``num_dim`` for the
        vector, plus plain fields for the chunk text and its provenance so
        results stay traceable and filterable — the same metadata discipline
        the rest of this project keeps.

        Parameters
        ----------
        drop_existing:
            Delete the collection first. Needed when the schema changes,
            since Typesense schemas are fixed once created.
        """
        if drop_existing:
            try:
                self.client.collections[self.collection_name].delete()
                print(f"Dropped existing collection '{self.collection_name}'")
            except Exception:  # noqa: BLE001 - absent collection is fine
                pass

        schema = {
            "name": self.collection_name,
            "fields": [
                {"name": "content", "type": "string"},
                {"name": "source_file", "type": "string", "facet": True},
                {"name": "file_type", "type": "string", "facet": True},
                {"name": "page", "type": "int32", "optional": True},
                {"name": "embedding", "type": "float[]", "num_dim": self.embedding_dim},
            ],
        }
        try:
            self.client.collections.create(schema)
            print(f"Created collection '{self.collection_name}' "
                  f"({self.embedding_dim}-dim vectors)")
        except Exception as exc:  # noqa: BLE001 - most often "already exists"
            print(f"create_collection: {type(exc).__name__}: {str(exc)[:120]}")

    # ------------------------------------------------------------------ #
    def build_from_documents(self, documents: List[Any], chunk_size: int = 1000,
                             chunk_overlap: int = 200) -> None:
        """Chunk, embed and upload documents to the server.

        Same injection pipeline as the FAISS store — only the final storage
        step differs.
        """
        from src.embedding import EmbeddingPipeline

        pipeline = EmbeddingPipeline(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = pipeline.chunk_documents(documents)
        embeddings = pipeline.embed_chunks(chunks)

        payload: List[Dict[str, Any]] = []
        for chunk, vector in zip(chunks, embeddings):
            page = chunk.metadata.get("page")
            payload.append({
                "content": chunk.page_content,
                "source_file": str(chunk.metadata.get("source_file", "unknown")),
                "file_type": str(chunk.metadata.get("file_type", "unknown")),
                # Typesense is strictly typed: page must be an int or omitted.
                **({"page": int(page)} if isinstance(page, int) else {}),
                "embedding": np.asarray(vector, dtype=np.float32).tolist(),
            })

        results = self.client.collections[self.collection_name].documents.import_(
            payload, {"action": "upsert"}
        )
        failures = [r for r in results if isinstance(r, dict) and not r.get("success", True)]
        print(f"Uploaded {len(payload) - len(failures)}/{len(payload)} chunks to Typesense")
        if failures:
            print(f"  {len(failures)} failed, first error: {failures[0].get('error')}")

    # ------------------------------------------------------------------ #
    def query(self, query_text: str, top_k: int = 3,
              filter_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """Vector-search the collection.

        Parameters
        ----------
        query_text:
            The user's question.
        top_k:
            Number of chunks to return.
        filter_by:
            Optional Typesense filter, e.g. ``"file_type:=pdf"``. This is the
            payoff of declaring facet fields — something a bare FAISS index
            cannot do at all.

        Returns
        -------
        list[dict]
            ``content``, ``metadata`` and ``distance`` per hit — the same
            shape :class:`FaissVectorStore.query` returns, so retrievers and
            the evaluation module work unchanged.
        """
        vector = self.model.encode([query_text])[0].astype(np.float32).tolist()
        search: Dict[str, Any] = {
            "collection": self.collection_name,
            "q": "*",
            "vector_query": f"embedding:([{','.join(map(str, vector))}], k:{top_k})",
        }
        if filter_by:
            search["filter_by"] = filter_by

        response = self.client.multi_search.perform({"searches": [search]}, {})
        hits = response["results"][0].get("hits", [])

        out: List[Dict[str, Any]] = []
        for hit in hits:
            doc = hit["document"]
            out.append({
                "content": doc.get("content", ""),
                "metadata": {
                    "source_file": doc.get("source_file", "unknown"),
                    "file_type": doc.get("file_type", "unknown"),
                    "page": doc.get("page", "n/a"),
                },
                # Typesense reports vector_distance; keep the FAISS key name.
                "distance": float(hit.get("vector_distance", 0.0)),
            })
        return out

    def keyword_query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Plain keyword search — the half FAISS and Chroma cannot do.

        Useful for exact identifiers (error codes, part numbers, ticket IDs)
        that semantic search reliably misses, and the basis for building
        hybrid retrieval on a single engine.
        """
        response = self.client.collections[self.collection_name].documents.search({
            "q": query_text,
            "query_by": "content",
            "per_page": top_k,
        })
        return [{
            "content": hit["document"].get("content", ""),
            "metadata": {"source_file": hit["document"].get("source_file", "unknown")},
            "text_match": hit.get("text_match", 0),
        } for hit in response.get("hits", [])]
