from pathlib import Path
from unittest.mock import patch

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ui.pages.document_tool import ContentControlDialog


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
