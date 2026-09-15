import json
import re
import time
import hashlib
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, UnexpectedAlertPresentException, ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from ui.pages.login_tool import BrowserCloseMonitor, LongtermLoginThread
from ui.pages.logging_util import log, should_log_message
from ui.pages.branch_task_settings import filter_branches_for_task
from ui.pages.federation_batch import BranchBatchDialog, BranchBatchThread
from ui.pages.macro_ranges import RANGE_TYPES, range_values
from ui.pages.macro_popup_recovery import dismiss_blocking_popups, dismiss_native_alert, find_clickable_context


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

REPEAT_MODES = {
    "fixed": "고정 반복",
    "increment": "증가 반복",
    "range": "값 범위 반복 (시작·종료값)",
}

PROCESS_TYPES = {
    "url_navigation": "URL 이동",
    "element": "엘레멘트",
    "table": "테이블",
    "text_assert": "텍스트 검증",
    "alert": "alert",
    "confirm": "confirm",
    "prompt": "prompt",
    "window": "새창/팝업창",
    "legacy_action": "레거시 동작",
    "condition_start": "조건처리의 조건",
    "condition_true": "조건처리-참",
    "condition_false": "조건처리-거짓",
    "condition_end": "조건처리 종료",
    "repeat_start": "반복지점 시작",
    "repeat_end": "반복지점 종료",
}

PROCESS_ACTIONS = {
    "url_navigation": {"navigate": "이동"},
    "element": {**ACTION_TYPES, "input_text": "값 입력 (검증)", "select_text": "텍스트로 옵션 선택 (검증)", "pointer_click": "마우스로 클릭 후 화면 확인"},
    "table": {"verify_click_increment": "증가 검증 후 클릭"},
    "text_assert": {
        "equals_repeat_number": "반복번호와 일치",
        "contains_repeat_number": "반복번호 포함",
        "equals_repeat_text": "반복번호 텍스트 일치",
        "text_exists": "텍스트 존재",
    },
    "alert": {"accept": "확인/수락", "dismiss": "취소/닫기", "accept_if_present": "확인/수락 (없으면 계속)", "dismiss_if_present": "취소/닫기 (없으면 계속)"},
    "confirm": {"accept": "확인/수락", "dismiss": "취소/닫기", "accept_if_present": "확인/수락 (없으면 계속)", "dismiss_if_present": "취소/닫기 (없으면 계속)"},
    "prompt": {"accept": "텍스트 입력 후 확인", "dismiss": "취소/닫기", "accept_if_present": "텍스트 입력 후 확인 (없으면 계속)", "dismiss_if_present": "취소/닫기 (없으면 계속)"},
    "window": {"keep": "유지", "switch_last": "마지막 창으로 전환", "close_extra": "추가 창 닫기"},
    "legacy_action": {
        "last_table_click": "마지막 테이블 행 다시 클릭",
        "last_table_next_row_click": "마지막 테이블의 다음 행 클릭",
        "last_table_previous_row_click": "마지막 테이블의 이전 행 클릭",
        "last_table_double_click": "마지막 테이블 행 더블클릭",
        "last_table_force_click": "마지막 테이블 행 강제 클릭",
        "last_table_force_double_click": "마지막 테이블 행 강제 더블클릭",
        "short_wait": "짧은 대기",
        "wait_loading_done": "로딩 사라짐 대기",
    },
    "condition_start": {
        "field_empty": "필드값 비어 있음",
        "field_not_empty": "필드값 있음",
        "text_exists": "텍스트 존재",
        "equals_value": "조건값과 일치",
        "contains_value": "조건값 포함",
        "equals_repeat_number": "반복번호와 일치",
        "contains_repeat_number": "반복번호 포함",
    },
    "condition_true": {"branch": "참 구역"},
    "condition_false": {"branch": "거짓 구역"},
    "condition_end": {"end": "종료"},
    "repeat_start": REPEAT_MODES,
    "repeat_end": {"end": "종료"},
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


DEFAULT_TASK_CONFIGS = {
    "invoice": {"label": "청구 명세서 만들기", "config_file": "federation_selectors_invoice.json", "template": SELECTOR_TEMPLATE, "implemented": True},
    "long_service": {"label": "장기근속수당 입력하기", "config_file": "federation_selectors_long_service.json", "template": EMPTY_SELECTOR_TEMPLATE, "implemented": True},
}


def task_template(task_config: dict) -> dict:
    template_name = task_config.get("template_name", "empty")
    if template_name == "selector":
        return SELECTOR_TEMPLATE
    return EMPTY_SELECTOR_TEMPLATE


def normalize_task_configs(configs: dict | None, deleted_task_keys: set[str] | None = None) -> dict:
    deleted_task_keys = deleted_task_keys or set()
    result = {}
    for task_key, task_config in DEFAULT_TASK_CONFIGS.items():
        if task_key in deleted_task_keys:
            continue
        normalized = dict(task_config)
        normalized.setdefault("template_name", "selector" if task_key == "invoice" else "empty")
        result[task_key] = normalized

    for task_key, task_config in (configs or {}).items():
        if not isinstance(task_config, dict):
            continue
        label = str(task_config.get("label", "")).strip()
        config_file = str(task_config.get("config_file", "")).strip()
        if not task_key or not label or not config_file:
            continue
        normalized = {
            "label": label,
            "config_file": config_file,
            "template_name": task_config.get("template_name", "empty"),
            "implemented": bool(task_config.get("implemented", True)),
        }
        normalized["template"] = task_template(normalized)
        result[task_key] = normalized

    for task_config in result.values():
        task_config["template"] = task_template(task_config)
        task_config["implemented"] = bool(task_config.get("implemented", True))
    return result

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
        if selector.get("type") == "delay":
            selector["type"] = "legacy_action"
            selector["action"] = "short_wait"
            selector.setdefault("label", "짧은 대기")
            changed = True

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
        def replace_expression(match):
            name = match.group(1)
            operator = match.group(2)
            amount = int(match.group(3) or 0)
            if not operator:
                return str(context.get(name, 0))
            base = int(context.get(name, 0))
            if operator == "-":
                return str(base - amount)
            return str(base + amount)

        value = re.sub(
            r"\{(repeat_index|repeat_number)(?:([+-])(\d+))?\}",
            replace_expression,
            value,
        )
        replacements = {
            "{repeat_value}": str(context.get("repeat_value", context.get("repeat_number", ""))),
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
            "테이블은 기준 행 XPath의 숫자 인덱스를 1씩 올리며 텍스트 숫자를 검증하고 클릭합니다."
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
                "max_key_steps", "timeout",
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
                not is_range and (process_type in {"element", "table", "text_assert", "condition_start"}
                or process_type == "repeat_start")
            )
            if is_range:
                self.table.item(row, 3).setToolTip("횟수 셀렉터를 사용하지 않습니다. 메인 화면의 범위 반복값 설정을 사용합니다.")
        if number_cell_item:
            number_cell_item.setFlags(
                number_cell_item.flags() | Qt.ItemFlag.ItemIsEditable
                if process_type in {"table", "condition_start", "url_navigation", "element"}
                else number_cell_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )

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
        metadata = label_item.data(Qt.ItemDataRole.UserRole) if label_item else {}
        if metadata and "timeout" in metadata:
            selector["timeout"] = metadata["timeout"]
        if process_type == "element" and action in {"select_text", "pointer_click"} and label_item:
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
        stack = []
        for key, selector in rows:
            process_type = selector.get("type", "element")
            if process_type == "repeat_start":
                stack.append(("repeat_start", key))
            elif process_type == "condition_start":
                stack.append(("condition_start", key))
            elif process_type == "condition_true":
                if not stack or stack[-1][0] != "condition_start":
                    QMessageBox.warning(self, "저장 실패", f"조건처리의 조건 없이 참 구역이 나타났습니다: {key}")
                    return False
                stack.append(("condition_true", key))
            elif process_type == "condition_false":
                if not stack or stack[-1][0] != "condition_true":
                    QMessageBox.warning(self, "저장 실패", f"조건처리-참 없이 거짓 구역이 나타났습니다: {key}")
                    return False
                stack.pop()
                stack.append(("condition_false", key))
            elif process_type == "repeat_end":
                if not stack or stack[-1][0] != "repeat_start":
                    QMessageBox.warning(self, "저장 실패", f"반복지점 종료에 맞는 시작이 없습니다: {key}")
                    return False
                stack.pop()
            elif process_type == "condition_end":
                if not stack or stack[-1][0] != "condition_false":
                    QMessageBox.warning(self, "저장 실패", f"조건처리-거짓 없이 종료가 나타났습니다: {key}")
                    return False
                stack.pop()
                if not stack or stack[-1][0] != "condition_start":
                    QMessageBox.warning(self, "저장 실패", f"조건처리 시작에 맞는 종료가 아닙니다: {key}")
                    return False
                stack.pop()
        if stack:
            QMessageBox.warning(self, "저장 실패", f"시작에 맞는 종료가 없습니다: {stack[-1][1]}")
            return False
        return True

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


def english_task_stem(label):
    words = {
        "장기근속수당": "long_service_allowance", "본인부담금": "copayment",
        "급여제공": "care_provision", "명세서": "statement", "입소자": "resident",
        "수급자": "recipient", "출근부": "attendance", "프로그램": "program",
        "기관기호": "organization_code", "청구": "claim", "공단": "federation",
        "명단": "roster", "급여": "payroll", "의료비": "medical_expense",
        "만들기": "create", "생성": "create", "입력하기": "entry", "입력": "entry",
        "조회": "search", "등록": "register", "수정": "update", "저장": "save",
        "다운로드": "download", "업로드": "upload", "검토": "review", "확인": "check",
        "발송": "send", "월간": "monthly", "일간": "daily", "연간": "annual",
        "업무": "task", "작업": "task", "복사": "copy", "테스트": "test",
        "삭제": "delete", "관리": "management", "결정요청": "decision_request",
    }
    translated = label.lower()
    for korean in sorted(words, key=len, reverse=True):
        translated = translated.replace(korean, f" {words[korean]} ")
    tokens = re.findall(r"[a-z0-9_]+", translated)
    stem = "_".join(tokens).strip("_")[:90] or "task"
    if re.search(r"[가-힣]", translated):
        stem += "_" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
    return stem


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


class FederationTool(QWidget):
    def __init__(
        self,
        tool_name="공단툴",
        task_config_name="federation_tasks.json",
        legacy_selector_name="federation_selectors.json",
        login_thread_class=LongtermLoginThread,
        login_label="롱텀",
        log_source="FederationTool",
    ):
        super().__init__()

        root = Path(__file__).resolve().parents[2]
        self.root = root
        self.tool_name = tool_name
        self.login_thread_class = login_thread_class
        self.login_label = login_label
        self.log_source = log_source
        self.data_file = root / "data" / "branches.json"
        self.task_config_file = root / "data" / task_config_name
        self.legacy_selector_config_file = root / "data" / legacy_selector_name
        self.deleted_task_keys = set()
        self.task_configs = self._load_task_configs()
        self.selector_config_file = None
        for task in self.task_configs:
            self._ensure_task_selector_config(task)
        self.login_threads = []
        self.current_task = None
        self.batch_thread = None

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.main_layout)

        top_label = QLabel(self.tool_name)
        self.main_layout.addWidget(top_label)

        l1_label = QLabel("작업 선택")
        self.main_layout.addWidget(l1_label)

        task_layout = QHBoxLayout()
        self.task_button_layout = task_layout
        task_layout.addStretch()
        self.main_layout.addLayout(task_layout)

        task_manage_layout = QHBoxLayout()
        self.add_task_button = QPushButton("작업 추가")
        self.add_task_button.clicked.connect(self.open_add_task_dialog)
        task_manage_layout.addWidget(self.add_task_button)
        self.delete_task_button = QPushButton("작업 삭제")
        self.delete_task_button.clicked.connect(self.open_delete_task_dialog)
        task_manage_layout.addWidget(self.delete_task_button)
        self.copy_task_button = QPushButton("매크로 복사")
        self.copy_task_button.clicked.connect(self.copy_task)
        task_manage_layout.addWidget(self.copy_task_button)
        task_manage_layout.addStretch()
        self.main_layout.addLayout(task_manage_layout)

        self.l2_container = QWidget()
        l2_layout = QVBoxLayout()
        l2_layout.setContentsMargins(0, 0, 0, 0)
        self.l2_container.setLayout(l2_layout)
        toolbar = QHBoxLayout()
        self.selector_button = QPushButton("매크로 설정")
        self.selector_button.clicked.connect(self.open_selector_settings)
        toolbar.addWidget(self.selector_button)
        toolbar.addWidget(QLabel("시작번호"))
        self.run_start_number_spin = QSpinBox()
        self.run_start_number_spin.setRange(1, 1000000)
        self.run_start_number_spin.setValue(1)
        self.run_start_number_spin.setToolTip("지점 버튼을 누르기 전에 지정하세요. 전체 실행은 1입니다.")
        toolbar.addWidget(self.run_start_number_spin)
        self.run_start_number_spin.valueChanged.connect(self.save_start_number)
        self.batch_button = QPushButton("다중 지점 선택")
        self.batch_button.clicked.connect(self.open_batch_dialog)
        toolbar.addWidget(self.batch_button)
        toolbar.addStretch()
        l2_layout.addLayout(toolbar)
        self.popup_recovery_check = QCheckBox("예상치 못한 팝업/얼렛/프롬프트를 닫고 계속 진행")
        self.popup_recovery_check.setToolTip("명시적인 창 처리 단계와 매크로 대상이 있는 창은 유지합니다. 확인·프롬프트는 취소로 닫습니다.")
        self.popup_recovery_check.toggled.connect(self.save_popup_recovery)
        l2_layout.addWidget(self.popup_recovery_check)
        range_form = QHBoxLayout()
        range_form.addWidget(QLabel("범위 반복값"))
        self.range_kind = QComboBox()
        self.range_kind.addItem("기존 명단 번호", "legacy")
        for key, label in RANGE_TYPES.items():
            self.range_kind.addItem(label, key)
        self.range_start = QLineEdit()
        self.range_start.setPlaceholderText("시작: 2026-08")
        self.range_end = QLineEdit()
        self.range_end.setPlaceholderText("종료: 2025-01 (포함)")
        self.range_direction = QComboBox()
        self.range_direction.addItem("역순", "descending")
        self.range_direction.addItem("정순", "ascending")
        self.range_step = QSpinBox()
        self.range_step.setRange(1, 1000000)
        for widget in (self.range_kind, self.range_start, self.range_end, self.range_direction):
            range_form.addWidget(widget)
        range_form.addWidget(QLabel("간격"))
        range_form.addWidget(self.range_step)
        l2_layout.addLayout(range_form)
        self.range_hint = QLabel("값 범위 반복은 매크로의 반복지점 동작에서 선택합니다. 입력값은 {repeat_value}로 사용합니다.")
        self.range_hint.setWordWrap(True)
        l2_layout.addWidget(self.range_hint)
        self.range_kind.currentIndexChanged.connect(self.save_range_settings)
        self.range_direction.currentIndexChanged.connect(self.save_range_settings)
        self.range_step.valueChanged.connect(self.save_range_settings)
        self.range_start.editingFinished.connect(self.save_range_settings)
        self.range_end.editingFinished.connect(self.save_range_settings)
        l2_label = QLabel("지점선택")
        l2_layout.addWidget(l2_label)
        self.l2_container.setVisible(False)
        self.main_layout.addWidget(self.l2_container)

        self.l3_label = QLabel("작업 상태", self)
        self.l3_label.setVisible(False)

        self.branch_grid_layout = QGridLayout()
        self.branch_grid_layout.setSpacing(10)

        self.branch_container = QWidget()
        self.branch_container.setLayout(self.branch_grid_layout)
        self.branch_container.setVisible(False)
        self.main_layout.addWidget(self.branch_container)
        self.stop_batch_button = QPushButton("현재 지점 완료 후 중단")
        self.stop_batch_button.clicked.connect(self.stop_batch)
        self.stop_batch_button.setVisible(False)
        self.main_layout.addWidget(self.stop_batch_button)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(180)
        self.log_console.setPlaceholderText("작업 로그가 여기에 표시됩니다.")
        self.main_layout.addWidget(self.log_console)

        self.refresh_task_buttons()

    def _load_task_configs(self):
        try:
            with open(self.task_config_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
        except FileNotFoundError:
            saved_data = {}
        except Exception:
            saved_data = {}

        if isinstance(saved_data, dict) and "tasks" in saved_data:
            saved_configs = saved_data.get("tasks", {})
            self.deleted_task_keys = set(saved_data.get("deleted_task_keys", []))
        else:
            saved_configs = saved_data
            self.deleted_task_keys = set()
        return normalize_task_configs(saved_configs, self.deleted_task_keys)

    def _save_task_configs(self):
        data = {}
        for task_key, task_config in self.task_configs.items():
            data[task_key] = {
                "label": task_config["label"],
                "config_file": task_config["config_file"],
                "template_name": task_config.get("template_name", "empty"),
                "implemented": bool(task_config.get("implemented", True)),
            }
        with open(self.task_config_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 1,
                    "tasks": data,
                    "deleted_task_keys": sorted(self.deleted_task_keys),
                },
                f,
                ensure_ascii=False,
                indent=4,
            )

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def refresh_task_buttons(self):
        self._clear_layout(self.task_button_layout)
        self.task_buttons = {}
        for task_key, task_config in self.task_configs.items():
            button = QPushButton(task_config["label"])
            button.clicked.connect(lambda _, t=task_key: self.select_task(t))
            self.task_button_layout.addWidget(button)
            self.task_buttons[task_key] = button
        self.task_button_layout.addStretch()
        self.update_task_button_styles()

    def update_task_button_styles(self):
        for task_key, button in getattr(self, "task_buttons", {}).items():
            if task_key == self.current_task:
                button.setStyleSheet(
                    "QPushButton { background-color: #2563eb; color: white; font-weight: bold; "
                    "border: 1px solid #1d4ed8; padding: 6px 10px; }"
                )
            else:
                button.setStyleSheet("")

    def open_add_task_dialog(self):
        dialog = TaskConfigDialog(self, self._occupied_task_keys())
        if dialog.exec() != QDialog.Accepted:
            return

        task_key, task_config = dialog.task_data()
        task_config["template"] = task_template(task_config)
        self.task_configs[task_key] = task_config
        self.deleted_task_keys.discard(task_key)
        self._save_task_configs()
        self._ensure_task_selector_config(task_key)
        self.refresh_task_buttons()
        self.status_label.setText(f"작업을 추가했습니다: {task_config['label']}")

    def _occupied_task_keys(self):
        return set(self.task_configs) | {path.stem.removeprefix("federation_selectors_")
                                       for path in (self.root / "data").glob("federation_selectors_*.json")}

    def copy_task(self):
        if not self.current_task:
            QMessageBox.warning(self, "매크로 복사", "복사할 작업을 먼저 선택하세요.")
            return
        source = self.task_configs[self.current_task]
        dialog = TaskConfigDialog(self, self._occupied_task_keys())
        dialog.setWindowTitle("매크로를 새 작업으로 복사")
        dialog.name_edit.setText(source["label"] + " 복사")
        if dialog.exec() != QDialog.Accepted:
            return
        key, target = dialog.task_data()
        target["template_name"] = source.get("template_name", "empty")
        target["template"] = task_template(target)
        config = deepcopy(ensure_selector_config(self._selector_config_path(self.current_task), source["template"]))
        save_selector_config(self.root / "data" / target["config_file"], config)
        self.task_configs[key] = target
        self.deleted_task_keys.discard(key)
        self._save_task_configs()
        self.refresh_task_buttons()
        self.select_task(key)
        self._log(f"매크로 복사 완료: {source['label']} → {target['label']}")

    def save_start_number(self, value):
        if not self.current_task:
            return
        config = ensure_selector_config(self._selector_config_path(self.current_task), self.task_configs[self.current_task]["template"])
        config["start_number"] = value
        save_selector_config(self._selector_config_path(self.current_task), config)

    def save_popup_recovery(self, checked):
        if self.current_task:
            config = ensure_selector_config(self._selector_config_path(self.current_task), self.task_configs[self.current_task]["template"])
            config["dismiss_unexpected_popups"] = checked
            save_selector_config(self._selector_config_path(self.current_task), config)

    def load_range_settings(self, config):
        self.popup_recovery_check.blockSignals(True)
        self.popup_recovery_check.setChecked(bool(config.get("dismiss_unexpected_popups", False)))
        self.popup_recovery_check.blockSignals(False)
        settings = config.get("iteration", {})
        widgets = (self.range_kind, self.range_start, self.range_end, self.range_direction, self.range_step)
        for widget in widgets:
            widget.blockSignals(True)
        self.range_kind.setCurrentIndex(self.range_kind.findData(settings.get("kind", "legacy")))
        self.range_start.setText(str(settings.get("start", "")))
        self.range_end.setText(str(settings.get("end", "")))
        self.range_direction.setCurrentIndex(self.range_direction.findData(settings.get("direction", "descending")))
        self.range_step.setValue(settings.get("step", 1))
        for widget in widgets:
            widget.blockSignals(False)
        self._range_enabled()
        self._show_range_hint(settings)

    def _range_enabled(self):
        active = self.range_kind.currentData() != "legacy"
        self.run_start_number_spin.setEnabled(not active)
        for widget in (self.range_start, self.range_end, self.range_direction, self.range_step):
            widget.setEnabled(active)

    def save_range_settings(self, *_args):
        self._range_enabled()
        if not self.current_task:
            return
        settings = {"kind": self.range_kind.currentData(), "start": self.range_start.text().strip(),
                    "end": self.range_end.text().strip(), "direction": self.range_direction.currentData(),
                    "step": self.range_step.value()}
        config = ensure_selector_config(self._selector_config_path(self.current_task), self.task_configs[self.current_task]["template"])
        config["iteration"] = settings
        save_selector_config(self._selector_config_path(self.current_task), config)
        self._show_range_hint(settings)

    def _show_range_hint(self, settings):
        try:
            values = range_values(settings) if settings.get("kind", "legacy") != "legacy" else []
            self.range_hint.setText(f"{len(values)}회: {values[0]} → {values[-1]} / 매크로 동작 ‘값 범위 반복’, 입력값 {{repeat_value}}" if values else "기존 명단 번호 반복을 사용합니다.")
        except ValueError as exc:
            self.range_hint.setText(str(exc))

    def validate_run_range(self):
        self.save_range_settings()
        config = ensure_selector_config(self._selector_config_path(self.current_task), self.task_configs[self.current_task]["template"])
        if any(step.get("repeat_mode") == "range" for step in config["selectors"].values()):
            try:
                range_values(config.get("iteration", {}))
            except ValueError as exc:
                QMessageBox.warning(self, "반복 범위", str(exc))
                return False
        return True

    def open_batch_dialog(self):
        if not self.current_task or self.batch_thread is not None:
            return
        if not self.validate_run_range():
            return
        if any(thread.isRunning() for thread in self.login_threads):
            QMessageBox.warning(self, "다중 지점", "개별 실행과 브라우저 종료가 완료된 뒤 다중 지점을 실행하세요.")
            return
        dialog = BranchBatchDialog(self, self._load_branches())
        if dialog.exec() != QDialog.Accepted:
            return
        task = self.task_configs[self.current_task]
        self.batch_thread = BranchBatchThread(
            dialog.selected_branches(), self.login_thread_class, ClaimProcessThread,
            self._selector_config_path(self.current_task), task["template"], self.run_start_number_spin.value(),
            invoice=self.current_task == "invoice",
        )
        self.batch_thread.status_signal.connect(self._log)
        self.batch_thread.summary_signal.connect(self._batch_summary)
        self.batch_thread.finished.connect(self._batch_finished)
        self._set_batch_busy(True)
        self.batch_thread.start()

    def _set_batch_busy(self, busy):
        for widget in [self.l2_container, self.branch_container,
                       self.add_task_button, self.delete_task_button, self.copy_task_button, *self.task_buttons.values()]:
            widget.setEnabled(not busy)
        self.stop_batch_button.setVisible(busy)
        self.stop_batch_button.setEnabled(busy)

    def stop_batch(self):
        if self.batch_thread is not None:
            self.batch_thread.requestInterruption()
            self.stop_batch_button.setEnabled(False)
            self._log("중단 요청: 현재 지점 실행과 브라우저 종료 후 멈춥니다.")

    def _batch_summary(self, results):
        success = sum(result["success"] for result in results)
        self._log(f"다중 지점 종료: 성공 {success}, 실패 {len(results) - success}, 미실행 {len(self.batch_thread.branches) - len(results)}")

    def _batch_finished(self):
        self.batch_thread.deleteLater()
        self.batch_thread = None
        self._set_batch_busy(False)

    def closeEvent(self, event):
        if self.batch_thread is not None and self.batch_thread.isRunning():
            self.stop_batch()
            event.ignore()
            return
        super().closeEvent(event)

    def open_delete_task_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("작업 삭제")
        dialog.resize(420, 160)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("삭제할 작업을 선택하세요."))
        tasks = QComboBox()
        tasks.setObjectName("delete_task_selection")
        for task_key, task_config in self.task_configs.items():
            tasks.addItem(task_config["label"], task_key)
        index = tasks.findData(self.current_task)
        if index >= 0:
            tasks.setCurrentIndex(index)
        layout.addWidget(tasks)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("선택 작업 삭제")
        buttons.button(QDialogButtonBox.Ok).setEnabled(tasks.count() > 0)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.delete_task(tasks.currentData())

    def delete_task(self, task_key):
        task_config = self.task_configs.get(task_key)
        if not task_config:
            return

        reply = QMessageBox.question(
            self,
            "작업 삭제",
            f"'{task_config['label']}' 작업을 삭제할까요?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self.task_configs[task_key]
        if task_key in DEFAULT_TASK_CONFIGS:
            self.deleted_task_keys.add(task_key)
        self._save_task_configs()
        if self.current_task == task_key:
            self.current_task = None
            self.l2_container.setVisible(False)
            self.l3_label.setVisible(False)
            self.branch_container.setVisible(False)
            self.status_label.setText("")
        self.refresh_task_buttons()

    def open_selector_settings(self):
        if not self.current_task:
            QMessageBox.warning(self, "작업 선택", "먼저 작업을 선택하세요.")
            return

        task_config = self.task_configs[self.current_task]
        config_path = self._ensure_task_selector_config(self.current_task)
        SelectorConfigDialog(
            self,
            config_path,
            template=task_config["template"],
            task_label=task_config["label"],
            tool_name=self.tool_name,
        ).exec()
        config = ensure_selector_config(config_path, task_config["template"])
        self.run_start_number_spin.setValue(int(config.get("start_number", 1)))
        self.load_range_settings(config)

    def select_task(self, task):
        self.current_task = task
        self.update_task_button_styles()
        task_config = self.task_configs[task]
        self.selector_config_file = self._ensure_task_selector_config(task)
        config = ensure_selector_config(self.selector_config_file, task_config["template"])
        self.run_start_number_spin.setValue(int(config.get("start_number", 1)))
        self.load_range_settings(config)
        self.l2_container.setVisible(True)
        self.l3_label.setVisible(False)
        self.branch_container.setVisible(True)
        self.status_label.setText(f"{task_config['label']}: 지점을 선택하면 자동화가 시작됩니다.")
        self.refresh_buttons()

    def _selector_config_path(self, task):
        return self.root / "data" / self.task_configs[task]["config_file"]

    def _ensure_task_selector_config(self, task):
        task_config = self.task_configs[task]
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
        if not self.current_task:
            QMessageBox.warning(self, "작업 선택", "먼저 작업을 선택하세요.")
            return

        if not self.validate_run_range():
            return
        branch_name = branch.get("branch_name", "Unknown")
        self._log(f"[{branch_name}] {self.tool_name} 지점 버튼 클릭, {self.login_label} 로그인 시작")
        selected_task = self.current_task
        selected_config_file = self.selector_config_file

        login_thread = self.login_thread_class(branch)
        login_thread.macro_start_number = self.run_start_number_spin.value()
        self._log(f"이번 실행 시작번호: {login_thread.macro_start_number}")
        login_thread.finished_signal.connect(
            lambda msg, ok, lt=login_thread, task=selected_task, config_file=selected_config_file:
            self._on_longterm_finished(msg, ok, lt, task, config_file)
        )
        login_thread.start()
        self.login_threads.append(login_thread)

    def _on_longterm_finished(self, message, success, login_thread: LongtermLoginThread, task, config_file):
        self.status_label.setText(message)
        self._log(message, level=("INFO" if success else "ERROR"))
        if not success:
            return

        driver = getattr(login_thread, "driver", None)
        if not driver:
            self._log("로그인 드라이버를 가져올 수 없어 자동화를 시작할 수 없습니다.")
            return

        task_config = self.task_configs.get(task, {})
        claim_thread = ClaimProcessThread(
            driver,
            login_thread.branch,
            config_file,
            task_template(task_config),
            use_invoice_fallback=(task == "invoice"),
            start_number=getattr(login_thread, "macro_start_number", None),
        )
        self._log(f"윈도우 전환 준비: handles={driver.window_handles}, current_url={driver.current_url}")

        def _update_status(s):
            self.status_label.setText(s)
            self._log(s)

        def _on_finished(m, ok):
            self.status_label.setText(m)
            self._log(m, level=("INFO" if ok else "ERROR"))
            self._watch_browser(driver)

        claim_thread.status_signal.connect(_update_status)
        claim_thread.finished_signal.connect(_on_finished)
        claim_thread.start()
        self.login_threads.append(claim_thread)

    def _watch_browser(self, driver):
        """후속 자동화가 끝난 뒤 브라우저 종료를 감시합니다."""
        monitor = BrowserCloseMonitor(driver)
        monitor.closed_signal.connect(
            lambda: self._log("브라우저 종료를 감지해 자동화 프로세스를 종료했습니다.")
        )
        monitor.finished.connect(lambda m=monitor: self._remove_thread(m))
        self.login_threads.append(monitor)
        monitor.start()

    def _remove_thread(self, thread):
        if thread in self.login_threads:
            self.login_threads.remove(thread)

    def showEvent(self, event):
        super().showEvent(event)
        if self.branch_container.isVisible():
            self.refresh_buttons()

    def _load_branches(self):
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                task_key = "carefor" if self.tool_name == "케어포툴" else "federation"
                return filter_branches_for_task(
                    json.load(f), task_key, self.root / "data" / "branch_task_settings.json"
                )
        except FileNotFoundError:
            return []

    def _log(self, message, level="INFO"):
        if not should_log_message(message):
            return
        text = log(self.log_source, message, level=level)
        if hasattr(self, "log_console"):
            self.log_console.append(text)
            scroll_bar = self.log_console.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.maximum())


class TimedWebDriverWait(WebDriverWait):
    def __init__(self, owner, timeout):
        interval = float(owner.config.get("performance", {}).get("poll_interval", 0.5))
        super().__init__(owner.driver, timeout, poll_frequency=max(0.05, interval))
        self.owner = owner

    def until(self, method, message=""):
        with self.owner.measure_time("element_wait", f"timeout={self._timeout}s"):
            def guarded(driver):
                try:
                    if getattr(self.owner, "_popup_recovery_active", False) and getattr(self.owner, "_popup_recovery_count", 0) < 3:
                        if dismiss_native_alert(driver, self.owner._log):
                            self.owner._popup_recovery_count += 1
                            return False
                    return method(driver)
                except UnexpectedAlertPresentException as exc:
                    if getattr(self.owner, "_popup_recovery_active", False) and getattr(self.owner, "_popup_recovery_count", 0) < 3:
                        self.owner._log("[popup_recovery] WebDriver가 예상하지 못한 대화상자를 보고했습니다. 닫힘 상태 확인 후 요소 탐색을 계속합니다.")
                        self.owner.recover_unexpected_popups()
                        # WebDriver may already have dismissed the alert when reporting it.
                        return False
                    raise
            try:
                return super().until(guarded, message)
            except TimeoutException:
                if self.owner.recover_unexpected_popups():
                    return super().until(guarded, message)
                raise


class InvoiceProcessor:
    def __init__(self, driver, config_path: Path, template: dict | None = None, status_callback=None):
        self.driver = driver
        self.config = ensure_selector_config(config_path, template or SELECTOR_TEMPLATE)
        self.status_callback = status_callback or (lambda msg: None)
        self.timeouts = self.config.get("timeouts", {})
        self.timeout = int(self.timeouts.get("default", 20))
        self.wait = TimedWebDriverWait(self, self.timeout)
        self.last_element_key = None
        self.last_table_row = None
        self.last_table_selector = None
        self.last_table_expected_number = None

    def _log(self, message):
        self.status_callback(message)

    def recover_unexpected_popups(self):
        if not self.config.get("dismiss_unexpected_popups", False) or not getattr(self, "_popup_recovery_active", False):
            return False
        if getattr(self, "_popup_recovery_count", 0) >= 3:
            return False
        self._popup_recovery_count += 1
        return dismiss_blocking_popups(self.driver, self._popup_protected_handles,
                                       self._popup_target_locator, self._log)

    @contextmanager
    def measure_time(self, kind, detail=""):
        started = time.perf_counter()
        outcome = "ok"
        try:
            yield
        except Exception as exc:
            outcome = type(exc).__name__
            raise
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            self._log(f"[timing] step={getattr(self, '_timing_step', '-')} kind={kind} "
                      f"elapsed_ms={elapsed:.1f} outcome={outcome} {detail}")

    def sleep(self, seconds):
        with self.measure_time("fixed_wait", f"requested_ms={seconds * 1000:.1f}"):
            time.sleep(seconds)

    def selector_text(self, key):
        selector = self.config.get("selectors", {}).get(key, {})
        return (
            f"{key} ({selector.get('label', key)}) "
            f"by={selector.get('by', '')} value={selector.get('value', '')}"
        )

    def selector_timeout(self, selector, default=None):
        """Resolve a selector-specific timeout from seconds or a named timeout."""
        value = selector.get("timeout")
        if value in (None, ""):
            return default or self.timeout
        if isinstance(value, str) and value in self.timeouts:
            return float(self.timeouts[value])
        try:
            return max(0.1, float(value))
        except (TypeError, ValueError):
            raise ValueError(f"올바르지 않은 요소 대기시간입니다: {value}")

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
            if selector.get("type", "element") in {"alert", "confirm", "prompt", "window", "delay", "legacy_action"}:
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
        if process_type == "legacy_action":
            return self.handle_legacy_action_control(key, selector)
        return False

    def handle_delay_control(self, key, selector):
        value = selector.get("value", "0")
        try:
            seconds = max(0, int(str(value).strip() or "0"))
        except ValueError:
            raise ValueError(f"delay 값은 정수여야 합니다: {key}={value}")
        self._log(f"[delay] {key}: sleep {seconds}s")
        self.sleep(seconds)
        return True

    def legacy_wait_seconds(self, selector, default=0.2):
        value = str(selector.get("value", "")).strip()
        if not value:
            return default
        try:
            return max(0, float(value))
        except ValueError:
            raise ValueError(f"레거시 동작 값은 초 단위 숫자여야 합니다: {value}")

    def wait_loading_selector_done(self, key, selector):
        loading_selector = dict(selector)
        if not str(loading_selector.get("value", "")).strip():
            loading_selector = self.config.get("selectors", {}).get("loading_canvas", {})

        locator = build_locator(loading_selector)
        if not locator:
            self._log(f"[loading_wait] {key}: 로딩 셀렉터가 비어 있어 0.5초 대기")
            self.sleep(0.5)
            return True

        short_timeout = int(self.timeouts.get("short", 3))
        loading_timeout = int(self.timeouts.get("loading", 120))
        try:
            TimedWebDriverWait(self, short_timeout).until(EC.presence_of_element_located(locator))
            self._log(f"[loading_wait] {key}: 로딩 요소 감지, 사라짐 대기 timeout={loading_timeout}")
        except TimeoutException:
            self._log(f"[loading_wait] {key}: 로딩 요소 없음, 진행")
            return True

        TimedWebDriverWait(self, loading_timeout).until(EC.invisibility_of_element_located(locator))
        self._log(f"[loading_wait] {key}: 로딩 완료")
        return True

    def handle_legacy_action_control(self, key, selector):
        action = selector.get("action", "last_table_click")
        if action == "wait_loading_done":
            return self.wait_loading_selector_done(key, selector)

        seconds = self.legacy_wait_seconds(selector)
        if seconds:
            self._log(f"[legacy] {key}: wait {seconds}s")
            self.sleep(seconds)

        if action == "short_wait":
            return True

        if not self.last_table_row or not self.last_table_selector or self.last_table_expected_number is None:
            raise ValueError(f"레거시 동작 실패: 마지막 테이블 행 정보가 없습니다: {key}")

        if action in {"last_table_next_row_click", "last_table_previous_row_click"}:
            delta = 1 if action == "last_table_next_row_click" else -1
            row_label = "다음" if delta > 0 else "이전"
            log_label = "next_row" if delta > 0 else "previous_row"
            expected_number = self.last_table_expected_number + delta
            if expected_number < 1:
                raise ValueError(
                    f"레거시 동작 실패: {key} {row_label} 행({expected_number}번)은 유효하지 않습니다."
                )

            element, row_path, text = self.find_virtual_table_row_for_number(
                self.last_table_selector,
                expected_number,
                key=key,
                direction=delta,
            )
            if not element:
                self._log(
                    f"[legacy] {key}: {expected_number}번 {row_label} 행 가상 스크롤 탐색 실패, XPath fallback 시작"
                )
                element, row_path, text = self.find_table_row_for_number(
                    self.last_table_selector,
                    expected_number,
                    key=key,
                    debug=True,
                    direction=delta,
                )
            if not element:
                raise ValueError(
                    f"레거시 동작 실패: {key} {row_label} 행({expected_number}번)을 찾을 수 없습니다."
                )

            self._log(f"[legacy] {key}: {log_label} expected={expected_number} path={row_path} text={text}")
            self.click_table_row(key, element, self.last_table_selector, expected_number)
            return True

        repeat = 2 if action in {"last_table_double_click", "last_table_force_double_click"} else 1
        self._log(
            f"[legacy] {key}: action={action} repeat={repeat} "
            f"expected={self.last_table_expected_number}"
        )
        for index in range(repeat):
            if index:
                self.sleep(0.15)
            if action in {"last_table_force_click", "last_table_force_double_click"}:
                self.force_click_table_row(
                    key,
                    self.last_table_row,
                    self.last_table_selector,
                    self.last_table_expected_number,
                    dblclick=(action == "last_table_force_double_click" and index == repeat - 1),
                )
            else:
                self.click_table_row(
                    key,
                    self.last_table_row,
                    self.last_table_selector,
                    self.last_table_expected_number,
                )
        return True

    def handle_dialog_control(self, key, selector):
        timeout = self.selector_timeout(selector, self.timeouts.get("short", 3))
        configured_action = selector.get("action", "accept")
        required = not configured_action.endswith("_if_present")
        action = configured_action.removesuffix("_if_present")
        try:
            alert = TimedWebDriverWait(self, timeout).until(EC.alert_is_present())
            text = (alert.text or "").strip()
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
            self._log(f"[제어스킵] {message} - 조건부 대화상자가 없어 계속 진행합니다.")
            return False

    def handle_window_control(self, key, selector):
        action = selector.get("action", "keep")
        required = True
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
                raise ValueError(f"매크로 설정이 없습니다: {key}")
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
        wait = TimedWebDriverWait(self, timeout or self.timeout)
        element = wait.until(EC.presence_of_element_located(locator))
        self.last_element_key = key
        return element

    def wait_elements(self, key, timeout=None, context=None, run_controls=True):
        if run_controls:
            self.run_control_steps_before(key)
        locator = self.locator(key, context=context)
        wait = TimedWebDriverWait(self, timeout or self.timeout)
        elements = wait.until(lambda driver: driver.find_elements(*locator) or False)
        self.last_element_key = key
        return elements

    def wait_clickable_context(self, key, locator, timeout=None):
        last_scan = [time.monotonic()]
        last_diagnostic = [None]
        # Report frames are replaced after export-option actions. Waiting three
        # seconds before rescanning made every download/save iteration slow.
        # A short interval still lets the current context win without delaying
        # discovery of the replacement frame.
        scan_interval = max(
            0.1,
            float(getattr(self, "config", {}).get("performance", {}).get("context_scan_interval", 0.35)),
        )

        def log_context(message):
            if message != last_diagnostic[0]:
                self._log(message)
                last_diagnostic[0] = message

        def find(driver):
            try:
                element = EC.element_to_be_clickable(locator)(driver)
                if element:
                    return element
            except (NoSuchElementException, StaleElementReferenceException):
                pass
            now = time.monotonic()
            if now - last_scan[0] < scan_interval:
                return False
            last_scan[0] = now
            return find_clickable_context(driver, locator, log_context)

        try:
            return TimedWebDriverWait(self, timeout or self.timeout).until(find)
        except TimeoutException as exc:
            raise TimeoutException(f"{key}: 열린 창·프레임에서도 클릭 가능한 대상을 찾지 못했습니다. locator={locator}") from exc

    def click(self, key, timeout=None, required=True, context=None, run_controls=True):
        if run_controls:
            self.run_control_steps_before(key)
        locator = self.locator(key, required=required, context=context)
        if not locator:
            return None
        self._log(f"[click_wait] {self.selector_text(key)} timeout={timeout or self.timeout}")
        element = self.wait_clickable_context(key, locator, timeout)
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

    def pointer_click(self, element, key):
        last_state = None
        def ready(driver):
            nonlocal last_state
            state = driver.execute_script("""
                const el = arguments[0], r = el.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                let disabled = false;
                for (let p = el; p; p = p.parentElement) {
                    if (p.getAttribute('aria-disabled') === 'true' || p.getAttribute('status') === 'disabled') disabled = true;
                }
                return {ready: !!hit && !disabled && (hit === el || el.contains(hit)),
                        target: el.id, hit: hit ? hit.id : '', disabled};
            """, element)
            if state != last_state:
                self._log(f"[pointer_ready] {key}: {state}")
                last_state = state
            return state.get("ready") and element.is_enabled()
        TimedWebDriverWait(self, self.timeout).until(ready)
        ActionChains(self.driver).move_to_element(element).click_and_hold().pause(0.08).release().perform()
        self._log(f"[pointer_click] {key}: mouse down/up completed")

    def perform_action(self, key, element):
        action = self.config.get("selectors", {}).get(key, {}).get("action", "click")
        action = action if action in ACTION_TYPES else "click"
        if action == "hover":
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            ActionChains(self.driver).move_to_element(element).perform()
        elif action == "hover_click":
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            ActionChains(self.driver).move_to_element(element).perform()
            self.sleep(0.2)
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

            element = TimedWebDriverWait(self, timeout).until(EC.element_to_be_clickable(locator))
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

    def verify_text_step(self, key, selector, context=None):
        runtime_selector = apply_runtime_context(selector, context)
        locator = build_locator(runtime_selector)
        if not locator:
            raise ValueError(f"텍스트 검증 대상 셀렉터가 비어 있습니다: {key}")

        element = TimedWebDriverWait(self, self.timeout).until(EC.presence_of_element_located(locator))
        actual = (element.text or element.get_attribute("value") or "").strip()
        action = selector.get("action", "equals_repeat_number")
        expected = str((context or {}).get("repeat_number", "")).strip()

        self._log(f"[text_assert] {key}: action={action} actual={actual} expected={expected}")
        if action == "text_exists":
            if actual:
                return True
            raise ValueError(f"텍스트 검증 실패: 값이 비어 있습니다: {key}")

        if action == "contains_repeat_number":
            if expected and expected in actual:
                return True
            raise ValueError(f"텍스트 검증 실패: '{actual}' 안에 '{expected}'가 없습니다: {key}")

        if action == "equals_repeat_text":
            if actual == expected:
                return True
            raise ValueError(f"텍스트 검증 실패: '{actual}'가 '{expected}'와 일치하지 않습니다: {key}")

        actual_match = re.search(r"-?[\d,]+", actual)
        if not actual_match:
            raise ValueError(f"텍스트 검증 실패: 숫자를 찾을 수 없습니다: {key}={actual}")
        actual_number = int(actual_match.group(0).replace(",", ""))
        expected_number = int(expected or "0")
        if actual_number != expected_number:
            raise ValueError(
                f"텍스트 검증 실패: {key} 실제값={actual_number}, 기대값={expected_number}, 원문={actual}"
            )
        return True

    def element_number_text(self, element):
        text = (element.text or element.get_attribute("value") or "").strip()
        match = re.search(r"-?[\d,]+", text)
        if not match:
            return text, None
        return text, int(match.group(0).replace(",", ""))

    def increment_xpath_at(self, xpath, position, amount):
        matches = list(re.finditer(r"\[(\d+)\]", xpath))
        if position >= len(matches):
            return xpath
        match = matches[position]
        next_number = int(match.group(1)) + amount
        return f"{xpath[:match.start(1)]}{next_number}{xpath[match.end(1):]}"

    def table_xpath_candidates(self, base_xpath, offset):
        matches = list(re.finditer(r"\[(\d+)\]", base_xpath))
        if not matches:
            return [base_xpath]
        return [self.increment_xpath_at(base_xpath, position, offset) for position in range(len(matches) - 1, -1, -1)]

    def table_row_collection_locator(self, base_selector):
        by = base_selector.get("by", "xpath")
        value = base_selector.get("value", "").strip()
        if by == "xpath":
            parent_xpath = re.sub(r"/[^/]+\[\d+\]$", "", value)
            if parent_xpath and parent_xpath != value:
                return By.XPATH, f"{parent_xpath}/*"
        return build_locator(base_selector)

    def visible_table_rows(self, base_selector):
        locator = self.table_row_collection_locator(base_selector)
        if not locator:
            return []
        rows = self.driver.find_elements(*locator)
        if not self.config.get("performance", {}).get("batch_visibility", False):
            return [row for row in rows if self.table_row_in_view(self.table_click_target(row, base_selector))]
        return self.driver.execute_script("""
            const rows = arguments[0], selector = arguments[1];
            return rows.filter(row => {
                const cell = row.querySelector(selector) || row;
                const r = cell.getBoundingClientRect();
                const x = r.left + r.width / 2, y = r.top + r.height / 2;
                if (!r.width || !r.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
                for (let p = cell; p; p = p.parentElement) {
                    const s = getComputedStyle(p), b = p.getBoundingClientRect();
                    if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse' || Number(s.opacity) === 0) return false;
                    if (/(auto|scroll|hidden|clip)/.test(s.overflowY) && (y < b.top || y >= b.bottom)) return false;
                }
                const hit = document.elementFromPoint(x, y);
                return !!hit && (hit === cell || cell.contains(hit));
            });
        """, rows, self.table_number_cell_selector(base_selector))

    def table_row_in_view(self, row):
        if not row.is_displayed():
            return False
        return bool(self.driver.execute_script("""
            const row = arguments[0], r = row.getBoundingClientRect();
            const x = r.left + r.width / 2, y = r.top + r.height / 2;
            if (!r.width || !r.height || x < 0 || y < 0 ||
                x >= innerWidth || y >= innerHeight) return false;
            for (let p = row.parentElement; p; p = p.parentElement) {
                const s = getComputedStyle(p), b = p.getBoundingClientRect();
                if (/(auto|scroll|hidden|clip)/.test(s.overflowY) &&
                    (y < b.top || y >= b.bottom)) return false;
            }
            const hit = document.elementFromPoint(x, y);
            return !!hit && (hit === row || row.contains(hit));
        """, row))

    def table_number_cell_selector(self, base_selector):
        return str(base_selector.get("number_cell_selector") or "div[id$='cell_0_0:text']").strip()

    def table_row_number_text(self, row, base_selector=None):
        try:
            number_cell_selector = self.table_number_cell_selector(base_selector or {})
            number_cell = row.find_element(By.CSS_SELECTOR, number_cell_selector)
            text = (number_cell.text or number_cell.get_attribute("value") or "").strip()
            match = re.search(r"-?[\d,]+", text)
            if match:
                return text, int(match.group(0).replace(",", ""))
        except Exception as e:
            if base_selector and base_selector.get("_debug_number_cell"):
                self._log(f"[table_virtual] number_cell_error={type(e).__name__}: {e}")
            pass
        return self.element_number_text(row)

    def table_click_target(self, row, base_selector):
        try:
            return row.find_element(By.CSS_SELECTOR, self.table_number_cell_selector(base_selector))
        except Exception:
            return row

    def log_table_click_state(self, key, row, base_selector, phase):
        if not should_log_message("[table_click]"):
            return
        try:
            row_text, row_number = self.table_row_number_text(row, base_selector)
            row_class = row.get_attribute("class") or ""
            active_text = self.driver.execute_script(
                "return document.activeElement ? (document.activeElement.innerText || document.activeElement.value || '') : '';"
            )
            self._log(
                f"[table_click] {key}: {phase} row_number={row_number} "
                f"displayed={row.is_displayed()} enabled={row.is_enabled()} "
                f"class={row_class} text={row_text} active={str(active_text).strip()[:80]}"
            )
        except Exception as e:
            self._log(f"[table_click] {key}: {phase}_state_error={type(e).__name__}: {e}")

    def click_table_row(self, key, row, base_selector, expected_number):
        self.log_table_click_state(key, row, base_selector, "before")
        target = self.table_click_target(row, base_selector)
        if not self.table_row_in_view(target):
            row, _, _ = self.find_virtual_table_row_for_number(base_selector, expected_number, key=key)
            if row is None:
                raise ValueError(f"클릭 가능한 {expected_number}번 행을 찾지 못했습니다: {key}")
            target = self.table_click_target(row, base_selector)
        action = self.config.get("selectors", {}).get(key, {}).get("action", "click")
        action = action if action in ACTION_TYPES else "click"

        try:
            ActionChains(self.driver).move_to_element(target).click().perform()
        except Exception as e:
            self._log(f"[table_click] {key}: actionchains_error={type(e).__name__}: {e}")
            try:
                target.click()
            except Exception as inner:
                self._log(f"[table_click] {key}: native_click_error={type(inner).__name__}: {inner}")
                self.driver.execute_script("arguments[0].click();", target)

        self.sleep(0.15)
        self.log_table_click_state(key, row, base_selector, "after")
        text, actual_number = self.table_row_number_text(row, base_selector)
        if actual_number != expected_number:
            self._log(
                f"[table_click] {key}: click 후 행 번호 변경 감지 expected={expected_number} "
                f"actual={actual_number} text={text}"
            )
        self.last_table_row = row
        self.last_table_selector = base_selector
        self.last_table_expected_number = expected_number
        self._log(f"[action] {key}: {action}")

    def force_click_table_row(self, key, row, base_selector, expected_number, dblclick=False):
        self.log_table_click_state(key, row, base_selector, "force_before")
        target = self.table_click_target(row, base_selector)
        try:
            result = self.driver.execute_script(
                """
                const el = arguments[0];
                const dbl = arguments[1];
                const rect = el.getBoundingClientRect();
                const x = Math.floor(rect.left + rect.width / 2);
                const y = Math.floor(rect.top + rect.height / 2);
                const opts = {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: x,
                    clientY: y,
                    screenX: window.screenX + x,
                    screenY: window.screenY + y,
                    button: 0,
                    buttons: 1
                };
                const eventNames = ['mousemove', 'mousedown', 'mouseup', 'click'];
                for (const name of eventNames) {
                    el.dispatchEvent(new MouseEvent(name, opts));
                }
                if (dbl) {
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    el.dispatchEvent(new MouseEvent('click', opts));
                    el.dispatchEvent(new MouseEvent('dblclick', opts));
                }
                return {x, y, id: el.id || '', className: el.className || '', text: el.innerText || ''};
                """,
                target,
                dblclick,
            )
            self._log(f"[table_click] {key}: force_result={result}")
        except Exception as e:
            self._log(f"[table_click] {key}: force_error={type(e).__name__}: {e}")
            ActionChains(self.driver).move_to_element(target).click(target).perform()

        self.sleep(0.2)
        self.log_table_click_state(key, row, base_selector, "force_after")
        text, actual_number = self.table_row_number_text(row, base_selector)
        if actual_number != expected_number:
            self._log(
                f"[table_click] {key}: force click 후 행 번호 변경 감지 expected={expected_number} "
                f"actual={actual_number} text={text}"
            )
        self.last_table_row = row
        self.last_table_selector = base_selector
        self.last_table_expected_number = expected_number
        self._log(f"[action] {key}: {'force_double_click' if dblclick else 'force_click'}")

    def scroll_last_table_row_slightly(self, key, direction=1):
        try:
            scrolled = self.driver.execute_script(
                """
                let el = arguments[0];
                const direction = arguments[1] < 0 ? -1 : 1;
                while (el) {
                    const style = window.getComputedStyle(el);
                    const overflow = `${style.overflowY} ${style.overflow}`;
                    if (el.scrollHeight > el.clientHeight && /(auto|scroll)/.test(overflow)) {
                        const before = el.scrollTop;
                        el.scrollTop = Math.max(
                            0,
                            Math.min(el.scrollTop + (direction * 40), el.scrollHeight - el.clientHeight)
                        );
                        return {
                            method: 'scrollTop',
                            before,
                            after: el.scrollTop,
                            direction,
                            id: el.id || '',
                            className: el.className || ''
                        };
                    }
                    el = el.parentElement;
                }
                return {method: 'none'};
                """,
                self.last_table_row,
                direction,
            )
            self._log(f"[legacy] {key}: slight_scroll={scrolled}")
            if scrolled and scrolled.get("method") != "none" and scrolled.get("before") != scrolled.get("after"):
                self.sleep(0.1)
        except Exception as e:
            self._log(f"[legacy] {key}: slight_scroll_error={type(e).__name__}: {e}")

    def table_visible_signature(self, rows, base_selector):
        signature = []
        for row in rows:
            text, actual_number = self.table_row_number_text(row, base_selector)
            row_id = row.get_attribute("id") or ""
            signature.append(f"{actual_number}:{row_id}:{text[:40]}")
        return "|".join(signature)

    def scroll_virtual_table(self, key, base_selector, rows, direction=1):
        settings = self.config.get("table_scroll", {})
        expected = base_selector.get("_expected_number")
        numbers = base_selector.get("_visible_numbers")
        if numbers is None:
            numbers = [self.table_row_number_text(row, base_selector)[1] for row in rows] if expected else []
            numbers = [number for number in numbers if number is not None]
        gap = max(min(numbers) - expected, expected - max(numbers), 0) if numbers and expected else 0
        limit = max(1, min(12, int(base_selector.get("_wheel_burst_limit", settings.get("wheel_events", 8)))))
        events = min(limit, max(1, gap // 2)) if gap >= 5 else 1
        if rows:
            target = self.table_click_target(rows[len(rows) // 2], base_selector)
        else:
            locator = build_locator(settings)
            if not locator:
                return False
            target = self.driver.find_element(*locator)
        # Fix the pointer position in the viewport; virtual rows may be replaced mid-burst.
        point_script = """
            const r = arguments[0].getBoundingClientRect();
            const x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
            if (!r.width || !r.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
            const hit = document.elementFromPoint(x, y);
            if (!hit || !(hit === arguments[0] || arguments[0].contains(hit))) return null;
            return {x, y};
        """
        point = self.driver.execute_script(point_script, target)
        if not point:
            self._log(f"[scroll_move] {key}: wheel target obstructed, waiting for table readiness")
            def ready_point(driver):
                try:
                    fresh_rows = self.visible_table_rows(base_selector)
                    if fresh_rows:
                        fresh_target = self.table_click_target(fresh_rows[len(fresh_rows) // 2], base_selector)
                    else:
                        locator = build_locator(settings)
                        if not locator:
                            return False
                        fresh_target = driver.find_element(*locator)
                    return driver.execute_script(point_script, fresh_target) or False
                except StaleElementReferenceException:
                    return False
            try:
                point = TimedWebDriverWait(self, self.timeout).until(ready_point)
            except TimeoutException as exc:
                raise TimeoutException(f"테이블 휠 위치가 계속 가려져 있습니다: {key}, 목표={expected}번. 모달 또는 로딩 상태를 확인하세요.") from exc
        origin = ScrollOrigin.from_viewport(point["x"], point["y"])
        delta = (-1 if direction < 0 else 1) * int(settings.get("wheel_delta", 120))
        actions = ActionChains(self.driver)
        for index in range(events):
            actions.scroll_from_origin(origin, 0, delta)
            if index + 1 < events:
                actions.pause(0.03)
        actions.perform()
        self._log(f"[scroll_move] {key}: method=wheel events={events} delta={delta} target={expected} visible={numbers} gap={gap}")
        self.sleep(0.15)
        return True

    def find_virtual_table_row_for_number(self, base_selector, expected_number, key=None, debug=False, direction=1):
        max_scrolls = int(base_selector.get("max_scrolls", self.config.get("table_scroll", {}).get("max_scrolls", 500)))
        previous_signature = None
        unchanged = 0
        last_direction = None
        burst_limit = int(self.config.get("table_scroll", {}).get("wheel_events", 8))
        for attempt in range(max_scrolls + 1):
            rows = self.visible_table_rows(base_selector)
            if not rows and self.config.get("performance", {}).get("wait_for_rows", False):
                self._log(f"[table_ready_wait] {key}: 가려진 명단이 다시 보이면 목표 행부터 확인합니다")
                rows = TimedWebDriverWait(self, self.timeout).until(
                    lambda driver: self.visible_table_rows(base_selector) or False)
            row_info = [(row, *self.table_row_number_text(row, base_selector)) for row in rows]
            signature = "|".join(f"{number}:{text}" for _, text, number in row_info)
            if debug or attempt > 0:
                self._log(
                    f"[table_virtual] {key}: expected={expected_number} attempt={attempt} "
                    f"visible_count={len(rows)} number_cell={self.table_number_cell_selector(base_selector)} "
                    f"signature={signature[:500]}"
                )

            for row_index, (row, text, actual_number) in enumerate(row_info, start=1):
                if debug or attempt > 0:
                    self._log(
                        f"[table_virtual] {key}: row[{row_index}] "
                        f"id={row.get_attribute('id')} actual_number={actual_number} text={text}"
                    )
                if actual_number == expected_number:
                    return row, f"visible_row[{row_index}]", (row.text or text).strip()

            unchanged = unchanged + 1 if signature == previous_signature else 0
            if unchanged >= int(self.config.get("table_scroll", {}).get("max_unchanged", 8)):
                raise TimeoutException(f"테이블 휠 이동 후 명단 변화가 없습니다: {key}, 목표={expected_number}번, 연속={unchanged}회")
            previous_signature = signature
            numbers = [number for _, _, number in row_info if number is not None]
            if numbers:
                direction = -1 if expected_number < min(numbers) else 1
            if attempt == max_scrolls:
                break
            if last_direction is not None and direction != last_direction:
                burst_limit = max(1, burst_limit // 2)
            last_direction = direction
            scroll_selector = dict(base_selector, _expected_number=expected_number,
                                   _visible_numbers=numbers, _wheel_burst_limit=burst_limit)
            if not self.scroll_virtual_table(key, scroll_selector, rows, direction=direction):
                self._log(f"[table_virtual] {key}: scroll failed, stop")
                break

        return None, None, None

    def log_table_debug_state(self, key, expected_number, base_selector, candidates):
        try:
            state = self.driver.execute_script(
                """
                return {
                    readyState: document.readyState,
                    url: location.href,
                    x: window.scrollX,
                    y: window.scrollY,
                    width: window.innerWidth,
                    height: window.innerHeight,
                    activeText: document.activeElement ? (document.activeElement.innerText || document.activeElement.value || '') : ''
                };
                """
            )
            self._log(
                f"[table_debug] {key}: expected={expected_number} "
                f"ready={state.get('readyState')} scroll=({state.get('x')},{state.get('y')}) "
                f"viewport={state.get('width')}x{state.get('height')} url={state.get('url')}"
            )
            active_text = str(state.get("activeText", "")).strip()
            if active_text:
                self._log(f"[table_debug] {key}: activeText={active_text[:200]}")
        except Exception as e:
            self._log(f"[table_debug] {key}: page_state_error={type(e).__name__}: {e}")

        by = base_selector.get("by", "xpath")
        value = base_selector.get("value", "").strip()
        self._log(
            f"[table_debug] {key}: base by={by} value={value} "
            f"candidate_count={len(candidates)}"
        )

    def find_table_row_for_number(self, base_selector, expected_number, key=None, debug=False, direction=1):
        expected_offset = expected_number - 1
        by = base_selector.get("by", "xpath")
        value = base_selector.get("value", "").strip()
        if by != "xpath":
            locator = build_locator(base_selector)
            if not locator:
                return None, None, None
            element = TimedWebDriverWait(self, self.timeout).until(EC.presence_of_element_located(locator))
            text, actual_number = self.element_number_text(element)
            if debug:
                self._log(
                    f"[table_debug] {key}: non-xpath found displayed={element.is_displayed()} "
                    f"enabled={element.is_enabled()} actual_number={actual_number} text={text}"
                )
            if actual_number == expected_number and self.table_row_in_view(element):
                return element, value, text
            return self.find_virtual_table_row_for_number(
                base_selector,
                expected_number,
                key=key,
                debug=debug,
                direction=direction,
            )

        candidates = self.table_xpath_candidates(value, expected_offset)
        if debug:
            self.log_table_debug_state(key, expected_number, base_selector, candidates)

        for index, candidate_xpath in enumerate(candidates, start=1):
            candidate_selector = dict(base_selector)
            candidate_selector["value"] = candidate_xpath
            locator = build_locator(candidate_selector)
            if not locator:
                if debug:
                    self._log(f"[table_debug] {key}: candidate[{index}] locator_empty path={candidate_xpath}")
                continue
            try:
                elements = self.driver.find_elements(*locator)
                if not elements:
                    continue
                element = elements[0]
                text, actual_number = self.element_number_text(element)
                if debug:
                    self._log(
                        f"[table_debug] {key}: candidate[{index}] found "
                        f"displayed={element.is_displayed()} enabled={element.is_enabled()} "
                        f"location={element.location} size={element.size} "
                        f"actual_number={actual_number} text={text} path={candidate_xpath}"
                    )
                if actual_number == expected_number and self.table_row_in_view(element):
                    return element, candidate_xpath, text
            except StaleElementReferenceException as e:
                if debug:
                    self._log(
                        f"[table_debug] {key}: candidate[{index}] error={type(e).__name__}: {e} "
                        f"path={candidate_xpath}"
                    )
        return self.find_virtual_table_row_for_number(
            base_selector,
            expected_number,
            key=key,
            debug=debug,
            direction=direction,
        )

    def run_table_step(self, key, selector, context=None):
        base_selector = apply_runtime_context(selector, context)
        if context and context.get("repeat_total") is not None:
            base_selector["_total_rows"] = context["repeat_total"]
        if not build_locator(base_selector):
            raise ValueError(f"테이블 기준 셀렉터가 비어 있습니다: {key}")

        if context and "repeat_number" in context:
            expected_number = int(context.get("repeat_number", 1))
            element, row_path, text = self.find_virtual_table_row_for_number(
                base_selector,
                expected_number,
                key=key,
            )
            if not element:
                self._log(f"[table_debug] {key}: {expected_number}번 가상 스크롤 탐색 실패, XPath fallback 시작")
                element, row_path, text = self.find_table_row_for_number(
                    base_selector,
                    expected_number,
                    key=key,
                    debug=True,
                )
            if not element:
                raise ValueError(
                    f"테이블 증가 검증 실패: {key} {expected_number}번 행을 찾거나 검증할 수 없습니다."
                )

            self._log(f"[table] {key}: {expected_number}번 검증 OK path={row_path} text={text}")
            self.click_table_row(key, element, base_selector, expected_number)
            return 1

        expected_number = 1
        success_count = 0
        while True:
            element, row_path, text = self.find_table_row_for_number(base_selector, expected_number, key=key)
            if not element:
                self._log(f"[table_debug] {key}: {expected_number}번 1차 탐색 실패, 상세 진단 시작")
                element, row_path, text = self.find_table_row_for_number(
                    base_selector,
                    expected_number,
                    key=key,
                    debug=True,
                )
            if not element:
                if success_count == 0:
                    raise ValueError(f"테이블 증가 검증 실패: {key} 1번 행을 찾거나 검증할 수 없습니다.")
                self._log(f"[table] {key}: {expected_number}번 행 없음/불일치, 종료")
                break

            self._log(f"[table] {key}: {expected_number}번 검증 OK path={row_path} text={text}")
            self.click_table_row(key, element, base_selector, expected_number)
            success_count += 1
            expected_number += 1

        self._log(f"[table] {key}: 처리 완료 count={success_count}")
        return success_count

    def run_selector_step(self, key, selector, context=None):
        previous = getattr(self, "_timing_step", "-")
        self._timing_step = key
        self._popup_recovery_active = self.config.get("dismiss_unexpected_popups", False) and selector.get("type", "element") not in {"alert", "confirm", "prompt", "window"}
        self._popup_recovery_count = 0
        if self._popup_recovery_active:
            self._popup_target_locator = build_locator(apply_runtime_context(selector, context)) if selector.get("type", "element") in {"element", "table", "text_assert"} else None
            if not hasattr(self, "_popup_known_handles"):
                self._popup_known_handles = set(self.driver.window_handles)
            self._popup_protected_handles = self._popup_known_handles
        try:
            with self.measure_time("step", f"action={selector.get('action')} repeat={(context or {}).get('repeat_number', '-')} label={selector.get('label', key)}"):
                try:
                    return self._run_selector_step(key, selector, context)
                except ElementClickInterceptedException:
                    if not self.recover_unexpected_popups():
                        raise
                    return self._run_selector_step(key, selector, context)
        finally:
            self._timing_step = previous
            self._popup_recovery_active = False

    def _run_selector_step(self, key, selector, context=None):
        process_type = selector.get("type", "element")
        if process_type == "url_navigation":
            base_url = str(selector.get("value", "")).strip()
            payload = str(selector.get("payload", ""))
            if not base_url:
                raise ValueError(f"URL 이동 주소가 비어 있습니다: {key}")
            target_url = f"{base_url}?{payload}"
            self._log(f"[url_navigation] {key}: {target_url}")
            self.driver.get(target_url)
            return True
        if process_type == "element":
            if selector.get("action") == "input_text":
                return self.input_field_text(key, selector, context)
            if selector.get("action") == "pointer_click":
                locator = build_locator(apply_runtime_context(selector, context))
                element = self.wait_clickable_context(
                    key,
                    locator,
                    self.selector_timeout(selector),
                )
                self.pointer_click(element, key)
                expected_xpath = selector.get("expected_visible_xpath")
                if expected_xpath:
                    self._log(f"[screen_wait] {key}: click sent, waiting for next screen")
                    TimedWebDriverWait(self, self.timeouts.get("long", 60)).until(
                        EC.visibility_of_element_located((By.XPATH, expected_xpath)))
                    self._log(f"[screen_ready] {key}: next screen visible")
                return True
            if selector.get("action") == "select_text":
                return self.select_field_text(key, selector, context)
            return self.click(
                key,
                timeout=self.selector_timeout(selector),
                context=context,
                run_controls=False,
            )
        if process_type == "table":
            return self.run_table_step(key, selector, context=context)
        if process_type == "text_assert":
            return self.verify_text_step(key, selector, context=context)
        if process_type in {"alert", "confirm", "prompt", "window", "delay", "legacy_action"}:
            return self.run_control_step(key, selector, context=context)
        if process_type in {"repeat_start", "repeat_end"}:
            self._log(f"[workflow_skip] {key}: repeat marker")
            return None
        raise ValueError(f"지원하지 않는 처리 종류입니다: {key} ({process_type})")

    def repeat_count(self, key, selector, context=None):
        action = selector.get("action", "element_text")
        value = str(apply_runtime_context(selector, context).get("value", "")).strip()
        if action == "element_text":
            locator = build_locator(apply_runtime_context(selector, context))
            if not locator:
                raise ValueError(f"반복 횟수 특정값 셀렉터가 비어 있습니다: {key}")
            element = TimedWebDriverWait(self, self.timeout).until(EC.presence_of_element_located(locator))
            value = (element.text or element.get_attribute("value") or "").strip()

        match = re.search(r"-?[\d,]+", value)
        if not match:
            raise ValueError(f"반복 횟수를 숫자로 변환할 수 없습니다: {key}={value}")
        count = int(match.group(0).replace(",", ""))
        if count < 0:
            raise ValueError(f"반복 횟수는 0 이상이어야 합니다: {key}={count}")
        return count

    def input_field_text(self, key, selector, context=None):
        expected = self.runtime_text_value(selector.get("expected_value", ""), context)
        locator = build_locator(apply_runtime_context(selector, context))
        if not locator:
            raise ValueError(f"입력 대상 셀렉터가 없습니다: {key}")
        container = self.wait_clickable_context(key, locator)
        if container.tag_name.lower() in {"input", "textarea"}:
            field = container
        else:
            fields = [element for element in container.find_elements(By.CSS_SELECTOR, "input, textarea")
                      if element.is_displayed() and element.is_enabled()]
            if len(fields) != 1:
                raise ValueError(f"{key}: 지정한 영역에서 입력칸을 하나로 찾을 수 없습니다 ({len(fields)}개). 입력칸 XPath를 확인하세요.")
            field = fields[0]
        # element_to_be_clickable does not detect a Nexacro/modal overlay that
        # covers the field. Wait until the field is the actual pointer target.
        self.pointer_click(field, key)
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(expected)
        field.send_keys(Keys.TAB)

        def matches(_driver):
            actual = str(field.get_attribute("value") or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", expected):
                return actual.replace("-", "").replace("/", "") == expected.replace("-", "")
            return actual == expected

        try:
            TimedWebDriverWait(self, self.timeout).until(matches)
        except TimeoutException as exc:
            raise ValueError(f"{key}: 입력값 검증 실패 (기대값 {expected}, 실제값 {field.get_attribute('value')})") from exc
        self._log(f"[input_ok] {key}: {expected}")
        self.last_element_key = key
        return True

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
        raise ValueError(f"반복지점 종료를 찾을 수 없습니다: {items[start_index][0]}")

    def find_condition_indices(self, items, start_index):
        depth = 0
        true_index = None
        false_index = None
        for index in range(start_index, len(items)):
            process_type = items[index][1].get("type", "element")
            if process_type == "condition_start":
                depth += 1
            elif process_type == "condition_true" and depth == 1:
                true_index = index
            elif process_type == "condition_false" and depth == 1:
                false_index = index
            elif process_type == "condition_end":
                if depth == 1:
                    if true_index is None or false_index is None:
                        raise ValueError(f"조건처리 참/거짓 구역을 찾을 수 없습니다: {items[start_index][0]}")
                    return true_index, false_index, index
                depth -= 1
        raise ValueError(f"조건처리 종료를 찾을 수 없습니다: {items[start_index][0]}")

    def runtime_text_value(self, value, context=None):
        return apply_runtime_context({"value": str(value or "")}, context).get("value", "")

    def field_text(self, element):
        """Read the current field, not all options or a hidden editor's value."""
        if element.tag_name.lower() == "select":
            selected = Select(element).first_selected_option
            if not (selected.get_attribute("value") or "").strip():
                return ""
            return (selected.text or "").strip()
        if element.tag_name.lower() in {"input", "textarea"}:
            return (element.get_attribute("value") or "").strip()
        editors = element.find_elements(By.CSS_SELECTOR, "input, textarea, select")
        for editor in editors:
            if editor.is_displayed():
                return self.field_text(editor)
        displays = element.find_elements(By.CSS_SELECTOR, "[id$=':text'], [id$='comboedit'], [role='textbox']")
        for display in displays:
            if display.is_displayed():
                return (display.text or display.get_attribute("value") or "").replace("\u200b", "").strip()
        return (element.text or "").replace("\u200b", "").strip()

    def select_field_text(self, key, selector, context=None):
        if selector.get("selection_method") == "keyboard":
            return self.select_field_with_keys(key, selector, context)
        expected = self.runtime_text_value(selector.get("expected_value", ""), context).strip()
        if not expected:
            raise ValueError(f"선택할 옵션 텍스트가 비어 있습니다: {key}")
        locator = build_locator(apply_runtime_context(selector, context))
        if not locator:
            raise ValueError(f"선택 대상 셀렉터가 비어 있습니다: {key}")
        wait = TimedWebDriverWait(self, self.timeout)
        element = wait.until(EC.element_to_be_clickable(locator))
        if self.field_text(element) == expected:
            self._log(f"[select_text] {key}: 이미 선택됨 expected={expected}")
            return True
        if element.tag_name.lower() == "select":
            Select(element).select_by_visible_text(expected)
        else:
            native = [item for item in element.find_elements(By.TAG_NAME, "select") if item.is_displayed()]
            if native:
                Select(native[0]).select_by_visible_text(expected)
            else:
                dropdown_xpath = selector.get("dropdown_xpath", "").strip()
                buttons = ([wait.until(EC.element_to_be_clickable((By.XPATH, dropdown_xpath)))]
                           if dropdown_xpath else [item for item in element.find_elements(
                    By.CSS_SELECTOR, "[id*='dropbutton'], [id*='dropdownbutton'], [aria-haspopup='listbox']"
                ) if item.is_displayed() and item.is_enabled()])
                target = buttons[0] if buttons else element
                self._log(f"[field_select] {key}: open tag={target.tag_name} id={target.get_attribute('id')}")
                # Do not scroll a Nexacro grid cell with scrollIntoView or synthesize a JS click.
                self.pointer_click(target, key)
                if not buttons:
                    # Grid combo editors can be created only after activating the cell.
                    def opened_control(driver):
                        current = driver.find_element(*locator)
                        for button in current.find_elements(By.CSS_SELECTOR,
                                "[id*='dropbutton'], [id*='dropdownbutton'], [aria-haspopup='listbox']"):
                            if button.is_displayed() and button.is_enabled():
                                return button
                        popups = driver.find_elements(By.CSS_SELECTOR,
                            "[role='listbox'], [id*='combolist'], [id*='popup'][id*='list']")
                        return True if any(popup.is_displayed() for popup in popups) else False

                    opened = wait.until(opened_control)
                    if opened is not True:
                        self._log(f"[field_select] {key}: activated dropdown id={opened.get_attribute('id')}")
                        self.pointer_click(opened, key)

            def visible_option(driver):
                popups = driver.find_elements(By.CSS_SELECTOR,
                    "[role='listbox'], [id*='combolist'], [id*='listbox'], [id*='popup'][id*='list']")
                candidates = {}
                for popup in popups:
                    if popup.is_displayed():
                        for item in popup.find_elements(By.XPATH, ".//*[not(*)]"):
                            candidates[item.id] = item
                matches = [item for item in candidates.values()
                           if item.is_displayed() and item.is_enabled()
                           and (item.text or "").strip() == expected]
                if len(matches) > 1:
                    raise ValueError(f"동일한 옵션이 여러 개 보여 선택할 수 없습니다: {key} ({expected})")
                return matches[0] if matches else False

            if not native:
                try:
                    try:
                        option = TimedWebDriverWait(self, min(self.timeout, 3)).until(visible_option)
                    except TimeoutException:
                        popups = self.driver.find_elements(By.CSS_SELECTOR,
                            "[role='listbox'], [id*='combolist'], [id*='listbox'], [id*='popup'][id*='list']")
                        if not any(popup.is_displayed() for popup in popups):
                            self._log(f"[field_select] {key}: popup not opened, retry pointer click once")
                            if dropdown_xpath:
                                target = wait.until(EC.element_to_be_clickable((By.XPATH, dropdown_xpath)))
                            self.pointer_click(target, key)
                        else:
                            self._log(f"[field_select] {key}: popup visible, waiting for option text")
                        option = wait.until(visible_option)
                except TimeoutException as exc:
                    self._log(f"[field_select] {key}: 옵션 탐색 실패 dropdown_xpath={selector.get('dropdown_xpath', '')} expected={expected}")
                    raise TimeoutException(f"드롭다운 클릭 후 '{expected}' 옵션을 찾지 못했습니다: {key}") from exc
                self._log(f"[field_select] {key}: option id={option.get_attribute('id')} text={expected}")
                option.click()
        try:
            wait.until(lambda driver: self.field_text(driver.find_element(*locator)) == expected)
        except TimeoutException as exc:
            raise TimeoutException(f"필드 선택값 검증 실패: {key} (기대값={expected}). 저장을 중단합니다.") from exc
        self._log(f"[select_text] {key}: 선택값 검증 OK expected={expected}")
        return True

    def select_field_with_keys(self, key, selector, context=None):
        expected = self.runtime_text_value(selector.get("expected_value", ""), context).strip()
        locator = build_locator(apply_runtime_context(selector, context))
        if not expected or not locator:
            raise ValueError(f"키보드 선택 대상 또는 기대값이 비어 있습니다: {key}")
        wait = TimedWebDriverWait(self, self.timeout)
        element = wait.until(EC.element_to_be_clickable(locator))
        if self.field_text(element) == expected:
            return True
        # Focus the field itself, not the decorative dropdown icon.
        self.pointer_click(element, key)
        limit = max(1, min(50, int(selector.get("max_key_steps", 10))))
        for index in range(1, limit + 1):
            ActionChains(self.driver).send_keys(Keys.ARROW_DOWN).perform()
            self.sleep(0.15)
            element = self.driver.find_element(*locator)
            actual = self.field_text(element)
            self._log(f"[field_key] {key}: key=ARROW_DOWN attempt={index}/{limit} actual={actual!r} expected={expected!r}")
            if actual != expected:
                continue
            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            self.sleep(0.15)
            wait.until(lambda driver: self.field_text(driver.find_element(*locator)) == expected)
            self._log(f"[field_key] {key}: ENTER 선택값 검증 OK expected={expected}")
            return True
        raise TimeoutException(f"아래 방향키 {limit}회 입력 후 '{expected}'에 도달하지 못했습니다: {key}. 저장을 중단합니다.")

    def condition_result(self, key, selector, context=None):
        previous = getattr(self, "_timing_step", "-")
        self._timing_step = key
        try:
            with self.measure_time("condition", f"repeat={(context or {}).get('repeat_number', '-')}"):
                return self._condition_result(key, selector, context)
        finally:
            self._timing_step = previous

    def _condition_result(self, key, selector, context=None):
        runtime_selector = apply_runtime_context(selector, context)
        locator = build_locator(runtime_selector)
        if not locator:
            raise ValueError(f"조건처리 대상 셀렉터가 비어 있습니다: {key}")

        element = TimedWebDriverWait(self, self.timeout).until(EC.presence_of_element_located(locator))
        action = selector.get("action", "text_exists")
        actual = (self.field_text(element) if action in {"field_empty", "field_not_empty"}
                  else (element.text or element.get_attribute("value") or "").strip())
        if action in {"field_empty", "field_not_empty"}:
            self._log(f"[field_read] {key}: tag={element.tag_name} id={element.get_attribute('id')} value={actual!r}")
        expected = self.runtime_text_value(selector.get("expected_value", ""), context).strip()
        repeat_number = str((context or {}).get("repeat_number", "")).strip()

        if action == "field_empty":
            result = not actual
        elif action == "field_not_empty":
            result = bool(actual)
        elif action == "text_exists":
            result = bool(actual)
        elif action == "equals_value":
            result = actual == expected
        elif action == "contains_value":
            result = bool(expected) and expected in actual
        elif action == "equals_repeat_number":
            result = actual == repeat_number
        elif action == "contains_repeat_number":
            result = bool(repeat_number) and repeat_number in actual
        else:
            raise ValueError(f"지원하지 않는 조건처리 동작입니다: {key} ({action})")

        self._log(
            f"[condition] {key}: action={action} result={result} "
            f"actual={actual[:120]} expected={expected or repeat_number}"
        )
        return result

    def run_workflow_items_once(self, items, context=None):
        index = 0
        while index < len(items):
            key, selector = items[index]
            if selector.get("type", "element") == "repeat_start":
                end_index = self.find_repeat_end_index(items, index)
                repeat_items = items[index + 1:end_index]
                if selector.get("repeat_mode") == "range":
                    values = range_values(self.config.get("iteration", {}))
                    base_window = self.driver.current_window_handle if self.config.get("restore_range_context", False) else None
                    self._log(f"[range_start] {key}: {values[0]} → {values[-1]}, {len(values)}회")
                    for ordinal, value in enumerate(values):
                        if ordinal and base_window is not None:
                            if base_window not in self.driver.window_handles:
                                raise ValueError("반복 시작 화면의 창이 닫혀 다음 연월을 진행할 수 없습니다.")
                            self.driver.switch_to.window(base_window)
                            self.driver.switch_to.default_content()
                            self._log(f"[range_context] {value}: 반복 시작 창의 기본 화면으로 복귀")
                        repeat_context = dict(context or {})
                        repeat_context.update(repeat_index=ordinal, repeat_number=value,
                                              repeat_value=value, repeat_total=len(values))
                        self._log(f"[range] {key}: {ordinal + 1}/{len(values)}, value={value}")
                        self.run_workflow_items_once(repeat_items, context=repeat_context)
                    self._log(f"[range_end] {key}")
                    index = end_index + 1
                    continue
                count = self.repeat_count(key, selector, context=context)
                repeat_mode = selector.get("repeat_mode", "fixed")
                self._log(f"[repeat_start] {key}: mode={REPEAT_MODES.get(repeat_mode, repeat_mode)} count={count}")
                start = int(self.config.get("start_number", 1)) if repeat_mode == "increment" and not context else 1
                if start < 1 or (count and start > count):
                    raise ValueError(f"시작번호가 명단 범위를 벗어났습니다: {start} (총 {count}명)")
                self._log(f"[repeat_start_number] {key}: start={start} total={count}")
                for repeat_index in range(start - 1, count):
                    repeat_context = dict(context or {})
                    repeat_context["repeat_index"] = repeat_index
                    repeat_context["repeat_total"] = count
                    repeat_context["repeat_number"] = repeat_index + 1 if repeat_mode == "increment" else count
                    repeat_context["repeat_value"] = repeat_context["repeat_number"]
                    self._log(f"[repeat] {key}: {repeat_index + 1}/{count}")
                    self.run_workflow_items_once(repeat_items, context=repeat_context)
                self._log(f"[repeat_end] {key}")
                index = end_index + 1
                continue
            if selector.get("type", "element") == "condition_start":
                true_index, false_index, end_index = self.find_condition_indices(items, index)
                is_true = self.condition_result(key, selector, context=context)
                if is_true:
                    branch_items = items[true_index + 1:false_index]
                    self._log(f"[condition_true] {key}")
                else:
                    branch_items = items[false_index + 1:end_index]
                    self._log(f"[condition_false] {key}")
                self.run_workflow_items_once(branch_items, context=context)
                self._log(f"[condition_end] {key}")
                index = end_index + 1
                continue
            if selector.get("type", "element") == "repeat_end":
                raise ValueError(f"반복지점 시작 없이 종료가 나타났습니다: {key}")
            if selector.get("type", "element") in {"condition_true", "condition_false", "condition_end"}:
                raise ValueError(f"조건처리 시작 없이 구역/종료가 나타났습니다: {key}")
            self.run_selector_step(key, selector, context=context)
            index += 1

    def run_configured_workflow(self):
        self._log("[workflow] 설정 순서 실행 시작")
        self.run_workflow_items_once(list(self.config.get("selectors", {}).items()))
        self._log("[workflow] 설정 순서 실행 완료")

    def wait_loading_done(self):
        locator = self.locator("loading_canvas", required=False)
        if not locator:
            self.sleep(0.5)
            return

        long_timeout = int(self.timeouts.get("loading", 120))
        try:
            TimedWebDriverWait(self, int(self.timeouts.get("short", 3))).until(EC.presence_of_element_located(locator))
        except TimeoutException:
            return
        try:
            TimedWebDriverWait(self, long_timeout).until(EC.invisibility_of_element_located(locator))
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
                        self.sleep(0.2)
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
        self.sleep(0.5)
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

    def __init__(
        self,
        driver,
        branch: dict,
        config_path: Path,
        template: dict | None = None,
        use_invoice_fallback: bool = False,
        start_number: int | None = None,
    ):
        super().__init__()
        self.driver = driver
        self.branch = branch
        self.config_path = config_path
        self.template = template or SELECTOR_TEMPLATE
        self.use_invoice_fallback = use_invoice_fallback
        self.start_number = start_number

    def switch_window(self):
        try:
            config = ensure_selector_config(self.config_path, self.template)
            window_index = int(config.get("browser", {}).get("window_index", -1))
            if window_index > 0:
                WebDriverWait(self.driver, 3).until(lambda d: len(d.window_handles) >= window_index)
                handles = self.driver.window_handles
                target_index = min(window_index - 1, len(handles) - 1)
            else:
                WebDriverWait(self.driver, 3).until(lambda d: len(d.window_handles) > 1)
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

            processor = InvoiceProcessor(self.driver, self.config_path, self.template, status_callback=self.status_signal.emit)
            if self.start_number is not None:
                processor.config["start_number"] = self.start_number
            processor.snapshot("초기 상태")
            if processor.config.get("selectors"):
                self.status_signal.emit("[단계] 설정 요소 한 번 실행")
                processor.run_configured_workflow()
                self.finished_signal.emit("설정된 요소 자동화 작업이 완료되었습니다.", True)
                return

            if not self.use_invoice_fallback:
                self.finished_signal.emit("설정된 매크로가 없어 자동화를 시작할 수 없습니다. 매크로 설정을 먼저 입력하세요.", False)
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
