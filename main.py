import sys

from data_paths import user_data_path
from menu_layout import load_layout, reconcile_groups
from ui.pages.menu_management_page import MenuManagementPage

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QMainWindow,
    QHBoxLayout,
    QWidget,
    QTabWidget,
    QPushButton,
)

from ui.pages.branch_list import BranchPage
from ui.pages.login_tool import LoginTool
from ui.pages.login_log import LoginLogPage
from ui.pages.document_tool import UnifiedDocumentTool
from ui.pages.table_list_page import TableListPage
from ui.pages.federation_tool import FederationTool
from ui.pages.carefor_tool import CareforTool
from ui.pages.labor_cost_ratio_page import LaborCostRatioPage
from ui.pages.service_fee_page import ServiceFeePage
from ui.pages.annual_leave_page import AnnualLeavePage
from ui.pages.monthly_work_check_page import MonthlyWorkCheckPage
from ui.pages.memo_page import MemoPage
from ui.pages.incomplete_task_page import IncompleteTaskPage
from ui.pages.branch_task_settings import BranchTaskSettingsPage
from ui.pages.attendance_analysis_page import AttendanceAnalysisPage
from ui.pages.excel_data_sort_page import ExcelDataSortPage
from ui.pages.committee_minutes_page import CommitteeMinutesPage, PlannedPage
from ui.pages.business_plan_page import BusinessPlanPage
from ui.pages.budget_page import BudgetPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("요양원 업무툴")
        self.resize(1400, 900)

        # ===== 중앙 위젯 =====
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # ===== 메인 레이아웃 =====
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        central_widget.setLayout(layout)

        # =========================================================
        # 좌측 메뉴
        # =========================================================

        self.menu = QTreeWidget()
        self.menu.setHeaderHidden(True)
        self.menu.setExpandsOnDoubleClick(False)
        self.menu.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.menu.setMinimumWidth(260)
        self.menu.setMaximumWidth(340)
        self.menu.setObjectName("sideMenu")
        self.menu.setStyleSheet(
            """
            QTreeWidget#sideMenu {
                border: none;
                border-right: 1px solid #d9dde3;
                background: #f7f8fa;
                padding: 10px 6px;
            }
            QTreeWidget#sideMenu::item {
                border-radius: 5px;
                padding: 8px 10px;
            }
            QTreeWidget#sideMenu::item:selected {
                background: #dce8f8;
                color: #174a87;
            }
            QTreeWidget#sideMenu::item:hover:!selected {
                background: #e9edf2;
            }
            """
        )

        layout.addWidget(self.menu)
        layout.setStretch(0, 1)
        
        # =========================================================
        # 우측 콘텐츠 (페이지)
        # =========================================================

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._sync_menu_selection)
        self.close_all_tabs_button = QPushButton("모든 탭 닫기")
        self.close_all_tabs_button.setToolTip("입력값과 진행 중인 작업을 유지하고 모든 탭을 닫습니다.")
        self.close_all_tabs_button.clicked.connect(self.close_all_tabs)
        self.tabs.setCornerWidget(self.close_all_tabs_button, Qt.TopRightCorner)
        self.page_items = {}
        # 닫은 탭도 보관하여 입력값과 실행 상태를 유지합니다.
        self.page_storage = QWidget(central_widget)
        self.page_storage.hide()

        # 각 페이지 추가
        self.branch_page = BranchPage()
        self.login_page = LoginTool()
        self.login_log_page = LoginLogPage()
        self.document_page = UnifiedDocumentTool()
        self.table_list_page = TableListPage()
        self.federation_page = FederationTool()
        self.carefor_page = CareforTool()
        self.labor_cost_ratio_page = LaborCostRatioPage()
        self.service_fee_page = ServiceFeePage()
        self.annual_leave_page = AnnualLeavePage()
        self.monthly_work_check_page = MonthlyWorkCheckPage()
        self.memo_page = MemoPage()
        self.incomplete_task_page = IncompleteTaskPage()
        self.branch_task_settings_page = BranchTaskSettingsPage()
        self.attendance_analysis_page = AttendanceAnalysisPage()
        self.excel_data_sort_page = ExcelDataSortPage()
        self.committee_minutes_page = CommitteeMinutesPage()

        self.budget_page = BudgetPage()
        self.business_plan_page = BusinessPlanPage()
        self.menu_management_page = MenuManagementPage()

        # 새 업무 페이지는 여기에 등록하면 메뉴관리에도 자동으로 포함됩니다.
        menu_groups = (
            ("필수도구", (("로그인툴", self.login_page),)),
            ("사업기획", (
                ("예산편성", self.budget_page),
                ("사업계획", self.business_plan_page),
                ("운영위원회 회의록 작성", self.committee_minutes_page),
            )),
            (
                "문서작성툴",
                (
                    ("문서작성툴", self.document_page),
                    ("테이블 목록 관리", self.table_list_page),
                ),
            ),
            ("문서 분석", (
                ("출근부 분석", self.attendance_analysis_page),
                ("엑셀 데이터 정렬", self.excel_data_sort_page),
            )),
            (
                "개인 업무",
                (
                    ("월간업무체크", self.monthly_work_check_page),
                    ("메모장", self.memo_page),
                    ("미비된일", self.incomplete_task_page),
                ),
            ),
            (
                "설정",
                (
                    ("지점 관리", self.branch_page),
                    ("업무별 지점 설정", self.branch_task_settings_page),
                    ("메뉴관리", self.menu_management_page),
                ),
            ),
            (
                "정보",
                (
                    ("연도별 장기요양인건비 비율", self.labor_cost_ratio_page),
                    ("연도별 장기요양 수가", self.service_fee_page),
                    ("연차 계산기", self.annual_leave_page),
                ),
            ),
            ("기타", (("로그", self.login_log_page),)),
            (
                "테스트중",
                (
                    ("공단툴", self.federation_page),
                    ("케어포툴", self.carefor_page),
                ),
            ),
        )

        # 표시명과 별개인 속성명을 저장 키로 사용하여 대메뉴/페이지명 변경에도 배치를 유지합니다.
        page_keys = {page: name for name, page in vars(self).items() if isinstance(page, QWidget)}
        self.page_registry = {}
        defaults = []
        for group_name, entries in menu_groups:
            keys = []
            for label, page in entries:
                key = page_keys[page]
                self.page_registry[key] = dict(label=label, page=page)
                keys.append(key)
                page.setParent(self.page_storage)
            defaults.append(dict(id='default_' + group_name, name=group_name, pages=keys))
        settings_path = user_data_path("menu_layout.json")
        error = ""
        try:
            groups = load_layout(settings_path, defaults)
        except (OSError, ValueError) as exc:
            groups = reconcile_groups(defaults, defaults)
            error = f"메뉴 설정을 읽지 못했습니다. 원본 보호를 위해 저장을 중지합니다: {exc}"
            self.statusBar().showMessage(error)
        self.menu_management_page.configure(settings_path, self.page_registry, groups, error)
        self.menu_management_page.layout_saved.connect(self.apply_menu_layout)
        self.apply_menu_layout(groups)

        layout.addWidget(self.tabs)
        layout.setStretch(1, 3)

        # 메뉴 선택 이벤트 연결
        self.menu.itemClicked.connect(self.on_menu_clicked)

        # 시작 시 로그인툴이 배치된 대메뉴를 펼치고 로그인 탭을 표시합니다.
        self.open_page(self.login_page)

    def _add_menu_group(self, group_name, entries):
        """접고 펼칠 수 있는 대메뉴 아래에 업무 화면을 등록합니다."""
        group_item = QTreeWidgetItem(self.menu, [group_name])
        group_item.setFlags(Qt.ItemIsEnabled)
        group_font = group_item.font(0)
        group_font.setBold(True)
        group_item.setFont(0, group_font)
        for label, page in entries:
            menu_item = QTreeWidgetItem(group_item, [label])
            menu_item.setData(0, Qt.UserRole, page)
            self.page_items[page] = menu_item

    def apply_menu_layout(self, groups):
        """메뉴 항목만 다시 구성하고 열린 페이지는 그대로 유지합니다."""
        self.menu.clear()
        self.page_items.clear()
        for group in groups:
            entries = [(self.page_registry[key]['label'], self.page_registry[key]['page'])
                       for key in group['pages']]
            self._add_menu_group(group['name'], entries)
        self._sync_menu_selection(self.tabs.currentIndex())

    def on_menu_clicked(self, item, column=0):
        page = item.data(0, Qt.UserRole)
        if page is None:
            item.setExpanded(not item.isExpanded())
            return
        self.open_page(page)

    def open_page(self, page):
        """열린 업무는 기존 탭으로 이동하고 닫힌 업무는 다시 엽니다."""
        index = self.tabs.indexOf(page)
        if index < 0:
            index = self.tabs.addTab(page, self.page_items[page].text(0))
        self.tabs.setCurrentIndex(index)
        self._sync_menu_selection(index)

    def close_tab(self, index):
        """탭만 숨기며 입력값과 진행 중인 작업을 유지합니다."""
        page = self.tabs.widget(index)
        if page is None:
            return
        self.tabs.removeTab(index)
        page.setParent(self.page_storage)
        page.hide()

    def close_all_tabs(self):
        """각 페이지를 보관하면서 열린 탭을 모두 닫습니다."""
        for index in range(self.tabs.count() - 1, -1, -1):
            self.close_tab(index)

    def _sync_menu_selection(self, index):
        self.close_all_tabs_button.setEnabled(self.tabs.count() > 0)
        page = self.tabs.widget(index)
        item = self.page_items.get(page)
        self.menu.setCurrentItem(item)
        if item is not None:
            item.parent().setExpanded(True)
            self.menu.scrollToItem(item)

    def closeEvent(self, event):
        if self.committee_minutes_page.worker is not None:
            self.open_page(self.committee_minutes_page)
            self.committee_minutes_page.status.setText("AI 요청이 진행 중입니다. 완료 후 닫아 주세요.")
            event.ignore()
            return
        if not self.committee_minutes_page.may_replace():
            event.ignore()
            return
        for page in self.findChildren(FederationTool):
            if page.batch_thread is not None:
                page.stop_batch()
                self.open_page(page)
                event.ignore()
                return
        if self.excel_data_sort_page.worker is not None:
            self.open_page(self.excel_data_sort_page)
            self.excel_data_sort_page.status.setText("엑셀 작업이 진행 중입니다. 완료 후 창을 닫아 주세요.")
            event.ignore()
            return
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
