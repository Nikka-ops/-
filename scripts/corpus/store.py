import json
from pathlib import Path

from scripts.models import RawPost, Question


def save_raw_posts(posts: list[RawPost], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [p.to_dict() for p in posts]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_raw_posts(path) -> list[RawPost]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [RawPost.from_dict(d) for d in data]


def save_questions(questions: list[Question], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [q.to_dict() for q in questions]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_questions(path) -> list[Question]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Question.from_dict(d) for d in data]
