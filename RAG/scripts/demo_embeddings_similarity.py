"""Inspect the sentence-transformer pipeline and cosine similarity end to end.

Produces the numbers used in "Vectors & Angles": tokenization, mean pooling
verified by hand, cosine similarity on real sentence pairs, the metric
equivalences, the truncation trap, and a bi-encoder vs cross-encoder comparison.
Run from the RAG folder:
    python scripts/demo_embeddings_similarity.py
Results are also written to scripts/out_embeddings.json for reference.
"""
import json
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
out = {}

# ---------- 1. Tokenization ----------
tok = AutoTokenizer.from_pretrained(MODEL)
sentence = "Vector databases enable semantic search."
enc = tok(sentence)
out["tokens"] = {
    "sentence": sentence,
    "pieces": tok.convert_ids_to_tokens(enc["input_ids"]),
    "ids": enc["input_ids"],
    "vocab_size": tok.vocab_size,
}
out["subword"] = {
    "word": "hallucination",
    "pieces": tok.tokenize("hallucination"),
    "word2": "databases",
    "pieces2": tok.tokenize("databases"),
}

# ---------- 2. Token vectors -> pooling ----------
encoder = AutoModel.from_pretrained(MODEL)
t = tok(sentence, return_tensors="pt")
with torch.no_grad():
    hidden = encoder(**t).last_hidden_state          # (1, n_tokens, 384)
mask = t["attention_mask"].unsqueeze(-1).float()
mean_pooled = (hidden * mask).sum(1) / mask.sum(1)
manual = torch.nn.functional.normalize(mean_pooled, dim=1)[0].numpy()

st = SentenceTransformer("all-MiniLM-L6-v2")
library = st.encode([sentence], normalize_embeddings=True)[0]

out["pooling"] = {
    "n_tokens": int(hidden.shape[1]),
    "dim": int(hidden.shape[2]),
    "token_vector_shape": list(hidden.shape),
    "pooled_shape": list(mean_pooled.shape),
    "max_abs_diff": float(np.abs(manual - library).max()),
    "first8_manual": [round(float(x), 5) for x in manual[:8]],
    "first8_library": [round(float(x), 5) for x in library[:8]],
}

# a couple of individual token vectors (first 5 dims) to show they differ per token
out["token_vectors_sample"] = {
    "pieces": tok.convert_ids_to_tokens(t["input_ids"][0])[:6],
    "first5dims": [[round(float(x), 3) for x in hidden[0, i, :5]] for i in range(6)],
}

# ---------- 3. Contextual proof: same word, two meanings ----------
s_river = "He sat on the river bank and watched the water."
s_money = "She deposited her paycheck at the bank downtown."

def word_vector(sent, target):
    """Return the normalized contextual vector of one token inside a sentence."""
    tt = tok(sent, return_tensors="pt")
    with torch.no_grad():
        h = encoder(**tt).last_hidden_state[0]
    pieces = tok.convert_ids_to_tokens(tt["input_ids"][0])
    idx = pieces.index(target)
    v = h[idx].numpy()
    return v / np.linalg.norm(v)
v1, v2 = word_vector(s_river, "bank"), word_vector(s_money, "bank")
out["contextual"] = {
    "s1": s_river, "s2": s_money,
    "cosine_between_the_two_bank_vectors": round(float(v1 @ v2), 3),
}

# ---------- 4. Hand-computable 2D cosine ----------
def cos(a, b):
    """Cosine similarity between two vectors (direction only, scale-free)."""
    a, b = np.array(a, float), np.array(b, float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
def l2(a, b):
    """Euclidean (straight-line) distance between two vectors."""
    return float(np.linalg.norm(np.array(a, float) - np.array(b, float)))
pairs = [([3, 4], [4, 3]), ([3, 4], [-4, 3]), ([3, 4], [6, 8]), ([3, 4], [-3, -4])]
out["toy2d"] = [{"a": a, "b": b, "dot": float(np.dot(a, b)),
                 "norm_a": float(np.linalg.norm(a)), "norm_b": float(np.linalg.norm(b)),
                 "cosine": round(cos(a, b), 3), "euclidean": round(l2(a, b), 3)}
                for a, b in pairs]

# ---------- 5. Real sentence similarities ----------
sent_pairs = [
    ("How do I reset my password?", "Steps to recover your account credentials", "paraphrase"),
    ("The cat sat on the mat.", "A feline was resting on the rug.", "paraphrase, no shared words"),
    ("How do I reset my password?", "The transformer uses self-attention.", "unrelated"),
    ("I love this product.", "I hate this product.", "opposite meaning, similar words"),
    ("Paris is the capital of France.", "France's capital city is Paris.", "reordered, same fact"),
]
out["real_pairs"] = []
for a, b, label in sent_pairs:
    va, vb = st.encode([a, b], normalize_embeddings=True)
    out["real_pairs"].append({"a": a, "b": b, "label": label,
                              "cosine": round(float(va @ vb), 3)})

# ---------- 6. Similarity matrix ----------
matrix_sents = [
    "How do I reset my password?",
    "I forgot my login details.",
    "What is the attention mechanism?",
    "How does self-attention work?",
    "Pasta should be cooked in salted water.",
]
mv = st.encode(matrix_sents, normalize_embeddings=True)
out["matrix"] = {"sentences": matrix_sents,
                 "values": [[round(float(x), 3) for x in row] for row in (mv @ mv.T)]}

# ---------- 7. Normalization + metric equivalence ----------
raw = st.encode(matrix_sents, normalize_embeddings=False)
nrm = st.encode(matrix_sents, normalize_embeddings=True)
out["norms"] = {
    "raw_norms": [round(float(x), 4) for x in np.linalg.norm(raw, axis=1)],
    "normalized_norms": [round(float(x), 4) for x in np.linalg.norm(nrm, axis=1)],
}
a, b = nrm[0], nrm[1]
out["equivalence"] = {
    "cosine": round(float(a @ b), 4),
    "dot": round(float(a @ b), 4),
    "l2_squared": round(float(np.sum((a - b) ** 2)), 4),
    "two_minus_2cos": round(float(2 - 2 * (a @ b)), 4),
}
# ranking agreement between cosine and L2 on normalized vectors
q = st.encode(["how do I recover my account?"], normalize_embeddings=True)[0]
cos_rank = np.argsort(-(nrm @ q))
l2_rank = np.argsort(np.linalg.norm(nrm - q, axis=1))
out["ranking_agreement"] = {
    "by_cosine": [matrix_sents[i] for i in cos_rank],
    "by_l2": [matrix_sents[i] for i in l2_rank],
    "identical": bool(list(cos_rank) == list(l2_rank)),
}

# ---------- 8. What counts as "high"? baseline of unrelated text ----------
rng = np.random.default_rng(0)
unrelated = [
    "The stock market closed higher on Tuesday.",
    "Penguins huddle together for warmth.",
    "She replaced the timing belt on her car.",
    "The recipe calls for three eggs.",
    "Quantum tunneling occurs at small scales.",
    "He practices the cello every morning.",
    "Rainfall in the region has decreased.",
    "The library closes at eight.",
]
uv = st.encode(unrelated, normalize_embeddings=True)
sims = [float(uv[i] @ uv[j]) for i in range(len(uv)) for j in range(i + 1, len(uv))]
out["baseline"] = {
    "n_pairs": len(sims),
    "mean": round(float(np.mean(sims)), 3),
    "max": round(float(np.max(sims)), 3),
    "min": round(float(np.min(sims)), 3),
}

# ---------- 9. Truncation gotcha ----------
long_text = "word " * 400
n_tok = len(tok.tokenize(long_text))
out["truncation"] = {
    "max_seq_length": int(st.max_seq_length),
    "tokens_in_input": n_tok,
    "note": "input longer than max_seq_length is silently truncated",
}
# prove it: two texts identical for the first 256 tokens, differing after
head = "The capital of France is Paris. " * 40
tail_a = head + " The secret code is ALPHA."
tail_b = head + " The secret code is OMEGA."
va, vb = st.encode([tail_a, tail_b], normalize_embeddings=True)
out["truncation"]["cosine_of_texts_differing_only_after_limit"] = round(float(va @ vb), 6)
out["truncation"]["head_token_count"] = len(tok.tokenize(head))

# ---------- 10. Cross-encoder comparison (optional) ----------
try:
    from sentence_transformers import CrossEncoder
    ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    query = "How do I reset my password?"
    cands = [
        "Steps to recover your account credentials",
        "Password reset instructions are in the help centre.",
        "The transformer uses self-attention.",
        "I love this product.",
    ]
    bi = st.encode([query] + cands, normalize_embeddings=True)
    bi_scores = [round(float(bi[0] @ bi[i + 1]), 3) for i in range(len(cands))]
    ce_scores = [round(float(s), 3) for s in ce.predict([(query, c) for c in cands])]
    out["cross_encoder"] = {"query": query, "candidates": cands,
                            "bi_encoder_cosine": bi_scores, "cross_encoder_logit": ce_scores}
except Exception as e:
    out["cross_encoder"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}

out_path = Path(__file__).resolve().parent / "out_embeddings.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nWrote {out_path}")
