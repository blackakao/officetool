import json

from ui.pages.branch_task_settings import branch_key, filter_branches_for_task


def test_task_filter_defaults_to_all_active_branches(tmp_path):
    branches = [
        {"organization_code": "1", "branch_name": "A", "active": True},
        {"organization_code": "2", "branch_name": "B", "active": False},
    ]

    assert filter_branches_for_task(branches, "document", tmp_path / "missing.json") == [branches[0]]


def test_task_filter_uses_configured_branch_keys(tmp_path):
    branches = [
        {"organization_code": "1", "branch_name": "A", "active": True},
        {"organization_code": "2", "branch_name": "B", "active": True},
    ]
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"tasks": {"monthly_work": ["2"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert filter_branches_for_task(branches, "monthly_work", settings_path) == [branches[1]]
    assert filter_branches_for_task(branches, "login", settings_path) == branches


def test_branch_key_falls_back_to_branch_name():
    assert branch_key({"organization_code": "", "branch_name": "본점"}) == "본점"
