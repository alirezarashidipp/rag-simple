# Simple RAG 📚

A complete but deliberately simple RAG system for learning: upload a PDF, ask a question, get an answer with its sources — plus an interactive course on how RAG actually works.

## Pipeline

```
PDF Upload → Extract Text → Split into Chunks → OpenAI Embedding → Pinecone
User Question → Question Embedding → Top 3 Similar Chunks → OpenAI LLM → Answer + Sources
```

## Project structure

| File | Role |
|---|---|
| `app.py` | All the RAG logic (Flask backend) |
| `templates/index.html` | The UI — also 9 interactive learning sections |
| `.env.local` | Keys and model names (not in git — see `.env.example`) |

## Setup

Create `.env.local` from `.env.example` and fill in your keys:

```
OPENAI_API_KEY=...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4.1-mini
```

Then run:

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. The Pinecone index is created automatically on first run if it does not exist.

## Code map — where each RAG concept lives

| Concept | Where in `app.py` |
|---|---|
| Extract text | `upload()` — via `pypdf` |
| Chunking (3 strategies) | `chunk_fixed` / `chunk_sentence` / `chunk_paragraph` |
| Embedding | `embed_texts()` |
| Storing vectors | `index.upsert(...)` inside `upload()` |
| Similarity search | `index.query(top_k=3)` inside `ask()` |
| Prompt + LLM | `system_prompt` and `client.chat.completions.create` inside `ask()` |

## The three chunking strategies

- **Fixed size** — a chunk every N characters plus an overlap, so sentences on a border are not lost.
- **Sentence** — sentences stay whole and are packed up to the size limit.
- **Paragraph** — split on blank lines; short paragraphs are merged together.

## Learning sections in the UI

**3 · Vector Lab** — *Embed & Compare* really embeds two texts and shows their L2 norms plus all three metrics; you can see the norms are ≈ 1, meaning OpenAI pre-normalizes, so cosine ≈ dot. The *2D playground* lets you drag two vectors and watch the angle (cosine), the projection (dot) and the tip-to-tip distance (euclidean) change live. The *worked example* stores 4 toy 5-dimensional chunks plus a query: switch metrics and watch the ranking and the arithmetic update. Key lessons — with raw dot product two chunks tie (dot rewards vector length!), after normalization dot ≡ cosine, and on unit vectors euclidean always reproduces the cosine ranking. Output is shown exactly like FAISS: `top_k=2 → [A, C]`.

**4 · ANN Index Zoo** — the four families of fast approximate search, each with a diagram: **IVF** (cluster first, search only the nearest cells), **HNSW** (multi-layer graph — long hops on top, fine steps below; what Pinecone uses under the hood), **DiskANN** (graph on SSD with compressed codes in RAM, billion scale), **Tree-based** (recursive space partitioning — KD-Tree, Annoy).

**5 · Chunking Zoo** — four splitting families with pros, cons and a How line: **Fixed-size**, **Recursive/structure-aware** (the industry default), **Semantic** (embed sentences, cut where similarity drops), **Document-specific** (use the format's own structure). Rule of thumb: start recursive; if retrieval disappoints try semantic; when you control the format go document-specific.

**6 · Embedding dimensions** — 384 / 768 / 1536 / 3072 compared with their real memory cost. More dimensions means a richer semantic space but linearly more memory, storage and search time; fewer is lighter and *not automatically worse* — quality comes from training, not size (check the MTEB leaderboard). OpenAI v3 models are Matryoshka-trained, so the `dimensions` parameter gives you a shorter vector that keeps most of the quality.

**7 · Hybrid search: Fusion & Reranking** — production RAG runs two retrievers in parallel (vector for meaning, BM25 for exact keywords). **Weighted Score Fusion**: `α·vec + (1−α)·bm25` — tunable but normalization is mandatory and fragile. **RRF**: throw the scores away and use ranks only, `Σ 1/(k+rank)` with k≈60 — no normalization, the safe industry default. **Fusion vs Reranking**: fusion merges several lists with cheap arithmetic (microseconds); a reranker is a neural cross-encoder that reads the question and the chunk together and fixes the final order (slower, costs money, runs after fusion and before the LLM). In most stacks the reranker is the single biggest quality jump.

**8 · RAG quality metrics** — eight metrics, each with *how to measure / what is good and bad / how to improve*, a diagram and a threshold gauge: **Recall@k** (was the needed chunk retrieved at all — the ceiling of the whole system), **Context Precision**, **MRR**, **Faithfulness** (hallucination check), **Answer Relevance**, **Latency p50/p95**, **Cost per query**, **Top score** (live warning light). Golden rule: change one thing, re-run the same eval set, compare the numbers. Tools that automate this: RAGAS, TruLens, LangSmith.

**9 · Troubleshooting** — 15 common failures, each with how to spot it and how to fix it: slowness, hallucination, irrelevant retrieval, low recall, chunks cut mid-sentence, oversized or junk chunks, broken PDF extraction, vocabulary mismatch, exact codes not found, multi-hop questions, lost in the middle, stale index, duplicates, and no refusal when the answer is not there. Debug top-down: is the right chunk in the index? → is it retrieved? → does the LLM use it?

## Suggested exercise 🎓

1. Index a PDF with **Fixed**, ask a question, note the `top score`.
2. Clear the index, re-index the same PDF with **Sentence**, ask the same question.
3. Compare the scores and the answer quality — this is exactly what RAG engineers do.

Note: the score is the cosine similarity between the question vector and the chunk vector (0 to 1).
