from unittest.mock import Mock, PropertyMock

import pytest
from selenium.common.exceptions import NoAlertPresentException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from PySide6.QtWidgets import QApplication

from ui.pages import federation_tool as module
from ui.pages.macro_popup_recovery import NoQueryResultsError, dismiss_blocking_popups, find_clickable_context


def driver_with_windows():
    driver = Mock()
    driver.current_window_handle = "main"
    driver.window_handles = ["main", "login", "popup"]
    driver.find_elements.return_value = []
    return driver


def test_dismiss_alert_without_closing_loading_report_window():
    driver = driver_with_windows()
    assert dismiss_blocking_popups(driver, {"main", "login"}, None, Mock())
    driver.switch_to.alert.dismiss.assert_called_once()
    driver.switch_to.alert.accept.assert_not_called()
    driver.close.assert_not_called()
    driver.switch_to.window.assert_not_called()


def test_keep_window_with_macro_target():
    driver = driver_with_windows()
    driver.find_elements.side_effect = [[Mock()], [Mock()], []]
    dismiss_blocking_popups(driver, {"main", "login"}, (By.ID, "target"), Mock())
    driver.close.assert_not_called()


@pytest.mark.parametrize("contains_target", [False, True])
def test_html_modal_close_and_target_protection(contains_target):
    driver = driver_with_windows()
    driver.window_handles = ["main"]
    dialog, button, target = Mock(), Mock(), Mock()
    button.get_attribute.return_value = "닫기"
    dialog.find_elements.return_value = [button]
    driver.find_elements.side_effect = [[target], [dialog]]
    driver.execute_script.return_value = contains_target
    dismiss_blocking_popups(driver, {"main"}, (By.ID, "target"), Mock())
    clicks = [call for call in driver.execute_script.call_args_list if call.args[0] == "arguments[0].click();"]
    assert len(clicks) == (0 if contains_target else 1)


def test_wait_recovers_alert_without_replaying_step():
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = driver_with_windows()
    type(owner.driver.switch_to).alert = PropertyMock(side_effect=NoAlertPresentException())
    owner.config = {"dismiss_unexpected_popups": True, "performance": {"poll_interval": 0.05}}
    owner.status_callback = Mock()
    owner._popup_recovery_active = True
    owner._popup_recovery_count = 0
    owner._popup_protected_handles = {"main", "login"}
    owner._popup_target_locator = None
    predicate = Mock(side_effect=[UnexpectedAlertPresentException(), "found"])
    assert module.TimedWebDriverWait(owner, 1).until(predicate) == "found"
    assert predicate.call_count == 2
    owner._popup_recovery_active = False
    with pytest.raises(UnexpectedAlertPresentException):
        module.TimedWebDriverWait(owner, 1).until(Mock(side_effect=UnexpectedAlertPresentException()))


def test_explicit_dialog_step_is_not_auto_dismissed():
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.config = {"dismiss_unexpected_popups": True}
    runner.status_callback = Mock()
    runner._run_selector_step = Mock(side_effect=lambda *args: not runner._popup_recovery_active)
    assert runner.run_selector_step("alert", {"type": "alert", "action": "accept"})


def test_setting_persists_per_task(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, "__file__", str(tmp_path / "ui" / "pages" / "federation_tool.py"))
    page = module.FederationTool()
    page.select_task("invoice")
    assert not page.popup_recovery_check.isChecked()
    page.popup_recovery_check.setChecked(True)
    page.select_task("long_service")
    assert not page.popup_recovery_check.isChecked()
    page.select_task("invoice")
    assert page.popup_recovery_check.isChecked()
    page.close()


@pytest.mark.parametrize("target_context", [("report", ()), ("report", (0, 0)), ("main", (0,)), None])
def test_search_new_window_and_nested_frames_without_closing(target_context):
    element = Mock()
    element.is_displayed.return_value = True
    element.is_enabled.return_value = True

    class Switch:
        def __init__(self, driver):
            self.driver = driver

        def window(self, handle):
            self.driver.current_window_handle = handle
            self.driver.path = ()

        def default_content(self):
            self.driver.path = ()

        def frame(self, frame):
            self.driver.path += (frame,)

        def parent_frame(self):
            self.driver.path = self.driver.path[:-1]

    class Driver:
        window_handles = ["main", "report"]
        current_window_handle = "main"
        path = ()
        title = "report"

        def __init__(self):
            self.switch_to = Switch(self)

        def find_elements(self, by, value):
            if value == "iframe, frame":
                return [0] if len(self.path) < 2 else []
            return [element] if (self.current_window_handle, self.path) == target_context else []

    driver = Driver()
    found = find_clickable_context(driver, (By.ID, "download"), Mock())
    if target_context:
        assert found is element
        assert (driver.current_window_handle, driver.path) == target_context
    else:
        assert found is None
        assert driver.current_window_handle == "main" and driver.path == ()


def test_native_alert_is_closed_before_poll_and_execution_continues():
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = driver_with_windows()
    alert = Mock()
    alert.text = "알림"
    type(owner.driver.switch_to).alert = PropertyMock(side_effect=[alert, NoAlertPresentException()])
    owner.config = {"dismiss_unexpected_popups": True, "performance": {"poll_interval": 0.05}}
    owner.status_callback = Mock()
    owner._popup_recovery_active = True
    owner._popup_recovery_count = 0
    predicate = Mock(return_value="ready")
    assert module.TimedWebDriverWait(owner, 1).until(predicate) == "ready"
    alert.dismiss.assert_called_once()
    predicate.assert_called_once()
    assert owner._popup_recovery_count == 1


@pytest.mark.parametrize("webdriver_closed", [False, True])
def test_no_results_alert_stops_without_retrying_target(webdriver_closed):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = driver_with_windows()
    owner.config = {"dismiss_unexpected_popups": True}
    owner.status_callback = Mock()
    owner._popup_recovery_active = True
    owner._popup_recovery_count = 0
    alert = Mock()
    alert.text = "조회된 대상자 내역이 없습니다."
    type(owner.driver.switch_to).alert = PropertyMock(
        side_effect=NoAlertPresentException() if webdriver_closed else None,
        return_value=alert,
    )
    predicate = Mock(side_effect=UnexpectedAlertPresentException(alert_text=alert.text))
    with pytest.raises(NoQueryResultsError, match="현재 실행을 중단"):
        module.TimedWebDriverWait(owner, 20).until(predicate)
    assert predicate.call_count == (1 if webdriver_closed else 0)
    if not webdriver_closed:
        alert.dismiss.assert_called_once()


def test_no_results_stops_remaining_months():
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.config = {"iteration": dict(kind="month", start="2026-08", end="2026-05", direction="descending")}
    owner.status_callback = Mock()
    owner.run_selector_step = Mock(side_effect=NoQueryResultsError("조회된 대상자 내역이 없습니다."))
    items = [("start", {"type": "repeat_start", "repeat_mode": "range"}),
             ("print", {"type": "element"}), ("download", {"type": "element"}),
             ("end", {"type": "repeat_end"})]
    with pytest.raises(NoQueryResultsError):
        owner.run_workflow_items_once(items)
    owner.run_selector_step.assert_called_once()
    assert owner.run_selector_step.call_args.kwargs["context"]["repeat_value"] == "2026-08"


def test_context_search_starts_without_waiting_full_timeout(monkeypatch):
    from selenium.common.exceptions import NoSuchElementException
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = Mock()
    owner.driver.find_element.side_effect = NoSuchElementException()
    owner.timeout = 20
    owner._log = Mock()
    element = Mock()
    scan = Mock(return_value=element)
    monkeypatch.setattr(module, "find_clickable_context", scan)
    monkeypatch.setattr(module.time, "monotonic", Mock(side_effect=[0.0, 0.2, 1.1]))
    wait = Mock()

    def until(predicate):
        assert predicate(owner.driver) is False
        scan.assert_not_called()
        return predicate(owner.driver)

    wait.until.side_effect = until
    factory = Mock(return_value=wait)
    monkeypatch.setattr(module, "TimedWebDriverWait", factory)
    assert owner.wait_clickable_context("download", (By.ID, "download")) is element
    factory.assert_called_once_with(owner, 20)
    scan.assert_called_once()
