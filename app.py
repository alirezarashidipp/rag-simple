# -*- coding: utf-8 -*-
"""
Simple RAG — a learning project
===============================
Pipeline:
  PDF Upload -> Extract Text -> Split into Chunks -> OpenAI Embedding
  -> Pinecone -> Question Embedding -> Top 3 Chunks -> LLM -> Answer + Sources

Routes:
  POST /upload  upload a PDF, split it, embed the chunks, store them in Pinecone
  POST /ask     user question -> similarity search -> LLM answer with sources
  GET  /stats   index stats (vector count, dimension, model names)
  POST /lab     educational: embed two texts, compare norms and metrics
  POST /reset   delete every vector in the index
"""

import os
import re
import math
import time
import hashlib

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from pypdf import PdfReader
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

# ---------------------------------------------------------------
# 1) Load configuration from .env.local
# ---------------------------------------------------------------
load_dotenv(".env.local")

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME      = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL")
CHAT_MODEL      = os.getenv("OPENAI_CHAT_MODEL")

TOP_K = 3  # how many chunks to send to the LLM

client = OpenAI(api_key=OPENAI_API_KEY)   # OpenAI client
pc = Pinecone(api_key=PINECONE_API_KEY)   # Pinecone client

app = Flask(__name__)


# ---------------------------------------------------------------
# 2) Embedding: turn text into vectors
# ---------------------------------------------------------------
def embed_texts(texts):
    """Convert a list of texts into a list of vectors.
    Large inputs are sent in batches of 100."""
    vectors = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i + 100]
        res = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        vectors.extend([d.embedding for d in res.data])
    return vectors


# ---------------------------------------------------------------
# 3) Pinecone index (created on first run if missing)
# ---------------------------------------------------------------
def get_index():
    if not pc.has_index(INDEX_NAME):
        # Discover the vector dimension by embedding a probe text
        dim = len(embed_texts(["hello"])[0])
        pc.create_index(
            name=INDEX_NAME,
            dimension=dim,
            metric="cosine",  # cosine similarity: the standard choice for embeddings
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        # Wait until the index is ready to accept vectors
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


index = get_index()


# ---------------------------------------------------------------
# 4) Chunking strategies
# ---------------------------------------------------------------
def chunk_fixed(text, size, overlap):
    """Strategy 1: fixed-length chunks with overlap.
    The overlap keeps a sentence that falls on a chunk border from being lost."""
    chunks = []
    step = max(1, size - overlap)
    for start in range(0, len(text), step):
        piece = text[start:start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(text):
            break
    return chunks


def chunk_sentence(text, max_chars):
    """Strategy 2: split into sentences, then pack them up to max_chars.
    Benefit: no sentence is ever cut in half."""
    sentences = re.split(r'(?<=[.!?؟])\s+', text)  # ؟ = Arabic/Persian question mark
    chunks, current = [], ""
    for s in sentences:
        if not current or len(current) + len(s) + 1 <= max_chars:
            current = (current + " " + s).strip()
        else:
            chunks.append(current)
            current = s.strip()
    if current:
        chunks.append(current)
    return chunks


def chunk_paragraph(text, max_chars):
    """Strategy 3: split on blank lines. Short paragraphs are merged
    up to max_chars so the chunks do not end up too small."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if not current or len(current) + len(p) + 2 <= max_chars:
            current = (current + "\n\n" + p).strip()
        else:
            chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    return chunks


def split_text(text, strategy, size, overlap):
    """Run whichever strategy the user picked in the UI."""
    if strategy == "sentence":
        chunks = chunk_sentence(text, size)
    elif strategy == "paragraph":
        chunks = chunk_paragraph(text, size)
    else:
        chunks = chunk_fixed(text, size, overlap)

    # Safety net: break up oversized chunks (e.g. a PDF with no blank lines)
    safe = []
    for c in chunks:
        if len(c) > size * 2:
            safe.extend(chunk_fixed(c, size, overlap))
        else:
            safe.append(c)
    return safe


# ---------------------------------------------------------------
# 5) Web routes
# ---------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """PDF -> text -> chunks -> vectors -> Pinecone"""
    t0 = time.time()

    file = request.files["file"]
    strategy = request.form.get("strategy", "fixed")
    size = int(request.form.get("chunk_size", 800))
    overlap = int(request.form.get("overlap", 150))

    # --- Extract text from the PDF ---
    reader = PdfReader(file)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        return jsonify({"error": "No text found in this PDF (maybe it is a scanned image)."}), 400

    # --- Split into chunks ---
    chunks = split_text(text, strategy, size, overlap)

    # --- Embed ---
    t1 = time.time()
    vectors = embed_texts(chunks)
    embed_ms = int((time.time() - t1) * 1000)

    # --- Store in Pinecone ---
    # Each vector ID is derived from filename + strategy + chunk number, so
    # re-uploading the same file replaces its vectors instead of duplicating them.
    t2 = time.time()
    items = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        uid = hashlib.md5(f"{file.filename}-{strategy}-{i}".encode()).hexdigest()
        items.append({
            "id": uid,
            "values": vec,
            "metadata": {"filename": file.filename, "text": chunk,
                         "chunk_index": i, "strategy": strategy},
        })
    for i in range(0, len(items), 100):  # batched upsert
        index.upsert(vectors=items[i:i + 100])
    upsert_ms = int((time.time() - t2) * 1000)

    sizes = [len(c) for c in chunks]
    return jsonify({
        "filename": file.filename,
        "pages": len(reader.pages),
        "total_chars": len(text),
        "num_chunks": len(chunks),
        "avg_chunk_chars": sum(sizes) // len(sizes),
        "min_chunk_chars": min(sizes),
        "max_chunk_chars": max(sizes),
        "embed_ms": embed_ms,
        "upsert_ms": upsert_ms,
        "total_ms": int((time.time() - t0) * 1000),
    })


@app.route("/ask", methods=["POST"])
def ask():
    """question -> vector -> top 3 chunks -> LLM -> answer + sources"""
    t0 = time.time()
    question = request.json["question"]

    # --- 1) Turn the question into a vector ---
    t1 = time.time()
    q_vector = embed_texts([question])[0]
    embed_ms = int((time.time() - t1) * 1000)

    # --- 2) Fetch the nearest chunks from Pinecone ---
    t2 = time.time()
    result = index.query(vector=q_vector, top_k=TOP_K, include_metadata=True)
    search_ms = int((time.time() - t2) * 1000)

    matches = result["matches"]
    if not matches:
        return jsonify({"error": "The index is empty. Upload a PDF first."}), 400

    # --- 3) Put those chunks into the prompt as "sources" ---
    context = ""
    for n, m in enumerate(matches, 1):
        context += f"[Source {n} | file: {m['metadata']['filename']}]\n{m['metadata']['text']}\n\n"

    system_prompt = (
        "You are a helpful assistant in a RAG system. "
        "Answer the question using ONLY the sources below. "
        "If the answer is not in the sources, say you don't know. "
        "Reply in the same language as the question.\n\n"
        "SOURCES:\n" + context
    )

    # --- 4) Final answer from the LLM ---
    t3 = time.time()
    chat = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
    llm_ms = int((time.time() - t3) * 1000)
    answer = chat.choices[0].message.content

    # --- 5) Return the answer, the sources and the timing metrics ---
    sources = [{
        "filename": m["metadata"]["filename"],
        "text": m["metadata"]["text"],
        "score": round(m["score"], 4),  # cosine similarity (0 to 1)
        "chunk_index": int(m["metadata"]["chunk_index"]),
    } for m in matches]

    return jsonify({
        "answer": answer,
        "sources": sources,
        "metrics": {
            "embed_ms": embed_ms,
            "search_ms": search_ms,
            "llm_ms": llm_ms,
            "total_ms": int((time.time() - t0) * 1000),
            "top_score": sources[0]["score"],
        },
    })


@app.route("/stats")
def stats():
    """Index stats for the dashboard"""
    s = index.describe_index_stats()
    return jsonify({
        "total_vectors": s["total_vector_count"],
        "dimension": s["dimension"],
        "index_name": INDEX_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "chat_model": CHAT_MODEL,
    })


@app.route("/lab", methods=["POST"])
def lab():
    """Educational lab: really embed two texts, then compute their
    lengths (L2 norm) and all three similarity metrics."""
    data = request.json
    va, vb = embed_texts([data["text_a"], data["text_b"]])

    # Dot product: sum of the products of matching components
    dot = sum(x * y for x, y in zip(va, vb))
    # Length (L2 norm) of each vector: square root of the sum of squares
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(x * x for x in vb))
    # Cosine: dot product divided by the product of the lengths -> only the angle is left
    cosine = dot / (norm_a * norm_b)
    # Euclidean: straight-line distance between two points in n-dimensional space
    euclidean = math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb)))

    return jsonify({
        "dimension": len(va),
        "norm_a": round(norm_a, 6),
        "norm_b": round(norm_b, 6),
        # Both lengths close to 1 means the model already normalizes its output
        "is_normalized": abs(norm_a - 1) < 0.01 and abs(norm_b - 1) < 0.01,
        "sample_a": [round(x, 4) for x in va[:6]],  # first few components, for display only
        "cosine": round(cosine, 4),
        "dot": round(dot, 4),
        "euclidean": round(euclidean, 4),
    })


@app.route("/reset", methods=["POST"])
def reset():
    """Delete every vector — useful for starting over and comparing strategies"""
    index.delete(delete_all=True)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
