"""S3 动态分类：文本嵌入 + 聚类 + LLM 主题命名/归并。

默认（无第三方库）用 TF-IDF + 纯 Python KMeans 作为确定性兜底；
安装了 sentence-transformers / scikit-learn 时自动使用模型嵌入与更强聚类。
主题命名始终由 LLM 完成（模型驱动核心之一），LLM 不可用时用「主题 N」占位。
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from typing import Optional

_WORD_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "for", "to", "of", "in", "on", "with",
    "it", "is", "are", "was", "were", "be", "been", "i", "you", "we", "they",
    "my", "your", "our", "this", "that", "app", "apps", "very", "really", "just",
}


def tokenize(text: str) -> list[str]:
    tokens = _WORD_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _ngrams(tokens: list[str]) -> list[str]:
    return tokens + [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]


def tfidf_embed(texts: list[str]) -> list[list[float]]:
    """轻量 TF-IDF（词 + 二元组）L2 归一化向量，纯标准库。"""
    docs = [_ngrams(tokenize(t)) for t in texts]
    df: Counter = Counter()
    for doc in docs:
        df.update(set(doc))
    vocab = [term for term, count in df.items() if count >= 1]
    index = {term: i for i, term in enumerate(vocab)}
    n_docs = len(docs) or 1
    vectors = []
    for doc in docs:
        tf = Counter(doc)
        vec = [0.0] * len(vocab)
        for term, count in tf.items():
            if term in index:
                idf = math.log((1 + n_docs) / (1 + df[term])) + 1.0
                vec[index[term]] = count * idf
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


def embed_texts(texts: list[str], backend: str = "auto") -> tuple[list[list[float]], str]:
    """优先模型嵌入（sentence-transformers），否则 TF-IDF 兜底。返回 (向量, 实际后端)。"""
    if backend in ("auto", "sentence-transformers"):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            _model = getattr(embed_texts, "_st_model", None)
            if _model is None:
                _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
                embed_texts._st_model = _model  # type: ignore[attr-defined]
            return _model.encode(texts, normalize_embeddings=True).tolist(), "sentence-transformers"
        except Exception:  # noqa: BLE001 - 库未安装或下载失败时回退
            pass
    return tfidf_embed(texts), "tfidf"


def _init_centers(data: list[list[float]], k: int, rng: random.Random) -> list[list[float]]:
    centers = [list(data[rng.randrange(len(data))])]
    while len(centers) < k:
        dists = [min(sum((a - b) ** 2 for a, b in zip(point, c)) for c in centers) for point in data]
        total = sum(dists)
        if total <= 0:
            break
        target = rng.uniform(0, total)
        acc = 0.0
        for i, d in enumerate(dists):
            acc += d
            if acc >= target:
                centers.append(list(data[i]))
                break
    return centers


def kmeans(data: list[list[float]], k: int, iters: int = 40, seed: int = 7) -> tuple[list[int], list[list[float]]]:
    rng = random.Random(seed)
    centers = _init_centers(data, k, rng)
    if len(centers) < k:
        k = len(centers)
    labels = [0] * len(data)
    for _ in range(iters):
        for i, point in enumerate(data):
            labels[i] = min(range(len(centers)), key=lambda c: sum((point[j] - centers[c][j]) ** 2 for j in range(len(point))))
        new_centers = []
        for c in range(len(centers)):
            members = [data[i] for i in range(len(data)) if labels[i] == c]
            if not members:
                new_centers.append(list(centers[c]))
            else:
                new_centers.append([sum(m[j] for m in members) / len(members) for j in range(len(members[0]))])
        if new_centers == centers:
            break
        centers = new_centers
    return labels, centers


def _silhouette(data: list[list[float]], labels: list[int]) -> float:
    groups: dict[int, list[int]] = defaultdict(list)
    for i, label in enumerate(labels):
        groups[label].append(i)
    if len(groups) < 2:
        return 0.0
    score = 0.0
    for i, point in enumerate(data):
        same = groups[labels[i]]
        if len(same) <= 1:
            continue
        a = sum(sum((point[j] - data[j2][j]) ** 2 for j in range(len(point))) for j2 in same if j2 != i) / (len(same) - 1)
        others = [c for c in groups if c != labels[i]]
        b = min(
            sum(sum((point[j] - data[j2][j]) ** 2 for j in range(len(point))) for j2 in groups[c]) / len(groups[c])
            for c in others
        )
        score += (b - a) / max(a, b, 1e-9)
    return score / len(data)


def cluster(texts: list[str], embeddings: list[list[float]], k_max: int = 8) -> list[int]:
    n = len(texts)
    if n <= 1:
        return [0] * n
    best: Optional[tuple[float, list[int]]] = None
    for k in range(2, min(k_max, n) + 1):
        for seed in range(3):
            labels, _ = kmeans(embeddings, k, seed=seed)
            score = _silhouette(embeddings, labels)
            if best is None or score > best[0]:
                best = (score, labels)
    labels = best[1] if best else [0] * n
    mapping = {label: i for i, label in enumerate(sorted(set(labels)))}
    return [mapping[label] for label in labels]


def name_topics(clusters: list[dict], llm: Optional[object] = None, goal_text: str = "") -> list[dict]:
    """给每个聚类命名；LLM 不可用或输出非法时用「主题 N」占位。"""
    allowed = {c["topic_id"] for c in clusters}
    if llm is not None and clusters:
        try:
            from ..prompts import topic_messages

            result = llm.chat_json(topic_messages(clusters, goal_text))
            topics = result.get("topics") or result.get("themes") or []
            named = {}
            for item in topics:
                if isinstance(item, dict) and item.get("topic_id") in allowed:
                    named[int(item["topic_id"])] = {
                        "label": str(item.get("label") or "")[:60],
                        "description": str(item.get("description") or "")[:300],
                        "keywords": [str(k)[:40] for k in (item.get("keywords") or [])][:8],
                    }
            if len(named) == len(allowed):
                return [{**c, **named[c["topic_id"]]} for c in clusters]
        except Exception as exc:  # noqa: BLE001
            return [{**c, "label": f"主题{c['topic_id']}", "description": f"（LLM 命名失败：{exc}）", "keywords": []} for c in clusters]
    return [{**c, "label": f"主题{c['topic_id']}", "description": "", "keywords": []} for c in clusters]


def discover_topics(
    reviews: list[dict],
    *,
    embed_backend: str = "auto",
    k_max: int = 8,
    llm: Optional[object] = None,
    goal_text: str = "",
) -> dict:
    """输入清洗后的评论（含 review_key/text），输出主题与成员关系。"""
    texts = [r["text"] for r in reviews]
    embeddings, backend_used = embed_texts(texts, backend=embed_backend)
    labels = cluster(texts, embeddings, k_max=k_max)
    groups: dict[int, list[dict]] = defaultdict(list)
    for review, label in zip(reviews, labels):
        groups[label].append(review)
    clusters = []
    for topic_id, members in groups.items():
        ordered = sorted(members, key=lambda r: (-r.get("helpful_votes", 0), r["review_key"]))
        samples = [
            {"review_id": r["review_key"], "text": (r["title"] + " " + r["body"]).strip()[:200]}
            for r in ordered[:4]
        ]
        clusters.append({"topic_id": topic_id, "count": len(members), "samples": samples})
    named = name_topics(clusters, llm=llm, goal_text=goal_text)
    memberships = []
    for i, review in enumerate(reviews):
        memberships.append({
            "review_key": review["review_key"],
            "topic_id": labels[i],
            "method": "embedding+cluster",
        })
    return {
        "topics": named,
        "memberships": memberships,
        "embed_backend": backend_used,
        "model_driven": llm is not None,
    }
