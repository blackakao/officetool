import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QHBoxLayout,
    QWidget,
    QStackedWidget,
)

from ui.pages.branch_list import BranchPage
from ui.pages.login_tool import LoginTool
from ui.pages.login_log import LoginLogPage
from ui.pages.document_tool import DocumentTool
from ui.pages.federation_tool import FederationTool
from ui.pages.carefor_tool import CareforTool
from ui.pages.labor_cost_ratio_page import LaborCostRatioPage
from ui.pages.service_fee_page import ServiceFeePage
from ui.pages.annual_leave_page import AnnualLeavePage
from ui.pages.monthly_work_check_page import MonthlyWorkCheckPage

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

        self.menu = QListWidget()
        self.menu.setObjectName("sideMenu")
        self.menu.setSpacing(2)
        self.menu.setStyleSheet(
            """
            QListWidget#sideMenu {
                border: none;
                border-right: 1px solid #d9dde3;
                background: #f7f8fa;
                padding: 10px 6px;
            }
            QListWidget#sideMenu::item {
                border-radius: 5px;
                padding: 8px 10px;
            }
            QListWidget#sideMenu::item:selected {
                background: #dce8f8;
                color: #174a87;
            }
            QListWidget#sideMenu::item:hover:!selected {
                background: #e9edf2;
            }
            """
        )

        layout.addWidget(self.menu)
        layout.setStretch(0, 1)
        
        # =========================================================
        # 우측 콘텐츠 (페이지)
        # =========================================================

        self.stacked_widget = QStackedWidget()

        # 각 페이지 추가
        self.branch_page = BranchPage()
        self.login_page = LoginTool()
        self.login_log_page = LoginLogPage()
        self.document_page = DocumentTool()
        self.federation_page = FederationTool()
        self.carefor_page = CareforTool()
        self.labor_cost_ratio_page = LaborCostRatioPage()
        self.service_fee_page = ServiceFeePage()
        self.annual_leave_page = AnnualLeavePage()
        self.monthly_work_check_page = MonthlyWorkCheckPage()

        menu_groups = (
            ("필수도구", (("로그인툴", self.login_page),)),
            ("문서작성툴", (("문서작성툴", self.document_page),)),
            ("개인 업무", (("월간업무체크", self.monthly_work_check_page),)),
            ("설정", (("지점 관리", self.branch_page),)),
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

        for group_name, entries in menu_groups:
            self._add_menu_group(group_name, entries)

        layout.addWidget(self.stacked_widget)
        layout.setStretch(1, 3)

        # 메뉴 선택 이벤트 연결
        self.menu.itemClicked.connect(self.on_menu_clicked)

        # 첫 번째 중메뉴를 기본 화면으로 표시합니다.
        first_page_item = self.menu.item(1)
        self.menu.setCurrentItem(first_page_item)
        self.stacked_widget.setCurrentWidget(first_page_item.data(Qt.UserRole))

    def _add_menu_group(self, group_name, entries):
        """선택할 수 없는 대메뉴와 그 아래 중메뉴를 추가합니다."""
        group_item = QListWidgetItem(group_name)
        group_item.setFlags(Qt.ItemIsEnabled)
        group_font = group_item.font()
        group_font.setBold(True)
        group_item.setFont(group_font)
        group_item.setForeground(Qt.gray)
        group_item.setData(Qt.UserRole, None)
        self.menu.addItem(group_item)

        for label, page in entries:
            self.stacked_widget.addWidget(page)
            menu_item = QListWidgetItem(f"    {label}")
            menu_item.setData(Qt.UserRole, page)
            self.menu.addItem(menu_item)

    def on_menu_clicked(self, item):
        """메뉴 아이템을 클릭했을 때 호출"""
        page = item.data(Qt.UserRole)
        if page is not None:
            self.stacked_widget.setCurrentWidget(page)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
