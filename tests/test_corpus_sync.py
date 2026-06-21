from pathlib import Path

import yaml

from scripts.corpus.company_normalize import (
    normalize_company_name,
    reload_company_aliases_cache,
)
from scripts.corpus.tech_roles import parse_role_ids
from scripts.scrape.keywords import merged_nowcoder_queries_for_roles


def test_custom_company_aliases_yaml(tmp_path, monkeypatch):
    yaml_path = tmp_path / "aliases.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "subsidiaries": {"示例子公司": "示例集团"},
                "not_companies": ["badtag"],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_ALIASES_PATH", str(yaml_path))
    reload_company_aliases_cache()

    assert normalize_company_name("示例子公司") == "示例集团"
    assert normalize_company_name("badtag") is None
    assert normalize_company_name("淘天") == "阿里巴巴"


def test_parse_role_ids_dedupes_and_aliases():
    assert parse_role_ids("ai_app", "") == ["ai_app"]
    assert parse_role_ids("", "backend,ai_app,backend") == ["backend", "ai_app"]
    assert parse_role_ids("", "agent,backend") == ["ai_app", "backend"]


def test_merged_queries_cover_multiple_roles():
    companies = ["字节跳动", "腾讯"]
    queries = merged_nowcoder_queries_for_roles(["ai_app", "backend"], companies)
    assert queries
    assert len(queries) >= len(companies) * 2
