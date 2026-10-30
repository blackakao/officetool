"""공단 매크로 단계 편집 및 작업 추가 대화상자."""

import json
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QAction, QColor, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ui.pages.federation_config import (
    ACTION_TYPES, BY_TYPES, PROCESS_ACTIONS, PROCESS_TYPES, REPEAT_MODES,
    SELECTOR_TEMPLATE, english_task_stem, ensure_selector_config, save_selector_config,
)
from ui.pages.federation_workflow import validate_workflow_structure


class SelectorTableWidget(QTableWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.drag_row = -1

    def startDrag(self, supported_actions):
        self.drag_row = self.currentRow()
        if self.drag_row < 0:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(self.drag_row))
        drag.setMimeData(mime_data)
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.drag_row < 0:
            event.ignore()
            return

        try:
            point = event.position().toPoint()
        except AttributeError:
            point = event.pos()

        target_row = self.indexAt(point).row()
        if target_row < 0:
            target_row = self.rowCount() - 1

        self.owner.move_selector_row(self.drag_row, target_row)
        self.drag_row = -1
        event.accept()


class SelectorConfigDialog(QDialog):
    def __init__(
        self,
        parent,
        config_path: Path,
        template: dict | None = None,
        task_label: str = "",
        tool_name: str = "공단툴",
    ):
        super().__init__(parent)
        self.config_path = config_path
        self.template = template or SELECTOR_TEMPLATE
        self.config = ensure_selector_config(config_path, self.template)
        title = f"{tool_name} 매크로 설정"
        self.setWindowTitle(f"{title} - {task_label}" if task_label else title)
        self.resize(1100, 760)

        layout = QVBoxLayout()
        self.setLayout(layout)

        title_text = f"작업: {task_label}\n설정 파일: {self.config_path}" if task_label else f"설정 파일: {self.config_path}"
        title = QLabel(title_text)
        title.setWordWrap(True)
        layout.addWidget(title)

        browser_layout = QHBoxLayout()
        browser_layout.addWidget(QLabel("브라우저 윈도우/탭 번호"))
        self.window_index_combo = QComboBox()
        self.window_index_combo.addItem("마지막", -1)
        for index in range(1, 51):
            self.window_index_combo.addItem(f"{index}", index)
        saved_window_index = int(self.config.get("browser", {}).get("window_index", -1))
        combo_index = self.window_index_combo.findData(saved_window_index)
        self.window_index_combo.setCurrentIndex(combo_index if combo_index >= 0 else 0)
        browser_layout.addWidget(self.window_index_combo)
        browser_layout.addWidget(QLabel("1부터 지정"))
        browser_layout.addStretch()
        layout.addLayout(browser_layout)

        action_layout = QHBoxLayout()
        add_button = QPushButton("추가")
        add_menu = QMenu(add_button)
        for type_key, type_label in PROCESS_TYPES.items():
            if type_key in {"repeat_start", "repeat_end", "condition_start", "condition_true", "condition_false", "condition_end"}:
                continue
            action = QAction(type_label, add_menu)
            action.triggered.connect(lambda _, t=type_key: self.add_selector_row(t))
            add_menu.addAction(action)
        add_menu.addSeparator()
        repeat_action = QAction("반복지점 생성", add_menu)
        repeat_action.triggered.connect(self.add_repeat_rows)
        add_menu.addAction(repeat_action)
        condition_action = QAction("조건처리 생성", add_menu)
        condition_action.triggered.connect(self.add_condition_rows)
        add_menu.addAction(condition_action)
        add_button.setMenu(add_menu)
        copy_button = QPushButton("복사")
        copy_button.clicked.connect(self.copy_selected_row)
        delete_button = QPushButton("삭제")
        delete_button.clicked.connect(self.delete_selected_row)
        action_layout.addWidget(add_button)
        action_layout.addWidget(copy_button)
        action_layout.addWidget(delete_button)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        self.table = SelectorTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["이름", "작업종류", "요소", "메인값", "보조값", "동작"])
        self.table.setDragDropMode(QAbstractItemView.DragDrop)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._refresh_selected_row_font)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self._load_table()

        guide = QLabel(
            "작업종류가 엘레멘트이면 Selenium 선택자를 사용하고, prompt 행의 값은 입력할 텍스트로 사용됩니다. "
            "짧은 대기는 레거시 동작에서 설정합니다. 반복지점 시작은 특정값 방식으로 고정되며, 동작에서 고정 반복/증가 반복을 고르고 메인값에 반복 횟수 셀렉터를 입력합니다. "
            "조건처리는 메인값에 조건 대상 셀렉터를, 보조값에 비교값을 입력합니다. "
            "텍스트 검증은 요소의 text/value를 읽어 반복번호와 비교하며, XPath에는 {repeat_number+32} 같은 반복식도 사용할 수 있습니다. "
            "테이블은 기준 행 XPath의 숫자 인덱스를 1씩 올리며 텍스트 숫자를 검증하고 클릭합니다. "
            "테이블 데이터 추출은 메인값에 표 영역 XPath, 보조값에 출력 이름을 입력합니다. "
            "표 내부를 맨 위부터 끝까지 묶음 스크롤하여 한 작업 XLSX에 표별 시트를 추가합니다. 작업 완료 시 열기를 선택할 수 있습니다."
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_table(self):
        selectors = self.config.get("selectors", {})
        self.table.setRowCount(len(selectors))
        for row, (key, selector) in enumerate(selectors.items()):
            self._set_row(row, key, selector)
        self._refresh_repeat_indentation()
        self._refresh_selected_row_font()

    def _set_row(self, row, key, selector):
        selector = dict(selector)
        label = selector.get("label", "") or key
        self.table.setItem(row, 0, QTableWidgetItem(label))
        self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, {
            name: selector[name] for name in (
                "dropdown_xpath", "expected_visible_xpath", "selection_method",
                "max_key_steps", "timeout", "wait_for_download", "download_timeout",
                "scroll", "max_scrolls", "skip_empty", "close_browser_if_false",
                "navigation_attempts", "navigation_retry_wait", "stop_branch_on_alert",
            ) if name in selector
        })

        type_combo = QComboBox()
        for type_key, type_label in PROCESS_TYPES.items():
            type_combo.addItem(type_label, type_key)
        type_index = type_combo.findData(selector.get("type", "element"))
        type_combo.setCurrentIndex(type_index if type_index >= 0 else 0)
        type_combo.setEnabled(False)
        self.table.setCellWidget(row, 1, type_combo)

        by_combo = QComboBox()
        by_combo.addItems(BY_TYPES.keys())
        if selector.get("type") == "url_navigation":
            by_combo.setCurrentIndex(-1)
        else:
            by_combo.setCurrentText(selector.get("by", "xpath"))
        self.table.setCellWidget(row, 2, by_combo)

        self.table.setItem(row, 3, QTableWidgetItem(selector.get("value", "")))

        extra_value = ""
        if selector.get("type") == "table":
            extra_value = selector.get("number_cell_selector", "div[id$='cell_0_0:text']")
        elif selector.get("type") in {"condition_start", "element"}:
            extra_value = selector.get("expected_value", "")
        elif selector.get("type") == "url_navigation":
            extra_value = selector.get("payload", "")
        elif selector.get("type") == "table_extract":
            extra_value = selector.get("output_name", "")
        self.table.setItem(row, 4, QTableWidgetItem(extra_value))

        action_combo = QComboBox()
        self.table.setCellWidget(row, 5, action_combo)
        selected_action = selector.get("repeat_mode", "fixed") if selector.get("type") == "repeat_start" else selector.get("action")
        self._refresh_action_combo(row, selected_action)
        action_combo.currentIndexChanged.connect(lambda _, r=row: self._refresh_row_controls(r))
        self._refresh_row_controls(row)

    def _refresh_action_combo(self, row, selected_action=None):
        type_combo = self.table.cellWidget(row, 1)
        action_combo = self.table.cellWidget(row, 5)
        if not action_combo:
            return
        process_type = type_combo.currentData() if type_combo else "element"
        actions = REPEAT_MODES if process_type == "repeat_start" else PROCESS_ACTIONS.get(process_type, ACTION_TYPES)
        selected_action = selected_action or action_combo.currentData()
        action_combo.clear()
        for action_key, action_label in actions.items():
            action_combo.addItem(action_label, action_key)
        action_index = action_combo.findData(selected_action)
        action_combo.setCurrentIndex(action_index if action_index >= 0 else 0)
        self._refresh_row_controls(row)

    def _refresh_row_controls(self, row):
        type_combo = self.table.cellWidget(row, 1)
        by_combo = self.table.cellWidget(row, 2)
        number_cell_item = self.table.item(row, 4)
        process_type = type_combo.currentData() if type_combo else "element"
        if by_combo:
            action_combo = self.table.cellWidget(row, 5)
            is_range = process_type == "repeat_start" and action_combo and action_combo.currentData() == "range"
            by_combo.setEnabled(
                not is_range and (process_type in {"element", "table", "table_extract", "text_assert", "condition_start"}
                or process_type == "repeat_start")
            )
            if is_range:
                self.table.item(row, 3).setToolTip("횟수 셀렉터를 사용하지 않습니다. 메인 화면의 범위 반복값 설정을 사용합니다.")
        if number_cell_item:
            number_cell_item.setFlags(
                number_cell_item.flags() | Qt.ItemFlag.ItemIsEditable
                if process_type in {"table", "table_extract", "condition_start", "url_navigation", "element"}
                else number_cell_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            if process_type == "table_extract":
                number_cell_item.setToolTip("작업 XLSX 안의 시트 이름(생략하면 단계 이름). 저장 위치: data/runtime/macro_exports. 작업 완료 시 파일 하나를 엽니다.")

    def _row_data(self, row):
        label_item = self.table.item(row, 0)
        type_combo = self.table.cellWidget(row, 1)
        by_combo = self.table.cellWidget(row, 2)
        value_item = self.table.item(row, 3)
        number_cell_item = self.table.item(row, 4)
        action_combo = self.table.cellWidget(row, 5)
        number_cell_selector = number_cell_item.text().strip() if number_cell_item else ""
        process_type = type_combo.currentData() if type_combo else "element"
        action = action_combo.currentData() if action_combo else "click"
        selector = {
            "label": label_item.text().strip() if label_item else "",
            "type": process_type,
            "repeat_mode": action if process_type == "repeat_start" else "fixed",
            "by": "" if process_type == "url_navigation" else (by_combo.currentText() if by_combo else "xpath"),
            "value": value_item.text().strip() if value_item else "",
            "required": not (
                process_type in {"alert", "confirm", "prompt"}
                and str(action).endswith("_if_present")
            ),
            "action": "element_text" if process_type == "repeat_start" else action,
        }
        if process_type == "table" and number_cell_selector:
            selector["number_cell_selector"] = number_cell_selector
        if process_type in {"condition_start", "element"} and number_cell_selector:
            selector["expected_value"] = number_cell_selector
        if process_type == "url_navigation":
            selector["payload"] = number_cell_selector
        if process_type == "table_extract":
            selector["output_name"] = number_cell_selector
        metadata = label_item.data(Qt.ItemDataRole.UserRole) if label_item else {}
        if metadata:
            selector.update({
                name: metadata[name]
                for name in ("timeout", "wait_for_download", "download_timeout", "scroll", "max_scrolls", "skip_empty", "close_browser_if_false",
                             "navigation_attempts", "navigation_retry_wait", "stop_branch_on_alert")
                if name in metadata
            })
        if process_type == "element" and action in {"select_text", "pointer_click", "hover_click"} and label_item:
            selector.update({
                key: value for key, value in (metadata or {}).items()
                if key != "timeout"
            })
        return (
            "",
            selector,
        )

    def _all_row_data(self):
        return [self._row_data(row) for row in range(self.table.rowCount())]

    def _rebuild_table(self, rows):
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for row, (key, selector) in enumerate(rows):
            self._set_row(row, key, selector)
        self._refresh_repeat_indentation()
        self._refresh_selected_row_font()

    def move_selector_row(self, source_row, target_row):
        if source_row == target_row or source_row < 0 or target_row < 0:
            return
        rows = self._all_row_data()
        if source_row >= len(rows) or target_row >= len(rows):
            return
        move_indices = self._paired_move_indices(rows, source_row)
        if target_row in move_indices:
            return
        moving_rows = [rows[index] for index in move_indices]
        remaining_rows = [row for index, row in enumerate(rows) if index not in move_indices]
        insert_row = target_row - sum(1 for index in move_indices if index < target_row)
        insert_row = max(0, min(insert_row, len(remaining_rows)))
        rows = remaining_rows[:insert_row] + moving_rows + remaining_rows[insert_row:]
        self._rebuild_table(rows)
        self.table.selectRow(insert_row)

    def _paired_move_indices(self, rows, source_row):
        process_type = rows[source_row][1].get("type", "element")
        if process_type in {"repeat_start", "repeat_end"}:
            return self._repeat_marker_indices(rows, source_row)
        if process_type in {"condition_start", "condition_true", "condition_false", "condition_end"}:
            return self._condition_marker_indices(rows, source_row)
        return [source_row]

    def _repeat_marker_indices(self, rows, source_row):
        process_type = rows[source_row][1].get("type", "element")
        if process_type == "repeat_start":
            start_index = source_row
            end_index = self._matching_repeat_end(rows, source_row)
        else:
            start_index = self._matching_repeat_start(rows, source_row)
            end_index = source_row
        if start_index is None or end_index is None:
            return [source_row]
        return sorted([start_index, end_index])

    def _matching_repeat_end(self, rows, start_row):
        depth = 0
        for index in range(start_row, len(rows)):
            process_type = rows[index][1].get("type", "element")
            if process_type == "repeat_start":
                depth += 1
            elif process_type == "repeat_end":
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _matching_repeat_start(self, rows, end_row):
        depth = 0
        for index in range(end_row, -1, -1):
            process_type = rows[index][1].get("type", "element")
            if process_type == "repeat_end":
                depth += 1
            elif process_type == "repeat_start":
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _condition_marker_indices(self, rows, source_row):
        start_index = self._condition_start_index(rows, source_row)
        if start_index is None:
            return [source_row]
        indices = self._matching_condition_indices(rows, start_index)
        return indices or [source_row]

    def _condition_start_index(self, rows, source_row):
        process_type = rows[source_row][1].get("type", "element")
        if process_type == "condition_start":
            return source_row

        for index, (_, selector) in enumerate(rows):
            if selector.get("type", "element") != "condition_start":
                continue
            indices = self._matching_condition_indices(rows, index)
            if indices and source_row in indices:
                return index
        return None

    def _matching_condition_indices(self, rows, start_row):
        depth = 0
        true_index = None
        false_index = None
        for index in range(start_row, len(rows)):
            process_type = rows[index][1].get("type", "element")
            if process_type == "condition_start":
                depth += 1
            elif process_type == "condition_true" and depth == 1:
                true_index = index
            elif process_type == "condition_false" and depth == 1:
                false_index = index
            elif process_type == "condition_end":
                if depth == 1:
                    if true_index is None or false_index is None:
                        return None
                    return [start_row, true_index, false_index, index]
                depth -= 1
        return None

    def _refresh_repeat_indentation(self):
        repeat_depth = 0
        condition_stack = []
        for row in range(self.table.rowCount()):
            type_combo = self.table.cellWidget(row, 1)
            process_type = type_combo.currentData() if type_combo else "element"

            if process_type == "condition_false" and condition_stack and condition_stack[-1] == "condition_true":
                condition_stack.pop()
            elif process_type == "condition_end" and condition_stack:
                if condition_stack[-1] in {"condition_true", "condition_false"}:
                    condition_stack.pop()
                if condition_stack and condition_stack[-1] == "condition":
                    condition_stack.pop()

            if repeat_depth > 0 or process_type in {"repeat_start", "repeat_end"}:
                color_role = "repeat"
            elif process_type == "condition_start":
                color_role = "condition"
            elif process_type == "condition_true":
                color_role = "condition_true"
            elif process_type == "condition_false":
                color_role = "condition_false"
            else:
                color_role = condition_stack[-1] if condition_stack else None

            self._apply_repeat_row_style(row, color_role)

            if process_type == "repeat_start":
                repeat_depth += 1
            elif process_type == "repeat_end":
                repeat_depth = max(0, repeat_depth - 1)
            elif process_type == "condition_start":
                condition_stack.append("condition")
            elif process_type == "condition_true":
                condition_stack.append("condition_true")
            elif process_type == "condition_false":
                condition_stack.append("condition_false")

    def _apply_repeat_row_style(self, row, color_role):
        colors = {
            "repeat": "#eeeeee",
            "condition": "#f4f7fb",
            "condition_true": "#dbeafe",
            "condition_false": "#fee2e2",
        }
        color_value = colors.get(color_role, "#ffffff")
        color = QColor(color_value)
        widget_style = f"background-color: {color_value};" if color_role else ""
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item:
                item.setBackground(color)
            widget = self.table.cellWidget(row, column)
            if widget:
                widget.setStyleSheet(widget_style)
        self._refresh_selected_row_font()

    def _refresh_selected_row_font(self):
        current_row = self.table.currentRow()
        for row in range(self.table.rowCount()):
            bold = row == current_row
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                if item:
                    font = item.font()
                    font.setBold(bold)
                    item.setFont(font)
                widget = self.table.cellWidget(row, column)
                if widget:
                    font = widget.font()
                    font.setBold(bold)
                    widget.setFont(font)

    def _auto_selector_key(self, row, selector):
        process_type = selector.get("type", "element")
        return f"{process_type}_{row + 1:03d}"

    def add_selector_row(self, process_type="element"):
        if process_type == "repeat_start":
            self.add_repeat_rows()
            return

        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_row(row, self._auto_selector_key(row, {"type": process_type}), {
            "label": f"새 {PROCESS_TYPES.get(process_type, '요소')}",
            "type": process_type,
            "repeat_mode": "fixed",
            "by": "xpath",
            "value": "",
            "required": True,
            "action": next(iter(PROCESS_ACTIONS.get(process_type, ACTION_TYPES))),
        })
        self._refresh_repeat_indentation()
        self.table.selectRow(row)

    def add_repeat_rows(self):
        insert_row = self.table.currentRow()
        if insert_row < 0:
            insert_row = self.table.rowCount()
        else:
            insert_row += 1

        self.table.insertRow(insert_row)
        self._set_row(insert_row, self._auto_selector_key(insert_row, {"type": "repeat_start"}), {
            "label": "반복지점 시작",
            "type": "repeat_start",
            "repeat_mode": "fixed",
            "by": "xpath",
            "value": "",
            "required": True,
            "action": "element_text",
        })
        self.table.insertRow(insert_row + 1)
        self._set_row(insert_row + 1, self._auto_selector_key(insert_row + 1, {"type": "repeat_end"}), {
            "label": "반복지점 종료",
            "type": "repeat_end",
            "repeat_mode": "fixed",
            "by": "xpath",
            "value": "",
            "required": True,
            "action": "end",
        })
        self._refresh_repeat_indentation()
        self.table.selectRow(insert_row)

    def add_condition_rows(self):
        insert_row = self.table.currentRow()
        if insert_row < 0:
            insert_row = self.table.rowCount()
        else:
            insert_row += 1

        rows = [
            {
                "label": "조건처리의 조건",
                "type": "condition_start",
                "repeat_mode": "fixed",
                "by": "xpath",
                "value": "",
                "expected_value": "",
                "required": True,
                "action": "text_exists",
            },
            {
                "label": "조건처리-참",
                "type": "condition_true",
                "repeat_mode": "fixed",
                "by": "xpath",
                "value": "",
                "required": True,
                "action": "branch",
            },
            {
                "label": "조건처리-거짓",
                "type": "condition_false",
                "repeat_mode": "fixed",
                "by": "xpath",
                "value": "",
                "required": True,
                "action": "branch",
            },
            {
                "label": "조건처리 종료",
                "type": "condition_end",
                "repeat_mode": "fixed",
                "by": "xpath",
                "value": "",
                "required": True,
                "action": "end",
            },
        ]
        for offset, selector in enumerate(rows):
            self.table.insertRow(insert_row + offset)
            self._set_row(
                insert_row + offset,
                self._auto_selector_key(insert_row + offset, selector),
                selector,
            )
        self._refresh_repeat_indentation()
        self.table.selectRow(insert_row)

    def copy_selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "복사 실패", "복사할 작업을 선택하세요.")
            return

        rows = self._all_row_data()
        if row >= len(rows):
            return
        copy_indices = self._paired_move_indices(rows, row)
        copied_rows = [
            ("", json.loads(json.dumps(rows[index][1], ensure_ascii=False)))
            for index in copy_indices
        ]
        insert_row = max(copy_indices) + 1
        rows = rows[:insert_row] + copied_rows + rows[insert_row:]
        self._rebuild_table(rows)
        self.table.selectRow(insert_row)

    def delete_selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "삭제 실패", "삭제할 요소를 선택하세요.")
            return

        rows = self._all_row_data()
        if row >= len(rows):
            return
        delete_indices = self._paired_move_indices(rows, row)
        label_item = self.table.item(row, 0)
        label = label_item.text() if label_item else ""
        delete_count = len(delete_indices)
        suffix = f" 외 {delete_count - 1}개" if delete_count > 1 else ""
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"'{label}'{suffix} 작업을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            remaining_rows = [item for index, item in enumerate(rows) if index not in delete_indices]
            self._rebuild_table(remaining_rows)
            if remaining_rows:
                self.table.selectRow(min(min(delete_indices), len(remaining_rows) - 1))

    def _validate_repeat_pairs(self, rows):
        try:
            return validate_workflow_structure(rows)
        except ValueError as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return False

    def save(self):
        selectors = {}
        seen_keys = set()
        rows = [
            (self._auto_selector_key(row, selector), selector)
            for row, (_, selector) in enumerate(self._all_row_data())
        ]
        if not self._validate_repeat_pairs(rows):
            return

        for key, selector in rows:
            if key in seen_keys:
                QMessageBox.warning(self, "저장 실패", f"중복된 요소 키입니다: {key}")
                return
            seen_keys.add(key)
            selectors[key] = selector

        self.config["selectors"] = selectors
        template_selector_keys = set(self.template.get("selectors", {}).keys())
        deleted_selector_keys = set(self.config.get("deleted_selector_keys", []))
        deleted_selector_keys.update(template_selector_keys - set(selectors.keys()))
        deleted_selector_keys.difference_update(selectors.keys())
        self.config["deleted_selector_keys"] = sorted(deleted_selector_keys)
        self.config.setdefault("browser", {})["window_index"] = self.window_index_combo.currentData()
        save_selector_config(self.config_path, self.config)
        QMessageBox.information(self, "저장 완료", "매크로 설정을 저장했습니다.")
        self.accept()


class TaskConfigDialog(QDialog):
    def __init__(self, parent, existing_keys: set[str]):
        super().__init__(parent)
        self.existing_keys = existing_keys
        self.setWindowTitle("작업 추가")
        self.resize(420, 180)

        layout = QVBoxLayout()
        self.setLayout(layout)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("작업의 이름", self.name_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def task_data(self):
        label = self.name_edit.text().strip()
        base = english_task_stem(label)
        task_key = base
        suffix = 2
        while task_key in self.existing_keys:
            task_key = f"{base}_{suffix}"
            suffix += 1
        config_file = f"federation_selectors_{task_key}.json"
        return task_key, {
            "label": label,
            "config_file": config_file,
            "template_name": "empty",
            "implemented": True,
        }

    def accept(self):
        task_key, task_config = self.task_data()
        if not task_config["label"]:
            QMessageBox.warning(self, "작업 추가", "작업의 이름을 입력하세요.")
            return
        super().accept()
