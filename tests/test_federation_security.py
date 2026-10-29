from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException

from ui.pages import login_tool as login
from ui.pages import federation_tool as module


def test_anysign_install_failure_is_an_environment_error_and_closes_browser():
    owner = login.BaseLoginThread({}, 'about:blank')
    driver = Mock()
    owner.background_mode = True
    owner._create_driver = Mock(return_value=driver)
    owner.perform_login = Mock(side_effect=UnexpectedAlertPresentException(
        'blocked', alert_text='[AnySign for PC] 인증 보안 프로그램 설치가 필요합니다.'))
    results = []
    owner.finished_signal.connect(lambda message, ok: results.append((message, ok)))
    owner.run()
    assert owner.environment_error
    assert results and not results[0][1]
    assert '백그라운드' in results[0][0] and '반복 이동하지 않고 중단' in results[0][0]
    driver.quit.assert_called_once()


@pytest.mark.parametrize('background', [False, True])
def test_longterm_preserves_existing_browser_permissions(background):
    owner = login.LongtermLoginThread({})
    owner.background_mode = background
    owner.driver = Mock()
    owner.prepare_browser()
    owner.driver.execute_cdp_cmd.assert_not_called()


@pytest.mark.parametrize('macro', [False, True])
def test_standalone_login_keeps_legacy_completion_check(monkeypatch, macro):
    owner = login.LongtermLoginThread({})
    owner.driver = Mock()
    owner.require_work_window = macro
    owner._wait_and_click = Mock()
    owner._wait_for_work_window = Mock()
    monkeypatch.setattr(login.webdriver, 'ActionChains', Mock())
    waits = []
    class Wait:
        def __init__(self, driver, timeout):
            waits.append(timeout)
        def until(self, condition):
            raise TimeoutException()
    monkeypatch.setattr(login, 'WebDriverWait', Wait)
    owner.perform_login(Mock())
    assert waits == ([] if macro else [2])
    assert owner._wait_for_work_window.call_count == int(macro)


@pytest.mark.parametrize('reuse_window', [False, True])
def test_login_waits_for_actual_work_window_without_repeated_parent_switch(monkeypatch, reuse_window):
    owner = login.LongtermLoginThread({})
    polls = [0]
    current = ['parent']
    switched = []
    class Driver:
        window_handles = ['parent'] if reuse_window else ['parent', 'work']

        @property
        def current_window_handle(self):
            return current[0]

        @property
        def current_url(self):
            if polls[0] >= 2 and (reuse_window or current[0] == 'work'):
                return 'https://www.longtermcare.or.kr/npbs/xui/manage.html'
            return 'about:blank'

        def find_elements(self, *args):
            return [Mock()] if polls[0] >= 3 else []

    owner.driver = Driver()
    owner.driver.switch_to = Mock()
    def switch(handle):
        switched.append(handle)
        current[0] = handle
    owner.driver.switch_to.window.side_effect = switch

    class Wait:
        def __init__(self, *args, **kwargs):
            pass
        def until(self, condition, *args):
            for count in range(1, 5):
                polls[0] = count
                if condition(owner.driver):
                    return True
            raise TimeoutException()
    monkeypatch.setattr(login, 'WebDriverWait', Wait)
    owner._wait_for_work_window()
    assert polls[0] == 3
    assert switched == ([] if reuse_window else ['work'])
    assert owner.driver._longterm_work_handle == ('parent' if reuse_window else 'work')


@pytest.mark.parametrize('already_open', [True, False])
def test_hover_does_not_toggle_an_already_open_submenu(monkeypatch, already_open):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.config = {'selectors': {'menu': {'action': 'hover_click', 'expected_visible_xpath': '//submenu'}}}
    owner.driver = Mock()
    owner._log = Mock()
    owner.click_element = Mock()
    owner.sleep = Mock()
    owner.timeout = 20
    owner.timeouts = {'short': 3}
    waits = []
    class Wait:
        def __init__(self, *args):
            waits.append(1)
        def until(self, condition):
            if not already_open and len(waits) == 1:
                raise TimeoutException()
            return True
    monkeypatch.setattr(module, 'TimedWebDriverWait', Wait)
    monkeypatch.setattr(module, 'ActionChains', Mock())
    button = Mock()
    owner.perform_action('menu', button)
    assert owner.click_element.call_count == (0 if already_open else 1)
    owner.sleep.assert_not_called()
