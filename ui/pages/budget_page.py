"""사업계획을 읽기 전용으로 집계하는 예산편성 화면."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QDialogButtonBox, QPlainTextEdit,
)

from business_planning.budget import GROUPS, aggregate_budget
from business_planning.plans import PlanStore, ACCOUNTS, annual_count, calculate_line, fmt


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.verticalHeader().hide()
    return widget


def fill_row(widget, row, values):
    for col, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        item.setToolTip(str(value))
        if str(value).endswith('원'):
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        widget.setItem(row, col, item)


class BudgetPlanSummary(QDialog):
    def __init__(self, plan, account_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle('사업 요약 — ' + plan['title'])
        self.resize(780, 650)
        root = QVBoxLayout(self)
        count = annual_count(plan)
        lines = [f"사업명: {plan['title']}", f"구분: {plan['category']}",
                 f"주기: {plan['cycle']} / 제공횟수: {plan['frequency']}회 / 연간: {count if count is not None else '미산정'}회",
                 '', '[목표]', plan['goal'], '', '[세부내용]', plan['details'], '', '[예산 산출내역]']
        for line in plan['accounts']:
            _, formula = calculate_line(plan, line)
            label = ACCOUNTS[line['account_id']]['name']
            if line['account_id'] == account_id:
                label += ' (선택한 계정과목)'
            lines.extend([label, line.get('description', ''), formula, ''])
        self.content = QPlainTextEdit('\n'.join(lines))
        self.content.setReadOnly(True)
        root.addWidget(self.content)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText('닫기')
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class BudgetPage(QWidget):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or PlanStore()
        self.data = None
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel('당해년도 예산 · 저장된 사업의 기본 1년 산출액'))
        top.addStretch()
        refresh = QPushButton('새로고침')
        refresh.clicked.connect(self.reload)
        top.addWidget(refresh)
        root.addLayout(top)
        hint = QLabel('사업계획에서 저장한 계정과목별 금액을 합산합니다. 사업을 수정한 뒤 이 화면으로 돌아오면 갱신됩니다.\n'
                      '현재 사업 데이터는 회계연도별로 분리되지 않으며, 계정과목이 없는 사업은 합산하지 않습니다.')
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        overview = QWidget()
        layout = QHBoxLayout(overview)
        self.summary_tables = {}
        for direction, label in [('income', '세입'), ('expense', '세출')]:
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            grid = table(['관', '항', '당해년도 금액'])
            grid.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            column.addWidget(grid)
            layout.addLayout(column, 1)
            self.summary_tables[direction] = grid
        self.tabs.addTab(overview, '예산총괄표')
        details = QWidget()
        layout = QVBoxLayout(details)
        filters = QHBoxLayout()
        self.direction = QComboBox()
        for label, value in [('전체', ''), ('세입', 'income'), ('세출', 'expense')]:
            self.direction.addItem(label, value)
        self.guan, self.hang, self.mok = QComboBox(), QComboBox(), QComboBox()
        for label, combo in [('세입/세출', self.direction), ('관', self.guan), ('항', self.hang), ('목', self.mok)]:
            filters.addWidget(QLabel(label))
            filters.addWidget(combo, 1)
        layout.addLayout(filters)
        self.details = table(['번호', '구분', '관', '항', '목', '당해년도 금액', '산출내역 · 사업명 클릭'])
        self.details.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        layout.addWidget(self.details)
        self.detail_total = QLabel()
        layout.addWidget(self.detail_total)
        self.tabs.addTab(details, '예산서내역')
        self.direction.currentIndexChanged.connect(lambda: self.update_filters(0))
        self.guan.currentIndexChanged.connect(lambda: self.update_filters(1))
        self.hang.currentIndexChanged.connect(lambda: self.update_filters(2))
        self.mok.currentIndexChanged.connect(self.render_details)
        self.reload()

    def showEvent(self, event):
        super().showEvent(event)
        self.reload()

    def reload(self):
        try:
            plans = self.store.list()
            self.data = aggregate_budget(plans)
        except (OSError, ValueError) as exc:
            self.data = None
            for grid in self.summary_tables.values():
                grid.setRowCount(0)
            self.details.setRowCount(0)
            self.detail_total.clear()
            self.status.setText('예산을 불러오지 못했습니다. ' + str(exc))
            return
        amounts = self.data['totals']
        self.status.setText(f"세입 합계 {fmt(amounts['income'])}원 · 세출 합계 {fmt(amounts['expense'])}원 · "
                            f"예산 입력 사업 {sum(bool(p['accounts']) for p in plans)}개 / 전체 {len(plans)}개")
        for direction, grid in self.summary_tables.items():
            groups = GROUPS[direction]
            grid.setRowCount(len(groups) + 1)
            for row, (key, (guan, hang)) in enumerate(groups.items()):
                fill_row(grid, row, [guan, hang, f"{fmt(self.data['summary'][direction][key])}원"])
            fill_row(grid, len(groups), ['합계', '', f"{fmt(amounts[direction])}원"])
            for col in range(3):
                item = grid.item(len(groups), col)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
        self.update_filters(0, preserve=True)

    def update_filters(self, level, preserve=False):
        rows = self.data['rows'] if self.data else []
        if self.direction.currentData():
            rows = [r for r in rows if r['direction'] == self.direction.currentData()]
        for index, (combo, key) in enumerate([(self.guan, 'guan'), (self.hang, 'hang'), (self.mok, 'account_id')]):
            if index >= level:
                selected = combo.currentData() if preserve else ''
                combo.blockSignals(True)
                combo.clear()
                combo.addItem('전체', '')
                options = {r[key]: r['name'] if key == 'account_id' else r[key] for r in rows}
                for value, label in options.items():
                    combo.addItem(label, value)
                combo.setCurrentIndex(max(0, combo.findData(selected)))
                combo.blockSignals(False)
            if combo.currentData():
                rows = [r for r in rows if r[key] == combo.currentData()]
        self.render_details()

    def render_details(self, *_):
        self.details.setRowCount(0)
        if self.data is None:
            return
        sums = dict(income=0, expense=0)
        for entry in self.data['rows']:
            if any(combo.currentData() and entry[key] != combo.currentData() for combo, key in
                   [(self.direction, 'direction'), (self.guan, 'guan'), (self.hang, 'hang'), (self.mok, 'account_id')]):
                continue
            row = self.details.rowCount()
            self.details.insertRow(row)
            sums[entry['direction']] += entry['amount']
            fill_row(self.details, row, [row+1, '세입' if entry['direction'] == 'income' else '세출',
                                        entry['guan'], entry['hang'], entry['name'], f"{fmt(entry['amount'])}원"])
            if not entry['contributions']:
                self.details.setItem(row, 6, QTableWidgetItem('—'))
                continue
            container = QWidget()
            buttons = QVBoxLayout(container)
            buttons.setContentsMargins(4, 3, 4, 3)
            for contribution in entry['contributions'].values():
                plan = contribution['plan']
                button = QPushButton(f"{plan['title']} · {fmt(contribution['amount'])}원")
                button.setToolTip('\n'.join(line['formula'] for line in contribution['lines']))
                button.clicked.connect(lambda checked=False, p=plan, account=entry['account_id']: self.open_summary(p, account))
                buttons.addWidget(button)
            self.details.setCellWidget(row, 6, container)
            self.details.setRowHeight(row, container.sizeHint().height())
        self.detail_total.setText(f"표시 내역 합계: 세입 {fmt(sums['income'])}원 / 세출 {fmt(sums['expense'])}원")

    def open_summary(self, plan, account_id):
        BudgetPlanSummary(plan, account_id, self).exec()
