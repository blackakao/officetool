from collections import defaultdict
from datetime import date, timedelta
import calendar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QSizePolicy,
    QHeaderView,
)


def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_years(source_date, years):
    try:
        return source_date.replace(year=source_date.year + years)
    except ValueError:
        return source_date.replace(year=source_date.year + years, month=2, day=28)


def annual_leave_days_for_service_years(service_years):
    return min(15 + (service_years - 1) // 2, 25)


def calculate_annual_leave(start_date, end_date):
    yearly = defaultdict(lambda: {"monthly": 0, "annual": 0})

    for month_count in range(1, 12):
        accrued_date = add_months(start_date, month_count)
        if accrued_date > end_date:
            break
        yearly[accrued_date.year]["monthly"] += 1

    service_years = 1
    while True:
        accrued_date = add_years(start_date, service_years)
        if accrued_date > end_date:
            break
        yearly[accrued_date.year]["annual"] += annual_leave_days_for_service_years(service_years)
        service_years += 1

    return {
        year: {
            "monthly": days["monthly"],
            "annual": days["annual"],
            "total": days["monthly"] + days["annual"],
        }
        for year, days in sorted(yearly.items())
    }


class AnnualLeavePage(QWidget):
    def __init__(self):
        super().__init__()

        today = date.today()
        default_start = today - timedelta(days=365)
        self.year_min = today.year - 30
        self.year_max = today.year + 1

        layout = QVBoxLayout()
        self.setLayout(layout)

        title = QLabel("연차 계산기")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        form_layout = QFormLayout()
        self.start_year_combo, self.start_month_combo, self.start_day_combo = self._create_date_selects(default_start)
        self.end_year_combo, self.end_month_combo, self.end_day_combo = self._create_date_selects(today)

        form_layout.addRow("시작일:", self._date_row(self.start_year_combo, self.start_month_combo, self.start_day_combo))
        form_layout.addRow("종료일:", self._date_row(self.end_year_combo, self.end_month_combo, self.end_day_combo))
        layout.addLayout(form_layout)

        toolbar = QHBoxLayout()
        calculate_button = QPushButton("계산하기")
        calculate_button.clicked.connect(self.calculate)
        toolbar.addWidget(calculate_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        l2_label = QLabel("L2 - 연도별 발생 연차")
        l2_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(l2_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["연도", "월차", "연차", "합계"])
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.total_label = QLabel("총합계: 0개")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.total_label)

        self.calculate()

    def _create_date_selects(self, selected_date):
        year_combo = QComboBox()
        month_combo = QComboBox()
        day_combo = QComboBox()

        for year in range(self.year_min, self.year_max + 1):
            year_combo.addItem(str(year), year)
        for month in range(1, 13):
            month_combo.addItem(str(month), month)

        year_combo.setCurrentText(str(selected_date.year))
        month_combo.setCurrentText(str(selected_date.month))
        self._refresh_days(year_combo, month_combo, day_combo, selected_date.day)

        year_combo.currentIndexChanged.connect(lambda: self._refresh_days(year_combo, month_combo, day_combo))
        month_combo.currentIndexChanged.connect(lambda: self._refresh_days(year_combo, month_combo, day_combo))

        return year_combo, month_combo, day_combo

    def _date_row(self, year_combo, month_combo, day_combo):
        row = QHBoxLayout()
        row.addWidget(year_combo)
        row.addWidget(QLabel("년"))
        row.addWidget(month_combo)
        row.addWidget(QLabel("월"))
        row.addWidget(day_combo)
        row.addWidget(QLabel("일"))
        row.addStretch()

        container = QWidget()
        container.setLayout(row)
        return container

    def _refresh_days(self, year_combo, month_combo, day_combo, selected_day=None):
        current_day = selected_day or day_combo.currentData() or 1
        year = year_combo.currentData()
        month = month_combo.currentData()
        day_count = calendar.monthrange(year, month)[1]

        day_combo.blockSignals(True)
        day_combo.clear()
        for day in range(1, day_count + 1):
            day_combo.addItem(str(day), day)
        day_combo.setCurrentText(str(min(current_day, day_count)))
        day_combo.blockSignals(False)

    def _selected_date(self, year_combo, month_combo, day_combo):
        return date(year_combo.currentData(), month_combo.currentData(), day_combo.currentData())

    def calculate(self):
        start_date = self._selected_date(self.start_year_combo, self.start_month_combo, self.start_day_combo)
        end_date = self._selected_date(self.end_year_combo, self.end_month_combo, self.end_day_combo)

        if start_date > end_date:
            QMessageBox.warning(self, "입력 오류", "시작일은 종료일보다 늦을 수 없습니다.")
            return

        yearly = calculate_annual_leave(start_date, end_date)
        total = sum(days["total"] for days in yearly.values())

        self.table.setRowCount(len(yearly))
        for row, (year, days) in enumerate(yearly.items()):
            year_item = QTableWidgetItem(str(year))
            year_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, year_item)

            monthly_item = QTableWidgetItem(f"{days['monthly']}개")
            monthly_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, monthly_item)

            annual_item = QTableWidgetItem(f"{days['annual']}개")
            annual_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, annual_item)

            total_item = QTableWidgetItem(f"{days['total']}개")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, total_item)

        self.total_label.setText(f"총합계: {total}개")
