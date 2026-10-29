"""사업계획 목록과 계정과목별 산출내역 편집 화면."""
import copy
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QDialogButtonBox, QTabWidget,
    QScrollArea, QGroupBox,
)

from business_planning.plans import (
    CONFIG, CYCLES, ACCOUNTS, PlanStore, new_plan, annual_count, calculate_line,
    totals, fmt, validate_plan,
)


class AccountEditor(QGroupBox):
    def __init__(self, line, changed, removed):
        super().__init__('계정과목 / 산출내역')
        self.original = copy.deepcopy(line)
        self.changed = changed
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.account = QComboBox()
        self.account.addItem('계정과목 선택 *', '')
        for key, account in ACCOUNTS.items():
            self.account.addItem(account['name'], key)
        self.account.setCurrentIndex(max(0, self.account.findData(line['account_id'])))
        row.addWidget(self.account, 1)
        delete = QPushButton('계정 행 삭제')
        delete.clicked.connect(lambda: removed(self))
        row.addWidget(delete)
        root.addLayout(row)
        self.description = QLineEdit(line.get('description', ''))
        self.description.setPlaceholderText('산출내역 설명 (선택, 예: 식비 / 간식비)')
        root.addWidget(self.description)
        self.factors = QTableWidget(0, 3)
        self.factors.setHorizontalHeaderLabels(['계산 항목명 *', '값 *', '단위 (선택)'])
        self.factors.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.factors.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.factors.setMinimumHeight(125)
        self.factors.setMaximumHeight(200)
        root.addWidget(self.factors)
        for factor in line['factors']:
            self.add_factor(factor)
        buttons = QHBoxLayout()
        add, remove = QPushButton('계산 칸 추가'), QPushButton('선택 계산 칸 삭제')
        add.clicked.connect(lambda: self.add_factor())
        remove.clicked.connect(self.remove_factor)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        root.addLayout(buttons)
        self.formula = QLabel()
        self.formula.setWordWrap(True)
        self.formula.setTextFormat(Qt.PlainText)
        self.formula.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.formula)
        self.account.currentIndexChanged.connect(changed)
        self.description.textChanged.connect(changed)
        self.factors.itemChanged.connect(changed)

    def add_factor(self, factor=None):
        if self.factors.rowCount() >= 20:
            QMessageBox.information(self, '계산 항목', '계산 항목은 최대 20개입니다.')
            return
        factor = factor or dict(label='', value='1', unit='')
        self.factors.blockSignals(True)
        row = self.factors.rowCount()
        self.factors.insertRow(row)
        for column, key in enumerate(('label', 'value', 'unit')):
            self.factors.setItem(row, column, QTableWidgetItem(str(factor[key])))
        self.factors.blockSignals(False)
        self.changed()

    def remove_factor(self):
        rows = sorted({index.row() for index in self.factors.selectedIndexes()}, reverse=True)
        for row in rows:
            self.factors.removeRow(row)
        self.changed()

    def value(self):
        result = copy.deepcopy(self.original)
        result.update(account_id=self.account.currentData(), description=self.description.text().strip(),
                      factors=[dict(zip(('label', 'value', 'unit'),
                                        [self.factors.item(row, col).text().strip() for col in range(3)]))
                               for row in range(self.factors.rowCount())])
        return result


class BusinessPlanDialog(QDialog):
    def __init__(self, store, plan=None, categories=(), parent=None):
        super().__init__(parent)
        self.store = store
        self.original = copy.deepcopy(plan or new_plan())
        self.editors = []
        self.loading = True
        self.setWindowTitle('사업계획 수정' if plan else '사업계획 추가')
        self.resize(880, 750)
        root = QVBoxLayout(self)
        root.addWidget(QLabel('* 필수 입력 · 사업기간 기본 1년 · 계정과목은 필요한 경우 추가합니다.'))
        tabs = QTabWidget()
        root.addWidget(tabs)
        basic = QWidget()
        form = QFormLayout(basic)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(list(dict.fromkeys(CONFIG['categories'] + list(categories))))
        self.category.setCurrentText(self.original['category'])
        self.title = QLineEdit(self.original['title'])
        self.goal = QPlainTextEdit(self.original['goal'])
        self.goal.setMaximumHeight(110)
        self.details = QPlainTextEdit(self.original['details'])
        self.cycle = QComboBox()
        self.cycle.addItems(list(CYCLES))
        self.cycle.setCurrentText(self.original['cycle'])
        self.frequency = QSpinBox()
        self.frequency.setRange(1, 10000)
        self.frequency.setSuffix(' 회 / 주기')
        self.frequency.setValue(self.original['frequency'])
        self.count = QLabel()
        for label, widget in [('구분 *', self.category), ('사업명 *', self.title), ('목표 *', self.goal),
                              ('주기 *', self.cycle), ('제공횟수 *', self.frequency),
                              ('연간 제공횟수', self.count), ('세부내용 *', self.details)]:
            form.addRow(label, widget)
        tabs.addTab(basic, '사업 기본 정보')
        costs = QWidget()
        layout = QVBoxLayout(costs)
        hint = QLabel('항목의 값을 모두 곱한 뒤 연간 주기 수와 제공횟수를 곱합니다.\n'
                      '예: 입소자 10명 × 식비 단가 4500원 × 365(일간/년) × 3회 = 49,275,000원\n'
                      '숫자는 쉼표 없이 입력하세요. 원 미만은 계정 행마다 반올림합니다.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        add = QPushButton('계정과목 행 추가')
        add.clicked.connect(lambda: self.add_account())
        layout.addWidget(add)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.accounts_layout = QVBoxLayout(container)
        self.accounts_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        source = QLabel('계정과목: 장기요양기관 재무ㆍ회계 규칙 별표 1·2\n'
                        '직접비·간접비는 인건비 목의 내부 세부구분입니다.')
        layout.addWidget(source)
        tabs.addTab(costs, '계정과목 및 산출내역')
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('저장')
        buttons.button(QDialogButtonBox.Cancel).setText('취소')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        for line in self.original['accounts']:
            self.add_account(line)
        self.cycle.currentTextChanged.connect(self.recalculate)
        self.frequency.valueChanged.connect(self.recalculate)
        self.loading = False
        self.recalculate()
        self.initial_value = self.value()

    def add_account(self, line=None):
        line = line or dict(id=uuid.uuid4().hex, account_id='', description='',
                            factors=[dict(label='단가', value='0', unit='원')])
        editor = AccountEditor(line, self.recalculate, self.remove_account)
        self.editors.append(editor)
        self.accounts_layout.addWidget(editor)
        self.recalculate()

    def remove_account(self, editor):
        if QMessageBox.question(self, '계정 행 삭제', '이 계정과목과 계산 항목을 삭제할까요?') != QMessageBox.Yes:
            return
        self.editors.remove(editor)
        self.accounts_layout.removeWidget(editor)
        editor.deleteLater()
        self.recalculate()

    def value(self):
        result = copy.deepcopy(self.original)
        result.update(category=self.category.currentText().strip(), title=self.title.text().strip(),
                      goal=self.goal.toPlainText().strip(), details=self.details.toPlainText().strip(),
                      cycle=self.cycle.currentText(), frequency=self.frequency.value(),
                      accounts=[editor.value() for editor in self.editors])
        return result

    def recalculate(self, *_):
        if self.loading:
            return
        plan = self.value()
        count = annual_count(plan)
        self.frequency.setEnabled(count is not None)
        self.count.setText('산정하지 않음 (수시·미정)' if count is None else
                           f"{CYCLES[plan['cycle']]} × {plan['frequency']} = {count:,}회 / 년")
        errors = False
        for editor, line in zip(self.editors, plan['accounts']):
            try:
                _, formula = calculate_line(plan, line)
                editor.formula.setText(formula)
            except ValueError as exc:
                errors = True
                editor.formula.setText(str(exc))
        if errors:
            self.summary.setText('계정과목과 계산 항목을 완성하면 연간 예상액을 표시합니다.')
        else:
            amounts = totals(plan)
            self.summary.setText(f"연간 예상 세입 {fmt(amounts['income'])}원 / 세출 {fmt(amounts['expense'])}원")

    def save(self):
        try:
            plan = self.value()
            validate_plan(plan)
            self.store.save(plan)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, '저장 실패', str(exc))
            return
        self.accept()

    def reject(self):
        if self.value() != self.initial_value:
            if QMessageBox.question(self, '변경 내용 확인', '저장하지 않은 변경 내용을 버리고 닫을까요?') != QMessageBox.Yes:
                return
        super().reject()


class BusinessPlanPage(QWidget):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or PlanStore()
        self.records = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel('사업계획 관리'))
        hint = QLabel('기본 사업기간 1년: 일간 365 · 주간 52 · 월간 12 · 연간 1 · 분기 4 · 반기 2\n'
                      '사업을 추가한 뒤 계정과목별 산출내역을 입력하세요. 표의 행을 두 번 클릭하면 수정합니다.')
        hint.setWordWrap(True)
        root.addWidget(hint)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('구분 / 사업명 검색')
        self.search.textChanged.connect(self.render)
        row.addWidget(self.search, 1)
        self.add_button, self.edit_button, self.delete_button = (
            QPushButton('사업 추가'), QPushButton('선택 수정'), QPushButton('선택 삭제'))
        for button, action in [(self.add_button, self.add), (self.edit_button, self.edit),
                               (self.delete_button, self.delete)]:
            row.addWidget(button)
            button.clicked.connect(action)
        refresh = QPushButton('새로고침')
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        root.addLayout(row)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(['구분', '사업명', '주기', '제공횟수', '연간횟수', '계정과목', '연간 세입', '연간 세출'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(lambda _: self.edit())
        self.table.itemSelectionChanged.connect(self.selection_changed)
        root.addWidget(self.table)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.reload()

    def reload(self):
        try:
            self.records = self.store.list()
        except (OSError, ValueError) as exc:
            self.records = []
            self.render()
            self.add_button.setEnabled(False)
            self.status.setText(str(exc))
            return
        self.add_button.setEnabled(True)
        self.render()

    def render(self, *_):
        query = self.search.text().strip().casefold()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        sums = dict(income=0, expense=0)
        for plan in self.records:
            if query and query not in (plan['category'] + ' ' + plan['title']).casefold():
                continue
            amounts = totals(plan)
            for key in sums:
                sums[key] += amounts[key]
            row = self.table.rowCount()
            self.table.insertRow(row)
            names = ', '.join(ACCOUNTS[line['account_id']]['name'] for line in plan['accounts'])
            count = annual_count(plan)
            values = [plan['category'], plan['title'], plan['cycle'],
                      plan['frequency'] if count is not None else '—', count if count is not None else '미산정',
                      names or '없음', f"{fmt(amounts['income'])}원", f"{fmt(amounts['expense'])}원"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, plan['id'])
                item.setToolTip(str(value))
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.status.setText(f"표시 {self.table.rowCount()}건 / 전체 {len(self.records)}건 · "
                            f"표시 사업 합계: 세입 {fmt(sums['income'])}원 / 세출 {fmt(sums['expense'])}원")
        self.selection_changed()

    def selected(self):
        items = self.table.selectedItems()
        return next((p for p in self.records if items and p['id'] == items[0].data(Qt.UserRole)), None)

    def selection_changed(self):
        enabled = self.selected() is not None
        self.edit_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def open_editor(self, plan=None):
        dialog = BusinessPlanDialog(self.store, plan, [p['category'] for p in self.records], self)
        if dialog.exec() == QDialog.Accepted:
            self.reload()

    def add(self):
        self.open_editor()

    def edit(self):
        plan = self.selected()
        if plan:
            self.open_editor(plan)

    def delete(self):
        plan = self.selected()
        if not plan:
            return
        if QMessageBox.question(self, '사업 삭제', f"'{plan['title']}' 사업을 삭제할까요?") != QMessageBox.Yes:
            return
        try:
            self.store.delete(plan['id'])
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, '삭제 실패', str(exc))
            return
        self.reload()
