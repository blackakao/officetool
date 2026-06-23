import json
import re
import time
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QThread, Signal
from PySide6.QtGui import QAction, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from ui.pages.login_tool import LongtermLoginThread
from ui.pages.logging_util import log


BY_TYPES = {
    "xpath": By.XPATH,
    "css": By.CSS_SELECTOR,
    "id": By.ID,
    "name": By.NAME,
    "class": By.CLASS_NAME,
    "tag": By.TAG_NAME,
}


ACTION_TYPES = {
    "click": "클릭",
    "hover": "호버",
    "hover_click": "호버 후 클릭",
}

PROCESS_TYPES = {
    "element": "요소",
    "alert": "alert",
    "confirm": "confirm",
    "prompt": "prompt",
    "window": "새창/팝업창",
    "delay": "delay",
    "repeat_start": "반복 시작",
    "repeat_end": "반복 끝",
}

PROCESS_ACTIONS = {
    "element": ACTION_TYPES,
    "alert": {"accept": "확인/수락", "dismiss": "취소/닫기"},
    "confirm": {"accept": "확인/수락", "dismiss": "취소/닫기"},
    "prompt": {"accept": "텍스트 입력 후 확인", "dismiss": "취소/닫기"},
    "window": {"keep": "유지", "switch_last": "마지막 창으로 전환", "close_extra": "추가 창 닫기"},
    "delay": {"sleep": "sleep"},
    "repeat_start": {"fixed_count": "고정 횟수", "element_text": "요소 값에서 횟수", "element_count": "요소 개수만큼"},
    "repeat_end": {"end": "반복 끝"},
}


SELECTOR_TEMPLATE = {
    "version": 1,
    "timeouts": {"default": 20, "short": 3, "long": 60, "loading": 120},
    "browser": {"window_index": -1},
    "selectors": {
        "layer_popup_close": {"label": "레이어 팝업 닫기", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "layer_popup_confirm": {"label": "레이어 팝업 확인", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "browser_popup_close_button": {"label": "브라우저 팝업 닫기 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "main_menu": {"label": "상단 메뉴 - 급여비용청구", "type": "element", "by": "xpath", "value": "", "required": True, "action": "hover_click"},
        "payroll_claim_dropdown": {"label": "드롭다운 메뉴 - 급여비용청구", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "claim_page_warning_close": {"label": "급여비용청구 페이지 경고 모달 닫기/확인", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "operation_guide_close": {"label": "운영안내 팝업 닫기", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "claim_button": {"label": "우측 주황색 청구하기 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "entry_notice_tab": {"label": "원청구 모달 탭 - 입퇴소신고내용관리", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "entry_notice_rows": {"label": "입소신고자 테이블 행 목록", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "recipient_select_all_checkbox": {"label": "수급자명 테이블 상단 전체 체크박스", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "recipient_checkboxes": {"label": "수급자명 테이블 개별 체크박스 목록", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "add_recipient_button": {"label": "청구대상자로 넘기는 > 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "confirm_add_recipient": {"label": "청구대상자로 추가 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "loading_canvas": {"label": "진행중 캔버스/로딩 요소", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "claim_target_created_message": {"label": "청구대상자가 생성되었습니다 알림/확인", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "salary_data_tab": {"label": "원청구 모달 탭 - 급여내용 자료 관리", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "search_button": {"label": "급여내용 자료 관리 조회 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "claim_target_rows": {"label": "청구대상자 테이블 행 목록", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "save_button": {"label": "저장 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "confirm_save": {"label": "급여자료 저장 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "save_completed_confirm": {"label": "저장되었습니다 알림 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "generate_statement_button": {"label": "명세서자동생성 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "statement_register_complete_button": {"label": "자식 모달 - 명세서 등록완료 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "pay_result_select": {"label": "급여제공결과등록 - 급여제공결과 셀렉트", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "pay_result_continue_option": {"label": "급여제공결과 셀렉트 옵션 - 계속", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "pay_result_save_button": {"label": "급여제공결과등록 저장 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "confirm_pay_result_save": {"label": "급여제공결과 저장 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "statement_completed_confirm": {"label": "명세서가 등록완료되었습니다 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "statement_auto_modal_close": {"label": "시설/단기보호 청구명세서 자동생성 닫기", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
    },
    "popup_close_selectors": [
        {"label": "공통 버튼 - 닫기", "by": "xpath", "value": "//button[normalize-space(.)='닫기']"},
        {"label": "공통 버튼 - 확인", "by": "xpath", "value": "//button[normalize-space(.)='확인']"},
        {"label": "공통 링크 - 닫기", "by": "xpath", "value": "//a[normalize-space(.)='닫기']"},
        {"label": "공통 링크 - 확인", "by": "xpath", "value": "//a[normalize-space(.)='확인']"},
    ],
}


EMPTY_SELECTOR_TEMPLATE = {
    "version": 1,
    "timeouts": {"default": 20, "short": 3, "long": 60, "loading": 120},
    "browser": {"window_index": -1},
    "selectors": {},
    "popup_close_selectors": [
        {"label": "공통 버튼 - 닫기", "by": "xpath", "value": "//button[normalize-space(.)='닫기']"},
        {"label": "공통 버튼 - 확인", "by": "xpath", "value": "//button[normalize-space(.)='확인']"},
        {"label": "공통 링크 - 닫기", "by": "xpath", "value": "//a[normalize-space(.)='닫기']"},
        {"label": "공통 링크 - 확인", "by": "xpath", "value": "//a[normalize-space(.)='확인']"},
    ],
}


TASK_CONFIGS = {
    "invoice": {"label": "청구 명세서 만들기", "config_file": "federation_selectors_invoice.json", "template": SELECTOR_TEMPLATE, "implemented": True},
    "long_service": {"label": "장기근속수당 입력하기", "config_file": "federation_selectors_long_service.json", "template": EMPTY_SELECTOR_TEMPLATE, "implemented": False},
}

def ensure_selector_config(path: Path, template: dict | None = None) -> dict:
    template = template or SELECTOR_TEMPLATE
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        data = json.loads(json.dumps(template, ensure_ascii=False))
        save_selector_config(path, data)
        return data

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    data.setdefault("version", template["version"])
    data.setdefault("timeouts", {})
    data.setdefault("browser", {})
    data.setdefault("selectors", {})
    data.setdefault("popup_close_selectors", [])
    data.setdefault("deleted_selector_keys", [])

    for key, value in template["timeouts"].items():
        if key not in data["timeouts"]:
            data["timeouts"][key] = value
            changed = True

    for key, value in template.get("browser", {}).items():
        if key not in data["browser"]:
            data["browser"][key] = value
            changed = True

    deleted_selector_keys = set(data.get("deleted_selector_keys", []))
    for key, selector in template["selectors"].items():
        if key in deleted_selector_keys:
            continue
        if key not in data["selectors"]:
            data["selectors"][key] = selector
            changed = True
        else:
            data["selectors"][key].setdefault("label", selector["label"])
            data["selectors"][key].setdefault("type", selector.get("type", "element"))
            data["selectors"][key].setdefault("by", selector["by"])
            data["selectors"][key].setdefault("value", "")
            data["selectors"][key].setdefault("required", selector["required"])
            data["selectors"][key].setdefault("action", selector.get("action", "click"))

    for selector in data["selectors"].values():
        selector.setdefault("type", "element")
        selector.setdefault("action", "click")

    if not data["popup_close_selectors"]:
        data["popup_close_selectors"] = template["popup_close_selectors"]
        changed = True

    if changed:
        save_selector_config(path, data)

    return data


def save_selector_config(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def build_locator(selector: dict):
    by = selector.get("by", "xpath")
    value = selector.get("value", "").strip()
    if not value:
        return None
    if by not in BY_TYPES:
        raise ValueError(f"지원하지 않는 선택자 유형입니다: {by}")
    return BY_TYPES[by], value


def apply_runtime_context(selector: dict, context: dict | None = None) -> dict:
    if not context:
        return selector

    result = dict(selector)
    value = result.get("value", "")
    if isinstance(value, str):
        replacements = {
            "{repeat_index}": str(context.get("repeat_index", 0)),
            "{repeat_number}": str(context.get("repeat_number", 1)),
        }
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        result["value"] = value
    return result


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
    def __init__(self, parent, config_path: Path, template: dict | None = None, task_label: str = ""):
        super().__init__(parent)
        self.config_path = config_path
        self.template = template or SELECTOR_TEMPLATE
        self.config = ensure_selector_config(config_path, self.template)
        self.setWindowTitle(f"공단툴 요소 설정 - {task_label}" if task_label else "공단툴 요소 설정")
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

        self.table = SelectorTableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["키", "이름", "처리 종류", "방식", "값", "필수", "동작"])
        self.table.setDragDropMode(QAbstractItemView.DragDrop)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self._load_table()

        action_layout = QHBoxLayout()
        add_button = QPushButton("추가")
        add_menu = QMenu(add_button)
        for type_key, type_label in PROCESS_TYPES.items():
            action = QAction(type_label, add_menu)
            action.triggered.connect(lambda _, t=type_key: self.add_selector_row(t))
            add_menu.addAction(action)
        add_button.setMenu(add_menu)
        delete_button = QPushButton("삭제")
        delete_button.clicked.connect(self.delete_selected_row)
        action_layout.addWidget(add_button)
        action_layout.addWidget(delete_button)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        guide = QLabel(
            "처리 종류가 요소이면 Selenium 선택자를 사용하고, prompt 행의 값은 입력할 텍스트로 사용됩니다. "
            "delay 행은 값에 입력한 정수 초만큼 대기합니다. 반복 시작/반복 끝 사이의 행은 반복 시작 행의 동작에 따라 반복하며, "
            "반복 블록 안의 선택자 값에는 {repeat_index}(0부터) 또는 {repeat_number}(1부터)를 사용할 수 있습니다."
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

    def _set_row(self, row, key, selector):
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(selector.get("label", "")))

        type_combo = QComboBox()
        for type_key, type_label in PROCESS_TYPES.items():
            type_combo.addItem(type_label, type_key)
        type_index = type_combo.findData(selector.get("type", "element"))
        type_combo.setCurrentIndex(type_index if type_index >= 0 else 0)
        self.table.setCellWidget(row, 2, type_combo)

        by_combo = QComboBox()
        by_combo.addItems(BY_TYPES.keys())
        by_combo.setCurrentText(selector.get("by", "xpath"))
        self.table.setCellWidget(row, 3, by_combo)

        self.table.setItem(row, 4, QTableWidgetItem(selector.get("value", "")))

        required_widget = QWidget()
        required_layout = QHBoxLayout()
        required_layout.setContentsMargins(0, 0, 0, 0)
        required_radio = QRadioButton("필수")
        optional_radio = QRadioButton("선택")
        required_layout.addWidget(required_radio)
        required_layout.addWidget(optional_radio)
        required_layout.addStretch()
        required_widget.setLayout(required_layout)
        required_radio.setChecked(bool(selector.get("required", False)))
        optional_radio.setChecked(not bool(selector.get("required", False)))
        required_widget.required_radio = required_radio
        required_widget.optional_radio = optional_radio
        self.table.setCellWidget(row, 5, required_widget)

        action_combo = QComboBox()
        self.table.setCellWidget(row, 6, action_combo)
        self._refresh_action_combo(row, selector.get("action"))
        type_combo.currentIndexChanged.connect(lambda _, r=row: self._refresh_action_combo(r))

    def _refresh_action_combo(self, row, selected_action=None):
        type_combo = self.table.cellWidget(row, 2)
        action_combo = self.table.cellWidget(row, 6)
        if not action_combo:
            return
        process_type = type_combo.currentData() if type_combo else "element"
        actions = PROCESS_ACTIONS.get(process_type, ACTION_TYPES)
        selected_action = selected_action or action_combo.currentData()
        action_combo.clear()
        for action_key, action_label in actions.items():
            action_combo.addItem(action_label, action_key)
        action_index = action_combo.findData(selected_action)
        action_combo.setCurrentIndex(action_index if action_index >= 0 else 0)

    def _row_data(self, row):
        key_item = self.table.item(row, 0)
        label_item = self.table.item(row, 1)
        type_combo = self.table.cellWidget(row, 2)
        by_combo = self.table.cellWidget(row, 3)
        value_item = self.table.item(row, 4)
        required_widget = self.table.cellWidget(row, 5)
        action_combo = self.table.cellWidget(row, 6)
        return (
            key_item.text().strip() if key_item else "",
            {
                "label": label_item.text().strip() if label_item else "",
                "type": type_combo.currentData() if type_combo else "element",
                "by": by_combo.currentText() if by_combo else "xpath",
                "value": value_item.text().strip() if value_item else "",
                "required": bool(getattr(required_widget, "required_radio", None) and required_widget.required_radio.isChecked()),
                "action": action_combo.currentData() if action_combo else "click",
            },
        )

    def _all_row_data(self):
        return [self._row_data(row) for row in range(self.table.rowCount())]

    def _rebuild_table(self, rows):
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for row, (key, selector) in enumerate(rows):
            self._set_row(row, key, selector)

    def move_selector_row(self, source_row, target_row):
        if source_row == target_row or source_row < 0 or target_row < 0:
            return
        rows = self._all_row_data()
        if source_row >= len(rows) or target_row >= len(rows):
            return
        item = rows.pop(source_row)
        rows.insert(target_row, item)
        self._rebuild_table(rows)
        self.table.selectRow(target_row)

    def add_selector_row(self, process_type="element"):
        existing_keys = {
            self.table.item(row, 0).text().strip()
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
        }

        index = 1
        prefix = "custom_selector" if process_type == "element" else f"custom_{process_type}"
        while f"{prefix}_{index}" in existing_keys:
            index += 1

        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_row(row, f"{prefix}_{index}", {
            "label": f"새 {PROCESS_TYPES.get(process_type, '요소')}",
            "type": process_type,
            "by": "xpath",
            "value": "",
            "required": False,
            "action": next(iter(PROCESS_ACTIONS.get(process_type, ACTION_TYPES))),
        })
        self.table.selectRow(row)

    def delete_selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "삭제 실패", "삭제할 요소를 선택하세요.")
            return

        key_item = self.table.item(row, 0)
        key = key_item.text() if key_item else ""
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"'{key}' 요소를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.table.removeRow(row)

    def save(self):
        selectors = {}
        seen_keys = set()
        for row in range(self.table.rowCount()):
            key, selector = self._row_data(row)
            if not key:
                QMessageBox.warning(self, "저장 실패", "요소 키는 비워둘 수 없습니다.")
                return
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
        QMessageBox.information(self, "저장 완료", "요소 설정을 저장했습니다.")
        self.accept()


class FederationTool(QWidget):
    def __init__(self):
        super().__init__()

        root = Path(__file__).resolve().parents[2]
        self.root = root
        self.data_file = root / "data" / "branches.json"
        self.legacy_selector_config_file = root / "data" / "federation_selectors.json"
        self.selector_config_file = self._selector_config_path("invoice")
        self._ensure_task_selector_config("invoice")
        self._ensure_task_selector_config("long_service")
        self.login_threads = []
        self.current_task = None

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.main_layout)

        top_label = QLabel("공단툴")
        self.main_layout.addWidget(top_label)

        l1_label = QLabel("L1 - 작업 선택")
        self.main_layout.addWidget(l1_label)

        task_layout = QHBoxLayout()
        self.invoice_button = QPushButton("청구 명세서 만들기")
        self.invoice_button.clicked.connect(lambda: self.select_task("invoice"))
        task_layout.addWidget(self.invoice_button)

        self.long_service_button = QPushButton("장기근속수당 입력하기")
        self.long_service_button.clicked.connect(lambda: self.select_task("long_service"))
        task_layout.addWidget(self.long_service_button)
        task_layout.addStretch()
        self.main_layout.addLayout(task_layout)

        self.l2_container = QWidget()
        l2_layout = QVBoxLayout()
        l2_layout.setContentsMargins(0, 0, 0, 0)
        self.l2_container.setLayout(l2_layout)
        l2_label = QLabel("L2 - 지점선택")
        l2_layout.addWidget(l2_label)
        toolbar = QHBoxLayout()
        self.selector_button = QPushButton("요소 설정")
        self.selector_button.clicked.connect(self.open_selector_settings)
        toolbar.addWidget(self.selector_button)
        toolbar.addStretch()
        l2_layout.addLayout(toolbar)
        self.l2_container.setVisible(False)
        self.main_layout.addWidget(self.l2_container)

        self.l3_label = QLabel("L3 - 작업 상태")
        self.l3_label.setVisible(False)
        self.main_layout.addWidget(self.l3_label)

        self.branch_grid_layout = QGridLayout()
        self.branch_grid_layout.setSpacing(10)

        self.branch_container = QWidget()
        self.branch_container.setLayout(self.branch_grid_layout)
        self.branch_container.setVisible(False)
        self.main_layout.addWidget(self.branch_container)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.main_layout.addWidget(self.status_label)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(180)
        self.log_console.setPlaceholderText("작업 로그가 여기에 표시됩니다.")
        self.main_layout.addWidget(self.log_console)

    def open_selector_settings(self):
        if not self.current_task:
            QMessageBox.warning(self, "작업 선택", "먼저 L1에서 작업을 선택하세요.")
            return

        task_config = TASK_CONFIGS[self.current_task]
        config_path = self._ensure_task_selector_config(self.current_task)
        SelectorConfigDialog(
            self,
            config_path,
            template=task_config["template"],
            task_label=task_config["label"],
        ).exec()

    def select_task(self, task):
        self.current_task = task
        task_config = TASK_CONFIGS[task]
        self.selector_config_file = self._ensure_task_selector_config(task)
        self.l2_container.setVisible(True)
        self.l3_label.setVisible(True)
        self.branch_container.setVisible(True)
        if task == "invoice":
            self.status_label.setText("청구 명세서 만들기: 지점을 선택하면 자동화가 시작됩니다.")
        else:
            self.status_label.setText("장기근속수당 입력하기: 아직 준비 중입니다.")
        self.refresh_buttons()

    def _selector_config_path(self, task):
        return self.root / "data" / TASK_CONFIGS[task]["config_file"]

    def _ensure_task_selector_config(self, task):
        task_config = TASK_CONFIGS[task]
        config_path = self._selector_config_path(task)

        if task == "invoice" and not config_path.exists() and self.legacy_selector_config_file.exists():
            try:
                with open(self.legacy_selector_config_file, "r", encoding="utf-8") as f:
                    legacy_data = json.load(f)
                save_selector_config(config_path, legacy_data)
            except Exception:
                pass

        ensure_selector_config(config_path, task_config["template"])
        return config_path

    def refresh_buttons(self):
        while self.branch_grid_layout.count():
            child = self.branch_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        branches = self._load_branches()
        for index, branch in enumerate(branches):
            row = index // 5
            col = index % 5
            button = QPushButton(branch.get("branch_name", "Unnamed"))
            button.clicked.connect(lambda _, b=branch: self.on_branch_clicked(b))
            self.branch_grid_layout.addWidget(button, row, col)

    def on_branch_clicked(self, branch):
        if self.current_task == "long_service":
            self.status_label.setText("장기근속수당 입력하기는 아직 구현되지 않았습니다.")
            self._log("장기근속수당 작업 선택 - 아직 구현 안됨", level="WARNING")
            return

        branch_name = branch.get("branch_name", "Unknown")
        self._log(f"[{branch_name}] 공단툴 지점 버튼 클릭, 롱텀 로그인 시작")

        login_thread = LongtermLoginThread(branch)
        login_thread.finished_signal.connect(lambda msg, ok, lt=login_thread: self._on_longterm_finished(msg, ok, lt))
        login_thread.start()
        self.login_threads.append(login_thread)

    def _on_longterm_finished(self, message, success, login_thread: LongtermLoginThread):
        self.status_label.setText(message)
        self._log(message, level=("INFO" if success else "ERROR"))
        if not success:
            return

        driver = getattr(login_thread, "driver", None)
        if not driver:
            self._log("로그인 드라이버를 가져올 수 없어 자동화를 시작할 수 없습니다.")
            return

        claim_thread = ClaimProcessThread(driver, login_thread.branch, self.selector_config_file)
        self._log(f"윈도우 전환 준비: handles={driver.window_handles}, current_url={driver.current_url}")

        def _update_status(s):
            self.status_label.setText(s)
            self._log(s)

        def _on_finished(m, ok):
            self.status_label.setText(m)
            self._log(m, level=("INFO" if ok else "ERROR"))

        claim_thread.status_signal.connect(_update_status)
        claim_thread.finished_signal.connect(_on_finished)
        claim_thread.start()
        self.login_threads.append(claim_thread)

    def showEvent(self, event):
        super().showEvent(event)
        if self.branch_container.isVisible():
            self.refresh_buttons()

    def _load_branches(self):
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def _log(self, message, level="INFO"):
        text = log("FederationTool", message, level=level)
        if hasattr(self, "log_console"):
            self.log_console.append(text)


class InvoiceProcessor:
    def __init__(self, driver, config_path: Path, status_callback=None):
        self.driver = driver
        self.config = ensure_selector_config(config_path)
        self.status_callback = status_callback or (lambda msg: None)
        self.timeouts = self.config.get("timeouts", {})
        self.timeout = int(self.timeouts.get("default", 20))
        self.wait = WebDriverWait(self.driver, self.timeout)
        self.last_element_key = None

    def _log(self, message):
        self.status_callback(message)

    def selector_text(self, key):
        selector = self.config.get("selectors", {}).get(key, {})
        return (
            f"{key} ({selector.get('label', key)}) "
            f"by={selector.get('by', '')} value={selector.get('value', '')}"
        )

    def ordered_selector_keys(self):
        return list(self.config.get("selectors", {}).keys())

    def run_control_steps_before(self, target_key):
        if not self.last_element_key:
            return

        keys = self.ordered_selector_keys()
        if self.last_element_key not in keys or target_key not in keys:
            return

        start = keys.index(self.last_element_key)
        end = keys.index(target_key)
        if end <= start:
            return

        for key in keys[start + 1:end]:
            selector = self.config.get("selectors", {}).get(key, {})
            if selector.get("type", "element") in {"alert", "confirm", "prompt", "window", "delay"}:
                self.run_control_step(key, selector)

    def run_control_step(self, key, selector, context=None):
        selector = apply_runtime_context(selector, context)
        process_type = selector.get("type", "element")
        action = selector.get("action", "accept")
        label = selector.get("label", key)
        self._log(f"[제어] {key} ({label}) type={process_type} action={action}")

        if process_type in {"alert", "confirm", "prompt"}:
            return self.handle_dialog_control(key, selector)
        if process_type == "window":
            return self.handle_window_control(key, selector)
        if process_type == "delay":
            return self.handle_delay_control(key, selector)
        return False

    def handle_delay_control(self, key, selector):
        value = selector.get("value", "0")
        try:
            seconds = max(0, int(str(value).strip() or "0"))
        except ValueError:
            raise ValueError(f"delay 값은 정수여야 합니다: {key}={value}")
        self._log(f"[delay] {key}: sleep {seconds}s")
        time.sleep(seconds)
        return True

    def handle_dialog_control(self, key, selector):
        timeout = int(self.timeouts.get("short", 3))
        required = bool(selector.get("required", False))
        try:
            alert = WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
            text = (alert.text or "").strip()
            action = selector.get("action", "accept")
            if selector.get("type") == "prompt" and action == "accept":
                value = selector.get("value", "")
                alert.send_keys(value)
                self._log(f"[prompt] send_keys: {value}")
            self._log(f"[{selector.get('type')}] {action}: {text[:120]}")
            if action == "dismiss":
                alert.dismiss()
            else:
                alert.accept()
            return True
        except TimeoutException:
            message = f"{PROCESS_TYPES.get(selector.get('type'), '제어')} 대상을 찾지 못했습니다: {key}"
            if required:
                raise TimeoutException(message)
            self._log(f"[제어스킵] {message}")
            return False

    def handle_window_control(self, key, selector):
        action = selector.get("action", "keep")
        required = bool(selector.get("required", False))
        try:
            handles = self.driver.window_handles
            current = self.driver.current_window_handle
            self._log(f"[창제어] {key} action={action} handles={handles} current={current}")
            if len(handles) <= 1:
                if required:
                    raise RuntimeError(f"추가 창/팝업창이 없습니다: {key}")
                return False
            if action == "switch_last":
                self.driver.switch_to.window(handles[-1])
            elif action == "close_extra":
                self.close_extra_windows()
            return True
        except Exception as e:
            if required:
                raise
            self._log(f"[창제어오류] {key}: {type(e).__name__}: {e}")
            return False

    def snapshot(self, label):
        try:
            handles = self.driver.window_handles
        except Exception as e:
            handles = f"unavailable: {type(e).__name__}: {e}"
        try:
            current = self.driver.current_window_handle
        except Exception as e:
            current = f"unavailable: {type(e).__name__}: {e}"
        try:
            title = self.driver.title
        except Exception as e:
            title = f"unavailable: {type(e).__name__}: {e}"
        try:
            url = self.driver.current_url
        except Exception as e:
            url = f"unavailable: {type(e).__name__}: {e}"
        self._log(f"[스냅샷] {label}: handles={handles}, current={current}, title={title}, url={url}")

    def locator(self, key, required=True, context=None):
        selector = self.config.get("selectors", {}).get(key)
        if not selector:
            if required:
                raise ValueError(f"요소 설정이 없습니다: {key}")
            return None
        if selector.get("type", "element") != "element":
            if required:
                raise ValueError(f"요소 타입이 아닌 제어 행입니다: {key}")
            return None

        locator = build_locator(apply_runtime_context(selector, context))
        if locator:
            return locator

        if required or selector.get("required", False):
            label = selector.get("label", key)
            raise ValueError(f"필수 요소 값이 비어 있습니다: {label} ({key})")
        return None

    def wait_element(self, key, timeout=None, required=True, context=None, run_controls=True):
        if run_controls:
            self.run_control_steps_before(key)
        locator = self.locator(key, required=required, context=context)
        if not locator:
            return None
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        element = wait.until(EC.presence_of_element_located(locator))
        self.last_element_key = key
        return element

    def wait_elements(self, key, timeout=None, context=None, run_controls=True):
        if run_controls:
            self.run_control_steps_before(key)
        locator = self.locator(key, context=context)
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        elements = wait.until(lambda driver: driver.find_elements(*locator) or False)
        self.last_element_key = key
        return elements

    def click(self, key, timeout=None, required=True, context=None, run_controls=True):
        if run_controls:
            self.run_control_steps_before(key)
        locator = self.locator(key, required=required, context=context)
        if not locator:
            return None
        self._log(f"[click_wait] {self.selector_text(key)} timeout={timeout or self.timeout}")
        element = WebDriverWait(self.driver, timeout or self.timeout).until(EC.element_to_be_clickable(locator))
        self.perform_action(key, element)
        self._log(f"[click_ok] {key}")
        self.last_element_key = key
        return element

    def click_element(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def perform_action(self, key, element):
        action = self.config.get("selectors", {}).get(key, {}).get("action", "click")
        action = action if action in ACTION_TYPES else "click"
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        if action == "hover":
            ActionChains(self.driver).move_to_element(element).perform()
        elif action == "hover_click":
            ActionChains(self.driver).move_to_element(element).perform()
            time.sleep(0.2)
            self.click_element(element)
        else:
            self.click_element(element)
        self._log(f"[action] {key}: {action}")

    def click_if_exists(self, key, timeout=None, context=None, run_controls=True):
        timeout = timeout or self.timeouts.get("short", 3)
        if run_controls:
            self.run_control_steps_before(key)
        try:
            locator = self.locator(key, required=False, context=context)
            if not locator:
                self._log(f"[optional_skip] {key}: selector empty")
                return False

            elements = self.driver.find_elements(*locator)
            self._log(f"[요소조회] {self.selector_text(key)} found={len(elements)} timeout={timeout}")
            for index, element in enumerate(elements, start=1):
                try:
                    text = (element.text or "").strip().replace("\n", " ")[:80]
                    self._log(
                        f"[요소조회] {key}[{index}] "
                        f"displayed={element.is_displayed()} enabled={element.is_enabled()} text={text}"
                    )
                except Exception as e:
                    self._log(f"[요소처리오류] {key}[{index}] {type(e).__name__}: {e}")

            element = WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable(locator))
            self.perform_action(key, element)
            self._log(f"[optional_click_ok] {key}")
            self.last_element_key = key
            return True
        except TimeoutException:
            self._log(f"[optional_not_found] {key}: no clickable element within {timeout}s")
            return False
        except Exception as e:
            self._log(f"[요소처리오류] {key}: {type(e).__name__}: {e}")
            return False

    def click_optional_confirm(self, key, timeout=None):
        return self.click_if_exists(key, timeout=timeout or self.timeouts.get("short", 3))

    def has_configured_repeats(self):
        return any(
            selector.get("type") == "repeat_start"
            for selector in self.config.get("selectors", {}).values()
        )

    def find_repeat_end_index(self, items, start_index):
        depth = 0
        for index in range(start_index, len(items)):
            process_type = items[index][1].get("type", "element")
            if process_type == "repeat_start":
                depth += 1
            elif process_type == "repeat_end":
                depth -= 1
                if depth == 0:
                    return index
        raise ValueError(f"반복 끝 설정이 없습니다: {items[start_index][0]}")

    def parse_repeat_count(self, text, key):
        match = re.search(r"\d+", str(text or ""))
        if not match:
            raise ValueError(f"반복 횟수를 찾을 수 없습니다: {key}")
        return max(0, int(match.group(0)))

    def repeat_count(self, key, selector, context=None):
        action = selector.get("action", "fixed_count")
        runtime_selector = apply_runtime_context(selector, context)

        if action == "fixed_count":
            return self.parse_repeat_count(runtime_selector.get("value", "0"), key)

        locator = build_locator(runtime_selector)
        if not locator:
            raise ValueError(f"반복 횟수 요소 설정이 비어 있습니다: {key}")

        if action == "element_count":
            elements = WebDriverWait(self.driver, self.timeout).until(lambda driver: driver.find_elements(*locator) or False)
            count = len(elements)
            self._log(f"[repeat_count] {key}: element_count={count}")
            return count

        element = WebDriverWait(self.driver, self.timeout).until(EC.presence_of_element_located(locator))
        text = element.get_attribute("value") or element.text or ""
        count = self.parse_repeat_count(text, key)
        self._log(f"[repeat_count] {key}: element_text={text} count={count}")
        return count

    def run_selector_step(self, key, selector, context=None):
        process_type = selector.get("type", "element")
        if process_type == "element":
            required = bool(selector.get("required", False))
            if required:
                return self.click(key, context=context, run_controls=False)
            return self.click_if_exists(key, context=context, run_controls=False)
        if process_type in {"alert", "confirm", "prompt", "window", "delay"}:
            return self.run_control_step(key, selector, context=context)
        if process_type == "repeat_end":
            return None
        raise ValueError(f"지원하지 않는 처리 종류입니다: {key} ({process_type})")

    def run_workflow_items(self, items, context=None):
        index = 0
        while index < len(items):
            key, selector = items[index]
            process_type = selector.get("type", "element")
            if process_type == "repeat_start":
                end_index = self.find_repeat_end_index(items, index)
                block = items[index + 1:end_index]
                count = self.repeat_count(key, selector, context=context)
                self._log(f"[repeat_start] {key}: count={count}")
                for repeat_index in range(count):
                    child_context = dict(context or {})
                    child_context.update({
                        "repeat_index": repeat_index,
                        "repeat_number": repeat_index + 1,
                    })
                    self._log(f"[repeat] {key}: {repeat_index + 1}/{count}")
                    self.run_workflow_items(block, context=child_context)
                index = end_index + 1
                continue

            self.run_selector_step(key, selector, context=context)
            index += 1

    def run_configured_workflow(self):
        self._log("[workflow] 설정 순서 실행 시작")
        self.run_workflow_items(list(self.config.get("selectors", {}).items()))
        self._log("[workflow] 설정 순서 실행 완료")

    def wait_loading_done(self):
        locator = self.locator("loading_canvas", required=False)
        if not locator:
            time.sleep(0.5)
            return

        long_timeout = int(self.timeouts.get("loading", 120))
        try:
            WebDriverWait(self.driver, int(self.timeouts.get("short", 3))).until(EC.presence_of_element_located(locator))
        except TimeoutException:
            return
        try:
            WebDriverWait(self.driver, long_timeout).until(EC.invisibility_of_element_located(locator))
        except TimeoutException:
            self._log("로딩 요소가 사라지지 않았지만 다음 확인 단계로 진행합니다.")

    def close_configured_popups(self):
        for item in self.config.get("popup_close_selectors", []):
            locator = build_locator(item)
            if not locator:
                continue
            try:
                elements = self.driver.find_elements(*locator)
                self._log(
                    f"[요소조회] {item.get('label', '')} "
                    f"by={item.get('by')} value={item.get('value')} found={len(elements)}"
                )
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        self.click_element(element)
                        self._log(f"[요소처리] {item.get('label', '')}")
                        time.sleep(0.2)
            except Exception as e:
                self._log(f"[요소처리오류] {item.get('label', '')}: {type(e).__name__}: {e}")

    def close_extra_windows(self):
        main_window = self.driver.current_window_handle
        all_windows = list(self.driver.window_handles)
        closed_count = 0

        for window in all_windows:
            if window == main_window:
                continue
            try:
                self.driver.switch_to.window(window)
                self.driver.close()
                closed_count += 1
            except Exception as e:
                self._log(f"[popup_window_close_error] handle={window}: {type(e).__name__}: {e}")

        try:
            self.driver.switch_to.window(main_window)
        except Exception as e:
            self._log(f"[popup_window_restore_error] handle={main_window}: {type(e).__name__}: {e}")

        self._log(f"[popup_window_close] closed={closed_count} handles_before={all_windows}")
        return closed_count

    def close_all_popups(self):
        self._log("열려있는 알림/모달/팝업 닫기 시도")
        self.snapshot("팝업 닫기 전")
        self.close_extra_windows()
        clicked_keys = set()
        popup_keys = [
            "layer_popup_close",
            "layer_popup_confirm",
            "browser_popup_close_button",
            "first_modal_close",
            "second_modal_close",
            "claim_page_warning_close",
            "operation_guide_close",
        ]
        for attempt in range(1, 3):
            clicked_in_attempt = False
            self._log(f"[popup_close] attempt={attempt}")
            self.close_configured_popups()
            for key in popup_keys:
                if key in clicked_keys:
                    self._log(f"[optional_skip] {key}: already clicked")
                    continue
                if self.click_if_exists(key):
                    clicked_keys.add(key)
                    clicked_in_attempt = True

            frames = self.driver.find_elements(By.TAG_NAME, "iframe")
            self._log(f"[frame_search] iframe found={len(frames)}")
            for frame_index, frame in enumerate(frames, start=1):
                try:
                    self._log(f"[frame_enter] iframe {frame_index}/{len(frames)}")
                    self.driver.switch_to.frame(frame)
                    self.close_configured_popups()
                    for key in popup_keys:
                        if key in clicked_keys:
                            self._log(f"[optional_skip] {key}: already clicked")
                            continue
                        if self.click_if_exists(key):
                            clicked_keys.add(key)
                            clicked_in_attempt = True
                except Exception as e:
                    self._log(f"[frame_popup_close_fail] iframe {frame_index}: {type(e).__name__}: {e}")
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
            if clicked_in_attempt:
                self._log(f"[popup_close] clicked; stop retry: {sorted(clicked_keys)}")
                break
        self.snapshot("팝업 닫기 후")


    def open_payroll_claim_menu(self):
        self._log("상단 메뉴 급여비용청구 열기")
        main_menu = self.wait_element("main_menu")
        self.perform_action("main_menu", main_menu)
        time.sleep(0.5)
        self._log("[navbar] click payroll_claim_dropdown")
        self.click("payroll_claim_dropdown", timeout=5)

    def click_claim_button(self):
        self._log("청구하기 버튼 클릭")
        self.click("claim_button", timeout=self.timeouts.get("long", 60))

    def process_claim_targets(self):
        self._log("입퇴소신고내용관리에서 입소신고자 마지막 행 선택")
        self.click("entry_notice_tab")

        rows = self.wait_elements("entry_notice_rows", timeout=self.timeouts.get("long", 60))
        self.click_element(rows[-1])

        self._log("수급자명 목록 전체 체크 후 청구대상자로 이동")
        if not self.click_if_exists("recipient_select_all_checkbox"):
            checkboxes_locator = self.locator("recipient_checkboxes", required=False)
            if not checkboxes_locator:
                raise ValueError("수급자 전체 체크박스 또는 개별 체크박스 목록 중 하나는 입력해야 합니다.")
            for checkbox in self.driver.find_elements(*checkboxes_locator):
                if not checkbox.is_selected():
                    self.click_element(checkbox)

        self.click("add_recipient_button")
        self.click_optional_confirm("confirm_add_recipient", timeout=self.timeouts.get("short", 3))
        self.wait_loading_done()
        self.click("claim_target_created_message", timeout=self.timeouts.get("long", 60))

    def verify_claim_targets(self):
        self._log("급여내용 자료 관리 조회 후 청구대상자 목록 대기")
        self.click("salary_data_tab")
        self.click("search_button")
        return self.wait_elements("claim_target_rows", timeout=self.timeouts.get("long", 60))

    def process_all_claim_targets(self):
        rows = self.verify_claim_targets()
        total = len(rows)
        for index in range(total):
            rows = self.wait_elements("claim_target_rows", timeout=self.timeouts.get("long", 60))
            self._log(f"청구대상자 {index + 1}/{total} 처리 시작")
            self.process_recipient(rows[index])

    def process_recipient(self, row):
        self.click_element(row)

        self.click("save_button")
        self.click_optional_confirm("confirm_save")
        self.click_optional_confirm("save_completed_confirm", timeout=self.timeouts.get("long", 60))

        self.click("generate_statement_button", timeout=self.timeouts.get("long", 60))
        self.click("statement_register_complete_button", timeout=self.timeouts.get("long", 60))

        self.handle_pay_result()
        self.click("statement_auto_modal_close", timeout=self.timeouts.get("long", 60))

    def handle_pay_result(self):
        self._log("급여제공결과 확인 및 명세서 등록")
        select_element = self.wait_element("pay_result_select", timeout=self.timeouts.get("long", 60))
        select_box = Select(select_element)
        value = (select_box.first_selected_option.get_attribute("value") or "").strip()
        text = (select_box.first_selected_option.text or "").strip()

        if not value and not text:
            option_locator = self.locator("pay_result_continue_option", required=False)
            if option_locator:
                self.click("pay_result_continue_option")
            else:
                select_box.select_by_visible_text("계속")

        if not self.click_if_exists("pay_result_save_button"):
            self.click("save_button")

        self.click_optional_confirm("confirm_pay_result_save", timeout=self.timeouts.get("short", 3))
        self.click_optional_confirm("statement_completed_confirm", timeout=self.timeouts.get("long", 60))


class ClaimProcessThread(QThread):
    finished_signal = Signal(str, bool)
    status_signal = Signal(str)

    def __init__(self, driver, branch: dict, config_path: Path):
        super().__init__()
        self.driver = driver
        self.branch = branch
        self.config_path = config_path

    def switch_window(self):
        try:
            config = ensure_selector_config(self.config_path)
            window_index = int(config.get("browser", {}).get("window_index", -1))
            if window_index > 0:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) >= window_index)
                handles = self.driver.window_handles
                target_index = min(window_index - 1, len(handles) - 1)
            else:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
                handles = self.driver.window_handles
                target_index = len(handles) - 1

            self.status_signal.emit(f"브라우저 윈도우/탭 {target_index + 1}번으로 전환했습니다.")
            self.driver.switch_to.window(handles[target_index])
            try:
                self.driver.maximize_window()
            except Exception:
                pass
        except Exception:
            pass

    def run(self):
        try:
            self.status_signal.emit("로그인 후 공단 청구 자동화 초기화 중...")
            self.switch_window()

            processor = InvoiceProcessor(self.driver, self.config_path, status_callback=self.status_signal.emit)
            processor.snapshot("초기 상태")
            if processor.has_configured_repeats():
                self.status_signal.emit("[단계] 설정 반복 구간 실행")
                processor.run_configured_workflow()
                self.finished_signal.emit("설정된 반복 자동화 작업이 완료되었습니다.", True)
                return

            self.status_signal.emit("[단계] 팝업 닫기 시작")
            processor.close_all_popups()
            self.status_signal.emit("[단계] 급여비용청구 메뉴 열기")
            processor.open_payroll_claim_menu()
            self.status_signal.emit("[단계] 메뉴 진입 후 팝업 정리")
            processor.close_all_popups()
            self.status_signal.emit("[단계] 청구하기 버튼 클릭")
            processor.click_claim_button()
            self.status_signal.emit("[단계] 청구 화면 팝업 정리")
            processor.close_all_popups()
            self.status_signal.emit("[단계] 청구 대상자 생성")
            processor.process_claim_targets()
            self.status_signal.emit("[단계] 청구 명세서 자동 처리")
            processor.process_all_claim_targets()
            self.finished_signal.emit("청구 명세서 자동화 작업을 완료했습니다.", True)
        except Exception as e:
            self.finished_signal.emit(f"청구 명세서 자동화 중 오류: {e}", False)
