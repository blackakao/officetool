import copy
import json
import os
from urllib.error import HTTPError

import pytest

from business_planning.minutes import (
    MinutesStore, atomic_json, export_docx, generate, new_agenda, new_meeting,
    parse_response, validate,
)


@pytest.fixture
def meeting():
    m = new_meeting()
    m.update(branch_id='branch-1', branch_name='테스트 지점', title='운영회의', place='회의실')
    m['attendees'] = [dict(id='p1', name='위원1', position='시설장', role='진행', present=True),
                      dict(id='p2', name='위원2', position='대표', role='위원', present=True),
                      dict(id='p3', name='위원3', position='대표', role='위원', present=False)]
    for title in ['사업계획', '예산편성']:
        a = new_agenda()
        a.update(title=title, notes='복리후생비 100원 검토', final='검토 중입니다.')
        m['agendas'].append(a)
    return m


def response(meeting):
    return json.dumps({'agendas': [dict(id=a['id'], speeches=[
        dict(attendee_id='p1', text='복리후생비 100원을 검토하겠습니다.'),
        dict(attendee_id='p2', text='검토할 자료가 있습니까?')]) for a in meeting['agendas']]})


def test_roundtrip_and_branch_history(tmp_path, meeting):
    store = MinutesStore(tmp_path)
    store.save(meeting)
    restored = store.load(meeting['id'])
    assert restored['agendas'] == meeting['agendas']
    assert restored['attendees'] == meeting['attendees']
    assert store.history('other') == []
    assert store.history('branch-1')[0]['id'] == meeting['id']
    store.roster('branch-1', meeting['attendees'])
    assert store.roster('branch-1') == meeting['attendees']
    assert store.roster('other') == []
    with pytest.raises(ValueError):
        store.load('../outside')


def test_atomic_failure_preserves_original(tmp_path, monkeypatch):
    path = tmp_path / 'data.json'
    atomic_json(path, {'original': True})
    original = path.read_bytes()
    def fail(*_):
        raise OSError('disk error')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        atomic_json(path, {'original': False})
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))


def test_corrupt_storage_is_not_reset(tmp_path):
    store = MinutesStore(tmp_path)
    path = store.directory / 'rosters.json'
    path.parent.mkdir(parents=True)
    path.write_text('{broken', encoding='utf-8')
    with pytest.raises(json.JSONDecodeError):
        store.roster('b', [])
    assert path.read_text(encoding='utf-8') == '{broken'


def test_response_rejects_missing_agenda_and_absent_speaker(meeting):
    assert len(parse_response(response(meeting), meeting)) == 2
    data = json.loads(response(meeting))
    data['agendas'][0]['speeches'][0]['attendee_id'] = 'p3'
    with pytest.raises(ValueError):
        parse_response(json.dumps(data), meeting)
    with pytest.raises(ValueError):
        parse_response('{"agendas": []}', meeting)
    data = json.loads(response(meeting))
    data['agendas'][1]['id'] = data['agendas'][0]['id']
    with pytest.raises(ValueError):
        parse_response(json.dumps(data), meeting)


def test_mock_api_and_errors_preserve_input(meeting):
    import io
    original = copy.deepcopy(meeting)
    def fake(req, timeout):
        sent = json.loads(req.data)
        assert sent['model'] == 'chosen-model'
        assert 'final' not in json.loads(sent['messages'][1]['content'])['agendas'][0]
        assert timeout == 60
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': response(meeting)}}]}).encode())
    assert len(generate(meeting, 'https://example.invalid/v1/chat/completions', 'chosen-model', 'key', fake)) == 2
    for code, message in [(401, '인증'), (429, '사용량')]:
        def fail(*_, **__):
            raise HTTPError('url', code, 'secret response', {}, None)
        with pytest.raises(ValueError, match=message):
            generate(meeting, 'https://example.invalid/api', 'model', 'key', fail)
    assert meeting == original


def test_validation_and_docx_blank_signatures(tmp_path, meeting):
    from docx import Document
    validate(meeting)
    path = tmp_path / 'minutes.docx'
    with pytest.raises(ValueError, match='확인'):
        export_docx(meeting, path)
    meeting['confirmed'] = True
    export_docx(meeting, path)
    doc = Document(path)
    assert doc.tables[0].rows[0].cells[1].text == '운영회의'
    signatures = doc.tables[-1]
    assert len(signatures.rows) == 3
    assert all(row.cells[3].text == '' for row in signatures.rows[1:])
    assert not doc.inline_shapes
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        export_docx(meeting, path)
    assert path.read_bytes() == original
    meeting['end'] = '09:00'
    with pytest.raises(ValueError, match='종료'):
        validate(meeting)


@pytest.fixture
def app():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_page_edits_roundtrip_and_confirmation_reset(app, tmp_path, meeting, monkeypatch):
    from ui.pages import committee_minutes_page as page_module
    path = tmp_path / 'branches.json'
    path.write_text(json.dumps([dict(branch_name='테스트 지점', organization_code='branch-1')]), encoding='utf-8')
    monkeypatch.setattr(page_module, 'user_data_path', lambda _: path)
    page = page_module.CommitteeMinutesPage(MinutesStore(tmp_path))
    page.display(meeting)
    page.agenda_fields['final'].setPlainText('사용자 수정')
    page.agenda_combo.setCurrentIndex(1)
    page.agenda_fields['final'].setPlainText('두 번째 수정')
    page.confirmed.setChecked(True)
    page.save()
    restored = page.store.load(meeting['id'])
    assert restored['agendas'][0]['final'] == '사용자 수정'
    assert restored['agendas'][1]['final'] == '두 번째 수정'
    assert restored['confirmed']
    page.title.setText('주제 변경')
    assert not page.confirmed.isChecked()
    page.display(restored)
    assert page.collect()['attendees'] == meeting['attendees']
    page.apply_result(parse_response(response(meeting), meeting))
    assert page.collect()['agendas'][0]['draft'] == page.collect()['agendas'][0]['final']
    assert not page.confirmed.isChecked()
    page.deleteLater()


def test_menu_pages_and_existing_navigation(app, monkeypatch):
    import main
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    from ui.pages.committee_minutes_page import PlannedPage
    names = ['BranchPage', 'LoginTool', 'LoginLogPage', 'DocumentTool', 'HwpDocumentTool',
             'TableListPage', 'FederationTool', 'CareforTool', 'LaborCostRatioPage',
             'ServiceFeePage', 'AnnualLeavePage', 'MonthlyWorkCheckPage', 'MemoPage',
             'IncompleteTaskPage', 'BranchTaskSettingsPage', 'AttendanceAnalysisPage',
             'ExcelDataSortPage', 'CommitteeMinutesPage']
    for name in names:
        monkeypatch.setattr(main, name, QWidget)
    window = main.MainWindow()
    entries = {window.menu.item(i).text().strip(): window.menu.item(i)
               for i in range(window.menu.count())}
    assert entries['사업기획'].data(Qt.UserRole) is None
    assert isinstance(entries['예산편성 (예정)'].data(Qt.UserRole), PlannedPage)
    for label in ['사업계획 (예정)', '운영위원회 회의록 작성', '로그인툴', '문서작성툴(한글)']:
        window.on_menu_clicked(entries[label])
        assert window.stacked_widget.currentWidget() is entries[label].data(Qt.UserRole)
    window.deleteLater()


def test_worker_failure_keeps_meeting(app, meeting, monkeypatch):
    from ui.pages import committee_minutes_page as module
    original = copy.deepcopy(meeting)
    def fail(*args):
        # A provider must never be allowed to mutate the UI's source data.
        args[0]['title'] = 'changed by provider'
        raise ValueError('AI 사용량 제한')
    monkeypatch.setattr(module, 'generate', fail)
    worker = module.MinutesWorker(meeting, {})
    failures = []
    worker.failed.connect(failures.append)
    worker.run()
    assert failures == ['AI 사용량 제한']
    assert meeting == original
