"""题目详情 + AI 参考答案生成，带本地磁盘缓存。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.ai.gateway import chat_json

_MEM_CACHE: dict[str, dict] = {}

_ANSWER_SYS = """你是资深技术面试教练，为候选人提供面试题的参考答案。

输出 JSON（严格按格式，不要加注释）：
{
  "answer": "核心参考答案，3~5句，像候选人在面试中口述，简洁有力，直接切中考点",
  "key_points": ["考察点1（10字内）", "考察点2", "考察点3"],
  "depth": "若面试官追问可以展开的内容，1~2句",
  "pitfalls": "候选人常犯的错误或容易忽略的点，1句"
}

要求：
- answer 用第一人称，像真人在面试中说话，不要条目列表
- 技术细节准确，不要过度简化
- 不要重复题目本身的措辞"""


def _cache_path(banks_dir: Path, slug: str) -> Path:
    return banks_dir / slug / "qa_cache.json"


def _load_disk_cache(banks_dir: Path, slug: str) -> dict:
    p = _cache_path(banks_dir, slug)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_disk_cache(banks_dir: Path, slug: str, cache: dict) -> None:
    p = _cache_path(banks_dir, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _q_key(question: str) -> str:
    return hashlib.md5(question.strip().encode()).hexdigest()[:12]


def get_answer(
    question: str,
    *,
    topic: str = "",
    role: str = "数据开发",
    banks_dir: Path | None = None,
    slug: str = "",
) -> dict | None:
    """返回题目的 AI 参考答案，优先从缓存读取。"""
    key = _q_key(question)

    # 内存缓存
    if key in _MEM_CACHE:
        return _MEM_CACHE[key]

    # 磁盘缓存
    disk: dict = {}
    if banks_dir and slug:
        disk = _load_disk_cache(banks_dir, slug)
        if key in disk:
            _MEM_CACHE[key] = disk[key]
            return disk[key]

    # 调用 AI
    user_msg = json.dumps({
        "role": role,
        "topic": topic,
        "question": question,
    }, ensure_ascii=False)

    try:
        result = chat_json(_ANSWER_SYS, user_msg, task="prep", timeout=90)
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[question_answer] chat_json error: {e}")
        return None

    if not result or not result.get("answer"):
        print(f"[question_answer] empty result for: {question[:60]!r}, got: {result!r}")
        return None

    answer = {
        "answer":     result.get("answer", ""),
        "key_points": result.get("key_points") or [],
        "depth":      result.get("depth", ""),
        "pitfalls":   result.get("pitfalls", ""),
    }

    # 存缓存
    _MEM_CACHE[key] = answer
    if banks_dir and slug:
        disk[key] = answer
        _save_disk_cache(banks_dir, slug, disk)

    return answer
