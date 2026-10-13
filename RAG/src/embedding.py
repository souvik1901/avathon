"""
Chunking + Embedding component (Steps 2 and 3 of the data-injection pipeline).

Responsibility
--------------
1. **Chunking** — split the loaded Documents into smaller overlapping pieces.
   Every embedding model (and every LLM) has a fixed context size, so a whole
   100-page PDF can never be embedded in one shot. Chunking keeps each piece
   within the model's limit while the *overlap* preserves continuity between
   neighbouring chunks so no sentence gets cut off from its context.

2. **Embedding** — convert each chunk's text into a dense vector using an
   open-source Hugging Face model (``all-MiniLM-L6-v2``, 384 dimensions) via
   the ``sentence-transformers`` library. Vectors are the numerical
   representation of text that lets the vector store run similarity /
   cosine-similarity search.
"""

from typing import Any, List

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


class EmbeddingPipeline:
    """Chunks LangChain Documents and embeds them with a sentence-transformer.

    Parameters
    ----------
    model_name:
        Hugging Face sentence-transformers model to use. The default,
        ``all-MiniLM-L6-v2``, is a small, fast, fully open-source model that
        maps text to 384-dimensional vectors — the same model used in the
        crash course.
    chunk_size:
        Maximum number of characters per chunk (default 1000).
    chunk_overlap:
        Number of characters shared between consecutive chunks (default 200)
        so context flows across chunk boundaries.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        print(f"Loading embedding model: {model_name} ...")
        self.model = SentenceTransformer(model_name)
        # sentence-transformers 6.x renamed get_sentence_embedding_dimension;
        # prefer the new name, fall back for older versions.
        get_dim = getattr(
            self.model, "get_embedding_dimension",
            getattr(self.model, "get_sentence_embedding_dimension", lambda: "?"),
        )
        print(f"Model loaded. Embedding dimension: {get_dim()}")

    def chunk_documents(self, documents: List[Any]) -> List[Any]:
        """Split a list of Documents into smaller overlapping chunks.

        Uses :class:`RecursiveCharacterTextSplitter`, which tries the
        separators **in order** — paragraph breaks first (``"\\n\\n"``), then
        line breaks, then spaces, then individual characters — so chunks
        break at the most natural boundary available.

        Parameters
        ----------
        documents:
            The Documents produced by :func:`src.data_loader.load_all_documents`.

        Returns
        -------
        list[Document]
            The chunked Documents. Each chunk keeps the metadata of the
            Document it was split from.
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )
        chunks = splitter.split_documents(documents)
        print(f"Split {len(documents)} documents into {len(chunks)} chunks")
        return chunks

    def embed_chunks(self, chunks: List[Any]) -> np.ndarray:
        """Convert every chunk's ``page_content`` into an embedding vector.

        Parameters
        ----------
        chunks:
            Chunked Documents from :meth:`chunk_documents`.

        Returns
        -------
        numpy.ndarray
            Array of shape ``(num_chunks, embedding_dim)`` — one row per
            chunk, ready to be inserted into the vector store.
        """
        texts = [chunk.page_content for chunk in chunks]
        embeddings = self.model.encode(texts, show_progress_bar=True)
        print(f"Generated embeddings with shape {embeddings.shape}")
        return embeddings
