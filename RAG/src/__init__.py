"""
RAG pipeline package — modular implementation of the crash-course pipeline.

The package links four components into a single pipeline, in the same order
the data flows through a RAG system:

    data_loader.py   ->  Data Ingestion   (files -> LangChain Documents)
    embedding.py     ->  Chunking + Embeddings (Documents -> chunks -> vectors)
    vector_store.py  ->  Vector Store     (FAISS index persisted to disk)
    search.py        ->  Retrieval + Augmentation + Generation (query -> answer)

`app.py` at the project root wires these together end-to-end.
"""
