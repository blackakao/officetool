from ui.pages.hwp_document_tool import HwpAutomation


def test_hwp_field_names_remove_duplicate_suffixes():
    automation = HwpAutomation()

    class FakeHwp:
        @staticmethod
        def GetFieldList(_field_type, _option):
            return "이름{{0}}\x02주소\x02이름{{1}}"

    automation.hwp = FakeHwp()

    assert automation.field_names() == ["이름", "주소"]


def test_hwp_base_field_name_only_removes_numeric_suffix():
    assert HwpAutomation._base_field_name("계약자{{12}}") == "계약자"
    assert HwpAutomation._base_field_name("계약자{임의}") == "계약자{임의}"
