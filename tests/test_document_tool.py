from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ui.pages.document_tool import (
    ContentControlDialog,
    DocumentTool,
    EXCEL_BRANCH_FIELD,
    branch_child_type_options,
    branch_control_parts,
    calculate_number,
    control_structure_parts,
    format_number,
    group_control_parts,
    resolve_calculated_amounts,
)


def test_number_calculation_supports_all_four_operations():
    assert format_number(calculate_number("1,200", "add", "50")) == "1250"
    assert format_number(calculate_number("10", "subtract", "12.5")) == "-2.5"
    assert format_number(calculate_number("2.5", "multiply", "4")) == "10"
    assert format_number(calculate_number("9", "divide", "4")) == "2.25"
    assert calculate_number("9", "divide", "0") is None


def test_resolve_calculated_amounts_supports_chains_and_comma_formatting():
    settings = {"fields": {
        "base": {"type": "amount"},
        "doubled": {
            "type": "amount", "amount_default_type": "field_calculation",
            "source_amount_field": "base", "amount_operator": "multiply",
            "amount_operand": "2", "use_comma": False,
        },
        "result": {
            "type": "amount", "amount_default_type": "field_calculation",
            "source_amount_field": "doubled", "amount_operator": "add",
            "amount_operand": "500", "use_comma": True,
        },
    }}
    values = resolve_calculated_amounts(settings, {"base": "1,000"})
    assert values["doubled"] == "2000"
    assert values["result"] == "2,500"


def test_resolve_calculated_amounts_accepts_numeric_branch_value_source():
    settings = {"fields": {
        "식대 단가": {"type": "branch_value"},
        "식대 숫자금액 3끼": {
            "type": "amount", "amount_default_type": "field_calculation",
            "source_amount_field": "식대 단가", "amount_operator": "multiply",
            "amount_operand": "3", "use_comma": True,
        },
    }}

    values = resolve_calculated_amounts(settings, {"식대 단가": "6,200"})

    assert values["식대 숫자금액 3끼"] == "18,600"


def test_document_specific_settings_keep_field_presets():
    settings = {
        "documents": {
            "contract.hwp": {
                "fields": {"job": {"type": "text"}},
                "field_presets": [{"name": "사회복지사", "values": {"job": "사회복지사"}}],
            }
        }
    }
    selected = ContentControlDialog.settings_for_file(settings, Path("contract.hwp"))
    assert selected["field_presets"][0]["values"]["job"] == "사회복지사"


def test_branch_control_name_parsing():
    assert branch_control_parts("분기_시설종류_요양원") == ("시설종류", "요양원")
    assert branch_control_parts("분기_시설종류_주야간_보호") == ("시설종류", "주야간_보호")
    assert branch_control_parts("시설종류_요양원") is None
    assert branch_control_parts("분기__요양원") is None


def test_branch_child_cannot_select_branch_type():
    option_keys = [key for key, _label in branch_child_type_options()]
    assert "branch" not in option_keys
    assert "group" not in option_keys
    assert "text" in option_keys


def test_group_control_name_parsing():
    assert group_control_parts("그룹_인적사항_이름") == ("인적사항", "이름")
    assert group_control_parts("분기_구분_A_그룹_인적사항_이름") is None


def test_nested_structure_preserves_written_parent_order():
    assert control_structure_parts("분기_서식_A_그룹_인적사항_이름") == [
        ("branch", "서식", "A"),
        ("group", "인적사항", "이름"),
    ]
    assert control_structure_parts("그룹_인적사항_주소_분기_주소형태_도로명") == [
        ("group", "인적사항", "주소"),
        ("branch", "주소형태", "도로명"),
    ]


def test_branch_generation_only_updates_selected_control():
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    combo = lambda value: SimpleNamespace(currentData=lambda: value)
    dialog.generate_widgets = {
        "분기_변경전_대표자": {
            "type_combo": combo("branch"),
            "branch_option_combo": combo("분기_변경전_시설명칭"),
            "branch_members": [
                "분기_변경전_대표자",
                "분기_변경전_시설명칭",
                "분기_변경전_시설소재지",
            ],
        }
    }
    dialog._field_value = lambda field_key: f"입력:{field_key}"

    assert dialog._generation_values() == {
        "분기_변경전_시설명칭": "입력:분기_변경전_시설명칭"
    }


def test_branch_option_can_activate_a_nested_group_of_fields():
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    combo = lambda value: SimpleNamespace(currentData=lambda: value)
    members = [
        "분기_서식_A_그룹_인적사항_이름",
        "분기_서식_A_그룹_인적사항_주소",
    ]
    dialog.generate_widgets = {
        members[0]: {
            "type_combo": combo("branch"),
            "branch_option_combo": combo("A"),
            "branch_option_members": {"A": members},
        }
    }
    dialog._field_value = lambda field_key: f"입력:{field_key}"

    assert dialog._generation_values() == {
        member: f"입력:{member}" for member in members
    }


def test_inline_image_control_contains_run_instead_of_nested_paragraph():
    paragraph = OxmlElement("w:p")
    content_control = OxmlElement("w:sdt")
    content = OxmlElement("w:sdtContent")
    content_control.append(content)
    paragraph.append(content_control)

    value = {
        "type": "image",
        "path": str(Path(__file__).resolve()),
        "width": 15,
        "height": 15,
    }

    with patch("ui.pages.document_tool.Run.add_picture") as add_picture:
        ContentControlDialog._set_sdt_image(object(), object(), content, value)

    assert [child.tag for child in content] == [qn("w:r")]
    add_picture.assert_called_once()


def test_folder_image_value_matches_filename_without_extension(tmp_path):
    matching_image = tmp_path / "홍길동.PNG"
    matching_image.write_bytes(b"image")
    (tmp_path / "홍길동.txt").write_text("not an image", encoding="utf-8")

    value = ContentControlDialog._folder_image_value(
        {"folder_path": str(tmp_path)},
        "홍길동",
    )

    assert value == {
        "type": "image",
        "path": str(matching_image),
        "width": 30,
        "height": 30,
    }


def test_folder_image_value_returns_empty_when_image_is_missing(tmp_path):
    value = ContentControlDialog._folder_image_value(
        {"folder_path": str(tmp_path)},
        "없는 이름",
    )

    assert value == ""


def test_folder_image_value_uses_configured_size(tmp_path):
    matching_image = tmp_path / "김영희.jpg"
    matching_image.write_bytes(b"image")

    value = ContentControlDialog._folder_image_value(
        {"folder_path": str(tmp_path), "width": 45, "height": 20},
        "김영희",
    )

    assert value["width"] == 45
    assert value["height"] == 20


def test_prepare_excel_row_converts_image_field_path(tmp_path):
    image_path = tmp_path / "stamp.png"
    image_path.write_bytes(b"image")
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    dialog.settings = {
        "fields": {
            "image_test": {
                "type": "branch_value",
                "branch_value_key": "custom_법인인감",
            }
        }
    }
    dialog.branch_fields = [
        {"key": "custom_법인인감", "label": "법인인감", "type": "image"}
    ]
    dialog.root = tmp_path
    dialog.field_widgets = {}

    values = dialog._prepare_excel_row_values(
        {"image_test": str(image_path)},
        row_number=2,
    )

    assert values["image_test"] == {
        "type": "image",
        "path": str(image_path),
        "width": 30,
        "height": 30,
    }


def test_prepare_excel_row_keeps_text_field_as_text(tmp_path):
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    dialog.settings = {"fields": {"memo": {"type": "text"}}}
    dialog.branch_fields = []
    dialog.root = tmp_path
    dialog.field_widgets = {}

    values = dialog._prepare_excel_row_values({"memo": "C:\\image.png"}, row_number=2)

    assert values["memo"] == "C:\\image.png"


def test_prepare_excel_row_rejects_missing_image(tmp_path):
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    dialog.settings = {
        "fields": {
            "seal": {
                "type": "branch_value",
                "branch_value_key": "custom_법인인감",
            }
        }
    }
    dialog.branch_fields = [{"key": "custom_법인인감", "type": "image"}]
    dialog.root = tmp_path
    dialog.field_widgets = {}

    try:
        dialog._prepare_excel_row_values({"seal": "missing.png"}, row_number=3)
    except ValueError as error:
        assert "3행 seal" in str(error)
        assert "이미지 파일을 찾을 수 없습니다" in str(error)
    else:
        raise AssertionError("존재하지 않는 이미지 경로는 오류여야 합니다.")


def test_excel_fields_put_branch_first_and_exclude_automatic_values():
    tool = DocumentTool.__new__(DocumentTool)
    settings = {"fields": {
        "name": {"type": "text"},
        "owner": {"type": "branch_value", "branch_value_key": "owner_name"},
        "stamp": {"type": "branch_value", "branch_value_key": "custom_stamp"},
        "folder_image": {"type": "folder", "value_field": "name"},
    }}
    fields = tool._configured_field_names(Path("contract.hwp"), settings)
    assert fields == [EXCEL_BRANCH_FIELD, "name"]


def test_excel_row_resolves_branch_text_and_image_without_excel_paths(tmp_path):
    stamp = tmp_path / "stamp.png"
    stamp.write_bytes(b"image")
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    dialog.settings = {"fields": {
        "owner": {"type": "branch_value", "branch_value_key": "owner_name"},
        "stamp": {"type": "branch_value", "branch_value_key": "custom_stamp"},
    }}
    dialog.branches = [{
        "branch_name": "서울점", "owner_name": "홍길동",
        "custom_fields": {"custom_stamp": {"path": str(stamp), "width": 20, "height": 15}},
    }]
    dialog.branch_fields = [{"key": "custom_stamp", "type": "image"}]
    dialog.root = tmp_path
    dialog.field_widgets = {}

    values = dialog._prepare_excel_row_values({EXCEL_BRANCH_FIELD: "서울점"}, row_number=2)
    assert values["owner"] == "홍길동"
    assert values["stamp"] == {
        "type": "image", "path": str(stamp), "width": 20, "height": 15,
    }


def test_recent_generation_history_keeps_only_three_entries(tmp_path):
    dialog = ContentControlDialog.__new__(ContentControlDialog)
    dialog.root = tmp_path
    dialog.file_path = tmp_path / "양식.docx"
    dialog.settings_filename = "document_field_settings.json"
    dialog.branch_combos = {}

    for number in range(4):
        dialog._save_recent_generation(f"문서 {number}", {"이름": str(number)})

    entries = dialog._recent_generations()
    assert [entry["title"] for entry in entries] == ["문서 3", "문서 2", "문서 1"]
