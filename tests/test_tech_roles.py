from scripts.corpus.tech_roles import (
    DEFAULT_ROLE_ID,
    canonical_role_id,
    equivalent_role_ids,
    get_tech_role,
    list_tech_roles,
    resolve_role_label,
)


def test_list_tech_roles_has_core_jobs():
    roles = list_tech_roles()
    labels = {r["label"] for r in roles}
    assert "后端开发" in labels
    assert "算法工程师" in labels
    assert "AI/Agent 应用开发" in labels
    assert "Agent 开发" not in labels
    assert "测试开发" in labels


def test_resolve_role_label_by_id():
    assert resolve_role_label(role_id="backend") == "后端开发"
    assert resolve_role_label(role_id="agent") == "AI 应用开发"
    assert resolve_role_label(role_id="ai_app") == "AI 应用开发"


def test_resolve_role_label_custom_text():
    assert resolve_role_label(role_text="游戏客户端") == "游戏客户端"


def test_default_role():
    assert get_tech_role(DEFAULT_ROLE_ID) is not None


def test_canonical_and_equivalent_role_ids():
    assert canonical_role_id("agent") == "ai_app"
    assert set(equivalent_role_ids("ai_app")) == {"ai_app", "agent"}
    assert equivalent_role_ids("backend") == ["backend"]
