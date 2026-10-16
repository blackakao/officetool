import json
from copy import deepcopy

import pytest

from ui.pages import federation_config as config


def test_normalization_preserves_defaults_deletions_and_custom_tasks():
    source = {
        "custom": {"label": " 사용자 작업 ", "config_file": " custom.json ", "implemented": False},
        "invalid": None,
        "blank": {"label": "", "config_file": "blank.json"},
    }
    original = deepcopy(source)
    result = config.normalize_task_configs(source, {"invoice"})
    assert list(result) == ["long_service", "custom"]
    assert result["custom"] == {
        "label": "사용자 작업", "config_file": "custom.json", "implemented": False,
        "template_name": "empty", "template": config.EMPTY_SELECTOR_TEMPLATE,
    }
    assert source == original
    assert config.normalize_task_configs(None)["invoice"]["template"] is config.SELECTOR_TEMPLATE


def test_config_creation_copies_template_and_roundtrips_unicode(tmp_path):
    template = deepcopy(config.EMPTY_SELECTOR_TEMPLATE)
    path = tmp_path / "설정" / "매크로.json"
    created = config.ensure_selector_config(path, template)
    created["selectors"]["custom"] = {"label": "사용자 단계", "value": "//input"}
    assert template["selectors"] == {}
    config.save_selector_config(path, created)
    assert "사용자 단계" in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == created


def test_config_migration_preserves_order_deleted_steps_and_runtime_settings(tmp_path):
    template = deepcopy(config.EMPTY_SELECTOR_TEMPLATE)
    template["selectors"] = {
        key: {"label": key, "by": "xpath", "value": "//default", "required": True}
        for key in ("deleted", "added")
    }
    data = {
        "selectors": {"custom": {"label": "유지", "value": "//custom"},
                      "pause": {"type": "delay", "value": "3"}},
        "deleted_selector_keys": ["deleted"],
        "timeouts": {"default": 7}, "browser": {"window_index": 2},
        "iteration": {"kind": "month", "start": "2026-08", "end": "2026-01"},
        "start_number": 9, "extra": {"preserve": True},
    }
    path = tmp_path / "macro.json"
    config.save_selector_config(path, data)
    loaded = config.ensure_selector_config(path, template)
    assert list(loaded["selectors"]) == ["custom", "pause", "added"]
    assert loaded["selectors"]["custom"]["value"] == "//custom"
    assert loaded["selectors"]["pause"]["action"] == "short_wait"
    assert loaded["selectors"]["pause"]["type"] == "legacy_action"
    for key in ("iteration", "start_number", "extra", "browser"):
        assert loaded[key] == data[key]
    assert loaded["timeouts"]["default"] == 7
    assert config.ensure_selector_config(path, template) == loaded
    assert json.loads(path.read_text(encoding="utf-8")) == loaded


def test_locator_and_runtime_substitution_preserve_input():
    selector = {"by": "xpath", "value": " //row[{repeat_index+2}]/cell[{repeat_number-1}]/{repeat_value} "}
    original = dict(selector)
    assert config.apply_runtime_context(selector) is selector
    resolved = config.apply_runtime_context(selector, {"repeat_index": 3, "repeat_number": 8, "repeat_value": "2026-08"})
    assert config.build_locator(resolved) == ("xpath", "//row[5]/cell[7]/2026-08")
    assert selector == original
    assert config.build_locator({"value": " "}) is None
    with pytest.raises(ValueError, match="선택자 유형"):
        config.build_locator({"by": "unsupported", "value": "target"})


def test_legacy_imports_share_the_same_objects():
    from ui.pages import federation_dialogs as dialogs
    from ui.pages import federation_tool as legacy
    from ui.pages.carefor_tool import CareforTool

    for name in (
        "ACTION_TYPES", "BY_TYPES", "DEFAULT_TASK_CONFIGS", "EMPTY_SELECTOR_TEMPLATE",
        "PROCESS_ACTIONS", "PROCESS_TYPES", "REPEAT_MODES", "SELECTOR_TEMPLATE",
        "apply_runtime_context", "build_locator", "english_task_stem",
        "ensure_selector_config", "normalize_task_configs", "save_selector_config", "task_template",
    ):
        assert getattr(legacy, name) is getattr(config, name)
    for name in ("SelectorConfigDialog", "SelectorTableWidget", "TaskConfigDialog"):
        assert getattr(legacy, name) is getattr(dialogs, name)
    assert issubclass(CareforTool, legacy.FederationTool)


def test_editor_nested_markers_copy_move_delete_and_save(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ui.pages.federation_dialogs import SelectorConfigDialog

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    path = tmp_path / "editor.json"
    dialog = SelectorConfigDialog(None, path, config.EMPTY_SELECTOR_TEMPLATE)
    dialog.add_repeat_rows()
    dialog.table.selectRow(0)
    dialog.add_condition_rows()
    rows = dialog._all_row_data()
    assert [item[1]["type"] for item in rows] == [
        "repeat_start", "condition_start", "condition_true", "condition_false", "condition_end", "repeat_end",
    ]
    assert dialog._validate_repeat_pairs(rows)
    dialog.table.selectRow(1)
    dialog.copy_selected_row()
    assert dialog.table.rowCount() == 10
    dialog.delete_selected_row()
    assert dialog.table.rowCount() == 6
    dialog.move_selector_row(0, 3)
    assert dialog._validate_repeat_pairs(dialog._all_row_data())
    expected = [selector for _, selector in dialog._all_row_data()]
    dialog.save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert list(saved["selectors"].values()) == expected
    reopened = SelectorConfigDialog(None, path, config.EMPTY_SELECTOR_TEMPLATE)
    assert [selector for _, selector in reopened._all_row_data()] == expected
    reopened.close()
    dialog.close()
