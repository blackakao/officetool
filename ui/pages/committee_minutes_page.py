import copy
import json
import uuid

from PySide6.QtCore import QDate, QTime, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QTimeEdit, QLineEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit, QCheckBox,
    QMessageBox, QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
)

from business_planning.minutes import (
    NOTICE, MinutesStore, new_meeting, prompt_meeting, validate,
    document_text, export_docx,
)
from business_planning.local_ai import generate_local, download_model, model_ready
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
    progress = Signal(str)

    def __init__(self, meeting, settings, parent=None):
        super().__init__(parent)
        self.meeting, self.settings = copy.deepcopy(meeting), settings.copy()

    def run(self):
        try:
            if self.settings.get('download'):
                download_model(self.settings['directory'], self.progress.emit)
            else:
                result = generate_local(self.meeting, self.settings['directory'],
                                        self.progress.emit, self.isInterruptionRequested)
                self.result.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class CommitteeMinutesPage(QWidget):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or MinutesStore()
        self.worker = None
        self.meeting = new_meeting()
        self.dirty = False
        self.loading = False
        root = QVBoxLayout(self)
        warning = QLabel(NOTICE)
        warning.setWordWrap(True)
        root.addWidget(warning)
        required_hint = QLabel('* 필수 항목입니다. 프롬프트는 AI 작성 시, 회의록 내용과 확인 체크는 최종 문서 저장 시 필요합니다.\n'
                               '일반 저장은 지점만 선택해도 가능합니다.')
        required_hint.setWordWrap(True)
        root.addWidget(required_hint)
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
        self.quarter = QComboBox()
        for number in range(1, 5):
            self.quarter.addItem(f'{number}분기', number)
        self.title, self.place = QLineEdit(), QLineEdit()
        for label, widget in [('지점', self.branch), ('분기', self.quarter),
                              ('제목', self.title), ('회의일자', self.date), ('시작시간', self.start),
                              ('종료시간', self.end), ('회의장소', self.place)]:
            form.addRow(label + ' *', widget)
        layout.addLayout(form)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        people = QWidget()
        pl = QVBoxLayout(people)
        pl.addWidget(QLabel('참석자 * — 성명을 입력하고 최소 1명을 참석으로 선택하세요. 직책과 역할은 선택 입력입니다.'))
        self.people = QTableWidget(0, 4)
        self.people.setHorizontalHeaderLabels(['성명 *', '직책 / 위원 구분', '회의 내 역할', '참석'])
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
        writing = QWidget()
        wl = QVBoxLayout(writing)
        wl.addWidget(QLabel('프롬프트 * (AI 작성 시 필수) — 참석자의 역할·말투와 회의 내용을 자유롭게 적어 주세요.'))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(
            '예: A는 공손한 진행자입니다. B는 외부 인사로 질문과 감사 인사를 합니다. '
            '2026년 예산의 적법성을 검토하는 회의입니다. 두 사람이 의견을 주고받도록 작성해 주세요.')
        wl.addWidget(self.prompt, 1)
        wl.addWidget(QLabel('생성된 회의록 * (최종 문서 저장 시 필수) — 직접 수정한 뒤 확인하고 저장하세요.'))
        self.final_text = QPlainTextEdit()
        self.final_text.setPlaceholderText('AI가 작성한 대화형 회의록이 표시됩니다. 직접 작성할 수도 있습니다.')
        wl.addWidget(self.final_text, 2)
        self.tabs.addTab(writing, '프롬프트 / 회의록')
        self.tabs.setCurrentWidget(writing)
        self.confirmed = QCheckBox('실제 회의 내용과 참석자 발언·결정사항을 확인하고 수정했습니다. * (최종 문서 저장 시 필수)')
        layout.addWidget(self.confirmed)
        bottom = QHBoxLayout()
        for text, callback in [('AI 회의록 작성 / 재생성', self.generate), ('미리보기', self.preview),
                               ('최종 DOCX 저장', self.export)]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            bottom.addWidget(b)
        layout.addLayout(bottom)
        self.status = QLabel('내장 AI: 최초 1회 모델 다운로드 후 인터넷 없이 작성합니다.')
        root.addWidget(self.status)
        self.cancel_button = QPushButton('AI 작성 취소')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_generation)
        root.addWidget(self.cancel_button)
        self.people.itemChanged.connect(self.changed)
        for widget in [self.title, self.place]:
            widget.textChanged.connect(self.changed)
        for widget in [self.prompt, self.final_text]:
            widget.textChanged.connect(self.changed)
        self.date.dateChanged.connect(self.changed)
        self.start.timeChanged.connect(self.changed)
        self.end.timeChanged.connect(self.changed)
        self.quarter.currentIndexChanged.connect(self.changed)
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

    def collect(self):
        self.meeting.update(branch_id=self.branch.currentData() or '', branch_name=self.branch.currentText(),
                            fiscal_year=self.date.date().year(), quarter=self.quarter.currentData(),
                            date=self.date.date().toString('yyyy-MM-dd'),
                            start=self.start.time().toString('HH:mm'), end=self.end.time().toString('HH:mm'),
                            place=self.place.text(), title=self.title.text(),
                            attendees=self.attendees(), prompt=self.prompt.toPlainText(),
                            final=self.final_text.toPlainText(), confirmed=self.confirmed.isChecked())
        return copy.deepcopy(self.meeting)

    def display(self, meeting):
        self.loading = True
        meeting = prompt_meeting(meeting)
        self.meeting = meeting
        index = self.branch.findData(meeting['branch_id'])
        if index < 0:
            self.branch.addItem(meeting['branch_name'] + ' (보관된 지점)', meeting['branch_id'])
            index = self.branch.count() - 1
        self.branch.setCurrentIndex(index)
        self.quarter.setCurrentIndex(self.quarter.findData(meeting['quarter']))
        self.date.setDate(QDate.fromString(meeting['date'], 'yyyy-MM-dd'))
        self.start.setTime(QTime.fromString(meeting['start'], 'HH:mm'))
        self.end.setTime(QTime.fromString(meeting['end'], 'HH:mm'))
        for key in ['title', 'place']:
            getattr(self, key).setText(meeting[key])
        self.prompt.setPlainText(meeting['prompt'])
        self.final_text.setPlainText(meeting['final'])
        self.people.setRowCount(0)
        for p in meeting['attendees']:
            self.add_person(person=p)
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
        # Legacy external endpoint/key settings are deliberately never read.
        return {'directory': self.store.directory / 'models' / 'qwen3-0.6b'}

    def configure(self):
        try:
            settings = self.settings()
            dialog = QDialog(self)
            dialog.setWindowTitle('내장 AI')
            form = QFormLayout(dialog)
            ready = model_ready(settings['directory'])
            form.addRow(QLabel('Qwen3-0.6B · PC 내부 CPU 실행 · API 키/사용료 없음\n'
                               '회의 내용은 외부로 전송하지 않습니다.\n'
                               '최초 모델 다운로드 약 1.5GB / 실행 메모리 약 4GB 이상 여유 권장\n'
                               '소형 모델이므로 발언과 수치는 반드시 검토하세요.'))
            form.addRow('상태', QLabel('모델 파일 준비됨' if ready else '모델 다운로드 필요'))
            form.addRow('저장 위치', QLabel(str(settings['directory'])))
            form.addRow(QLabel('실행 패키지가 없는 경우:\npython -m pip install -r requirements-local-ai.txt'))
            download = QPushButton('모델 다시 확인 / 다운로드' if ready else '내장 모델 다운로드')
            download.clicked.connect(dialog.accept)
            form.addRow(download)
            buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if dialog.exec():
                settings['download'] = True
                self.start_worker(MinutesWorker({}, settings, self), downloading=True)
        except Exception as exc:
            self.error(exc)

    def generate(self):
        try:
            meeting = self.collect()
            validate(meeting)
            settings = self.settings()
            if not model_ready(settings['directory']):
                raise ValueError('AI 설정에서 내장 모델을 먼저 다운로드하세요.')
            if not meeting['prompt'].strip():
                raise ValueError('회의 내용과 참석자 역할을 프롬프트에 입력하세요.')
            if meeting['final'].strip() and not self.ask(
                    '재생성하면 현재 회의록 편집 내용을 교체합니다. 계속할까요?'):
                return
            self.start_worker(MinutesWorker(meeting, settings, self))
        except Exception as exc:
            self.error(exc)

    def start_worker(self, worker, downloading=False):
        self.worker = worker
        worker.result.connect(self.apply_result)
        worker.failed.connect(self.error)
        worker.progress.connect(self.status.setText)
        worker.finished.connect(self.worker_finished)
        self.body.setEnabled(False)
        self.cancel_button.setEnabled(not downloading)
        self.status.setText('내장 AI 준비 중…')
        worker.start()

    def cancel_generation(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText('취소 중… 모델 로딩 또는 현재 계산 완료 후 중단합니다.')

    def apply_result(self, result):
        if self.worker and self.worker.isInterruptionRequested():
            return
        self.meeting['draft'] = result
        self.final_text.setPlainText(result)
        self.changed()

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.body.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.setText('내장 AI 작업이 종료되었습니다. 결과 또는 오류 안내를 확인하세요.')

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
