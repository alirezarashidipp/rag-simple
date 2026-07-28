# -*- coding: utf-8 -*-
"""
پروژه ساده RAG برای یادگیری
============================
جریان کلی:
  PDF Upload → Extract Text → Split into Chunks → OpenAI Embedding
  → Pinecone → Question Embedding → Top 3 Chunks → LLM → Answer + Sources

فقط ۳ مسیر (route) داریم:
  POST /upload  آپلود PDF، تکه‌تکه کردن، امبدینگ و ذخیره در Pinecone
  POST /ask     سؤال کاربر → جستجو → پاسخ LLM همراه با منابع
  GET  /stats   آمار ایندکس (تعداد وکتورها، بُعد، نام مدل‌ها)
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
# ۱) خواندن تنظیمات از فایل .env.local
# ---------------------------------------------------------------
load_dotenv(".env.local")

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME      = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL")
CHAT_MODEL      = os.getenv("OPENAI_CHAT_MODEL")

TOP_K = 3  # طبق نمودار: ۳ تکه نزدیک به سؤال

client = OpenAI(api_key=OPENAI_API_KEY)   # کلاینت OpenAI
pc = Pinecone(api_key=PINECONE_API_KEY)   # کلاینت Pinecone

app = Flask(__name__)


# ---------------------------------------------------------------
# ۲) امبدینگ: تبدیل متن به وکتور
# ---------------------------------------------------------------
def embed_texts(texts):
    """لیستی از متن‌ها را به لیستی از وکتورها تبدیل می‌کند.
    برای متن‌های زیاد، دسته‌های ۱۰۰تایی می‌فرستیم."""
    vectors = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i + 100]
        res = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        vectors.extend([d.embedding for d in res.data])
    return vectors


# ---------------------------------------------------------------
# ۳) ایندکس Pinecone (اگر وجود نداشت، می‌سازیم)
# ---------------------------------------------------------------
def get_index():
    if not pc.has_index(INDEX_NAME):
        # بُعد وکتور را با امبد کردن یک متن آزمایشی پیدا می‌کنیم
        dim = len(embed_texts(["hello"])[0])
        pc.create_index(
            name=INDEX_NAME,
            dimension=dim,
            metric="cosine",  # شباهت کسینوسی: معیار رایج برای امبدینگ‌ها
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        # صبر می‌کنیم تا ایندکس آماده شود
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


index = get_index()


# ---------------------------------------------------------------
# ۴) استراتژی‌های تکه‌تکه کردن (Chunking)
# ---------------------------------------------------------------
def chunk_fixed(text, size, overlap):
    """روش ۱: تکه‌های با طول ثابت + همپوشانی.
    همپوشانی باعث می‌شود جمله‌ای که وسط دو تکه افتاده، از دست نرود."""
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
    """روش ۲: جمله‌ها را جدا می‌کنیم و تا سقف max_chars کنار هم می‌گذاریم.
    مزیت: هیچ جمله‌ای از وسط نصف نمی‌شود."""
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
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
    """روش ۳: بر اساس پاراگراف (خط خالی). پاراگراف‌های کوتاه را
    تا سقف max_chars به هم می‌چسبانیم تا تکه‌ها خیلی ریز نشوند."""
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
    """بر اساس انتخاب کاربر، یکی از سه روش بالا را اجرا می‌کند."""
    if strategy == "sentence":
        chunks = chunk_sentence(text, size)
    elif strategy == "paragraph":
        chunks = chunk_paragraph(text, size)
    else:
        chunks = chunk_fixed(text, size, overlap)

    # ایمنی: اگر تکه‌ای خیلی بزرگ شد (مثلاً PDF بدون خط خالی)، خردش می‌کنیم
    safe = []
    for c in chunks:
        if len(c) > size * 2:
            safe.extend(chunk_fixed(c, size, overlap))
        else:
            safe.append(c)
    return safe


# ---------------------------------------------------------------
# ۵) مسیرهای وب
# ---------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """PDF → متن → تکه‌ها → وکتور → Pinecone"""
    t0 = time.time()

    file = request.files["file"]
    strategy = request.form.get("strategy", "fixed")
    size = int(request.form.get("chunk_size", 800))
    overlap = int(request.form.get("overlap", 150))

    # --- استخراج متن از PDF ---
    reader = PdfReader(file)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        return jsonify({"error": "No text found in this PDF (maybe it is a scanned image)."}), 400

    # --- تکه‌تکه کردن ---
    chunks = split_text(text, strategy, size, overlap)

    # --- امبدینگ ---
    t1 = time.time()
    vectors = embed_texts(chunks)
    embed_ms = int((time.time() - t1) * 1000)

    # --- ذخیره در Pinecone ---
    # شناسه‌ی هر تکه از نام فایل + روش + شماره ساخته می‌شود؛
    # پس آپلود دوباره‌ی همان فایل، وکتورها را جایگزین می‌کند (نه تکراری).
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
    for i in range(0, len(items), 100):  # آپسرت دسته‌ای
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
    """سؤال → وکتور → ۳ تکه نزدیک → LLM → پاسخ + منابع"""
    t0 = time.time()
    question = request.json["question"]

    # --- ۱) سؤال را به وکتور تبدیل می‌کنیم ---
    t1 = time.time()
    q_vector = embed_texts([question])[0]
    embed_ms = int((time.time() - t1) * 1000)

    # --- ۲) نزدیک‌ترین تکه‌ها را از Pinecone می‌گیریم ---
    t2 = time.time()
    result = index.query(vector=q_vector, top_k=TOP_K, include_metadata=True)
    search_ms = int((time.time() - t2) * 1000)

    matches = result["matches"]
    if not matches:
        return jsonify({"error": "The index is empty. Upload a PDF first."}), 400

    # --- ۳) تکه‌ها را به عنوان «منبع» در پرامپت می‌گذاریم ---
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

    # --- ۴) پاسخ نهایی از LLM ---
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

    # --- ۵) پاسخ + منابع + شاخص‌ها را برمی‌گردانیم ---
    sources = [{
        "filename": m["metadata"]["filename"],
        "text": m["metadata"]["text"],
        "score": round(m["score"], 4),  # شباهت کسینوسی (۰ تا ۱)
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
    """آمار ایندکس برای داشبورد"""
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
    """آزمایشگاه آموزشی: دو متن را واقعاً امبد می‌کنیم و روی وکتورهایشان
    طول (نرم L2) و هر سه متریک شباهت را حساب می‌کنیم."""
    data = request.json
    va, vb = embed_texts([data["text_a"], data["text_b"]])

    # ضرب داخلی: جمعِ حاصل‌ضرب مؤلفه‌های متناظر
    dot = sum(x * y for x, y in zip(va, vb))
    # طول (نرم L2) هر وکتور: ریشه‌ی جمع مربع مؤلفه‌ها
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(x * x for x in vb))
    # کسینوس: ضرب داخلی تقسیم بر حاصل‌ضرب طول‌ها → فقط زاویه می‌ماند
    cosine = dot / (norm_a * norm_b)
    # اقلیدسی: فاصله‌ی خط مستقیم بین دو نقطه در فضای n بعدی
    euclidean = math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb)))

    return jsonify({
        "dimension": len(va),
        "norm_a": round(norm_a, 6),
        "norm_b": round(norm_b, 6),
        # اگر طول هر دو ≈ ۱ باشد یعنی مدل از قبل نرمال کرده است
        "is_normalized": abs(norm_a - 1) < 0.01 and abs(norm_b - 1) < 0.01,
        "sample_a": [round(x, 4) for x in va[:6]],  # چند مؤلفه اول، فقط برای نمایش
        "cosine": round(cosine, 4),
        "dot": round(dot, 4),
        "euclidean": round(euclidean, 4),
    })


@app.route("/reset", methods=["POST"])
def reset():
    """پاک کردن همه وکتورها — برای شروع دوباره و مقایسه استراتژی‌ها"""
    index.delete(delete_all=True)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
