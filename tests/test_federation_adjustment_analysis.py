import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException

from ui.pages import federation_tool as module


@pytest.mark.parametrize("screen_ready", [True, False])
@pytest.mark.parametrize('label,next_label', [
    ('당월운영', '근무내용관리'), ('근무내용관리', '종사자 입사보고 테이블 추출'),
])
def test_navigation_waits_for_next_screen_without_window_rescan(monkeypatch, screen_ready, label, next_label):
    path = Path(__file__).resolve().parents[1] / "data" / "federation_selectors_adjustment_analysis.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    key, step = next((key, step) for key, step in config["selectors"].items()
                     if step["label"] == label)
    management = next(step for step in config["selectors"].values()
                      if step["label"] == next_label)
    step = {**step, 'navigation_attempts': 1}
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.config = config
    runner.timeout = 20
    runner.timeouts = config["timeouts"]
    runner.driver = Mock()
    runner._log = Mock()
    button = Mock()
    runner.wait_clickable_context = Mock(return_value=button)
    runner.click = Mock(side_effect=AssertionError("Native click must not bypass pointer readiness"))
    runner.pointer_click = Mock()
    screen = Mock()
    screen.is_displayed.return_value = screen_ready
    runner.driver.find_element.return_value = screen

    class ScreenWait:
        def __init__(self, owner, timeout):
            assert owner is runner
            assert timeout == config["timeouts"]["long"]

        def until(self, condition):
            runner.pointer_click.assert_called_once_with(button, key)
            result = condition(runner.driver)
            runner.driver.find_element.assert_called_once_with("xpath", management["value"])
            if not result:
                raise TimeoutException("Management screen did not open")
            return result

    monkeypatch.setattr(module, "TimedWebDriverWait", ScreenWait)
    if screen_ready:
        assert runner._run_selector_step(key, step) is True
    else:
        with pytest.raises(TimeoutException, match=label) as error:
            runner._run_selector_step(key, step)
        assert management['value'] in str(error.value)

    runner.wait_clickable_context.assert_called_once_with(key, ("xpath", step["value"]), 20)
    runner.pointer_click.assert_called_once_with(button, key)
    runner.driver.switch_to.window.assert_not_called()
    runner.click.assert_not_called()


def test_open_modal_cancels_background_pointer_wait_without_click(monkeypatch):
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.driver = Mock()
    runner.config = {}
    runner.timeout = 0
    runner._log = Mock()
    runner._pointer_completion_xpath = '//opened-menu'
    runner.driver.find_element.return_value.is_displayed.return_value = True
    actions = Mock()
    monkeypatch.setattr(module, 'ActionChains', actions)
    assert runner.pointer_click(Mock(), 'background') is False
    actions.assert_not_called()
    runner.driver.execute_script.assert_not_called()


def test_work_menu_uses_popup_id_and_label_instead_of_absolute_div_position():
    path = Path(__file__).resolve().parents[1] / 'data' / 'federation_selectors_adjustment_analysis.json'
    steps = list(json.loads(path.read_text(encoding='utf-8'))['selectors'].values())
    current = next(step for step in steps if step['label'] == '당월운영')
    work = next(step for step in steps if step['label'] == '근무내용관리')
    assert current['expected_visible_xpath'] == work['value']
    assert '.npfa100m01.' in work['value'] and '.grid_menu.body.' in work['value']
    assert '근무내용관리' in work['value']
    assert not work['value'].startswith('/html/body')


def test_submission_verifies_screen_without_retry_and_empty_tables_can_skip():
    path = Path(__file__).resolve().parents[1] / 'data' / 'federation_selectors_adjustment_analysis.json'
    steps = json.loads(path.read_text(encoding='utf-8'))['selectors']
    submit = steps['element_008']
    assert submit['action'] == 'pointer_click'
    assert submit.get('navigation_attempts', 1) == 1
    assert submit['stop_branch_on_alert'] == '퇴직특례'
    assert submit['expected_visible_xpath'] == steps['table_extract_work_hours']['value']
    assert all(step['skip_empty'] for step in steps.values() if step.get('type') == 'table_extract')
    assert '기타자료관리' in steps['element_010']['value']
    assert '.grid_menu.body.' in steps['element_010']['value']


@pytest.mark.parametrize('scope,scans', [('current', 0), ('all', 1)])
def test_current_context_wait_does_not_switch_to_other_windows(monkeypatch, scope, scans):
    runner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    runner.driver = Mock()
    runner.config = {'performance': {'context_scope': scope}}
    runner.timeout = 20
    runner._log = Mock()
    monkeypatch.setattr(module.EC, 'element_to_be_clickable', lambda locator: lambda driver: False)
    clock = iter([0, 1])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(clock))
    scan = Mock(return_value=False)
    monkeypatch.setattr(module, 'find_clickable_context', scan)
    class Wait:
        def __init__(self, *args):
            pass
        def until(self, predicate):
            assert predicate(runner.driver) is False
            raise TimeoutException()
    monkeypatch.setattr(module, 'TimedWebDriverWait', Wait)
    with pytest.raises(TimeoutException):
        runner.wait_clickable_context('submit', ('xpath', '//button'))
    assert scan.call_count == scans
    runner.driver.switch_to.window.assert_not_called()


def test_adjustment_screen_guards_reject_background_grids():
    path = Path(__file__).resolve().parents[1] / 'data' / 'federation_selectors_adjustment_analysis.json'
    config = json.loads(path.read_text(encoding='utf-8'))
    assert config['performance']['context_scope'] == 'current'
    for key in ('element_005', 'element_006'):
        assert config['selectors'][key]['navigation_attempts'] == 1
    for key in ('table_extract_007', 'table_extract_work_hours'):
        assert '.npfa100m01.' in config['selectors'][key]['value']
    staff = config['selectors']['table_extract_007']['value']
    assert not staff.startswith('/html/body')
    assert ' Grid ' in staff and '생년월일' in staff and '입력여부' in staff
