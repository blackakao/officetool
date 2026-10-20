import copy
import json
import os
import uuid

from PySide6.QtCore import QDate, QTime, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QTimeEdit, QLineEdit, QSpinBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit, QCheckBox,
    QMessageBox, QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
)

from business_planning.minutes import (
    NOTICE, MinutesStore, new_meeting, new_agenda, generate, validate,
    document_text, export_docx, atomic_json,
)
from data_paths import user_data_path
from ui.pages.branch_task_settings import branch_key


class PlannedPage(QWidget):
    def __init__(self, title):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title + ' 기능은 준비 중입니다.'))
        layout.addStretch()


class MinutesWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, meeting, settings, parent=None):
        super().__init__(parent)
        self.meeting, self.settings = copy.deepcopy(meeting), settings.copy()

    def run(self):
        try:
            result = generate(self.meeting, self.settings.get('endpoint', ''),
                              self.settings.get('model', ''), os.environ.get('MYTOOL_AI_API_KEY', ''))
            self.result.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class CommitteeMinutesPage(QWidget):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or MinutesStore()
        self.worker = None
        self.meeting = new_meeting()
        self.agenda_index = -1
        self.dirty = False
        self.loading = False
        root = QVBoxLayout(self)
        warning = QLabel(NOTICE)
        warning.setWordWrap(True)
        root.addWidget(warning)
        self.body = QWidget()
        root.addWidget(self.body)
        layout = QVBoxLayout(self.body)
        actions = QHBoxLayout()
        for text, callback in [('새 회의', self.reset), ('저장', self.save),
                               ('지점별 이력 불러오기', self.load_history), ('AI 설정', self.configure)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        form = QFormLayout()
        self.branch = QComboBox()
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat('yyyy-MM-dd')
        self.start, self.end = QTimeEdit(QTime(10, 0)), QTimeEdit(QTime(11, 0))
        self.year = QSpinBox()
        self.year.setRange(2000, 2200)
        self.title, self.place, self.session = QLineEdit(), QLineEdit(), QLineEdit()
        for label, widget in [('지점', self.branch), ('회계연도', self.year), ('차수', self.session),
                              ('회의주제', self.title), ('회의일자', self.date), ('시작시간', self.start),
                              ('종료시간', self.end), ('회의장소', self.place)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        people = QWidget()
        pl = QVBoxLayout(people)
        self.people = QTableWidget(0, 4)
        self.people.setHorizontalHeaderLabels(['성명', '직책 / 위원 구분', '회의 내 역할', '참석'])
        self.people.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        pl.addWidget(self.people)
        buttons = QHBoxLayout()
        for text, callback in [('참석자 추가', self.add_person), ('선택 참석자 삭제', self.remove_person),
                               ('지점 명단 저장', self.save_roster), ('지점 명단 불러오기', self.load_roster)]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            buttons.addWidget(b)
        pl.addLayout(buttons)
        self.tabs.addTab(people, '참석자')
        agenda = QWidget()
        al = QVBoxLayout(agenda)
        row = QHBoxLayout()
        self.agenda_combo = QComboBox()
        row.addWidget(self.agenda_combo, 1)
        for text, callback in [('안건 추가', self.add_agenda), ('안건 삭제', self.remove_agenda)]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            row.addWidget(b)
        al.addLayout(row)
        self.agenda_fields = {}
        inner = QTabWidget()
        for key, label in [('title', '안건명'), ('notes', '주요 논의'), ('opinions', '참석자별 의견'),
                           ('decision', '결정사항'), ('follow_up', '후속 조치'), ('reference', '참고사항'),
                           ('final', '내용 편집'), ('draft', 'AI 원본 초안')]:
            editor = QPlainTextEdit()
            editor.setReadOnly(key == 'draft')
            editor.textChanged.connect(self.changed)
            self.agenda_fields[key] = editor
            inner.addTab(editor, label)
        al.addWidget(inner)
        self.tabs.addTab(agenda, '안건 및 내용 편집')
        declarations = QWidget()
        dl = QFormLayout(declarations)
        self.opening, self.closing = QPlainTextEdit(), QPlainTextEdit()
        dl.addRow('개회선언', self.opening)
        dl.addRow('폐회선언', self.closing)
        self.tabs.addTab(declarations, '개회 / 폐회')
        self.confirmed = QCheckBox('실제 회의 내용과 참석자 발언·결정사항을 확인하고 수정했습니다.')
        layout.addWidget(self.confirmed)
        bottom = QHBoxLayout()
        for text, callback in [('AI 회의록 작성 / 재생성', self.generate), ('미리보기', self.preview),
                               ('최종 DOCX 저장', self.export)]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            bottom.addWidget(b)
        layout.addLayout(bottom)
        self.status = QLabel('AI 미설정 상태에서도 입력·편집·저장이 가능합니다.')
        root.addWidget(self.status)
        self.agenda_combo.currentIndexChanged.connect(self.select_agenda)
        self.people.itemChanged.connect(self.changed)
        for widget in [self.title, self.place, self.session]:
            widget.textChanged.connect(self.changed)
        for widget in [self.opening, self.closing]:
            widget.textChanged.connect(self.changed)
        self.date.dateChanged.connect(self.changed)
        self.start.timeChanged.connect(self.changed)
        self.end.timeChanged.connect(self.changed)
        self.year.valueChanged.connect(self.changed)
        self.branch.currentIndexChanged.connect(self.changed)
        self.confirmed.toggled.connect(lambda: self.mark_dirty())
        self.refresh_branches()
        self.display(self.meeting)

    def mark_dirty(self):
        if not self.loading:
            self.dirty = True

    def changed(self, *_):
        if not self.loading:
            self.dirty = True
            self.confirmed.setChecked(False)

    def refresh_branches(self):
        current = self.branch.currentData()
        try:
            branches = json.loads(user_data_path('branches.json').read_text(encoding='utf-8'))
            self.branch.blockSignals(True)
            self.branch.clear()
            self.branch.addItem('지점 선택', '')
            for branch in branches:
                if branch.get('active', True):
                    self.branch.addItem(branch.get('branch_name', ''), branch_key(branch))
            if current and self.branch.findData(current) < 0:
                self.branch.addItem(self.meeting.get('branch_name', current) + ' (보관된 지점)', current)
            self.branch.setCurrentIndex(max(0, self.branch.findData(current)))
        except Exception as exc:
            self.status.setText('지점 로드 실패: ' + str(exc))
        finally:
            self.branch.blockSignals(False)

    def showEvent(self, event):
        self.refresh_branches()
        super().showEvent(event)

    def error(self, exc):
        QMessageBox.warning(self, '회의록', str(exc))

    def ask(self, text):
        return QMessageBox.question(self, '확인', text, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def may_replace(self):
        return not self.dirty or self.ask('저장하지 않은 변경이 있습니다. 버리고 불러올까요?')

    def add_person(self, _checked=False, person=None):
        p = person or dict(id=uuid.uuid4().hex, name='', position='', role='', present=True)
        row = self.people.rowCount()
        self.people.insertRow(row)
        for col, key in enumerate(['name', 'position', 'role']):
            item = QTableWidgetItem(p[key])
            item.setData(256, p['id'])
            self.people.setItem(row, col, item)
        check = QCheckBox()
        check.setChecked(p['present'])
        check.toggled.connect(self.changed)
        self.people.setCellWidget(row, 3, check)
        self.changed()

    def remove_person(self):
        row = self.people.currentRow()
        if row >= 0 and self.ask('선택한 참석자를 회의에서 삭제할까요?'):
            self.people.removeRow(row)
            self.changed()

    def attendees(self):
        return [dict(id=self.people.item(r, 0).data(256),
                     name=self.people.item(r, 0).text(), position=self.people.item(r, 1).text(),
                     role=self.people.item(r, 2).text(), present=self.people.cellWidget(r, 3).isChecked())
                for r in range(self.people.rowCount())]

    def stash_agenda(self):
        if 0 <= self.agenda_index < len(self.meeting['agendas']):
            for key, widget in self.agenda_fields.items():
                self.meeting['agendas'][self.agenda_index][key] = widget.toPlainText()
            title = self.meeting['agendas'][self.agenda_index]['title'] or '새 안건'
            self.agenda_combo.setItemText(self.agenda_index, f'{self.agenda_index + 1}. {title}')

    def select_agenda(self, index):
        self.stash_agenda()
        self.agenda_index = index
        old = self.loading
        self.loading = True
        for key, editor in self.agenda_fields.items():
            editor.setPlainText(self.meeting['agendas'][index][key] if index >= 0 else '')
            editor.setEnabled(index >= 0)
        self.loading = old

    def refresh_agendas(self, index=0):
        self.agenda_combo.blockSignals(True)
        self.agenda_combo.clear()
        for i, a in enumerate(self.meeting['agendas'], 1):
            self.agenda_combo.addItem(f"{i}. {a['title'] or '새 안건'}")
        self.agenda_index = -1
        index = min(index, len(self.meeting['agendas']) - 1)
        self.agenda_combo.setCurrentIndex(index)
        self.agenda_combo.blockSignals(False)
        self.select_agenda(index)

    def add_agenda(self):
        self.stash_agenda()
        self.meeting['agendas'].append(new_agenda())
        self.refresh_agendas(len(self.meeting['agendas']) - 1)
        self.changed()

    def remove_agenda(self):
        if self.agenda_index >= 0 and self.ask('선택 안건과 작성 내용을 삭제할까요?'):
            del self.meeting['agendas'][self.agenda_index]
            self.refresh_agendas()
            self.changed()

    def collect(self):
        self.stash_agenda()
        self.meeting.update(branch_id=self.branch.currentData() or '', branch_name=self.branch.currentText(),
                            fiscal_year=self.year.value(), date=self.date.date().toString('yyyy-MM-dd'),
                            start=self.start.time().toString('HH:mm'), end=self.end.time().toString('HH:mm'),
                            place=self.place.text(), title=self.title.text(), session=self.session.text(),
                            attendees=self.attendees(), opening=self.opening.toPlainText(),
                            closing=self.closing.toPlainText(), confirmed=self.confirmed.isChecked())
        return copy.deepcopy(self.meeting)

    def display(self, meeting):
        self.loading = True
        self.meeting = copy.deepcopy(meeting)
        index = self.branch.findData(meeting['branch_id'])
        if index < 0:
            self.branch.addItem(meeting['branch_name'] + ' (보관된 지점)', meeting['branch_id'])
            index = self.branch.count() - 1
        self.branch.setCurrentIndex(index)
        self.year.setValue(meeting['fiscal_year'])
        self.date.setDate(QDate.fromString(meeting['date'], 'yyyy-MM-dd'))
        self.start.setTime(QTime.fromString(meeting['start'], 'HH:mm'))
        self.end.setTime(QTime.fromString(meeting['end'], 'HH:mm'))
        for key in ['title', 'place', 'session']:
            getattr(self, key).setText(meeting[key])
        self.opening.setPlainText(meeting['opening'])
        self.closing.setPlainText(meeting['closing'])
        self.people.setRowCount(0)
        for p in meeting['attendees']:
            self.add_person(person=p)
        self.refresh_agendas()
        self.confirmed.setChecked(meeting['confirmed'])
        self.loading = False
        self.dirty = False

    def reset(self):
        if self.may_replace():
            self.display(new_meeting())

    def save(self):
        try:
            meeting = self.collect()
            if not meeting['branch_id']:
                raise ValueError('저장할 지점을 선택하세요.')
            self.store.save(meeting)
            self.dirty = False
            self.status.setText('회의록이 저장되었습니다.')
        except Exception as exc:
            self.error(exc)

    def load_history(self):
        try:
            records = self.store.history(self.branch.currentData())
            labels = [f"{m['date']} {m['title']} [{m['id'][:8]}]" for m in records]
            if not labels:
                self.status.setText('선택 지점의 저장된 회의록이 없습니다.')
                return
            label, ok = QInputDialog.getItem(self, '작성 이력', '회의록', labels, 0, False)
            if ok and self.may_replace():
                self.display(records[labels.index(label)])
        except Exception as exc:
            self.error(exc)

    def save_roster(self):
        try:
            key = self.branch.currentData()
            if not key:
                raise ValueError('지점을 선택하세요.')
            if self.store.roster(key) and not self.ask('저장된 지점 명단을 현재 명단으로 교체할까요?'):
                return
            self.store.roster(key, self.attendees())
            self.status.setText('지점 참석자 명단을 저장했습니다.')
        except Exception as exc:
            self.error(exc)

    def load_roster(self):
        try:
            people = self.store.roster(self.branch.currentData())
            if self.people.rowCount() and not self.ask('현재 참석자 명단을 저장된 명단으로 교체할까요?'):
                return
            self.people.setRowCount(0)
            for person in people:
                self.add_person(person=person)
            self.changed()
        except Exception as exc:
            self.error(exc)

    def settings(self):
        path = self.store.directory / 'ai_settings.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def configure(self):
        try:
            settings = self.settings()
            dialog = QDialog(self)
            dialog.setWindowTitle('AI 서비스 설정')
            form = QFormLayout(dialog)
            endpoint = QLineEdit(settings.get('endpoint', ''))
            model = QLineEdit(settings.get('model', ''))
            form.addRow('Chat Completions 호환 HTTPS 전체 URL', endpoint)
            form.addRow('모델', model)
            form.addRow(QLabel('인증키는 MYTOOL_AI_API_KEY 환경변수로 설정 후 앱을 다시 실행하세요.\n'
                               '주소와 모델만 저장합니다. 요청 시 사용료가 발생할 수 있습니다.'))
            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if dialog.exec():
                atomic_json(self.store.directory / 'ai_settings.json',
                            dict(endpoint=endpoint.text().strip(), model=model.text().strip()))
        except Exception as exc:
            self.error(exc)

    def generate(self):
        try:
            meeting = self.collect()
            validate(meeting)
            settings = self.settings()
            if not settings.get('endpoint') or not settings.get('model') or not os.environ.get('MYTOOL_AI_API_KEY'):
                raise ValueError('AI 설정과 MYTOOL_AI_API_KEY 환경변수를 확인하세요.')
            if any(a['final'] for a in meeting['agendas']) and not self.ask(
                    '재생성하면 현재 안건별 편집 내용을 교체합니다. 계속할까요?'):
                return
            if not self.ask(f"{settings['endpoint']}\n모델: {settings['model']}\n"
                            '회의 기본 정보, 참석자 성명·직책, 안건과 의견을 외부 AI로 전송합니다. '
                            '서비스 사용료가 발생할 수 있습니다. 전송할까요?'):
                return
            self.worker = MinutesWorker(meeting, settings, self)
            self.worker.result.connect(self.apply_result)
            self.worker.failed.connect(self.error)
            self.worker.finished.connect(self.worker_finished)
            self.body.setEnabled(False)
            self.status.setText('AI 회의록 작성 중…')
            self.worker.start()
        except Exception as exc:
            self.error(exc)

    def apply_result(self, result):
        for a in self.meeting['agendas']:
            a['draft'] = a['final'] = result[a['id']]
        self.refresh_agendas()
        self.changed()

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.body.setEnabled(True)
        self.status.setText('AI 요청이 종료되었습니다. 내용을 검토해 주세요.')

    def preview(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('문서 내용 미리보기 (DOCX 페이지 배치는 문서에서 확인)')
        dialog.resize(800, 700)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(document_text(self.collect()))
        text.setReadOnly(True)
        layout.addWidget(text)
        dialog.exec()

    def export(self):
        try:
            meeting = self.collect()
            validate(meeting)
            if not meeting['confirmed']:
                raise ValueError('실제 회의 내용 확인을 체크하세요.')
            self.preview()
            directory = self.store.directory / 'outputs'
            path, _ = QFileDialog.getSaveFileName(self, '최종 문서 저장',
                str(directory / f"{meeting['date']}_{meeting['id'][:8]}.docx"), 'Word 문서 (*.docx)')
            if path:
                export_docx(meeting, path)
                self.store.save(meeting)
                self.dirty = False
                self.status.setText('최종 문서와 회의록 데이터를 저장했습니다: ' + path)
        except Exception as exc:
            self.error(exc)
