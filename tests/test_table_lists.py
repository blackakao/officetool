from types import SimpleNamespace

from ui.pages.document_tool import ContentControlDialog, FIELD_TYPES, table_list_id, table_list_options, table_list_type
from ui.pages.table_list_page import normalize_table_data, reordered_values, table_item_count, table_values


def test_table_values_flattens_legacy_rows():
    table = {"cells": [["요양보호사"], ["간호사", "면허직"]]}
    assert table_values(table) == ["요양보호사", "간호사", "면허직"]
    assert table_item_count(table) == 3


def test_table_cells_become_document_select_options():
    table = {"cells": [["요양보호사", "직접인력"], ["", ""], ["간호사", "면허직"]]}
    assert table_list_options(table) == ["요양보호사", "직접인력", "간호사", "면허직"]


def test_table_list_type_round_trip():
    field_type = table_list_type("workers")
    assert field_type == "table_list:workers"
    assert table_list_id(field_type) == "workers"
    assert table_list_id("text") == ""


def test_table_list_is_a_single_field_type():
    assert FIELD_TYPES["table_list"] == "테이블 목록"


def test_branch_lists_are_selected_outside_field_types():
    assert "branch_select" not in FIELD_TYPES
    assert "branch_select_2" not in FIELD_TYPES
    assert FIELD_TYPES["branch_value"] == "지점의 값"


def test_legacy_branch_selector_becomes_branch_name_value():
    dialog = SimpleNamespace(settings={"fields": {"기관명": {
        "type": "branch_select",
        "branch_name": "분당점",
    }}})
    ContentControlDialog._migrate_branch_source_settings(dialog)
    assert dialog.settings["branches"] == {"branch_select": "분당점"}
    assert dialog.settings["fields"]["기관명"] == {
        "type": "branch_value",
        "source_field": "branch_select",
        "branch_value_key": "branch_name",
    }


def test_table_values_can_be_reordered_without_data_loss():
    assert reordered_values(["A", "B", "C", "D"], 1, 4) == (["A", "C", "D", "B"], 3)
    assert reordered_values(["A", "B", "C", "D"], 3, 1) == (["A", "D", "B", "C"], 1)


def test_invalid_table_storage_is_normalized():
    assert normalize_table_data(None) == {"version": 1, "tables": []}
