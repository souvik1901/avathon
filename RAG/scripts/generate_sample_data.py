"""
Generate the sample knowledge base used by the RAG pipeline.

The crash course ingests text files plus a few research-paper PDFs
("Attention Is All You Need", an embedding-model technical report, ...).
To keep this project fully self-contained (no downloads), this script
creates equivalent sample files locally:

* ``data/text_files/*.txt`` — created with plain Python, exactly like the
  video's first notebook.
* ``data/pdf/*.pdf``        — created with PyMuPDF (fitz), covering the same
  topics the video's PDFs cover, so the demo queries from the video
  ("What is the attention mechanism?", "hard negative mining techniques")
  return meaningful results.

Run once from the RAG folder:  python scripts/generate_sample_data.py
"""

import csv
import json
import sqlite3
from pathlib import Path

import pymupdf  # PyMuPDF
from openpyxl import Workbook

BASE_DIR = Path(__file__).resolve().parent.parent
TEXT_DIR = BASE_DIR / "data" / "text_files"
PDF_DIR = BASE_DIR / "data" / "pdf"
CSV_DIR = BASE_DIR / "data" / "csv"
JSON_DIR = BASE_DIR / "data" / "json"
EXCEL_DIR = BASE_DIR / "data" / "excel"
SQLITE_DIR = BASE_DIR / "data" / "sqlite"
WORD_DIR = BASE_DIR / "data" / "word"

# --------------------------------------------------------------------------- #
# 1. Plain-text sample files (same idea as the video's python_intro.txt etc.)
# --------------------------------------------------------------------------- #
SAMPLE_TEXTS = {
    "python_intro.txt": (
        "Python Programming Introduction\n\n"
        "Python is a high-level, interpreted programming language known for its "
        "simplicity and readability. Created by Guido van Rossum and first released "
        "in 1991, Python has become one of the most popular programming languages "
        "for data science, machine learning, and artificial intelligence.\n\n"
        "Key features of Python include dynamic typing, automatic memory management, "
        "a comprehensive standard library, and support for multiple programming "
        "paradigms including procedural, object-oriented, and functional programming.\n\n"
        "Python's ecosystem for AI includes libraries such as NumPy for numerical "
        "computing, pandas for data manipulation, scikit-learn for classical machine "
        "learning, and PyTorch and TensorFlow for deep learning."
    ),
    "machine_learning.txt": (
        "Machine Learning Overview\n\n"
        "Machine learning is a subset of artificial intelligence that enables systems "
        "to learn and improve from experience without being explicitly programmed. "
        "There are three main types of machine learning: supervised learning, "
        "unsupervised learning, and reinforcement learning.\n\n"
        "Supervised learning uses labeled training data to learn a mapping from "
        "inputs to outputs. Common tasks include classification and regression. "
        "Unsupervised learning finds hidden patterns in unlabeled data, for example "
        "through clustering or dimensionality reduction. Reinforcement learning "
        "trains agents to make sequences of decisions by rewarding desired behaviors.\n\n"
        "Deep learning, a further subset based on multi-layer neural networks, has "
        "driven recent breakthroughs in computer vision, natural language processing, "
        "and speech recognition."
    ),
}

# --------------------------------------------------------------------------- #
# 2. Sample PDFs — same topics as the papers used in the video
# --------------------------------------------------------------------------- #
SAMPLE_PDFS = {
    "attention_is_all_you_need.pdf": [
        (
            "Attention Is All You Need — An Overview\n\n"
            "The Transformer is a neural network architecture based entirely on "
            "attention mechanisms, dispensing with recurrence and convolutions "
            "entirely. The dominant sequence transduction models before the "
            "Transformer were based on complex recurrent or convolutional neural "
            "networks that include an encoder and a decoder.\n\n"
            "The attention mechanism can be described as mapping a query and a set "
            "of key-value pairs to an output, where the query, keys, values, and "
            "output are all vectors. The output is computed as a weighted sum of "
            "the values, where the weight assigned to each value is computed by a "
            "compatibility function of the query with the corresponding key."
        ),
        (
            "Scaled Dot-Product Attention\n\n"
            "The particular attention used in the Transformer is called Scaled "
            "Dot-Product Attention. The input consists of queries and keys of "
            "dimension dk, and values of dimension dv. We compute the dot products "
            "of the query with all keys, divide each by the square root of dk, and "
            "apply a softmax function to obtain the weights on the values.\n\n"
            "Multi-Head Attention allows the model to jointly attend to information "
            "from different representation subspaces at different positions. Instead "
            "of performing a single attention function, the queries, keys and values "
            "are linearly projected h times with different learned projections, "
            "attention is applied in parallel, and the outputs are concatenated."
        ),
        (
            "Why Self-Attention\n\n"
            "Self-attention, sometimes called intra-attention, is an attention "
            "mechanism relating different positions of a single sequence in order "
            "to compute a representation of the sequence. Self-attention layers are "
            "faster than recurrent layers when the sequence length is smaller than "
            "the representation dimensionality, and they allow significantly more "
            "parallelization.\n\n"
            "Positional encodings are added to the input embeddings to inject "
            "information about the relative or absolute position of tokens in the "
            "sequence, since the model contains no recurrence and no convolution."
        ),
    ],
    "embedding_models_report.pdf": [
        (
            "Text Embedding Models — Technical Report\n\n"
            "Text embedding models convert natural language into dense numerical "
            "vectors that capture semantic meaning. Similar texts map to nearby "
            "points in the vector space, which enables semantic search, clustering, "
            "recommendation, and retrieval augmented generation.\n\n"
            "Modern embedding models are trained with contrastive learning: the "
            "model learns to pull semantically related pairs (a query and its "
            "relevant passage) close together while pushing unrelated pairs apart. "
            "Training typically uses a unified multitask learning framework that "
            "combines retrieval, classification, and semantic similarity objectives."
        ),
        (
            "Hard Negative Mining Techniques\n\n"
            "Hard negative mining is a technique for improving embedding model "
            "quality. Instead of sampling random negatives, hard negatives are "
            "passages that are lexically or semantically similar to the query but "
            "do not actually answer it. Training against several hard-candidate "
            "negatives forces the model to learn fine-grained distinctions and "
            "substantially improves benchmark ranking performance.\n\n"
            "Common strategies include mining negatives from a first-stage BM25 "
            "retriever, using a previously trained dense retriever to select "
            "high-scoring but incorrect passages, and periodically refreshing the "
            "negative pool during training as the model improves."
        ),
        (
            "Evaluation and Dimensionality\n\n"
            "Embedding models are evaluated on benchmarks such as MTEB (Massive "
            "Text Embedding Benchmark) covering retrieval, reranking, clustering, "
            "and semantic textual similarity tasks.\n\n"
            "The all-MiniLM-L6-v2 sentence-transformers model is a widely used "
            "open-source embedding model that produces 384-dimensional vectors. It "
            "offers an excellent trade-off between speed and quality, which makes "
            "it a popular default choice for RAG prototypes and production systems "
            "with tight latency budgets."
        ),
    ],
    "rag_systems_overview.pdf": [
        (
            "Retrieval Augmented Generation (RAG) — Overview\n\n"
            "Retrieval Augmented Generation is the process of optimizing the output "
            "of a large language model by referencing an authoritative knowledge "
            "base outside of the model's training data before generating a "
            "response. RAG extends the capabilities of LLMs to specific domains or "
            "an organization's internal knowledge base without retraining the "
            "model, making it a cost-effective way to keep answers relevant, "
            "accurate, and useful.\n\n"
            "A RAG system consists of two pipelines: a data injection pipeline "
            "(parse documents, chunk them, embed the chunks, store vectors in a "
            "vector database) and a retrieval pipeline (embed the user query, run "
            "similarity search, pass the retrieved context plus a prompt to the "
            "LLM to generate the final answer)."
        ),
        (
            "Chunking Strategies\n\n"
            "Chunking divides documents into smaller pieces that fit within the "
            "context size of embedding models and LLMs. The recursive character "
            "splitter tries a hierarchy of separators — paragraphs, then lines, "
            "then words — so chunks break at natural boundaries. Chunk overlap "
            "preserves continuity between neighboring chunks so information at the "
            "boundary is not lost.\n\n"
            "RAG reduces hallucination: when the LLM is instructed to answer only "
            "from retrieved context, questions about content missing from the "
            "knowledge base can be answered with 'no relevant context found' "
            "instead of a fabricated response."
        ),
    ],
}


# --------------------------------------------------------------------------- #
# 3. Assignment formats — CSV, JSON, Excel, SQLite
#    (the crash course leaves these formats as an exercise; the content below
#     is retrieval-friendly so demo queries hit each format specifically)
# --------------------------------------------------------------------------- #
AI_MODELS_ROWS = [
    # (model_name, model_type, dimensions, provider, description)
    (
        "all-MiniLM-L6-v2", "embedding", "384",
        "Hugging Face (sentence-transformers)",
        "Small open-source sentence embedding model producing 384-dimensional "
        "vectors. The default choice for fast RAG prototypes and the model "
        "used throughout this pipeline.",
    ),
    (
        "all-mpnet-base-v2", "embedding", "768",
        "Hugging Face (sentence-transformers)",
        "Higher-quality open-source embedding model producing 768-dimensional "
        "vectors. Slower than MiniLM but more accurate.",
    ),
    (
        "text-embedding-3-small", "embedding", "1536",
        "OpenAI",
        "Commercial API embedding model producing 1536-dimensional vectors.",
    ),
    (
        "llama-3.1-8b-instant", "llm", "n/a",
        "Groq",
        "Fast open-weights chat model hosted on Groq. Used for the generation "
        "step of this RAG pipeline.",
    ),
]

RAG_FAQS = {
    "faqs": [
        {
            "category": "chunking",
            "question": "What is chunk overlap and why is it needed?",
            "answer": (
                "Chunk overlap is the number of characters shared between two "
                "consecutive chunks. It preserves continuity so a sentence at a "
                "chunk boundary is not cut off from its context. This pipeline "
                "uses a 1000-character chunk size with a 200-character overlap."
            ),
        },
        {
            "category": "retrieval",
            "question": "How is the similarity score computed?",
            "answer": (
                "The query is embedded with the same model used for the "
                "documents and compared by cosine similarity. In a cosine "
                "space the reported distance equals one minus the cosine "
                "similarity, so similarity = 1 - distance."
            ),
        },
        {
            "category": "hallucination",
            "question": "How does RAG reduce hallucination?",
            "answer": (
                "The prompt instructs the LLM to answer only from the "
                "retrieved context. If the knowledge base has no relevant "
                "content, the pipeline answers 'no relevant context found' "
                "instead of letting the model invent an answer."
            ),
        },
        {
            "category": "metadata",
            "question": "Why does every Document carry metadata?",
            "answer": (
                "Metadata such as the source file and page number makes every "
                "retrieved chunk traceable and lets the vector store filter "
                "results, for example restricting a search to one author or "
                "one file."
            ),
        },
    ]
}

VECTOR_DB_ROWS = [
    # (name, license, persistence, best_for)
    (
        "ChromaDB", "open source (Apache-2.0)",
        "embedded client, persists to local disk",
        "prototyping and small-to-medium RAG applications",
    ),
    (
        "FAISS", "open source (MIT)",
        "in-memory index, saved manually to a file",
        "fast exact or approximate similarity search at scale",
    ),
    (
        "Pinecone", "commercial SaaS",
        "fully managed cloud service",
        "production workloads without managing any infrastructure",
    ),
    (
        "Weaviate", "open source with a managed cloud offering",
        "self-hosted or managed",
        "hybrid keyword plus vector search",
    ),
]

LLM_CATALOG_ROWS = [
    # (name, provider, context_window, open_weights, notes)
    (
        "llama-3.1-8b-instant", "Groq", 131072, "yes",
        "Default generation model for this pipeline; very fast inference on "
        "Groq hardware.",
    ),
    (
        "gpt-4o", "OpenAI", 128000, "no",
        "Commercial multimodal model.",
    ),
    (
        "claude-sonnet", "Anthropic", 200000, "no",
        "Commercial model with a 200000-token context window, the largest "
        "context window in this catalog.",
    ),
    (
        "gemma2-9b-it", "Google", 8192, "yes",
        "Open-weights model used in the original crash course video; since "
        "decommissioned on Groq.",
    ),
]


def create_csv_files() -> None:
    """Write data/csv/ai_models.csv — one knowledge row per AI model."""
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    path = CSV_DIR / "ai_models.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["model_name", "model_type", "dimensions", "provider", "description"]
        )
        writer.writerows(AI_MODELS_ROWS)
    print(f"Created {path} ({len(AI_MODELS_ROWS)} rows)")


def create_json_files() -> None:
    """Write data/json/rag_faq.json — a FAQ list under a top-level 'faqs' key."""
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    path = JSON_DIR / "rag_faq.json"
    path.write_text(json.dumps(RAG_FAQS, indent=2), encoding="utf-8")
    print(f"Created {path} ({len(RAG_FAQS['faqs'])} FAQ entries)")


def create_excel_files() -> None:
    """Write data/excel/vector_databases.xlsx — a comparison sheet, header + rows."""
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    path = EXCEL_DIR / "vector_databases.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "vector_databases"
    sheet.append(["name", "license", "persistence", "best_for"])
    for row in VECTOR_DB_ROWS:
        sheet.append(list(row))
    workbook.save(path)
    print(f"Created {path} ({len(VECTOR_DB_ROWS)} rows)")


def create_sqlite_files() -> None:
    """Write data/sqlite/llm_catalog.db — one table (llm_models) of catalog rows."""
    SQLITE_DIR.mkdir(parents=True, exist_ok=True)
    path = SQLITE_DIR / "llm_catalog.db"
    path.unlink(missing_ok=True)  # rebuild from scratch each run
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE llm_models ("
        "name TEXT, provider TEXT, context_window INTEGER, "
        "open_weights TEXT, notes TEXT)"
    )
    conn.executemany(
        "INSERT INTO llm_models VALUES (?, ?, ?, ?, ?)", LLM_CATALOG_ROWS
    )
    conn.commit()
    conn.close()
    print(f"Created {path} ({len(LLM_CATALOG_ROWS)} rows in table llm_models)")


# --------------------------------------------------------------------------- #
# 4. Word document (.docx) — the tutor's repo adds this format; we match it
# --------------------------------------------------------------------------- #
WORD_DOC = {
    "retrieval_evaluation.docx": [
        ("heading", "Evaluating a RAG System"),
        ("para",
         "A RAG system has two halves that fail for different reasons, and they must "
         "be measured separately. If retrieval never surfaces the right passage, no "
         "language model can recover; if retrieval succeeds but generation ignores "
         "the context, the fault lies in the prompt or the model."),
        ("heading", "Retrieval metrics"),
        ("para",
         "Hit rate measures how often the correct document appears anywhere in the "
         "top k results. Mean Reciprocal Rank rewards placing the correct document "
         "higher: it averages one divided by the rank of the first correct hit. "
         "Recall at k measures what fraction of all relevant documents were found."),
        ("heading", "Generation metrics"),
        ("para",
         "Groundedness asks whether every claim in the answer is supported by the "
         "retrieved context; an ungrounded answer is a hallucination even when it "
         "happens to be true. Relevance asks whether the answer actually addresses "
         "the question that was asked. Both are commonly scored by using a language "
         "model as a judge."),
    ]
}


def create_word_files() -> None:
    """Write data/word/retrieval_evaluation.docx with python-docx."""
    from docx import Document as DocxDocument

    WORD_DIR.mkdir(parents=True, exist_ok=True)
    for filename, blocks in WORD_DOC.items():
        doc = DocxDocument()
        for kind, text in blocks:
            if kind == "heading":
                doc.add_heading(text, level=1)
            else:
                doc.add_paragraph(text)
        doc.save(WORD_DIR / filename)
        print(f"Created {WORD_DIR / filename} ({len(blocks)} blocks)")


def create_text_files() -> None:
    """Write the sample .txt files into data/text_files/."""
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in SAMPLE_TEXTS.items():
        (TEXT_DIR / filename).write_text(content, encoding="utf-8")
        print(f"Created {TEXT_DIR / filename}")


def create_pdf_files() -> None:
    """Render each sample PDF with PyMuPDF, one page per text block."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for filename, pages in SAMPLE_PDFS.items():
        doc = pymupdf.open()  # new empty PDF
        for page_text in pages:
            # The base-14 Helvetica font is Latin-1 only; keep the text ASCII-safe
            # so characters like the em dash don't render as '?'.
            page_text = page_text.replace("—", "-").replace("–", "-")
            page = doc.new_page()  # default A4-ish letter page
            # 1-inch margins; insert_textbox wraps the text automatically.
            rect = pymupdf.Rect(72, 72, page.rect.width - 72, page.rect.height - 72)
            page.insert_textbox(rect, page_text, fontsize=11, fontname="helv")
        doc.save(PDF_DIR / filename)
        doc.close()
        print(f"Created {PDF_DIR / filename} ({len(pages)} pages)")


if __name__ == "__main__":
    create_text_files()
    create_pdf_files()
    create_csv_files()
    create_json_files()
    create_excel_files()
    create_sqlite_files()
    create_word_files()
    print("\nSample knowledge base ready under data/")
