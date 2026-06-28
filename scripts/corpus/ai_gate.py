"""DeepSeek agent: post gate, question cluster/answers. Rules only when no API key."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from scripts.config import (
    cache_dir,
    deepseek_api_base,
    deepseek_api_key,
    deepseek_model,
    deepseek_use_proxy,
    post_ai_filter_enabled,
    post_ai_filter_max_chars,
)
from scripts.corpus.dedupe_rank import _max_date, _union, dedupe_and_rank
from scripts.corpus.semantic_merge import merge_similar_questions
from scripts.corpus.tech_roles import canonical_role_id
from scripts.models import Question

_POST_SYS = (
    "判断是否真实技术岗面试面经（本人复盘：题目/流程/手撕/凉经）。"
    "keep=false：广告、培训、求助、外贸/海关/营销、学习路线、非技术面试、后端/Java/Go/测开/前端/产品/运营。"
    "keep=true→role_id:data|ai_app|null；topics:涉及的考察方向列表，从[Spark/计算,Hive/SQL,数仓建模,Flink/实时,数据工程,RAG,Agent,MCP/协议,LLM基础,手撕代码,项目深挖,后端八股,产品/业务,综合]中选，可多选。"
    'JSON:{"keep":bool,"role_id":str|null,"topics":list[str],"reason":str}'
)
_CLUSTER_SYS = (
    "整理数据开发/AI应用面试题库。输入 [{id,text}]。"
    "合并相似题为 groups(canonical,topic,ids)；"
    "drop：自我介绍/薪资/反问/寒暄/废话/感慨吐槽/求职经验叙述/非问句段落，"
    "以及明显属于后端Java/Go/C++系统编程的题目（如shared_ptr/JVM/Spring/线程池/HTTP框架等纯后端题）。"
    "topic 从[Spark/计算,Hive/SQL,数仓建模,Flink/实时,数据工程,RAG,Agent,MCP/协议,LLM基础,手撕代码,项目深挖,后端八股,产品/业务,综合]选。"
    'JSON:{"groups":[{"canonical":str,"topic":str,"ids":[str]}],"drop":[str]}'
)
_ANSWER_SYS = (
    "写数据开发/Agent 面试题简明参考答案，要点式 120～280 字。"
    '输入 {"role":str,"items":[{"id":str,"text":str,"topic":str}]}→{"answers":[{"id":str,"answer":str}]}'
)
_OFFLINE_POST = re.compile(r"面经|凉经|[一二三四五]面|面试题|手撕|笔试|面试官|问了|被问|拷打", re.I)


def ai_enabled() -> bool:
    return post_ai_filter_enabled() and bool(deepseek_api_key())


@dataclass
class PostVerdict:
    keep: bool
    role_id: str | None = None
    topics: list[str] = None  # type: ignore[assignment]
    reason: str = ""

    def __post_init__(self) -> None:
        if self.topics is None:
            self.topics = []


def _cache_path(name: str) -> Path:
    p = cache_dir() / "daily" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_cache(name: str) -> dict:
    path = _cache_path(name)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(name: str, cache: dict) -> None:
    if cache:
        _cache_path(name).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_agent_caches() -> list[str]:
    removed: list[str] = []
    for name in ("post_ai_filter_cache.json", "question_answer_cache.json"):
        path = _cache_path(name)
        if path.is_file():
            path.unlink()
            removed.append(name)
    return removed


def chat_json(system: str, user: str) -> dict | None:
    url = f"{deepseek_api_base()}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {deepseek_api_key()}", "Content-Type": "application/json"}
    body = {
        "model": deepseek_model(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    for trust_env in ((True, False) if deepseek_use_proxy() else (False, True)):
        try:
            with requests.Session() as session:
                session.trust_env = trust_env
                resp = session.post(url, headers=headers, json=body, timeout=25)
                resp.raise_for_status()
                raw = re.sub(
                    r"^```(?:json)?\s*|\s*```$",
                    "",
                    str(resp.json()["choices"][0]["message"]["content"]).strip(),
                )
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
        except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return None


def _post_key(url: str, blob: str) -> str:
    return (url or "").strip() or hashlib.sha256(blob[:200].encode()).hexdigest()


def offline_post_keep(combined: str, *, has_images: bool = False) -> bool:
    plain = re.sub(r"\s+", "", combined)
    if not plain and not has_images:
        return False
    if len(plain) < 12 and not has_images:
        return False
    return bool(_OFFLINE_POST.search(combined))


def judge_post(snippet: str, *, url: str = "", cache: dict | None = None) -> PostVerdict | None:
    snip = re.sub(r"\s+", " ", (snippet or "").strip())[: post_ai_filter_max_chars()]
    if not snip:
        return PostVerdict(False, reason="empty")
    key = _post_key(url, snip)
    store = cache if cache is not None else load_cache("post_ai_filter_cache.json")
    if key in store and isinstance(store[key], dict):
        row = store[key]
        return PostVerdict(
            bool(row.get("keep")),
            canonical_role_id(str(row.get("role_id") or "")) or None,
            [str(t) for t in row.get("topics") or []],
            str(row.get("reason") or ""),
        )
    data = chat_json(_POST_SYS, snip)
    if not data:
        return None
    verdict = PostVerdict(
        bool(data.get("keep")),
        canonical_role_id(str(data.get("role_id") or "")) or None,
        [str(t) for t in (data.get("topics") or []) if t],
        str(data.get("reason") or ""),
    )
    if cache is not None:
        cache[key] = {
            "keep": verdict.keep,
            "role_id": verdict.role_id,
            "topics": verdict.topics,
            "reason": verdict.reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    return verdict


def cached_post_keep(url: str, blob: str) -> bool | None:
    if not ai_enabled():
        return None
    row = load_cache("post_ai_filter_cache.json").get(_post_key(url, blob))
    return bool(row.get("keep")) if isinstance(row, dict) else None


def _merge_batch(batch: list[tuple[int, Question]]) -> list[Question]:
    data = chat_json(_CLUSTER_SYS, json.dumps([{"id": str(i), "text": q.text[:280]} for i, q in batch], ensure_ascii=False))
    if not data:
        return [q for _, q in batch]

    drop = {int(x) for x in (data.get("drop") or []) if str(x).isdigit()}
    by_id = {i: q for i, q in batch}
    used: set[int] = set()
    out: list[Question] = []

    for grp in data.get("groups") or []:
        if not isinstance(grp, dict):
            continue
        ids = [int(x) for x in (grp.get("ids") or []) if str(x).isdigit() and int(x) in by_id]
        if not ids:
            continue
        canon = str(grp.get("canonical") or by_id[ids[0]].text).strip() or by_id[ids[0]].text
        topic = str(grp.get("topic") or by_id[ids[0]].topic or "综合").strip() or "综合"
        merged = Question(text=canon, topic=topic, modality_origin=by_id[ids[0]].modality_origin, variants=[], freq=0)
        for idx in ids:
            used.add(idx)
            o = by_id[idx]
            if o.text != canon and o.text not in merged.variants:
                merged.variants.append(o.text)
            merged.freq += o.freq
            merged.latest_posted_at = _max_date(merged.latest_posted_at, o.latest_posted_at)
            _union(merged.source_refs, o.source_refs)
            _union(merged.role_tags, o.role_tags)
            _union(merged.company_tags, o.company_tags)
            if not merged.answer and o.answer:
                merged.answer = o.answer
        out.append(merged)

    for i, q in batch:
        if i not in used and i not in drop:
            out.append(q)
    return out


def cluster_questions(
    questions: list[Question],
    *,
    batch_size: int = 35,
    offline_threshold: float = 0.68,
    today: date | None = None,
) -> list[Question]:
    if len(questions) < 2:
        return questions
    if not ai_enabled():
        merged = merge_similar_questions(questions, threshold=offline_threshold)
        return dedupe_and_rank(merged, today=today) if today else merged

    indexed = list(enumerate(questions))
    if len(indexed) > batch_size * 2:
        indexed = list(enumerate(merge_similar_questions(questions, threshold=0.55)))

    merged: list[Question] = []
    for start in range(0, len(indexed), batch_size):
        if start:
            time.sleep(0.15)
        merged.extend(_merge_batch(indexed[start : start + batch_size]))
    return dedupe_and_rank(merged) if merged else merge_similar_questions(questions, threshold=offline_threshold)


def enrich_answers(questions: list[Question], role: str, *, top_n: int = 40, batch_size: int = 12) -> list[Question]:
    if not ai_enabled() or not questions:
        return questions
    cache = load_cache("question_answer_cache.json")
    pending: list[tuple[int, Question, str]] = []

    for i, q in enumerate(questions[:top_n]):
        if q.answer:
            continue
        ck = hashlib.sha256(q.text.strip().encode()).hexdigest()[:16]
        if ck in cache and cache[ck].get("answer"):
            q.answer = str(cache[ck]["answer"])
            continue
        pending.append((i, q, ck))

    for start in range(0, len(pending), batch_size):
        if start:
            time.sleep(0.15)
        chunk = pending[start : start + batch_size]
        payload = {"role": role, "items": [{"id": str(i), "text": q.text[:240], "topic": q.topic or "综合"} for i, q, _ in chunk]}
        data = chat_json(_ANSWER_SYS, json.dumps(payload, ensure_ascii=False))
        by_id = {}
        if isinstance(data, dict) and isinstance(data.get("answers"), list):
            by_id = {str(a.get("id")): str(a.get("answer") or "").strip() for a in data["answers"] if isinstance(a, dict)}
        for idx, q, ck in chunk:
            if ans := by_id.get(str(idx), "").strip():
                q.answer = ans
                cache[ck] = {"answer": ans, "at": datetime.now(timezone.utc).isoformat()}
    save_cache("question_answer_cache.json", cache)
    return questions
