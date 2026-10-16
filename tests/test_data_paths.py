import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

import pytest

import data_paths
from data_paths import DEFAULTS_DIRECTORY, USER_DATA_FILES, user_data_path, user_image_directory


@pytest.mark.parametrize("name", sorted(USER_DATA_FILES))
def test_first_run_copies_default_and_round_trips_without_changing_default(tmp_path, name):
    default = DEFAULTS_DIRECTORY / name
    original = default.read_bytes()
    path = user_data_path(name, root=tmp_path)
    assert path == tmp_path / "data" / "runtime" / name
    assert path.read_bytes() == original
    assert path != default
    value = json.loads(original)
    if isinstance(value, list):
        value.append({"test": "사용자 값"})
    else:
        value["test"] = "사용자 값"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    assert json.loads(user_data_path(name, root=tmp_path).read_text(encoding="utf-8")) == value
    assert default.read_bytes() == original


@pytest.mark.parametrize("name", sorted(USER_DATA_FILES))
def test_existing_installation_preserves_exact_bytes_and_runtime_wins(tmp_path, name):
    legacy = tmp_path / "data" / name
    legacy.parent.mkdir()
    content = b'{ "custom": "legacy", "unknown_field": 1 }\r\n'
    legacy.write_bytes(content)
    path = user_data_path(name, root=tmp_path)
    assert path.read_bytes() == content
    path.write_text('{"edited": true}', encoding="utf-8")
    assert user_data_path(name, root=tmp_path).read_text(encoding="utf-8") == '{"edited": true}'
    assert legacy.read_bytes() == content


def test_invalid_legacy_is_preserved_instead_of_reset(tmp_path):
    legacy = tmp_path / "data" / "memos.json"
    legacy.parent.mkdir()
    legacy.write_bytes(b'broken json')
    assert user_data_path(legacy.name, root=tmp_path).read_bytes() == b'broken json'


def test_unreadable_legacy_does_not_fall_back_to_default(tmp_path, monkeypatch):
    legacy = tmp_path / "data" / "memos.json"
    legacy.parent.mkdir()
    legacy.write_text('{}', encoding="utf-8")
    read_bytes = Path.read_bytes

    def read(path):
        if path == legacy:
            raise PermissionError("locked")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(PermissionError):
        user_data_path(legacy.name, root=tmp_path)
    assert not (tmp_path / "data/runtime/memos.json").exists()
    assert not list((tmp_path / "data/runtime").glob("*.tmp"))


def test_parallel_initialization_publishes_complete_file(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda _: user_data_path("memos.json", root=tmp_path), range(24)))
    assert all(path.read_bytes() == (DEFAULTS_DIRECTORY / "memos.json").read_bytes() for path in paths)
    assert not list(paths[0].parent.glob("*.tmp"))


def test_legacy_image_paths_remain_valid(tmp_path):
    old = tmp_path / "data/branch_images/stamp.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"legacy image")
    path = user_image_directory(root=tmp_path)
    assert path == tmp_path / "data/runtime/branch_images"
    assert path.is_dir()
    assert old.read_bytes() == b"legacy image"


def test_project_settings_cannot_be_redirected(tmp_path):
    for name in ["federation_tasks.json", "../branches.json", "excel_templates/test.json"]:
        with pytest.raises(ValueError):
            user_data_path(name, root=tmp_path)


def test_runtime_edits_leave_git_clean_and_templates_visible(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True, encoding="utf-8").strip()

    (tmp_path / ".gitignore").write_bytes((data_paths.PROJECT_ROOT / ".gitignore").read_bytes())
    git("init")
    git("add", ".gitignore")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
    for name in USER_DATA_FILES:
        path = user_data_path(name, root=tmp_path)
        path.write_text('{"modified": true}', encoding="utf-8")
    (user_image_directory(root=tmp_path) / "new.png").write_bytes(b"image")
    assert git("status", "--porcelain") == ""
    template = tmp_path / "data/excel_templates/test.json"
    template.parent.mkdir()
    template.write_text('{}', encoding="utf-8")
    assert "data/" in git("status", "--porcelain")


def test_excel_lookup_uses_runtime_after_migration(tmp_path, monkeypatch):
    from excel_data_sort import branch_lookup

    monkeypatch.setattr(data_paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(branch_lookup, "DATA_DIRECTORY", None)
    path = user_data_path("branches.json")
    path.write_text('[{"branch_name": "테스트"}]', encoding="utf-8")
    assert branch_lookup.load_branch_data()[0] == [{"branch_name": "테스트"}]


@pytest.mark.parametrize("existing", [False, True])
def test_main_window_starts_with_isolated_user_data(tmp_path, monkeypatch, existing):
    import sys
    import main
    from PySide6.QtWidgets import QApplication
    from ui.pages import logging_util

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(data_paths, "PROJECT_ROOT", tmp_path)
    # Redirect project templates/logs too, so startup cannot write real data.
    for name, module in list(sys.modules.items()):
        if name.startswith("ui.pages.") and getattr(module, "__file__", None):
            monkeypatch.setattr(module, "__file__", str(tmp_path / "ui/pages" / Path(module.__file__).name))
    (tmp_path / "data").mkdir()
    for folder in ("dataset/files", "dataset/labels"):
        (tmp_path / folder).mkdir(parents=True)
    monkeypatch.setattr(logging_util, "LOG_FILE", tmp_path / "data/login.log")
    monkeypatch.setattr(logging_util, "LOG_SETTINGS_FILE", user_data_path("log_settings.json"))
    from ui.pages import login_log
    monkeypatch.setattr(login_log, "LOG_FILE", logging_util.LOG_FILE)
    legacy = tmp_path / "data/memos.json"
    original = '{"version": 2, "tags": [], "tag_colors": {}, "memos": []}\r\n'
    if existing:
        legacy.write_text(original, encoding="utf-8", newline="")
    window = main.MainWindow()
    try:
        assert window.branch_page.data_file == tmp_path / "data/runtime/branches.json"
        assert window.monthly_work_check_page.data_file == tmp_path / "data/runtime/monthly_work_check.json"
        assert window.memo_page.data_file == tmp_path / "data/runtime/memos.json"
        assert window.incomplete_task_page.data_file == tmp_path / "data/runtime/incomplete_tasks.json"
        if existing:
            assert legacy.read_bytes() == original.encode("utf-8")
            assert window.memo_page.data_file.read_bytes() == legacy.read_bytes()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
