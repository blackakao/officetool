import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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


def table_dimensions(table):
    cells = table.get("cells", [])
    row_count = len(cells)
    column_count = max((len(row) for row in cells if isinstance(row, list)), default=0)
    return row_count, column_count


def table_row_options(table):
    options = []
    for row in table.get("cells", []):
        if not isinstance(row, list):
            continue
        values = [str(value).strip() for value in row]
        if any(values):
            options.append(" / ".join(value for value in values if value))
    return options


class TableEditorDialog(QDialog):
    def __init__(self, parent=None, table_data=None):
        super().__init__(parent)
        self.table_data = table_data or {"id": uuid.uuid4().hex, "name": "", "cells": [[""]]}
        self.setWindowTitle("테이블 수정")
        self.resize(850, 600)

        self.name_edit = QLineEdit(str(self.table_data.get("name", "")))
        name_layout = QFormLayout()
        name_layout.addRow("테이블명", self.name_edit)

        self.table = QTableWidget()
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().sectionClicked.connect(self.table.selectColumn)
        self.table.verticalHeader().sectionClicked.connect(self.table.selectRow)
        self._load_cells(self.table_data.get("cells", [[""]]))

        add_row_button = QPushButton("줄추가")
        add_column_button = QPushButton("칸추가")
        delete_button = QPushButton("삭제")
        add_row_button.clicked.connect(self._add_row)
        add_column_button.clicked.connect(self._add_column)
        delete_button.clicked.connect(self._delete_selected)

        tools = QHBoxLayout()
        tools.addWidget(add_row_button)
        tools.addWidget(add_column_button)
        tools.addWidget(delete_button)
        tools.addStretch()
        tools.addWidget(QLabel("행/열 헤더를 클릭하면 전체를 선택할 수 있습니다."))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(name_layout)
        layout.addLayout(tools)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _load_cells(self, cells):
        rows = [row for row in cells if isinstance(row, list)] or [[""]]
        columns = max((len(row) for row in rows), default=1) or 1
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(columns)
        for row_index, row in enumerate(rows):
            for column_index in range(columns):
                value = row[column_index] if column_index < len(row) else ""
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(value)))

    def _add_row(self):
        self.table.insertRow(self.table.rowCount())

    def _add_column(self):
        self.table.insertColumn(self.table.columnCount())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def _delete_selected(self):
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        selected_columns = sorted({index.column() for index in self.table.selectedIndexes()}, reverse=True)
        all_columns = self.table.columnCount() > 0 and all(
            self.table.item(row, column) is None or self.table.item(row, column).isSelected()
            for row in range(self.table.rowCount())
            for column in selected_columns
        )
        all_rows = self.table.rowCount() > 0 and all(
            self.table.item(row, column) is None or self.table.item(row, column).isSelected()
            for row in selected_rows
            for column in range(self.table.columnCount())
        )

        if all_columns and selected_columns:
            for column in selected_columns:
                self.table.removeColumn(column)
        elif all_rows and selected_rows:
            for row in selected_rows:
                self.table.removeRow(row)
        else:
            for item in self.table.selectedItems():
                item.setText("")

        if self.table.rowCount() == 0:
            self.table.insertRow(0)
        if self.table.columnCount() == 0:
            self.table.insertColumn(0)

    def _accept_if_valid(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "입력 확인", "테이블명을 입력해 주세요.")
            return
        self.accept()

    def get_data(self):
        cells = []
        for row in range(self.table.rowCount()):
            cells.append([
                self.table.item(row, column).text().strip() if self.table.item(row, column) else ""
                for column in range(self.table.columnCount())
            ])
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
        self.table.setHorizontalHeaderLabels(["테이블명", "컬럼수"])
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
            rows, columns = table_dimensions(table)
            name_item = QTableWidgetItem(str(table.get("name", "")))
            size_item = QTableWidgetItem(f"{rows} X {columns}")
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
