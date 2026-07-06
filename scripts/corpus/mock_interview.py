"""模拟面试 Agent — 服务端会话管理。

流程：
  start(role, questions, background) → session_id + 第一题
    - AI 根据候选人背景从题库中挑选最合适的题目及顺序
  reply(session_id, answer) → AI 点评 + 下一题 / 结束
    - AI 面试官了解候选人背景，针对性追问
"""
from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field

from scripts.ai.gateway import chat_json

_SESSIONS: dict[str, "MockSession"] = {}


# ── AI 选题 Prompt ──────────────────────────────────────────────────────────

_SELECTOR_SYS = """你是资深技术面试官，负责为一场技术面试选题。
给定候选人背景和题库（含频次），选出最能考察候选人真实水平的题目。

选题原则：
1. 若候选人背景提到某技术（如 Spark、RAG），优先选该方向的题
2. 优先选高频题（batch_count 高），但适当加入一道中等难度的深挖题
3. 避免选候选人背景完全没提到的冷门方向（除非岗位必考）
4. 题目数量严格等于 n，不多不少

输出 JSON 数组（只含题目文本）：
["题目1", "题目2", ...]"""


def select_questions(
    background: str,
    questions: list[dict],
    *,
    n: int = 8,
    role: str = "数据开发",
) -> list[str]:
    """AI 根据候选人背景选题，fallback 为高频优先。"""
    candidates = sorted(questions, key=lambda q: q.get("batch_count", 1), reverse=True)[:40]
    q_list = [
        {"id": i, "text": q.get("text", ""), "topic": q.get("topic", ""), "freq": q.get("batch_count", 1)}
        for i, q in enumerate(candidates)
        if q.get("text")
    ]
    user_msg = json.dumps({
        "role": role,
        "n": n,
        "candidate_background": background[:800] if background else "（未提供）",
        "questions": q_list,
    }, ensure_ascii=False)

    result = chat_json(_SELECTOR_SYS, user_msg, task="prep")

    # result 应为 list[str]
    if isinstance(result, list) and result and isinstance(result[0], str):
        selected = [t for t in result if isinstance(t, str) and t.strip()][:n]
        if len(selected) >= min(n, 3):
            return selected

    # fallback: 高频 + shuffle 兜底
    texts = [q.get("text", "") for q in candidates if q.get("text")]
    random.shuffle(texts)
    return texts[:n]


# ── 面试官 Prompt ──────────────────────────────────────────────────────────

def _build_interviewer_sys(background: str, role: str) -> str:
    bg_section = f"\n\n候选人背景：\n{background[:600]}" if background and background.strip() else ""
    return f"""你是资深技术面试官，正在面试一名{role}候选人。{bg_section}

面试风格：
- 专业、直接，不客套
- 结合候选人背景追问（若他提到某项目/技术，深挖细节）
- 若回答笼统，追问"具体怎么实现的"/"遇到什么问题"
- 最多追问 2 次同一题

候选人回答后：
1. 简短点评（1~2句，指出具体亮点或不足，避免"不错/很好"等废话）
2. 决定是追问还是换题
3. 给出下一个问题

输出 JSON：
{{"comment": "点评", "next_question": "追问或新题", "is_followup": true/false, "finished": false}}

当所有题都问完，设 finished=true，comment 给 2~3 句整体点评（针对候选人背景指出强项和短板）。"""


# ── 数据结构 ───────────────────────────────────────────────────────────────

@dataclass
class MockSession:
    session_id: str
    role: str
    background: str
    questions: list[str]
    current_idx: int = 0
    followup_count: int = 0
    max_followups: int = 2
    history: list[dict] = field(default_factory=list)

    @property
    def current_question(self) -> str:
        if self.current_idx < len(self.questions):
            return self.questions[self.current_idx]
        return ""

    def advance(self) -> None:
        self.current_idx += 1
        self.followup_count = 0


# ── 公开 API ───────────────────────────────────────────────────────────────

def start_session(
    role: str,
    questions: list[dict | str],
    *,
    background: str = "",
    max_questions: int = 8,
) -> tuple[str, str]:
    """创建会话，返回 (session_id, 第一题文本)"""
    q_dicts: list[dict] = []
    for q in questions:
        if isinstance(q, dict) and q.get("text"):
            q_dicts.append(q)
        elif isinstance(q, str) and q:
            q_dicts.append({"text": q, "batch_count": 1})

    if not q_dicts:
        return "", ""

    # AI 选题（有 key 时）；无 key 时高频 fallback
    selected = select_questions(background, q_dicts, n=max_questions, role=role)
    if not selected:
        return "", ""

    sid = str(uuid.uuid4())[:8]
    _SESSIONS[sid] = MockSession(
        session_id=sid,
        role=role,
        background=background,
        questions=selected,
    )
    return sid, selected[0]


def reply(session_id: str, answer: str) -> dict:
    """处理候选人回答，返回 {comment, next_question, is_followup, finished, progress}"""
    sess = _SESSIONS.get(session_id)
    if sess is None:
        return {"error": "session_not_found"}

    current_q = sess.current_question
    sess.history.append({"question": current_q, "answer": answer})

    total = len(sess.questions)
    sys_prompt = _build_interviewer_sys(sess.background, sess.role)
    user_msg = json.dumps({
        "current_question": current_q,
        "candidate_answer": answer[:800],
        "questions_remaining": total - sess.current_idx - 1,
        "followup_used": sess.followup_count,
        "max_followups": sess.max_followups,
    }, ensure_ascii=False)

    result = chat_json(sys_prompt, user_msg, task="prep")

    if not result:
        sess.advance()
        next_q = sess.current_question
        finished = sess.current_idx >= total
        return {
            "comment": "收到，我们继续。",
            "next_question": next_q if not finished else "",
            "is_followup": False,
            "finished": finished,
            "progress": f"{min(sess.current_idx + 1, total)}/{total}",
        }

    is_followup = bool(result.get("is_followup"))
    finished = bool(result.get("finished"))

    if is_followup and sess.followup_count < sess.max_followups:
        sess.followup_count += 1
    else:
        sess.advance()
        finished = finished or sess.current_idx >= total

    next_q = result.get("next_question") or (sess.current_question if not finished else "")

    return {
        "comment": result.get("comment") or "",
        "next_question": next_q,
        "is_followup": is_followup,
        "finished": finished,
        "progress": f"{min(sess.current_idx + 1, total)}/{total}",
    }


def get_session_history(session_id: str) -> list[dict]:
    sess = _SESSIONS.get(session_id)
    return sess.history if sess else []
