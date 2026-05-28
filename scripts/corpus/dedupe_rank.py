import re

from scripts.models import Question

_PUNCT = re.compile(r"[^\w一-鿿]+")


def normalize(text: str) -> str:
    t = text.strip().lower()
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def _union(into: list[str], extra: list[str]) -> None:
    for item in extra:
        if item not in into:
            into.append(item)


def dedupe_and_rank(questions: list[Question]) -> list[Question]:
    merged: dict[str, Question] = {}
    order: list[str] = []
    for q in questions:
        key = normalize(q.text)
        if key not in merged:
            merged[key] = Question(
                text=q.text,
                source_refs=list(q.source_refs),
                freq=q.freq,
                role_tags=list(q.role_tags),
                topic=q.topic,
                modality_origin=q.modality_origin,
            )
            order.append(key)
        else:
            m = merged[key]
            m.freq += q.freq
            _union(m.source_refs, q.source_refs)
            _union(m.role_tags, q.role_tags)
    ranked = sorted(order, key=lambda k: -merged[k].freq)
    return [merged[k] for k in ranked]
