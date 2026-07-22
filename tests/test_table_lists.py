from ui.pages.document_tool import table_list_id, table_list_options, table_list_type
from ui.pages.table_list_page import normalize_table_data, table_dimensions


def test_table_dimensions_uses_largest_row():
    table = {"cells": [["요양보호사"], ["간호사", "면허직"]]}
    assert table_dimensions(table) == (2, 2)


def test_table_rows_become_document_select_options():
    table = {"cells": [["요양보호사", "직접인력"], ["", ""], ["간호사", "면허직"]]}
    assert table_list_options(table) == ["요양보호사 / 직접인력", "간호사 / 면허직"]


def test_table_list_type_round_trip():
    field_type = table_list_type("workers")
    assert field_type == "table_list:workers"
    assert table_list_id(field_type) == "workers"
    assert table_list_id("text") == ""


def test_invalid_table_storage_is_normalized():
    assert normalize_table_data(None) == {"version": 1, "tables": []}
