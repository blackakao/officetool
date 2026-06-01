import json
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QLineEdit,
    QTextEdit,
    QFormLayout,
    QDialogButtonBox,
    QMessageBox,
    QSizePolicy,
    QHeaderView,
)


class LaborCostRatioDialog(QDialog):
    def __init__(self, parent=None, item_data=None):
        super().__init__(parent)
        self.setWindowTitle("연도별 장기요양인건비 비율 추가" if item_data is None else "연도별 장기요양인건비 비율 수정")

        self.category_edit = QLineEdit()
        self.worker_edit = QTextEdit()
        self.ratio_edit = QLineEdit()

        if item_data:
            self.category_edit.setText(item_data.get("category", ""))
            self.worker_edit.setPlainText(item_data.get("worker", ""))
            self.ratio_edit.setText(item_data.get("ratio", ""))

        form_layout = QFormLayout()
        form_layout.addRow("구분:", self.category_edit)
        form_layout.addRow("장기요양요원:", self.worker_edit)
        form_layout.addRow("비율:", self.ratio_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_data(self):
        return {
            "category": self.category_edit.text().strip(),
            "worker": self.worker_edit.toPlainText().strip(),
            "ratio": self.ratio_edit.text().strip(),
        }


class LaborCostRatioPage(QWidget):
    def __init__(self):
        super().__init__()

        self.data_file = Path(__file__).resolve().parents[2] / "data" / "labor_cost_ratio.json"
        current_year = datetime.now().year
        self.current_year = str(current_year if 2021 <= current_year <= 2026 else 2026)
        self.selected_row = -1

        layout = QVBoxLayout()
        self.setLayout(layout)

        toolbar = QHBoxLayout()
        add_button = QPushButton("추가")
        self.edit_button = QPushButton("수정")
        self.delete_button = QPushButton("삭제")

        toolbar.addWidget(add_button)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        year_layout = QHBoxLayout()
        self.year_buttons = []
        for year in range(2021, 2027):
            button = QPushButton(str(year))
            button.setCheckable(True)
            button.clicked.connect(self.on_year_button_clicked)
            self.year_buttons.append(button)
            year_layout.addWidget(button)
        layout.addLayout(year_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["구분", "장기요양요원", "비율"])
        # 테이블이 가로 공간을 모두 사용하도록 설정
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        layout.addWidget(self.table)

        add_button.clicked.connect(self.add_item)
        self.edit_button.clicked.connect(self.edit_item)
        self.delete_button.clicked.connect(self.delete_item)
        self.table.itemClicked.connect(self.on_row_selected)

        self._ensure_data_file()
        self._update_year_buttons()
        self.load_data()

    def _ensure_data_file(self):
        if not self.data_file.exists():
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)

    def _load_data(self):
        with open(self.data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_data(self, data):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def on_year_button_clicked(self):
        sender = self.sender()
        if sender:
            self.current_year = sender.text()
            self._update_year_buttons()
            self.load_data()

    def _update_year_buttons(self):
        for button in self.year_buttons:
            button.setChecked(button.text() == self.current_year)

    def on_row_selected(self):
        self.selected_row = self.table.currentRow()

    def add_item(self):
        dialog = LaborCostRatioDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        new_item = dialog.get_data()
        if not new_item["category"] or not new_item["worker"] or not new_item["ratio"]:
            QMessageBox.warning(self, "입력 오류", "모든 항목을 입력해주세요.")
            return

        data = self._load_data()
        data.append({"year": self.current_year, **new_item})
        self._save_data(data)
        self.load_data()
        self.table.selectRow(self.table.rowCount() - 1)

    def edit_item(self):
        if self.selected_row < 0:
            QMessageBox.warning(self, "선택 오류", "수정할 항목을 선택해주세요.")
            return

        filtered = [item for item in self._load_data() if item.get("year") == self.current_year]
        item_data = filtered[self.selected_row]
        dialog = LaborCostRatioDialog(self, item_data)
        if dialog.exec() != QDialog.Accepted:
            return

        updated_item = dialog.get_data()
        if not updated_item["category"] or not updated_item["worker"] or not updated_item["ratio"]:
            QMessageBox.warning(self, "입력 오류", "모든 항목을 입력해주세요.")
            return

        data = self._load_data()
        index = data.index(item_data)
        data[index] = {"year": self.current_year, **updated_item}
        self._save_data(data)
        self.load_data()
        self.table.selectRow(self.selected_row)

    def delete_item(self):
        if self.selected_row < 0:
            QMessageBox.warning(self, "선택 오류", "삭제할 항목을 선택해주세요.")
            return

        reply = QMessageBox.question(self, "삭제 확인", "삭제하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        filtered = [item for item in self._load_data() if item.get("year") == self.current_year]
        item_data = filtered[self.selected_row]
        data = self._load_data()
        data.remove(item_data)
        self._save_data(data)
        self.load_data()

    def load_data(self):
        all_data = self._load_data()
        filtered = [item for item in all_data if item.get("year") == self.current_year]

        self.table.setRowCount(len(filtered))
        self.selected_row = -1

        for row, item in enumerate(filtered):
            category_item = QTableWidgetItem(item.get("category", ""))
            category_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, category_item)

            worker_item = QTableWidgetItem(item.get("worker", ""))
            worker_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, worker_item)

            ratio_item = QTableWidgetItem(item.get("ratio", ""))
            ratio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, ratio_item)

        self.table.resizeRowsToContents()
