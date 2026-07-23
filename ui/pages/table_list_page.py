import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.pages.document_tool import read_json_file, write_json_file


def normalize_table_data(data):
    if not isinstance(data, dict):
        return {"version": 1, "tables": []}
    tables = data.get("tables", [])
    return {
        "version": 1,
        "tables": [table for table in tables if isinstance(table, dict)],
    }


def table_values(table):
    """Return table storage as a one-dimensional list of cell values."""
    values = []
    for row in table.get("cells", []):
        if isinstance(row, list):
            values.extend(str(value) for value in row)
    return values


def table_item_count(table):
    return len(table_values(table))


def reordered_values(values, source_row, insertion_row):
    values = list(values)
    if source_row < 0 or source_row >= len(values):
        return values, source_row
    insertion_row = max(0, min(insertion_row, len(values)))
    value = values.pop(source_row)
    if insertion_row > source_row:
        insertion_row -= 1
    values.insert(insertion_row, value)
    return values, insertion_row


class ReorderableTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_row = -1
        self._drag_start = None
        self._dragging = False

    def _values(self):
        return [
            self.item(row, 0).text() if self.item(row, 0) else ""
            for row in range(self.rowCount())
        ]

    def _replace_values(self, values, selected_row):
        self.setRowCount(0)
        for value in values:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, 0, QTableWidgetItem(value))
        if 0 <= selected_row < self.rowCount():
            self.selectRow(selected_row)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self._drag_row = self.indexAt(event.position().toPoint()).row()
            self._drag_start = event.position().toPoint()
            self._dragging = False

    def mouseMoveEvent(self, event):
        if self._drag_row < 0 or self._drag_start is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if not self._dragging:
            distance = (event.position().toPoint() - self._drag_start).manhattanLength()
            if distance < QApplication.startDragDistance():
                super().mouseMoveEvent(event)
                return
            self._dragging = True

        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row < 0:
            target_row = self.rowCount() - 1 if event.position().y() > 0 else 0
        if target_row == self._drag_row:
            return

        values = self._values()
        moved_value = values.pop(self._drag_row)
        values.insert(target_row, moved_value)
        self._replace_values(values, target_row)
        self._drag_row = target_row

    def mouseReleaseEvent(self, event):
        was_dragging = self._dragging
        self._drag_row = -1
        self._drag_start = None
        self._dragging = False
        if was_dragging:
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TableEditorDialog(QDialog):
    def __init__(self, parent=None, table_data=None):
        super().__init__(parent)
        self.table_data = table_data or {"id": uuid.uuid4().hex, "name": "", "cells": [[""]]}
        self.setWindowTitle("테이블 수정")
        self.resize(850, 600)

        self.name_edit = QLineEdit(str(self.table_data.get("name", "")))
        name_layout = QFormLayout()
        name_layout.addRow("테이블명", self.name_edit)

        self.table = ReorderableTableWidget()
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["값"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._load_cells(self.table_data.get("cells", [[""]]))

        add_row_button = QPushButton("줄추가")
        delete_button = QPushButton("선택 줄 삭제")
        add_row_button.clicked.connect(self._add_row)
        delete_button.clicked.connect(self._delete_selected)

        tools = QHBoxLayout()
        tools.addWidget(add_row_button)
        tools.addWidget(delete_button)
        tools.addStretch()
        tools.addWidget(QLabel("줄을 드래그하면 순서를 바꿀 수 있습니다."))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(name_layout)
        layout.addLayout(tools)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _load_cells(self, cells):
        values = table_values({"cells": cells}) or [""]
        self.table.setRowCount(len(values))
        for row_index, value in enumerate(values):
            self.table.setItem(row_index, 0, QTableWidgetItem(value))

    def _add_row(self):
        self.table.insertRow(self.table.rowCount())

    def _delete_selected(self):
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in selected_rows:
            self.table.removeRow(row)

        if self.table.rowCount() == 0:
            self.table.insertRow(0)

    def _accept_if_valid(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "입력 확인", "테이블명을 입력해 주세요.")
            return
        self.accept()

    def get_data(self):
        cells = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            cells.append([item.text().strip() if item else ""])
        return {
            "id": self.table_data.get("id") or uuid.uuid4().hex,
            "name": self.name_edit.text().strip(),
            "cells": cells,
        }


class TableListPage(QWidget):
    def __init__(self):
        super().__init__()
        self.data_file = Path(__file__).resolve().parents[2] / "data" / "table_lists.json"

        add_button = QPushButton("추가")
        delete_button = QPushButton("삭제")
        add_button.clicked.connect(self.add_table)
        delete_button.clicked.connect(self.delete_table)

        tools = QHBoxLayout()
        tools.addWidget(add_button)
        tools.addWidget(delete_button)
        tools.addStretch()

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["테이블명", "개수"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.edit_table)

        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.table)
        self.load_data()

    def _load(self):
        return normalize_table_data(read_json_file(self.data_file, {"version": 1, "tables": []}))

    def _save(self, data):
        write_json_file(self.data_file, normalize_table_data(data))

    def load_data(self):
        tables = self._load()["tables"]
        self.table.setRowCount(len(tables))
        for row, table in enumerate(tables):
            name_item = QTableWidgetItem(str(table.get("name", "")))
            size_item = QTableWidgetItem(str(table_item_count(table)))
            name_item.setData(Qt.UserRole, table.get("id"))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, size_item)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()

    def add_table(self):
        name, accepted = QInputDialog.getText(self, "테이블 추가", "테이블명")
        if not accepted or not name.strip():
            return
        data = self._load()
        table = {"id": uuid.uuid4().hex, "name": name.strip(), "cells": [[""]]}
        dialog = TableEditorDialog(self, table)
        if dialog.exec() != QDialog.Accepted:
            return
        data["tables"].append(dialog.get_data())
        self._save(data)
        self.load_data()

    def edit_table(self, row, _column=0):
        data = self._load()
        if row < 0 or row >= len(data["tables"]):
            return
        dialog = TableEditorDialog(self, data["tables"][row])
        if dialog.exec() != QDialog.Accepted:
            return
        data["tables"][row] = dialog.get_data()
        self._save(data)
        self.load_data()
        self.table.selectRow(row)

    def delete_table(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 확인", "삭제할 테이블을 선택해 주세요.")
            return
        if QMessageBox.question(
            self,
            "삭제 확인",
            "선택한 테이블을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        data = self._load()
        if row < len(data["tables"]):
            del data["tables"][row]
            self._save(data)
        self.load_data()
