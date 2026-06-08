import json
import time
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QThread, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
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


SELECTOR_TEMPLATE = {
    "version": 1,
    "timeouts": {
        "default": 20,
        "short": 3,
        "long": 60,
        "loading": 120,
    },
    "selectors": {
        "main_menu": {
            "label": "상단 메뉴 - 급여비용청구",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "payroll_claim_dropdown": {
            "label": "드롭다운 메뉴 - 급여비용청구",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "claim_page_warning_close": {
            "label": "급여비용청구 페이지 경고 모달 닫기/확인",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "operation_guide_close": {
            "label": "운영안내 팝업 닫기",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "claim_button": {
            "label": "우측 주황색 청구하기 버튼",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "entry_notice_tab": {
            "label": "원청구 모달 탭 - 입퇴소신고내용관리",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "entry_notice_rows": {
            "label": "입소신고자 테이블 행 목록",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "recipient_select_all_checkbox": {
            "label": "수급자명 테이블 상단 전체 체크박스",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "recipient_checkboxes": {
            "label": "수급자명 테이블 개별 체크박스 목록",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "add_recipient_button": {
            "label": "청구대상자로 넘기는 > 버튼",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "confirm_add_recipient": {
            "label": "청구대상자로 추가 확인 버튼",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "loading_canvas": {
            "label": "진행중 캔버스/로딩 요소",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "claim_target_created_message": {
            "label": "청구대상자가 생성되었습니다 알림/확인",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "salary_data_tab": {
            "label": "원청구 모달 탭 - 급여내용 자료 관리",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "search_button": {
            "label": "급여내용 자료 관리 조회 버튼",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "claim_target_rows": {
            "label": "청구대상자 테이블 행 목록",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "save_button": {
            "label": "저장 버튼",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "confirm_save": {
            "label": "급여자료 저장 확인 버튼",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "save_completed_confirm": {
            "label": "저장되었습니다 알림 확인 버튼",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "generate_statement_button": {
            "label": "명세서자동생성 버튼",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "statement_register_complete_button": {
            "label": "자식 모달 - 명세서 등록완료 버튼",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "pay_result_select": {
            "label": "급여제공결과등록 - 급여제공결과 셀렉트",
            "by": "xpath",
            "value": "",
            "required": True,
        },
        "pay_result_continue_option": {
            "label": "급여제공결과 셀렉트 옵션 - 계속",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "pay_result_save_button": {
            "label": "급여제공결과등록 저장 버튼",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "confirm_pay_result_save": {
            "label": "급여제공결과 저장 확인 버튼",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "statement_completed_confirm": {
            "label": "명세서가 등록완료되었습니다 확인 버튼",
            "by": "xpath",
            "value": "",
            "required": False,
        },
        "statement_auto_modal_close": {
            "label": "시설/단기보호 청구명세서 자동생성 닫기",
            "by": "xpath",
            "value": "",
            "required": True,
        },
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
    "timeouts": {
        "default": 20,
        "short": 3,
        "long": 60,
        "loading": 120,
    },
    "selectors": {},
    "popup_close_selectors": [
        {"label": "공통 버튼 - 닫기", "by": "xpath", "value": "//button[normalize-space(.)='닫기']"},
        {"label": "공통 버튼 - 확인", "by": "xpath", "value": "//button[normalize-space(.)='확인']"},
        {"label": "공통 링크 - 닫기", "by": "xpath", "value": "//a[normalize-space(.)='닫기']"},
        {"label": "공통 링크 - 확인", "by": "xpath", "value": "//a[normalize-space(.)='확인']"},
    ],
}


TASK_CONFIGS = {
    "invoice": {
        "label": "청구 명세서 만들기",
        "config_file": "federation_selectors_invoice.json",
        "template": SELECTOR_TEMPLATE,
        "implemented": True,
    },
    "long_service": {
        "label": "장기근속수당 입력하기",
        "config_file": "federation_selectors_long_service.json",
        "template": EMPTY_SELECTOR_TEMPLATE,
        "implemented": False,
    },
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
    data.setdefault("selectors", {})
    data.setdefault("popup_close_selectors", [])

    for key, value in template["timeouts"].items():
        if key not in data["timeouts"]:
            data["timeouts"][key] = value
            changed = True

    for key, selector in template["selectors"].items():
        if key not in data["selectors"]:
            data["selectors"][key] = selector
            changed = True
        else:
            data["selectors"][key].setdefault("label", selector["label"])
            data["selectors"][key].setdefault("by", selector["by"])
            data["selectors"][key].setdefault("value", "")
            data["selectors"][key].setdefault("required", selector["required"])

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

        self.table = SelectorTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["키", "설명", "유형", "값", "필수"])
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
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self._load_table()

        action_layout = QHBoxLayout()
        add_button = QPushButton("추가")
        add_button.clicked.connect(self.add_selector_row)
        delete_button = QPushButton("삭제")
        delete_button.clicked.connect(self.delete_selected_row)
        action_layout.addWidget(add_button)
        action_layout.addWidget(delete_button)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        guide = QLabel("값 칸에 Selenium 선택자를 입력하세요. XPATH가 기본이며, 공란인 선택자는 선택 단계에 따라 건너뛰거나 실행 전에 오류로 표시됩니다.")
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

        by_combo = QComboBox()
        by_combo.addItems(BY_TYPES.keys())
        by_combo.setCurrentText(selector.get("by", "xpath"))
        self.table.setCellWidget(row, 2, by_combo)

        self.table.setItem(row, 3, QTableWidgetItem(selector.get("value", "")))

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
        self.table.setCellWidget(row, 4, required_widget)

    def _row_data(self, row):
        key_item = self.table.item(row, 0)
        label_item = self.table.item(row, 1)
        value_item = self.table.item(row, 3)
        by_combo = self.table.cellWidget(row, 2)
        required_widget = self.table.cellWidget(row, 4)
        return (
            key_item.text().strip() if key_item else "",
            {
                "label": label_item.text().strip() if label_item else "",
                "by": by_combo.currentText() if by_combo else "xpath",
                "value": value_item.text().strip() if value_item else "",
                "required": bool(getattr(required_widget, "required_radio", None) and required_widget.required_radio.isChecked()),
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

    def add_selector_row(self):
        existing_keys = {
            self.table.item(row, 0).text().strip()
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
        }

        index = 1
        while f"custom_selector_{index}" in existing_keys:
            index += 1

        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_row(row, f"custom_selector_{index}", {
            "label": "새 요소",
            "by": "xpath",
            "value": "",
            "required": False,
        })
        self.table.selectRow(row)

    def delete_selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "삭제 오류", "삭제할 요소를 선택하세요.")
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
                QMessageBox.warning(self, "저장 오류", "키가 비어 있는 요소가 있습니다.")
                return
            if key in seen_keys:
                QMessageBox.warning(self, "저장 오류", f"중복된 키가 있습니다: {key}")
                return
            seen_keys.add(key)
            selectors[key] = selector

        self.config["selectors"] = selectors
        save_selector_config(self.config_path, self.config)
        QMessageBox.information(self, "저장 완료", "공단툴 요소 설정을 저장했습니다.")
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

        l1_label = QLabel("L1 - 원하는 작업")
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
        l2_label = QLabel("L2 - 요소설정")
        l2_layout.addWidget(l2_label)
        toolbar = QHBoxLayout()
        self.selector_button = QPushButton("요소 설정")
        self.selector_button.clicked.connect(self.open_selector_settings)
        toolbar.addWidget(self.selector_button)
        toolbar.addStretch()
        l2_layout.addLayout(toolbar)
        self.l2_container.setVisible(False)
        self.main_layout.addWidget(self.l2_container)

        self.l3_label = QLabel("L3 - 지점 선택")
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
            self.status_label.setText("청구 명세서 만들기: 요소 설정을 확인한 뒤 지점을 선택하세요.")
        else:
            self.status_label.setText("장기근속수당 입력하기: 작업 틀은 준비됐고, 실행 로직은 다음 단계에서 연결하면 됩니다.")
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
            self.status_label.setText("장기근속수당 입력하기 자동화는 아직 연결되지 않았습니다.")
            self._log("장기근속수당 입력하기 지점 선택 - 실행 로직 미연결", level="WARNING")
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
        log("FederationTool", message, level=level)


class InvoiceProcessor:
    def __init__(self, driver, config_path: Path, status_callback=None):
        self.driver = driver
        self.config = ensure_selector_config(config_path)
        self.status_callback = status_callback or (lambda msg: None)
        self.timeouts = self.config.get("timeouts", {})
        self.timeout = int(self.timeouts.get("default", 20))
        self.wait = WebDriverWait(self.driver, self.timeout)

    def _log(self, message):
        self.status_callback(message)

    def locator(self, key, required=True):
        selector = self.config.get("selectors", {}).get(key)
        if not selector:
            if required:
                raise ValueError(f"요소 설정이 없습니다: {key}")
            return None

        locator = build_locator(selector)
        if locator:
            return locator

        if required or selector.get("required", False):
            label = selector.get("label", key)
            raise ValueError(f"필수 요소 값이 비어 있습니다: {label} ({key})")
        return None

    def wait_element(self, key, timeout=None, required=True):
        locator = self.locator(key, required=required)
        if not locator:
            return None
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        return wait.until(EC.presence_of_element_located(locator))

    def wait_elements(self, key, timeout=None):
        locator = self.locator(key)
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        return wait.until(lambda driver: driver.find_elements(*locator) or False)

    def click(self, key, timeout=None, required=True):
        locator = self.locator(key, required=required)
        if not locator:
            return None
        element = WebDriverWait(self.driver, timeout or self.timeout).until(EC.element_to_be_clickable(locator))
        self.click_element(element)
        return element

    def click_element(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def click_if_exists(self, key, timeout=None):
        try:
            return bool(self.click(key, timeout=timeout or self.timeouts.get("short", 3), required=False))
        except Exception:
            return False

    def accept_alert_if_exists(self, timeout=1):
        try:
            alert = WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
            alert.accept()
            return True
        except Exception:
            return False

    def click_optional_confirm(self, key, timeout=None):
        if self.accept_alert_if_exists(timeout=1):
            return True
        return self.click_if_exists(key, timeout=timeout or self.timeouts.get("short", 3))

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
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        self.click_element(element)
                        time.sleep(0.2)
            except Exception:
                pass

    def close_all_popups(self):
        self._log("열려있는 알림/모달/팝업 닫기 시도")
        for _ in range(2):
            self.accept_alert_if_exists(timeout=1)
            self.close_configured_popups()
            self.click_if_exists("claim_page_warning_close")
            self.click_if_exists("operation_guide_close")

            frames = self.driver.find_elements(By.TAG_NAME, "iframe")
            for frame in frames:
                try:
                    self.driver.switch_to.frame(frame)
                    self.accept_alert_if_exists(timeout=1)
                    self.close_configured_popups()
                except Exception:
                    pass
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass

    def open_payroll_claim_menu(self):
        self._log("상단 메뉴 '급여비용청구' 마우스 오버 후 드롭다운 메뉴 클릭")
        main_menu = self.wait_element("main_menu")
        ActionChains(self.driver).move_to_element(main_menu).perform()
        time.sleep(0.5)
        self.click("payroll_claim_dropdown")

    def click_claim_button(self):
        self._log("'청구하기' 버튼 클릭")
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
            WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
            self.driver.switch_to.window(self.driver.window_handles[-1])
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
            processor.close_all_popups()
            processor.open_payroll_claim_menu()
            processor.close_all_popups()
            processor.click_claim_button()
            processor.close_all_popups()
            processor.process_claim_targets()
            processor.process_all_claim_targets()
            self.finished_signal.emit("청구 명세서 자동화 작업을 완료했습니다.", True)
        except Exception as e:
            self.finished_signal.emit(f"청구 명세서 자동화 중 오류: {e}", False)
