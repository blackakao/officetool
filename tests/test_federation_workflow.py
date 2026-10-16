"""구조 해석의 기존 허용 범위와 실행 시점을 보존하는 회귀 테스트."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from ui.pages import federation_workflow as workflow


def rows(*types):
    return [(str(i), {"type": kind}) for i, kind in enumerate(types)]


def test_nested_structure_and_boundaries():
    items = rows("repeat_start", "condition_start", "condition_true",
                 "repeat_start", "element", "repeat_end", "condition_false",
                 "condition_start", "condition_true", "condition_false",
                 "condition_end", "condition_end", "repeat_end")
    assert workflow.validate_workflow_structure(items) is True
    assert workflow.find_repeat_end_index(items, 0) == 12
    assert workflow.find_repeat_end_index(items, 3) == 5
    assert workflow.find_condition_indices(items, 1) == (2, 6, 11)
    assert workflow.find_condition_indices(items, 7) == (8, 9, 10)


@pytest.mark.parametrize("types,message", [
    (("condition_true",), "조건처리의 조건 없이 참 구역이 나타났습니다: 0"),
    (("condition_false",), "조건처리-참 없이 거짓 구역이 나타났습니다: 0"),
    (("repeat_end",), "반복지점 종료에 맞는 시작이 없습니다: 0"),
    (("condition_end",), "조건처리-거짓 없이 종료가 나타났습니다: 0"),
    (("repeat_start",), "시작에 맞는 종료가 없습니다: 0"),
    (("repeat_start", "condition_start", "repeat_end"),
     "반복지점 종료에 맞는 시작이 없습니다: 2"),
])
def test_save_validation_preserves_first_error(types, message):
    with pytest.raises(ValueError) as error:
        workflow.validate_workflow_structure(rows(*types))
    assert str(error.value) == message


@pytest.mark.parametrize("function,types,message", [
    (workflow.find_repeat_end_index, ("repeat_start",), "반복지점 종료를 찾을 수 없습니다: 0"),
    (workflow.find_condition_indices, ("condition_start",), "조건처리 종료를 찾을 수 없습니다: 0"),
    (workflow.find_condition_indices, ("condition_start", "condition_end"),
     "조건처리 참/거짓 구역을 찾을 수 없습니다: 0"),
])
def test_runtime_structure_errors(function, types, message):
    with pytest.raises(ValueError) as error:
        function(rows(*types), 0)
    assert str(error.value) == message


def test_runtime_keeps_last_duplicate_marker_and_does_not_prevalidate():
    items = rows("condition_start", "condition_true", "condition_true",
                 "condition_false", "condition_end")
    assert workflow.find_condition_indices(items, 0) == (2, 3, 4)
    with pytest.raises(ValueError):
        workflow.validate_workflow_structure(items)
    assert workflow.validate_workflow_structure(rows("unknown_action_type")) is True


@pytest.mark.parametrize("value,count", [("총 1,234명", 1234), ("0", 0), ("2.5", 2), ("+3", 3)])
def test_repeat_count_keeps_existing_number_parsing(value, count):
    assert workflow.parse_repeat_count("count", value) == count


@pytest.mark.parametrize("value,message", [
    ("없음", "반복 횟수를 숫자로 변환할 수 없습니다: count=없음"),
    ("-2", "반복 횟수는 0 이상이어야 합니다: count=-2"),
])
def test_repeat_count_errors(value, message):
    with pytest.raises(ValueError) as error:
        workflow.parse_repeat_count("count", value)
    assert str(error.value) == message


@pytest.mark.parametrize("action,actual,expected,number,result", [
    ("field_empty", "", "", "", True),
    ("field_not_empty", "계속", "", "", True),
    ("text_exists", "", "", "", False),
    ("equals_value", "계속", "계속", "", True),
    ("contains_value", "계속 진행", "계속", "", True),
    ("contains_value", "계속", "", "", False),
    ("equals_repeat_number", "2", "", "2", True),
    ("contains_repeat_number", "총 2명", "", "2", True),
    ("contains_repeat_number", "총 2명", "", "", False),
])
def test_condition_comparison(action, actual, expected, number, result):
    assert workflow.evaluate_condition("check", action, actual, expected, number) is result


def test_unknown_condition_action_error():
    with pytest.raises(ValueError) as error:
        workflow.evaluate_condition("check", "unknown", "", "", "")
    assert str(error.value) == "지원하지 않는 조건처리 동작입니다: check (unknown)"


def test_runtime_error_still_occurs_after_previous_step():
    from ui.pages.federation_tool import InvoiceProcessor

    runner = InvoiceProcessor.__new__(InvoiceProcessor)
    runner.run_selector_step = Mock()
    items = rows("element", "repeat_start")
    with pytest.raises(ValueError, match="반복지점 종료"):
        runner.run_workflow_items_once(items)
    runner.run_selector_step.assert_called_once_with("0", items[0][1], context=None)


def test_editor_keeps_warning_and_false_return(monkeypatch):
    from ui.pages.federation_dialogs import SelectorConfigDialog, QMessageBox

    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    owner = Mock()
    assert SelectorConfigDialog._validate_repeat_pairs(owner, rows("repeat_end")) is False
    warning.assert_called_once_with(owner, "저장 실패", "반복지점 종료에 맞는 시작이 없습니다: 0")


@pytest.mark.parametrize("filename", [
    "federation_selectors.json", "federation_selectors_invoice.json",
    "federation_selectors_long_service.json", "federation_selectors_payroll_download.json",
    "carefor_selectors_work.json",
])
def test_existing_configs_and_legacy_methods(filename):
    from ui.pages.federation_tool import InvoiceProcessor, FederationTool
    from ui.pages.carefor_tool import CareforTool

    path = Path(__file__).resolve().parents[1] / "data" / filename
    config = json.loads(path.read_text(encoding="utf-8"))
    items = list(config["selectors"].items())
    assert workflow.validate_workflow_structure(items)
    assert issubclass(CareforTool, FederationTool)
    runner = InvoiceProcessor.__new__(InvoiceProcessor)
    for index, (_, selector) in enumerate(items):
        if selector.get("type") == "repeat_start":
            assert runner.find_repeat_end_index(items, index) == workflow.find_repeat_end_index(items, index)
        elif selector.get("type") == "condition_start":
            assert runner.find_condition_indices(items, index) == workflow.find_condition_indices(items, index)
