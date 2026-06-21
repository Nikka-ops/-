from scripts.corpus.company_catalog import (
    INTERNET_GIANTS,
    MANUFACTURING_GIANTS,
    is_preset_company,
    list_company_groups,
)


def test_list_company_groups():
    groups = list_company_groups()
    assert len(groups) == 2
    assert groups[0]["id"] == "internet"
    assert groups[1]["id"] == "manufacturing"
    assert "字节跳动" in groups[0]["companies"]
    assert "比亚迪" in groups[1]["companies"]


def test_is_preset_company():
    assert is_preset_company("腾讯")
    assert is_preset_company("蔚来")
    assert not is_preset_company("某未知公司")
