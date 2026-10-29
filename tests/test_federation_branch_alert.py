from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import NoAlertPresentException, TimeoutException, UnexpectedAlertPresentException

from ui.pages import federation_tool as module


@pytest.mark.parametrize('late', [False, True])
def test_retirement_alert_accepts_and_stops_only_remaining_branch_steps(late):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner._log = Mock()
    owner.open_extracted_files = Mock()
    pending = [False]
    alert = Mock()
    alert.text = '저장되지 않은 퇴직특례 내역이 있습니다.'
    alert.accept.side_effect = lambda: pending.__setitem__(0, False)

    class Switch:
        @property
        def alert(self):
            if not pending[0]:
                raise NoAlertPresentException()
            return alert

    owner.driver = SimpleNamespace(switch_to=Switch())
    owner.config = {'selectors': {
        'staff': {'type': 'table_extract'},
        'submit': {'type': 'element', 'stop_branch_on_alert': '퇴직특례'},
        'hours': {'type': 'table_extract'},
        'other': {'type': 'element'},
        'remaining': {'type': 'table_extract'},
    }}
    calls = []

    def action(key, selector, context=None):
        calls.append(key)
        if (key == 'submit' and not late) or (key == 'other' and late):
            pending[0] = True
            if late:
                raise UnexpectedAlertPresentException('blocked', alert_text=alert.text)

    owner._run_selector_step = action
    owner.run_configured_workflow()
    assert calls == (['staff', 'submit', 'hours', 'other'] if late else ['staff', 'submit'])
    alert.accept.assert_called_once()
    assert '퇴직특례' in owner.workflow_stop_reason
    owner.open_extracted_files.assert_called_once()


def test_unrelated_alert_is_not_accepted_as_retirement_notice():
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner._branch_stop_alert_text = '퇴직특례'
    alert = Mock()
    alert.text = '다른 안내'
    owner.driver = SimpleNamespace(switch_to=SimpleNamespace(alert=alert))
    owner.check_branch_stop_alert()
    alert.accept.assert_not_called()


def test_retirement_notice_takes_priority_over_generic_popup_dismissal(monkeypatch):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.config = {}
    owner._log = Mock()
    owner._branch_stop_alert_text = '퇴직특례'
    owner._popup_recovery_active = True
    owner._popup_recovery_count = 0
    alert = Mock()
    alert.text = '저장되지 않은 퇴직특례 내역이 있습니다.'
    owner.driver = SimpleNamespace(switch_to=SimpleNamespace(alert=alert))
    dismiss = Mock()
    monkeypatch.setattr(module, 'dismiss_native_alert', dismiss)
    with pytest.raises(module.BranchWorkflowStopped):
        module.TimedWebDriverWait(owner, 0).until(lambda driver: True)
    alert.accept.assert_called_once()
    dismiss.assert_not_called()


def test_retirement_during_click_never_replays_submission_with_javascript():
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = Mock()
    owner._log = Mock()
    owner._branch_stop_alert_text = '퇴직특례'
    alert = owner.driver.switch_to.alert
    alert.text = '저장되지 않은 퇴직특례 내역이 있습니다.'
    button = Mock()
    button.click.side_effect = UnexpectedAlertPresentException('blocked', alert_text=alert.text)
    with pytest.raises(module.BranchWorkflowStopped):
        owner.click_element(button)
    alert.accept.assert_called_once()
    owner.driver.execute_script.assert_called_once_with("arguments[0].scrollIntoView({block:'center'});", button)


@pytest.mark.parametrize('outcome,clicks', [('second', 2), ('late_screen', 1), ('never', 3)])
def test_navigation_retries_are_bounded_and_skip_already_open_screen(monkeypatch, outcome, clicks):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = Mock()
    owner.timeout = 20
    owner.timeouts = {'long': 60}
    owner._log = Mock()
    owner.wait_clickable_context = Mock(return_value=Mock())
    owner.pointer_click = Mock()
    owner.driver.find_element.return_value.is_displayed.return_value = outcome == 'late_screen'
    waits = []

    class ScreenWait:
        def __init__(self, owner, timeout):
            waits.append(timeout)

        def until(self, condition):
            if outcome == 'second' and len(waits) == 2:
                return True
            raise TimeoutException('no screen')

    monkeypatch.setattr(module, 'TimedWebDriverWait', ScreenWait)
    step = {'type': 'element', 'action': 'pointer_click', 'by': 'xpath', 'value': '//nav',
            'expected_visible_xpath': '//next', 'navigation_attempts': 3, 'navigation_retry_wait': 5}
    if outcome == 'never':
        with pytest.raises(TimeoutException, match='3회'):
            owner._run_selector_step('navigation', step)
        assert waits == [5, 5, 50]
    else:
        assert owner._run_selector_step('navigation', step)
    assert owner.pointer_click.call_count == clicks
    assert owner.wait_clickable_context.call_count == clicks
