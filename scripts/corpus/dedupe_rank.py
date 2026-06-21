import re
from datetime import date, datetime

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


def _max_date(a: str | None, b: str | None) -> str | None:
    # Returns the more recent ISO date string; any real date beats None.
    candidates = [d for d in (a, b) if d]
    return max(candidates) if candidates else None


def _append_variant_dedupe(into: Question, text: str) -> None:
    t = text.strip()
    if not t or t == into.text:
        return
    if t not in into.variants:
        into.variants.append(t)


def _recency_weight(posted_at: str | None, today: date) -> float:
    if not posted_at:
        return 0.2
    try:
        d = datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return 0.2
    days = (today - d).days
    if days <= 180:
        return 1.0
    if days <= 365:
        return 0.75
    return 0.3


def dedupe_and_rank(questions: list[Question], today: date | None = None) -> list[Question]:
    """Merge questions with the same normalized text and rank by frequency and recency.

    Contract: callers pass one Question per occurrence with freq=1; this sums
    incoming freq, so passing pre-aggregated freqs will skew ranking. Score is
    freq * recency_weight(latest_posted_at); ties keep first-seen order.
    """
    ref = today or date.today()
    merged: dict[str, Question] = {}
    order: list[str] = []
    for q in questions:
        key = normalize(q.text)
        if key not in merged:
            merged[key] = Question(
                text=q.text,
                source_refs=list(q.source_refs),
                freq=q.freq,
                latest_posted_at=q.latest_posted_at,
                role_tags=list(q.role_tags),
                company_tags=list(q.company_tags),
                topic=q.topic,
                modality_origin=q.modality_origin,
            )
            order.append(key)
        else:
            m = merged[key]
            _append_variant_dedupe(m, q.text)
            m.freq += q.freq
            m.latest_posted_at = _max_date(m.latest_posted_at, q.latest_posted_at)
            _union(m.source_refs, q.source_refs)
            _union(m.role_tags, q.role_tags)
            _union(m.company_tags, q.company_tags)

    def score(k: str) -> float:
        q = merged[k]
        return q.freq * _recency_weight(q.latest_posted_at, ref)

    ranked = sorted(order, key=lambda k: -score(k))
    return [merged[k] for k in ranked]
