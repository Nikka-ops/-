"""考点趋势分析 — 按时间窗口对比题目频次，识别新兴/升温考点。

逻辑：
  - 把 posts 按 posted_at 分为「近30天」和「30~90天前」两个窗口
  - 统计每个 topic 在两个窗口的出现次数
  - 计算增长率（新兴：仅出现在近期；升温：增长 >50%；下降：减少）
  - AI 生成趋势叙述
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta


# --------------------------------------------------------------------------- #
#  日期解析                                                                    #
# --------------------------------------------------------------------------- #
def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
#  统计                                                                        #
# --------------------------------------------------------------------------- #
def compute_trends(
    posts: list[dict],
    *,
    recent_days: int = 30,
    window_days: int = 90,
) -> dict:
    """
    返回：
    {
      "recent_window": "2026-06-01 ~ 2026-07-01",
      "baseline_window": "2026-04-01 ~ 2026-06-01",
      "topics": [
        {"topic": "RAG", "recent": 12, "baseline": 4, "trend": "rising", "delta_pct": 200}
      ],
      "rising": ["RAG", "MCP/协议"],
      "new": ["Agent 协同"],
      "falling": ["后端八股"],
      "summary_input": {...}   # 给 AI 用
    }
    """
    now = datetime.now()
    recent_cutoff = now - timedelta(days=recent_days)
    baseline_cutoff = now - timedelta(days=window_days)

    recent_topic: dict[str, int] = defaultdict(int)
    baseline_topic: dict[str, int] = defaultdict(int)

    for post in posts:
        dt = _parse_date(post.get("posted_at") or "")
        if dt is None:
            continue
        topic = post.get("topic") or post.get("role_label") or "综合"
        if dt >= recent_cutoff:
            recent_topic[topic] += 1
        elif dt >= baseline_cutoff:
            baseline_topic[topic] += 1

    all_topics = set(recent_topic) | set(baseline_topic)
    rows = []
    for t in sorted(all_topics):
        r = recent_topic.get(t, 0)
        b = baseline_topic.get(t, 0)
        if r == 0 and b == 0:
            continue
        if b == 0:
            trend = "new"
            delta_pct = 999
        elif r == 0:
            trend = "gone"
            delta_pct = -100
        else:
            delta_pct = round((r - b) / b * 100)
            if delta_pct >= 50:
                trend = "rising"
            elif delta_pct <= -30:
                trend = "falling"
            else:
                trend = "stable"
        rows.append({"topic": t, "recent": r, "baseline": b, "trend": trend, "delta_pct": delta_pct})

    rows.sort(key=lambda x: -x["recent"])

    rising  = [x["topic"] for x in rows if x["trend"] == "rising"]
    new     = [x["topic"] for x in rows if x["trend"] == "new"]
    falling = [x["topic"] for x in rows if x["trend"] == "falling"]

    return {
        "recent_window":   f"{recent_cutoff.strftime('%Y-%m-%d')} ~ {now.strftime('%Y-%m-%d')}",
        "baseline_window": f"{baseline_cutoff.strftime('%Y-%m-%d')} ~ {recent_cutoff.strftime('%Y-%m-%d')}",
        "topics": rows,
        "rising": rising,
        "new": new,
        "falling": falling,
    }


# --------------------------------------------------------------------------- #
#  AI 叙述                                                                    #
# --------------------------------------------------------------------------- #
_TREND_SYS = """你是数据/Agent 岗面试趋势分析师。
根据近30天 vs 30~90天前的面经考点频次对比，生成一段简洁的「考点趋势播报」：
- 重点点出新兴、升温、降温考点
- 结合岗位技术背景解释可能原因
- 100~200字，不废话，不列表，直接写播报正文

JSON: {"broadcast": "播报文字"}"""


def ai_trend_broadcast(trend_data: dict) -> str:
    from scripts.ai.gateway import chat_json
    user = json.dumps({
        "recent_window": trend_data["recent_window"],
        "rising": trend_data["rising"],
        "new": trend_data["new"],
        "falling": trend_data["falling"],
        "top_topics": trend_data["topics"][:12],
    }, ensure_ascii=False)
    result = chat_json(_TREND_SYS, user, task="filter")
    if result and result.get("broadcast"):
        return str(result["broadcast"])
    # fallback
    parts = []
    if trend_data["new"]:
        parts.append(f"新兴考点：{', '.join(trend_data['new'][:3])}")
    if trend_data["rising"]:
        parts.append(f"升温考点：{', '.join(trend_data['rising'][:3])}")
    if trend_data["falling"]:
        parts.append(f"降温考点：{', '.join(trend_data['falling'][:3])}")
    return "；".join(parts) or "数据不足，暂无趋势"
