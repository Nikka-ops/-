import json
from pathlib import Path

from scripts.corpus.post_supplement import supplement_posts_for_role


def test_supplement_from_other_bank(tmp_path: Path):
    banks = tmp_path / "banks"
    slug_a = banks / "AI_应用开发_aaa"
    slug_a.mkdir(parents=True)

    post = {
        "source": "nowcoder",
        "url": "https://www.nowcoder.com/discuss/1",
        "post_type": "text",
        "raw_text": "字节 AI 应用开发 面经\n内容",
    }
    (slug_a / "raw_posts.json").write_text(json.dumps([post]), encoding="utf-8")
    (slug_a / "meta.json").write_text(
        json.dumps({"role": "AI 应用开发", "role_id": "ai_app", "post_count": 1}),
        encoding="utf-8",
    )
    (slug_a / "question_bank.json").write_text(
        json.dumps({"role": "AI 应用开发", "questions": []}),
        encoding="utf-8",
    )

    merged, meta = supplement_posts_for_role([], "AI 应用开发", "ai_app", banks)
    assert meta["from_banks"] == 1
    assert len(merged) == 1
