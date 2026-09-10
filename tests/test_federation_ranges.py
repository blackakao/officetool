import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from ui.pages import federation_tool as module
from ui.pages.macro_ranges import range_values


@pytest.mark.parametrize("kind,start,end,direction,expected", [
    ("month", "2026-02", "2025-11", "descending", ["2026-02", "2026-01", "2025-12", "2025-11"]),
    ("year", "2026", "2024", "descending", ["2026", "2025", "2024"]),
    ("day", "2024-03-01", "2024-02-28", "descending", ["2024-03-01", "2024-02-29", "2024-02-28"]),
    ("integer", "-1", "2", "ascending", [-1, 0, 1, 2]),
    ("month", "2026-08", "2026-08", "descending", ["2026-08"]),
])
def test_range_values(kind, start, end, direction, expected):
    assert range_values(dict(kind=kind, start=start, end=end, direction=direction)) == expected


@pytest.mark.parametrize("settings", [
    dict(kind="month", start="2026-13", end="2025-01"),
    dict(kind="day", start="2025-02-29", end="2025-01-01"),
    dict(kind="year", start="2025", end="2026", direction="descending"),
    dict(kind="month", start="2026", end="2025"),
    dict(kind="integer", start="5", end="1", step=0),
    dict(kind="legacy", start="1", end="2"),
])
def test_invalid_ranges(settings):
    with pytest.raises(ValueError):
        range_values(settings)


def test_range_workflow_payload_and_error_stop():
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.config = {"iteration": dict(kind="month", start="2026-08", end="2025-01", direction="descending")}
    runner._log = Mock()
    received = []
    runner.run_selector_step = lambda key, selector, context=None: received.append(
        (key, runner.runtime_text_value(selector.get("expected_value", ""), context)))
    items = [("before", {}), ("start", {"type": "repeat_start", "repeat_mode": "range"}),
             ("input", {"expected_value": "{repeat_value}"}), ("download", {}),
             ("end", {"type": "repeat_end"}), ("after", {})]
    runner.run_workflow_items_once(items)
    assert [value for key, value in received if key == "input"] == [f"2026-{n:02d}" for n in range(8, 0, -1)] + [f"2025-{n:02d}" for n in range(12, 0, -1)]
    assert received[0][0] == "before" and received[-1][0] == "after"
    assert sum(key == "download" for key, _ in received) == 20
    runner.run_selector_step = Mock(side_effect=ValueError("blocked"))
    with pytest.raises(ValueError, match="blocked"):
        runner.run_workflow_items_once(items[1:-1])
    assert runner.run_selector_step.call_count == 1
    assert module.apply_runtime_context({"value": "{repeat_number}"}, {"repeat_number": "2026-08"})["value"] == "2026-08"
    assert module.apply_runtime_context({"value": "{repeat_number+2}"}, {"repeat_number": 8})["value"] == "10"


def test_input_field_container_and_verification(monkeypatch):
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.driver = Mock()
    runner.timeout = 1
    runner._log = Mock()
    field = Mock()
    field.tag_name = "input"
    field.get_attribute.return_value = "202608"
    container = Mock()
    container.tag_name = "div"
    container.find_elements.return_value = [field]
    field.is_displayed.return_value = True
    field.is_enabled.return_value = True
    wait = Mock()
    wait.until.side_effect = [container, True]
    monkeypatch.setattr(module, "TimedWebDriverWait", lambda *args: wait)
    assert runner.input_field_text("input", {"by": "xpath", "value": "//container", "expected_value": "{repeat_value}"}, {"repeat_value": "2026-08"})
    field.send_keys.assert_any_call("2026-08")
    verification = wait.until.call_args_list[1].args[0]
    assert verification(runner.driver)
    field.get_attribute.return_value = "202607"
    assert not verification(runner.driver)
    container.find_elements.return_value = []
    wait.until.side_effect = [container]
    with pytest.raises(ValueError, match="입력칸"):
        runner.input_field_text("input", {"by": "xpath", "value": "//container"})


def test_payroll_template_and_editor_roundtrip(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = Path(__file__).resolve().parents[1] / "data" / "federation_selectors_payroll_download.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    # The user's saved end month is editable; use an explicit test range.
    config["iteration"] = dict(kind="month", start="2026-08", end="2025-01", direction="descending", step=1)
    assert len(range_values(config["iteration"])) == 20
    steps = list(config["selectors"].values())
    start = next(i for i, step in enumerate(steps) if step["type"] == "repeat_start")
    assert start == 3
    assert steps[start + 1]["action"] == "input_text"
    assert steps[start + 1]["expected_value"] == "{repeat_value}"
    assert steps[-1]["type"] == "repeat_end"
    path = tmp_path / "macro.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    dialog = module.SelectorConfigDialog(None, path)
    monkeypatch.setattr(module.QMessageBox, "information", lambda *args: None)
    dialog.save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["iteration"] == config["iteration"]
    assert any(step.get("repeat_mode") == "range" for step in saved["selectors"].values())
    assert any(step.get("action") == "input_text" and step["expected_value"] == "{repeat_value}" for step in saved["selectors"].values())
    dialog.close()


def test_range_toolbar_persists_per_task(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, "__file__", str(tmp_path / "ui" / "pages" / "federation_tool.py"))
    page = module.FederationTool()
    page.select_task("invoice")
    page.range_kind.setCurrentIndex(page.range_kind.findData("month"))
    page.range_start.setText("2026-08")
    page.range_end.setText("2025-01")
    page.save_range_settings()
    assert not page.run_start_number_spin.isEnabled()
    page.select_task("long_service")
    assert page.range_kind.currentData() == "legacy"
    page.select_task("invoice")
    assert page.range_start.text() == "2026-08"
    assert page.range_end.text() == "2025-01"
    assert page.range_kind.currentData() == "month"
    page.close()


def test_range_returns_to_start_window_before_next_month():
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.driver = Mock()
    runner.driver.current_window_handle = "main"
    runner.driver.window_handles = ["main", "report"]
    runner.config = {"restore_range_context": True, "iteration": dict(kind="month", start="2026-08", end="2026-07", direction="descending")}
    runner._log = Mock()
    calls = []
    runner.driver.switch_to.window.side_effect = lambda handle: calls.append(("window", handle))
    runner.driver.switch_to.default_content.side_effect = lambda: calls.append(("frame", "top"))
    runner.run_selector_step = lambda key, selector, context=None: calls.append((key, context["repeat_value"]))
    runner.run_workflow_items_once([
        ("start", {"type": "repeat_start", "repeat_mode": "range"}),
        ("input", {"type": "element"}), ("end", {"type": "repeat_end"}),
    ])
    assert calls == [("input", "2026-08"), ("window", "main"), ("frame", "top"), ("input", "2026-07")]
