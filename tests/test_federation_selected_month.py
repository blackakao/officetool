from datetime import date
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication
from selenium.common.exceptions import InvalidSessionIdException, TimeoutException

from ui.pages import federation_config as config
from ui.pages import federation_tool as module
from ui.pages.federation_workflow import validate_workflow_structure


@pytest.mark.parametrize('today,expected', [
    (date(2026, 10, 29), '2026-09'), (date(2026, 1, 1), '2025-12'),
    (date(2024, 3, 31), '2024-02'),
])
def test_default_selected_month_is_previous_calendar_month(today, expected):
    assert config.selected_month_value(today=today) == expected


def test_selected_month_format_and_runtime_input():
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.config = {'selected_month': '2026-09'}
    assert owner.runtime_text_value('{selected_month}') == '2026-09'
    assert owner.runtime_text_value('{selected_month}/{repeat_value}', {'repeat_value': '3'}) == '2026-09/3'
    for value in ('2026-9', '2026-13', '2026-00'):
        with pytest.raises(ValueError):
            config.selected_month_value(value)


def test_calendar_toolbar_defaults_and_persists_month_per_task(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, '__file__', str(tmp_path / 'ui' / 'pages' / 'federation_tool.py'))
    monkeypatch.setattr(module, 'selected_month_value', lambda value=None: config.selected_month_value(value, date(2026, 10, 29)))
    page = module.FederationTool()
    page.select_task('invoice')
    assert page.selected_month_edit.calendarPopup()
    assert page.selected_month_edit.displayFormat() == 'yyyy-MM'
    assert page.selected_month_edit.date().toString('yyyy-MM') == '2026-09'
    page.selected_month_edit.setDate(QDate(2025, 12, 25))
    saved = json.loads(page._selector_config_path('invoice').read_text(encoding='utf-8'))
    assert saved['selected_month'] == '2025-12'
    page.select_task('long_service')
    assert page.selected_month_edit.date().toString('yyyy-MM') == '2026-09'
    page.select_task('invoice')
    assert page.selected_month_edit.date().toString('yyyy-MM') == '2025-12'
    assert page.validate_run_range()
    assert saved.get('start_number', 1) == 1
    page.close()
    assert app is not None


@pytest.mark.parametrize('available,count', [(True, 7), (False, 4)])
def test_adjustment_detail_branch_completes_with_or_without_details(available, count):
    path = Path(__file__).resolve().parents[1] / 'data' / 'federation_selectors_adjustment_analysis.json'
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.config = json.loads(path.read_text(encoding='utf-8'))
    validate_workflow_structure(list(owner.config['selectors'].items()))
    owner._log = Mock()
    owner.condition_result = Mock(return_value=available)
    executed = []
    owner.run_selector_step = lambda key, selector, context=None: executed.append(selector)
    owner.open_extracted_files = Mock()
    owner.run_configured_workflow()
    assert sum(step['type'] == 'table_extract' for step in executed) == count
    assert any(step['label'] == '상세보기' for step in executed) == available
    owner.open_extracted_files.assert_called_once()
    month = next(step for step in executed if step['label'] == '급여기준연월')
    assert month['expected_value'] == '{selected_month}'


@pytest.mark.parametrize('displayed,enabled,expected', [(True, True, True), (False, True, False), (True, False, False)])
def test_detail_condition_checks_clickability_not_text(monkeypatch, displayed, enabled, expected):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = Mock()
    owner.timeout = 20
    owner.timeouts = {}
    owner._log = Mock()
    target = Mock()
    target.text = ''
    target.is_displayed.return_value = displayed
    target.is_enabled.return_value = enabled
    owner.driver.find_element.return_value = target

    class ImmediateWait:
        def __init__(self, *args):
            pass

        def until(self, condition):
            result = condition(owner.driver)
            if not result:
                raise TimeoutException()
            return result

    monkeypatch.setattr(module, 'TimedWebDriverWait', ImmediateWait)
    selector = {'action': 'element_clickable', 'by': 'xpath', 'value': '//details'}
    assert owner._condition_result('detail', selector) == expected
    owner.driver.find_element.side_effect = InvalidSessionIdException('closed')
    with pytest.raises(InvalidSessionIdException):
        owner._condition_result('detail', selector)
