from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from ui.pages import federation_tool as module
from ui.pages import login_tool as login_module


@pytest.mark.parametrize('background', [False, True])
def test_login_creates_headless_browser_before_authentication(tmp_path, monkeypatch, background):
    monkeypatch.setattr(login_module.Path, 'home', lambda: tmp_path)
    manager = Mock()
    manager.install.return_value = str(tmp_path / 'chromedriver.exe')
    monkeypatch.setattr(login_module, 'ChromeDriverManager', lambda: manager)
    create = Mock()
    monkeypatch.setattr(login_module.webdriver, 'Chrome', create)
    login = login_module.BaseLoginThread({}, 'about:blank', profile_path=tmp_path / 'profile')
    login.background_mode = background
    login._create_driver()
    options = create.call_args.kwargs['options']
    assert ('--headless=new' in options.arguments) == background
    assert ('--start-maximized' in options.arguments) != background
    if background:
        assert '--window-size=1920,1080' in options.arguments
        assert f'--user-data-dir={tmp_path / "profile_headless"}' in options.arguments
    else:
        assert f'--user-data-dir={tmp_path / "profile"}' in options.arguments


def test_background_setting_is_opt_in_and_saved_per_task(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, '__file__', str(tmp_path / 'ui' / 'pages' / 'federation_tool.py'))
    page = module.FederationTool()
    page.select_task('invoice')
    assert not page.background_check.isChecked()
    page.background_check.setChecked(True)
    page.select_task('long_service')
    assert not page.background_check.isChecked()
    page.select_task('invoice')
    assert page.background_check.isChecked()
    page.close()
    assert app is not None


def test_background_extraction_never_opens_external_excel(monkeypatch):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.background_mode = True
    owner.extracted_files_to_open = [Path('result.xlsx')]
    owner._log = Mock()
    opened = Mock()
    monkeypatch.setattr(module.os, 'startfile', opened)
    owner.open_extracted_files()
    opened.assert_not_called()
    assert owner.extracted_files_to_open == []


@pytest.mark.parametrize('background', [False, True])
def test_single_background_run_closes_browser_after_macro(tmp_path, monkeypatch, background):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, '__file__', str(tmp_path / 'ui' / 'pages' / 'federation_tool.py'))
    page = module.FederationTool()
    page._log = Mock()
    page._watch_browser = Mock()
    driver = Mock()
    driver.window_handles = []

    class Process(QThread):
        status_signal = Signal(str)
        finished_signal = Signal(str, bool)

        def __init__(self, *args, **kwargs):
            super().__init__()

        def start(self):
            assert self.background_mode == background
            self.close_browser_on_complete = True
            self.finished_signal.emit('done', True)

    monkeypatch.setattr(module, 'ClaimProcessThread', Process)
    login = SimpleNamespace(driver=driver, branch={}, background_mode=background, macro_start_number=1)
    page._on_longterm_finished('ok', True, login, 'invoice', tmp_path / 'macro.json')
    driver.quit.assert_called_once()
    page._watch_browser.assert_not_called()
    page.close()
    assert app is not None
