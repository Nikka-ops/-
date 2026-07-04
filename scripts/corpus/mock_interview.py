"""模拟面试 Agent — 服务端会话管理。

流程：
  start(role, questions) → session_id + 第一题
  reply(session_id, answer) → AI 点评 + 下一题 / 结束
"""
from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field

from scripts.ai.gateway import chat_json

_SESSIONS: dict[str, "MockSession"] = {}


_INTERVIEWER_SYS = """你是资深技术面试官，正在对候选人进行技术面试（数据开发/Agent岗）。
风格：专业、直接、适当追问，不客套。
候选人回答后你要：
1. 简短点评（1~2句，指出答案亮点或具体不足，勿夸赞"不错"）
2. 决定是深入追问还是换下一题（若答得很好则换题，若不足则追问一个具体问题）
3. 给出下一个问题（追问或新题，二选一）

输出 JSON：
{"comment": "点评", "next_question": "下一个问题（追问或新题）", "is_followup": true/false, "finished": false}

当所有预设题都问完且本题已评完，设 finished=true，在 comment 里给 2~3 句整体面试总结。"""


@dataclass
class MockSession:
    session_id: str
    role: str
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


def start_session(
    role: str,
    questions: list[dict | str],
    *,
    max_questions: int = 8,
) -> tuple[str, str]:
    """创建会话，返回 (session_id, 第一题文本)"""
    qs = []
    for q in questions:
        text = q.get("text") if isinstance(q, dict) else str(q)
        if text:
            qs.append(text)
    random.shuffle(qs)
    qs = qs[:max_questions]

    if not qs:
        return "", ""

    sid = str(uuid.uuid4())[:8]
    _SESSIONS[sid] = MockSession(
        session_id=sid,
        role=role,
        questions=qs,
    )
    return sid, qs[0]


def reply(session_id: str, answer: str) -> dict:
    """
    处理候选人回答，返回：
    {comment, next_question, is_followup, finished, progress}
    """
    sess = _SESSIONS.get(session_id)
    if sess is None:
        return {"error": "session_not_found"}

    current_q = sess.current_question
    sess.history.append({"question": current_q, "answer": answer})

    total = len(sess.questions)
    user = json.dumps({
        "role": sess.role,
        "current_question": current_q,
        "candidate_answer": answer[:600],
        "questions_remaining": total - sess.current_idx - 1,
        "followup_used": sess.followup_count,
        "max_followups": sess.max_followups,
    }, ensure_ascii=False)

    result = chat_json(_INTERVIEWER_SYS, user, task="prep")

    if not result:
        # fallback
        sess.advance()
        next_q = sess.current_question
        finished = sess.current_idx >= total
        return {
            "comment": "收到，我们继续。",
            "next_question": next_q if not finished else "",
            "is_followup": False,
            "finished": finished,
            "progress": f"{min(sess.current_idx+1, total)}/{total}",
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
        "progress": f"{min(sess.current_idx+1, total)}/{total}",
    }


def get_session_history(session_id: str) -> list[dict]:
    sess = _SESSIONS.get(session_id)
    return sess.history if sess else []
