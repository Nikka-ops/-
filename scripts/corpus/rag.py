"""本地语料 RAG — embedding + cosine 检索。

存储：每个 bank slug 对应一个 .npy 向量文件 + .json index 文件，缓存在 banks_dir。
检索：query 文本 → embed → cosine similarity → Top-K 题目 + source_refs。
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
#  Embedding helper                                                            #
# --------------------------------------------------------------------------- #
def _embed_batch(texts: list[str]) -> list[list[float]] | None:
    from scripts.ai.gateway import embed as gw_embed
    results: list[list[float]] = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vecs = gw_embed(batch)
        if vecs is None:
            return None
        results.extend(vecs)
    return results


# --------------------------------------------------------------------------- #
#  Cosine similarity (pure Python, no numpy dependency at import time)        #
# --------------------------------------------------------------------------- #
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# --------------------------------------------------------------------------- #
#  Index build / load                                                          #
# --------------------------------------------------------------------------- #
def _index_paths(banks_dir: Path, slug: str) -> tuple[Path, Path]:
    d = banks_dir / slug
    return d / "rag_index.json", d / "rag_vectors.json"


def build_index(
    banks_dir: Path,
    slug: str,
    questions: list[dict],
    *,
    max_questions: int = 2000,
) -> bool:
    """为题库生成 embedding 索引。返回是否成功。"""
    idx_path, vec_path = _index_paths(banks_dir, slug)
    qs = questions[:max_questions]

    texts = [q.get("text") or "" for q in qs]
    vecs = _embed_batch(texts)
    if vecs is None:
        return False

    index = [
        {
            "cluster_id": q.get("cluster_id") or q.get("id") or str(i),
            "text": q.get("text") or "",
            "topic": q.get("topic") or "",
            "batch_count": q.get("batch_count") or 0,
            "source_refs": q.get("source_refs") or [],
        }
        for i, q in enumerate(qs)
    ]
    idx_path.write_text(json.dumps(index, ensure_ascii=False), "utf-8")
    vec_path.write_text(json.dumps(vecs, ensure_ascii=False), "utf-8")
    return True


def load_index(
    banks_dir: Path,
    slug: str,
) -> tuple[list[dict], list[list[float]]] | None:
    idx_path, vec_path = _index_paths(banks_dir, slug)
    if not idx_path.exists() or not vec_path.exists():
        return None
    try:
        index = json.loads(idx_path.read_text("utf-8"))
        vecs = json.loads(vec_path.read_text("utf-8"))
        return index, vecs
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
#  Search                                                                      #
# --------------------------------------------------------------------------- #
def search(
    banks_dir: Path,
    slug: str,
    query: str,
    *,
    top_k: int = 10,
    topic_filter: str | None = None,
) -> list[dict]:
    """语义搜索题目，返回 [{cluster_id, text, topic, score, source_refs}]"""
    data = load_index(banks_dir, slug)
    if data is None:
        return []
    index, vecs = data

    q_vecs = _embed_batch([query])
    if not q_vecs:
        return []
    q_vec = q_vecs[0]

    scores: list[tuple[float, dict]] = []
    for item, vec in zip(index, vecs):
        if topic_filter and item.get("topic") != topic_filter:
            continue
        sim = _cosine(q_vec, vec)
        scores.append((sim, item))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [
        {**item, "score": round(sim, 4)}
        for sim, item in scores[:top_k]
    ]


def has_index(banks_dir: Path, slug: str) -> bool:
    idx, vec = _index_paths(banks_dir, slug)
    return idx.exists() and vec.exists()
