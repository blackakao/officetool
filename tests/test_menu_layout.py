import copy
import json
import os

import pytest

from menu_layout import load_layout, reconcile_groups, save_layout


@pytest.fixture
def defaults():
    return [dict(id='tools', name='도구', pages=['login', 'document']),
            dict(id='settings', name='설정', pages=['manager'])]


def test_new_pages_join_renamed_group_without_resetting_placement(tmp_path, defaults):
    saved = [dict(id='tools', name='자주 쓰는 메뉴', pages=['document']),
             dict(id='custom', name='내 메뉴', pages=['login', 'manager'])]
    path = tmp_path / 'menu.json'
    save_layout(path, saved)
    defaults[0]['pages'].append('new_page')
    loaded = load_layout(path, defaults)
    assert loaded[0] == dict(id='tools', name='자주 쓰는 메뉴', pages=['document', 'new_page'])
    assert loaded[1] == saved[1]
    assert loaded == reconcile_groups(loaded, defaults)


def test_deleted_default_group_returns_only_for_new_pages(defaults):
    saved = [dict(id='custom', name='통합', pages=['login', 'document', 'manager'])]
    assert reconcile_groups(saved, defaults) == saved
    defaults[1]['pages'].append('new')
    assert reconcile_groups(saved, defaults)[1] == dict(id='settings', name='설정', pages=['new'])


@pytest.mark.parametrize('data', [None, {}, {'version': 1}, {'version': 2, 'groups': []},
                                     {'version': 1, 'groups': {}},
                                     {'version': 1, 'groups': [dict(id='a', name='', pages=[])]}])
def test_invalid_settings_preserved(tmp_path, defaults, data):
    path = tmp_path / 'menu.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(ValueError):
        load_layout(path, defaults)
    assert path.read_bytes() == original


def test_failed_save_preserves_previous_file(tmp_path, defaults, monkeypatch):
    path = tmp_path / 'menu.json'
    save_layout(path, defaults)
    original = path.read_bytes()
    def fail(*args):
        raise PermissionError('locked')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(PermissionError):
        save_layout(path, defaults)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))


@pytest.fixture
def app():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_management_edit_save_reload_keeps_open_tabs(app, monkeypatch, tmp_path):
    import data_paths
    import main
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QInputDialog, QLineEdit, QWidget
    monkeypatch.setattr(data_paths, 'PROJECT_ROOT', tmp_path)
    for name in ['BranchPage', 'LoginTool', 'LoginLogPage', 'UnifiedDocumentTool',
                 'TableListPage', 'FederationTool', 'CareforTool', 'LaborCostRatioPage',
                 'ServiceFeePage', 'AnnualLeavePage', 'MonthlyWorkCheckPage', 'MemoPage',
                 'IncompleteTaskPage', 'BranchTaskSettingsPage', 'AttendanceAnalysisPage',
                 'ExcelDataSortPage', 'CommitteeMinutesPage', 'BusinessPlanPage', 'BudgetPage']:
        monkeypatch.setattr(main, name, QWidget)
    window = main.MainWindow()
    page = window.menu_management_page
    window.open_page(page)
    editor = QLineEdit(window.login_page)
    editor.setText('작업 중')
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **kw: ('내 업무', True))
    page.add_group()
    custom = page.tree.currentItem()
    assert custom.text(0) == '내 업무'
    destination = page.destination.findData(custom.data(0, Qt.UserRole))
    page.destination.setCurrentIndex(destination)
    first = page.tree.topLevelItem(0)
    page.tree.setCurrentItem(first.child(0))
    page.move_page()
    assert custom.child(0).data(0, Qt.UserRole) == 'login_page'
    page.tree.setCurrentItem(first)
    page.delete_group()
    assert len(page.groups()) == 9
    page.tree.setCurrentItem(custom)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **kw: ('내 즐겨찾기', True))
    page.rename_group()
    page.move_order(-1)
    expected = copy.deepcopy(page.groups())
    page.save()
    assert '저장하고 적용' in page.status.text()
    assert window.tabs.currentWidget() is page
    assert window.tabs.count() == 2
    assert editor.text() == '작업 중'
    assert window.page_items[window.login_page].parent().text(0) == '내 즐겨찾기'
    assert len(window.page_items) == 20
    other = main.MainWindow()
    assert other.menu_management_page.groups() == expected
    assert other.page_items[other.login_page].parent().text(0) == '내 즐겨찾기'
    other.deleteLater()
    window.deleteLater()


def test_cannot_delete_last_group_or_duplicate_name(app, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QWidget, QInputDialog
    from ui.pages.menu_management_page import MenuManagementPage
    page = MenuManagementPage()
    page.configure(tmp_path / 'menu.json', {'a': dict(label='페이지', page=QWidget())},
                   [dict(id='one', name='하나', pages=['a'])])
    page.tree.setCurrentItem(page.tree.topLevelItem(0))
    page.delete_group()
    assert len(page.groups()) == 1
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **kw: ('하나', True))
    page.add_group()
    assert len(page.groups()) == 1
    page.deleteLater()
