"""Run every chunking strategy on the same text and print the resulting chunks.

Produces the numbers used in "The Chunking Handbook". Run from the RAG folder:
    python scripts/demo_chunking_strategies.py
Results are also written to scripts/out_chunking.json for reference.
"""
import json, re, sys
from pathlib import Path

# Make the project's src/ package importable regardless of where this is run from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_text_splitters import (
    CharacterTextSplitter, RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter, Language,
)

results = {}

# One shared sample text used by strategies 1-4 so comparisons are fair.
SAMPLE = (
    "The Transformer uses self-attention. Attention maps a query and key-value pairs "
    "to an output vector. The output is a weighted sum of the values.\n\n"
    "Embedding models turn text into vectors. Similar texts land close together. "
    "Contrastive training sharpens this geometry."
)
results["sample_text"] = SAMPLE
results["sample_len"] = len(SAMPLE)

def show(chunks):
    """Render chunks as [{len, text}] for the JSON report."""
    return [{"len": len(c), "text": c} for c in chunks]

# --- 1. Fixed-size -------------------------------------------------------
fixed = CharacterTextSplitter(separator="", chunk_size=80, chunk_overlap=0,
                              strip_whitespace=False)
results["fixed"] = show(fixed.split_text(SAMPLE))

# --- 2. Recursive character ---------------------------------------------
rec = RecursiveCharacterTextSplitter(chunk_size=80, chunk_overlap=0,
                                     separators=["\n\n", "\n", " ", ""])
results["recursive"] = show(rec.split_text(SAMPLE))

# --- 3. Token-based -----------------------------------------------------
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
tokbased = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
    tok, chunk_size=20, chunk_overlap=0)
results["token"] = [{"len": len(c), "tokens": len(tok.tokenize(c)), "text": c}
                    for c in tokbased.split_text(SAMPLE)]

# --- 4. Sentence-based --------------------------------------------------
sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", SAMPLE) if s.strip()]
results["sentence"] = show(sentences)

# --- 5. Structure-aware (markdown) --------------------------------------
MD = """# RAG Handbook
## Ingestion
Parse files into Documents, then chunk them.
## Retrieval
Embed the query and search the vector store."""
md_split = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2")]).split_text(MD)
results["structure"] = [{"metadata": d.metadata, "text": d.page_content} for d in md_split]

# --- 5b. Structure-aware (code) -----------------------------------------
CODE = '''class EmbeddingPipeline:
    def chunk_documents(self, documents):
        """Split documents into chunks."""
        return self.splitter.split_documents(documents)

    def embed_chunks(self, chunks):
        """Embed each chunk."""
        return self.model.encode([c.page_content for c in chunks])
'''
code_split = RecursiveCharacterTextSplitter.from_language(
    Language.PYTHON, chunk_size=170, chunk_overlap=0).split_text(CODE)
results["code"] = show(code_split)
results["code_separators"] = RecursiveCharacterTextSplitter.get_separators_for_language(
    Language.PYTHON)

# --- 6. Semantic chunking -----------------------------------------------
import numpy as np
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")

TOPIC_TEXT = ("The transformer architecture relies entirely on attention mechanisms. "
              "Each token attends to every other token through scaled dot-product attention. "
              "Cooking pasta properly starts with generously salted boiling water. "
              "The pasta should finish cooking directly in the sauce. "
              "The French Revolution began in 1789 and transformed European politics. "
              "Revolutionary crowds stormed the Bastille prison in Paris.")
sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", TOPIC_TEXT) if s.strip()]
vecs = model.encode(sents, normalize_embeddings=True, show_progress_bar=False)
sims = [float(vecs[i] @ vecs[i + 1]) for i in range(len(vecs) - 1)]
threshold = float(np.percentile(sims, 40))
chunks, cur = [], [sents[0]]
for i, s in enumerate(sims):
    if s < threshold:
        chunks.append(" ".join(cur)); cur = []
    cur.append(sents[i + 1])
chunks.append(" ".join(cur))
results["semantic"] = {
    "sentences": sents,
    "similarities": [round(s, 3) for s in sims],
    "threshold": round(threshold, 3),
    "chunks": show(chunks),
}

# --- 7. Record-based (from notebook 03) ---------------------------------
from src.data_loader import _load_csv_files, _load_sqlite_files

csv_docs = _load_csv_files(PROJECT_ROOT / "data")
results["record"] = [{"text": d.page_content, "metadata": {
    k: v for k, v in d.metadata.items() if k in ("source_file", "row", "file_type")}}
    for d in csv_docs[:2]]

# --- 8. Parent-document / small-to-big ----------------------------------
parent = ("Attention maps a query and key-value pairs to an output. "
          "The output is a weighted sum of the values. "
          "Multi-head attention runs several attention functions in parallel. "
          "Positional encodings inject word order into the model.")
# Children = clean sentences (the small units we SEARCH over)
children = [s.strip() for s in re.split(r"(?<=[.])\s+", parent) if s.strip()]
q = "What injects word order?"
cv = model.encode(children, normalize_embeddings=True, show_progress_bar=False)
qv = model.encode([q], normalize_embeddings=True, show_progress_bar=False)[0]
scores = cv @ qv
best = int(np.argmax(scores))
results["parent_doc"] = {
    "query": q,
    "children": [{"text": c, "score": round(float(scores[i]), 3)}
                 for i, c in enumerate(children)],
    "matched_child": children[best],
    "returned_parent": parent,
}

out_path = Path(__file__).resolve().parent / "out_chunking.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nWrote {out_path}")
for k, v in results.items():
    if isinstance(v, list):
        print(f"{k}: {len(v)} items")
