import json
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QMessageBox

from ui.pages import federation_tool as module
from ui.pages.federation_batch import BranchBatchDialog, BranchBatchThread


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_task_names_are_automatic_unique_and_safe(app):
    dialog = module.TaskConfigDialog(None, {"claim_statement_create"})
    dialog.name_edit.setText("청구 명세서 만들기")
    key, config = dialog.task_data()
    assert key == "claim_statement_create_2"
    assert config["config_file"] == "federation_selectors_claim_statement_create_2.json"
    assert not hasattr(dialog, "json_name_edit")
    dialog.name_edit.setText("../../새로운 한글 업무?")
    _, config = dialog.task_data()
    assert Path(config["config_file"]).name == config["config_file"]
    assert config["config_file"].isascii()
    dialog.close()


def test_branch_selection_defaults_all_in_display_order(app):
    branches = [{"branch_name": name} for name in ("A", "B", "C")]
    dialog = BranchBatchDialog(None, branches)
    assert dialog.selected_branches() == branches
    dialog.table.item(1, 0).setCheckState(Qt.Unchecked)
    assert [b["branch_name"] for b in dialog.selected_branches()] == ["A", "C"]
    dialog.set_all(False)
    assert dialog.selected_branches() == []
    dialog.set_all(True)
    assert dialog.selected_branches() == branches
    dialog.close()


@pytest.mark.parametrize("failure", [None, "login", "macro", "close", "stop"])
def test_batch_order_cleanup_failures_and_stop(app, failure):
    events, summaries = [], []

    class Driver:
        def __init__(self, name):
            self.name = name

        def quit(self):
            events.append((self.name, "quit"))
            if failure == "close" and self.name == "A":
                raise RuntimeError("cannot close")

    class Login(QThread):
        finished_signal = Signal(str, bool)

        def __init__(self, branch):
            super().__init__()
            self.branch = branch
            self.driver = Driver(branch["branch_name"])

        def run(self):
            name = self.branch["branch_name"]
            events.append((name, "login"))
            self.finished_signal.emit("login", not (failure == "login" and name == "A"))

    class Process(QThread):
        finished_signal = Signal(str, bool)
        status_signal = Signal(str)

        def __init__(self, driver, branch, path, template, **kwargs):
            super().__init__()
            self.name = branch["branch_name"]
            self.start_number = kwargs["start_number"]

        def run(self):
            events.append((self.name, "macro", self.start_number))
            if failure == "stop":
                worker.requestInterruption()
            self.finished_signal.emit("macro", not (failure == "macro" and self.name == "A"))

    worker = BranchBatchThread([{"branch_name": "A"}, {"branch_name": "B"}],
                              Login, Process, Path("unused.json"), {}, 7)
    worker.summary_signal.connect(summaries.append)
    worker.start()
    deadline = time.monotonic() + 5
    while worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    worker.wait(1000)
    app.processEvents()
    assert summaries
    assert events[0] == ("A", "login")
    assert ("A", "quit") in events
    if failure in {"close", "stop"}:
        assert not any(event[0] == "B" for event in events)
    else:
        assert events.index(("A", "quit")) < events.index(("B", "login"))
        assert events[-1] == ("B", "quit")
    if failure != "login":
        assert ("A", "macro", 7) in events
    if failure in {"login", "macro", "close"}:
        assert not summaries[0][0]["success"]


def test_copy_task_and_single_start_setting(app, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "__file__", str(tmp_path / "ui" / "pages" / "federation_tool.py"))
    monkeypatch.setattr(module.FederationTool, "_log", lambda *args, **kwargs: None)
    page = module.FederationTool()
    page.select_task("invoice")
    page.run_start_number_spin.setValue(23)
    source_path = page._selector_config_path("invoice")
    original = json.loads(source_path.read_text(encoding="utf-8"))
    assert original["start_number"] == 23
    dialog = module.SelectorConfigDialog(page, source_path)
    assert not hasattr(dialog, "start_number_spin")
    dialog.close()
    monkeypatch.setattr(module.TaskConfigDialog, "exec", lambda self: QDialog.Accepted)
    page.copy_task()
    assert page.current_task != "invoice"
    copied_path = page._selector_config_path(page.current_task)
    assert copied_path != source_path
    assert json.loads(copied_path.read_text(encoding="utf-8")) == original
    page.run_start_number_spin.setValue(9)
    assert json.loads(copied_path.read_text(encoding="utf-8"))["start_number"] == 9
    assert json.loads(source_path.read_text(encoding="utf-8")) == original
    page.select_task("invoice")
    assert page.run_start_number_spin.value() == 23
    page.close()


def test_open_batch_cancel_does_not_launch(app, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "__file__", str(tmp_path / "ui" / "pages" / "federation_tool.py"))
    page = module.FederationTool()
    page.select_task("invoice")
    monkeypatch.setattr(module.BranchBatchDialog, "exec", lambda self: QDialog.Rejected)
    page.open_batch_dialog()
    assert page.batch_thread is None
    page.close()


@pytest.mark.parametrize("accepted,confirmed", [(False, False), (True, False), (True, True)])
def test_delete_task_popup_cancel_and_confirm(app, tmp_path, monkeypatch, accepted, confirmed):
    monkeypatch.setattr(module, "__file__", str(tmp_path / "ui" / "pages" / "federation_tool.py"))
    page = module.FederationTool()
    page.select_task("invoice")
    original = set(page.task_configs)
    config_path = page._selector_config_path("invoice")

    def show(dialog):
        assert dialog.windowTitle() == "작업 삭제"
        combo = dialog.findChild(QComboBox, "delete_task_selection")
        assert combo.count() == len(original)
        assert combo.currentData() == "invoice"
        return QDialog.Accepted if accepted else QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", show)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes if confirmed else QMessageBox.No)
    page.delete_task_button.click()
    if accepted and confirmed:
        assert "invoice" not in page.task_configs
        assert "invoice" in page.deleted_task_keys
        assert page.current_task is None
        assert "invoice" not in page._load_task_configs()
    else:
        assert set(page.task_configs) == original
        assert page.current_task == "invoice"
    assert not hasattr(page, "delete_task_container")
    assert config_path.exists()
    page.close()
