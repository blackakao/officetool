from ui.pages.hwp_document_tool import HwpAutomation


def test_hwp_field_names_preserve_duplicates_after_removing_suffixes():
    automation = HwpAutomation()

    class FakeHwp:
        @staticmethod
        def GetFieldList(_field_type, _option):
            return "이름{{0}}\x02주소\x02이름{{1}}"

    automation.hwp = FakeHwp()

    assert automation.field_names() == ["이름", "주소", "이름"]


def test_hwp_base_field_name_only_removes_numeric_suffix():
    assert HwpAutomation._base_field_name("계약자{{12}}") == "계약자"
    assert HwpAutomation._base_field_name("계약자{임의}") == "계약자{임의}"


def test_hwp_image_uses_explicit_millimeter_size(tmp_path):
    image_path = tmp_path / "sign.png"
    image_path.write_bytes(b"image")
    automation = HwpAutomation()
    calls = []

    class FakeHwp:
        @staticmethod
        def MoveToField(*_args):
            return True

        @staticmethod
        def InsertPicture(*args):
            calls.append(args)

    automation.hwp = FakeHwp()
    automation.put_image("Sign", {
        "type": "image", "path": str(image_path), "width": 3, "height": 5,
    })

    assert calls == [(str(image_path.resolve()), True, 1, False, False, 0, 3.0, 5.0)]
