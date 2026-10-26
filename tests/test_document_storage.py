from unittest.mock import Mock

from ui.pages import document_tool
from ui.pages.document_storage import unified_document_folder
from ui.pages.hwp_document_tool import HwpContentControlDialog


def test_migration_preserves_bytes_settings_keys_and_user_edits(tmp_path):
    legacy = tmp_path / "document_hwp"
    legacy.mkdir()
    source = legacy / "contract.hwp"
    source.write_bytes(b"original hwp")
    dialog = HwpContentControlDialog.__new__(HwpContentControlDialog)
    dialog.file_path = source
    history_key = dialog._history_key()
    folder = unified_document_folder(tmp_path)
    destination = folder / source.name
    assert destination.read_bytes() == source.read_bytes()
    dialog.file_path = destination
    assert dialog._history_key() == history_key
    destination.write_bytes(b"user edit")
    unified_document_folder(tmp_path)
    assert destination.read_bytes() == b"user edit"
    destination.unlink()
    unified_document_folder(tmp_path)
    assert not destination.exists()
    assert source.read_bytes() == b"original hwp"


def test_migration_preserves_conflicting_results_and_unified_template(tmp_path):
    legacy = tmp_path / "document_hwp"
    folder = tmp_path / "document"
    for base in (legacy, folder):
        (base / "maked").mkdir(parents=True)
    (legacy / "contract.hwp").write_bytes(b"legacy")
    (folder / "contract.hwp").write_bytes(b"current")
    (legacy / "maked" / "result.pdf").write_bytes(b"legacy pdf")
    (folder / "maked" / "result.pdf").write_bytes(b"current pdf")
    unified_document_folder(tmp_path)
    unified_document_folder(tmp_path)
    assert (folder / "contract.hwp").read_bytes() == b"current"
    assert (legacy / "contract.hwp").read_bytes() == b"legacy"
    assert (folder / "maked" / "result.pdf").read_bytes() == b"current pdf"
    assert (folder / "maked" / "result(1).pdf").read_bytes() == b"legacy pdf"
    assert len(list((folder / "maked").iterdir())) == 2


def test_folder_opens_directly_and_new_hwp_is_listed(tmp_path, monkeypatch):
    tool = document_tool.UnifiedDocumentTool.__new__(document_tool.UnifiedDocumentTool)
    tool.document_folder = unified_document_folder(tmp_path)
    source = tool.document_folder / "new.HWP"
    source.touch()
    opened = Mock(return_value=True)
    choose = Mock(side_effect=AssertionError("Must not ask for a folder"))
    monkeypatch.setattr(document_tool.QDesktopServices, "openUrl", opened)
    monkeypatch.setattr(document_tool.QInputDialog, "getItem", choose)
    tool.open_document_folder()
    assert opened.call_args.args[0].toLocalFile() == str(tool.document_folder).replace("\\", "/")
    assert tool._document_files() == [source]
    choose.assert_not_called()
