# RAG Pipeline — LangChain Crash Course Implementation

A complete Retrieval Augmented Generation (RAG) pipeline implemented by following the
*"Complete RAG Crash Course With Langchain In 2 Hours"* transcript (included in this
folder). It uses the same components, classes, open-source embedding model, and
retrieval strategy as the course:

| Piece | Choice (same as the course) |
|---|---|
| Framework | LangChain (`langchain`, `langchain-core`, `langchain-community`) |
| Document loaders | `PyPDFLoader`, `PyMuPDFLoader`, `TextLoader`, `DirectoryLoader`, `CSVLoader`, `Docx2txtLoader` + custom JSON/Excel/SQLite loaders (7 formats) |
| Chunking | `RecursiveCharacterTextSplitter` — chunk size 1000, overlap 200 |
| Embeddings | Open-source `all-MiniLM-L6-v2` (sentence-transformers, 384-dim, runs locally) |
| Vector stores | ChromaDB (notebook) and FAISS (modular `src/` pipeline), both persisted to disk |
| Retrieval | Query embedding → similarity search → `similarity = 1 − distance` → score threshold |
| LLM | Groq-hosted open model via `langchain-groq` — auto-selected, currently `openai/gpt-oss-120b`* |

\* Groq rotates its catalog: the course's `gemma2-9b-it` and its successor
`llama-3.1-8b-instant` are both decommissioned. Rather than hard-code a name that
expires, `src/search.py` exposes `resolve_model()`, which asks Groq what your key can
actually use and picks the best available open model. Pin one explicitly with
`RAGSearch(store, model_name="...")` if you prefer.

## How RAG works (the two pipelines)

```
DATA INJECTION PIPELINE  (run once, or when documents change)
  files (PDF/TXT/...) ─▶ parse to Documents ─▶ chunk ─▶ embed ─▶ vector store

QUERY RETRIEVAL PIPELINE (run per question)
  query ─▶ embed (same model) ─▶ similarity search ─▶ context
        ─▶ context + prompt (Augmentation) ─▶ LLM (Generation) ─▶ answer
```

## Project structure

```
RAG/
├── notebooks/
│   ├── 01_document_structure.ipynb              # Document structure + loaders (TXT, PDF, directory)
│   ├── 02_pdf_rag_pipeline.ipynb                # Full pipeline: ingestion → ChromaDB → retrieval → Groq LLM
│   ├── 03_multi_format_assignment.ipynb         # Assignment: CSV, JSON, Excel, SQLite → same pipeline
│   ├── 04_transformers_embeddings_deep_dive.ipynb  # Theory deep dive (see below)
│   ├── 05_rag_evaluation.ipynb                  # Is it any good? retrieval metrics + LLM-as-judge
│   ├── 06_agentic_rag.ipynb                     # LangGraph: routing, self-grading, query rewriting
│   └── 07_vectorless_and_typesense.ipynb        # Vectorless (PageIndex-style) RAG + Typesense server
├── src/                              # The same pipeline as modular, reusable code
│   ├── data_loader.py                #   load_all_documents(): 7 file formats → LangChain Documents
│   ├── embedding.py                  #   EmbeddingPipeline: chunk_documents() + embed_chunks()
│   ├── vector_store.py               #   FaissVectorStore: build / save / load / query
│   ├── search.py                     #   RAGSearch: retrieval + augmentation + Groq generation
│   ├── evaluation.py                 #   Retrieval metrics + 4 LLM-as-a-judge evaluators (see below)
│   ├── agentic_rag.py                #   AgenticRAG: LangGraph self-correcting graph
│   ├── vectorless_rag.py             #   VectorlessRAG: LLM tree search, no embeddings
│   └── typesense_store.py            #   TypesenseVectorStore (needs a running server)
├── app.py                            # End-to-end runner wiring the src/ components together
├── scripts/
│   ├── generate_sample_data.py       # Creates the whole sample knowledge base locally
│   ├── demo_chunking_strategies.py   # Runs every chunking strategy side by side
│   ├── demo_embeddings_similarity.py # Tokenization → pooling → cosine, end to end
│   ├── clean_notebook_widgets.py     # Strips un-renderable progress-bar output after nbconvert
│   └── run_evaluation.py             # One-command pipeline evaluation
├── data/
│   ├── text_files/                   # Generated sample .txt files
│   ├── pdf/                          # Generated sample .pdf files
│   ├── csv/                          # ai_models.csv — one Document per row (CSVLoader)
│   ├── json/                         # rag_faq.json — one Document per FAQ entry
│   ├── excel/                        # vector_databases.xlsx — one Document per sheet row
│   ├── sqlite/                       # llm_catalog.db — one Document per table row
│   ├── word/                         # retrieval_evaluation.docx — one Document per file
│   └── vector_store/                 # ChromaDB persistence (created by notebook 02)
├── eval/
│   └── golden_qa.json                # 12 questions + expected sources + reference answers
├── faiss_store/                      # FAISS persistence (created by app.py)
├── requirements.txt
├── .env.example                      # Template for your GROQ_API_KEY
└── README.md
```

## Learning companions

Three illustrated reference docs, built from real output of this pipeline:

| Doc | Covers |
|---|---|
| [Pipeline Blueprint](https://claude.ai/code/artifact/6a81bfc2-a842-4dd3-800a-b7cb58c143c2) | **Architecture & API reference** — the two-pipeline data flow, module dependency layers, a step-by-step trace of what `app.py` actually does, every file's public API, and a "where to change things" lookup table |
| [The Chunking Handbook](https://claude.ai/code/artifact/b8273dc9-07a5-4886-a641-fad02c884f76) | 13 chunking strategies — fixed-size, recursive, sentence, token, structure-aware, record, semantic, parent-document, sentence-window, contextual, late chunking, propositions, RAPTOR — plus a decision guide |
| [Vectors & Angles](https://claude.ai/code/artifact/4700a7f1-7917-4ea5-9147-7ea0646c8389) | Sentence transformers and cosine similarity from first principles: tokenization, mean pooling, the cosine formula worked by hand, cosine vs dot vs L2, and the production traps |

Reproduce every number in them with:

```bash
python scripts/demo_chunking_strategies.py     # → scripts/out_chunking.json
python scripts/demo_embeddings_similarity.py   # → scripts/out_embeddings.json
```

## Setup

Requires Python 3.13 (3.10+ works). From the `RAG/` folder:

```bash
# 1. Create and activate a virtual environment (uv shown; plain venv works too)
uv venv .venv                    # or: python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
uv pip install -r requirements.txt   # or: pip install -r requirements.txt

# 3. Generate the sample knowledge base (TXT + PDF files under data/)
python scripts/generate_sample_data.py

# 4. (Optional, enables answer generation) add your free Groq API key
cp .env.example .env
# then edit .env and set GROQ_API_KEY — free key at https://console.groq.com/keys
```

Without a `GROQ_API_KEY`, **retrieval still works fully** — only the final LLM
answer-generation step is skipped (the code degrades gracefully and tells you).

The first run downloads the `all-MiniLM-L6-v2` embedding model (~90 MB) from
Hugging Face; afterwards everything runs locally.

## Running the pipeline

### Option A — Notebooks (learning path, matches the course order)

```bash
source .venv/bin/activate
jupyter notebook notebooks/
```

1. **`01_document_structure.ipynb`** — the LangChain `Document` structure
   (`page_content` + `metadata`), `TextLoader`, `DirectoryLoader`, `PyMuPDFLoader`.
2. **`02_pdf_rag_pipeline.ipynb`** — the complete pipeline: `process_all_pdfs()` →
   `split_documents()` → `EmbeddingManager` → `VectorStore` (ChromaDB) →
   `RAGRetriever` → `rag_simple()` / `rag_advanced()` / `rag_pipeline_advanced()`
   (sources, confidence, citations, streaming, history, summarization).
3. **`03_multi_format_assignment.ipynb`** — the course assignment, completed: the same
   pipeline over **CSV** (`CSVLoader`), **JSON** (custom stdlib loader), **Excel**
   (custom `openpyxl` loader), and **SQLite** (custom `sqlite3` loader), with
   per-format retrieval tests proving each query lands in the right file.
4. **`04_transformers_embeddings_deep_dive.ipynb`** — theory at working-engineer depth:
   - **Transformers end to end**: tokenization (BPE/WordPiece), positional encodings
     (sinusoidal/learned/RoPE/ALiBi), scaled dot-product attention **implemented from
     scratch in NumPy** (with causal masking), multi-head attention, FFN/residuals/
     LayerNorm, encoder vs decoder vs enc-dec families, KV cache / GQA / FlashAttention.
   - **Embedding models**: word2vec → BERT → Sentence-BERT, pooling (mean pooling
     reproduced by hand and verified against the library), contrastive training
     (InfoNCE/MNRL, temperature, in-batch + hard negatives), bi- vs cross-encoders and
     reranking, cosine/dot/L2 equivalences, Matryoshka + instruction-tuned embeddings.
   - **Embedding techniques**: sparse (TF-IDF/BM25/SPLADE), multi-vector (ColBERT),
     **hybrid retrieval with Reciprocal Rank Fusion (runnable demo)**, ANN indexes
     (HNSW/IVF/PQ) and quantization.
   - **Chunking techniques**: fixed vs recursive vs token-based vs structure-aware
     (all demonstrated), a **semantic chunker implemented from scratch**, and advanced
     patterns (parent-document, contextual retrieval, late chunking, RAPTOR).
   - **Knowledge distillation**: soft targets and temperature (runnable), feature vs
     relation distillation, DistilBERT and MiniLM (the pipeline's own embedding model
     is a distilled student), cross-encoder→bi-encoder distillation, a PCA
     dimensionality-reduction demo, and distillation vs quantization vs pruning.
5. **`05_rag_evaluation.ipynb`** — measuring whether the pipeline actually works.
   Deterministic **retrieval metrics** (hit rate, MRR, recall@k, precision@k) against
   a 12-question golden set, a `top_k` sweep that shows *measurably* why `top_k=3` is
   right, and all **four LLM-as-a-judge** generation metrics on Groq — correctness,
   relevance, groundedness and retrieval relevance. Includes a real hallucination the
   groundedness judge caught while correctness scored 100%, a demonstration of judge
   non-determinism, and a warning about test-set contamination that bit during development.
6. **`06_agentic_rag.ipynb`** — **LangGraph** turns the straight pipeline into a graph
   with decisions: question **routing**, document **self-grading**, **query rewriting**
   on failure, and an honest "I don't know" when the corpus can't answer. Ends with a
   side-by-side where traditional RAG confidently hallucinates an answer the agentic
   version correctly refuses.
7. **`07_vectorless_and_typesense.ipynb`** — **Vectorless RAG** (the PageIndex idea):
   no embeddings, no chunking, no vector DB — an LLM navigates a table of contents by
   reasoning. Plus **Typesense**, a standalone search server with vector *and* keyword
   search and metadata filtering.

All notebooks are committed **pre-executed** so you can read the outputs without
running anything.

### Option B — Modular pipeline (production path)

```bash
source .venv/bin/activate
python app.py                                  # default query: "What is the attention mechanism?"
python app.py "hard negative mining techniques"  # ask your own question
```

- **First run** builds everything: loads `data/`, chunks, embeds, and saves a FAISS
  index to `faiss_store/`.
- **Later runs** load the persisted index directly — no re-ingestion. To force a
  rebuild (e.g. after adding documents to `data/`), delete the `faiss_store/` folder.

### Option C — Measure it

```bash
python scripts/run_evaluation.py            # retrieval metrics + top_k sweep (free, instant)
python scripts/run_evaluation.py --judge     # add LLM-as-a-judge metrics (uses Groq quota)
```

Current measured baseline on the 12-question golden set:

| top_k | hit rate | MRR | recall@k | precision@k |
|---|---|---|---|---|
| 1 | 91.7% | 0.917 | 83.3% | 91.7% |
| **3** | **100.0%** | **0.958** | **95.8%** | **66.7%** |
| 5 | 100.0% | 0.958 | 100.0% | 50.0% |
| 10 | 100.0% | 0.958 | 100.0% | 29.2% |

`top_k=3` reaches full hit rate; higher values only dilute precision — which is why
the pipeline defaults to 3.

All four LLM-as-a-judge evaluators, on the same 12 questions:

| Evaluator | Compares | Needs labels | Result |
|---|---|---|---|
| correctness | answer vs reference answer | **yes** | **100%** (12/12) |
| relevance | answer vs question | no | **5.00** / 5 |
| groundedness | answer vs retrieved context | no | **4.75–4.83** / 5 |
| retrieval relevance | context vs question | no | **5.00** / 5 |

Correctness at 100% while groundedness is below 5 is the point of running more than one:
every answer was factually right, but two contained a claim the retrieved context never
made. Correctness alone would have called the pipeline flawless.

Groundedness is given as a range because it genuinely moves between runs. Across three
identical runs, correctness / relevance / retrieval relevance were **identical every
time** and only groundedness varied — so treat a ±0.1 change there as noise.

Change one thing, re-run, compare. That's the loop that turns tuning into engineering.

Example output:

```
=== Raw retrieval results ===
[1] attention_is_all_you_need.pdf (page 0, distance 0.7134)
    The attention mechanism can be described as mapping a query and a set of key-value pairs...

=== RAG answer (Groq LLM) ===
Q: What is the attention mechanism?
A: The attention mechanism maps a query and a set of key-value pairs to an output ...
Sources:
  - attention_is_all_you_need.pdf (page 0)
```

## Using your own documents

1. Drop your PDFs / TXT files anywhere under `data/`.
2. Delete `faiss_store/` (and `data/vector_store/` if re-running the notebook).
3. Re-run `python app.py` (or notebook 02) — the injection pipeline rebuilds the index.

## Assignments (from the course) — ✅ completed

- ✅ `src/data_loader.py` now handles **CSV** (`CSVLoader`), **JSON** (custom stdlib
  loader), **Excel** (custom `openpyxl` loader), and **SQLite** (custom `sqlite3`
  loader) in addition to PDF and TXT — see `03_multi_format_assignment.ipynb` for the
  walkthrough and per-format retrieval tests. The chunking/embedding/vector-store code
  needed **zero changes** — that's the point of the `Document` abstraction.
- ✅ Chunking strategies compared hands-on (fixed vs recursive vs token-based vs
  structure-aware vs semantic) in `04_transformers_embeddings_deep_dive.ipynb` Part D.

Stretch ideas if you want to go further:

- Add a **web** source (`WebBaseLoader`) or **S3** (`S3DirectoryLoader`) to the loader.
- Swap FAISS ↔ ChromaDB in the modular pipeline — the interfaces are equivalent.
- Add a **cross-encoder reranker** between retrieval and generation (notebook 04, B.4).
- Implement **hybrid retrieval** in `src/` using the RRF demo from notebook 04, C.2.

## Troubleshooting

| Problem | Fix |
|---|---|
| `GROQ_API_KEY not set` warning | Copy `.env.example` → `.env` and add your key (retrieval works regardless) |
| `model_not_found` / 404 from Groq | `resolve_model()` normally prevents this; if you pinned `model_name` explicitly, drop it to auto-select, or check https://console.groq.com/docs/models |
| Empty `answer` from a `gpt-oss` model | These are reasoning models — they spend part of the token budget on hidden reasoning. Raise `max_tokens` (the default 1024 is enough). |
| Duplicate results in notebook 02 | Re-running the insert cell re-adds chunks; delete `data/vector_store/` and re-run the notebook |
| Stale FAISS answers after adding docs | Delete `faiss_store/` so `app.py` rebuilds the index |
| `Could not render content for 'application/vnd.jupyter.widget-view+json'` | Cosmetic leftover progress bar from a headless notebook run — nothing failed. Run `python scripts/clean_notebook_widgets.py` |
| Slow first query | One-time Hugging Face model download; subsequent runs are local and fast |
