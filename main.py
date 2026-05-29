import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QStackedWidget,
)

from ui.pages.branch_list import BranchPage
from ui.pages.login_tool import LoginTool
from ui.pages.login_log import LoginLogPage
from ui.pages.document_tool import DocumentTool
from ui.pages.federation_tool import FederationTool
from ui.pages.labor_cost_ratio_page import LaborCostRatioPage
from ui.pages.service_fee_page import ServiceFeePage

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

        self.menu.addItem("지점 목록")
        self.menu.addItem("로그인툴")
        self.menu.addItem("로그인 로그")
        self.menu.addItem("문서작성툴")
        self.menu.addItem("공단툴")
        self.menu.addItem("연도별 장기요양인건비 비율")
        self.menu.addItem("연도별 장기요양 수가")

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
        self.labor_cost_ratio_page = LaborCostRatioPage()
        self.service_fee_page = ServiceFeePage()

        self.stacked_widget.addWidget(self.branch_page)
        self.stacked_widget.addWidget(self.login_page)
        self.stacked_widget.addWidget(self.login_log_page)
        self.stacked_widget.addWidget(self.document_page)
        self.stacked_widget.addWidget(self.federation_page)
        self.stacked_widget.addWidget(self.labor_cost_ratio_page)
        self.stacked_widget.addWidget(self.service_fee_page)

        layout.addWidget(self.stacked_widget)
        layout.setStretch(1, 3)

        # 메뉴 선택 이벤트 연결
        self.menu.itemClicked.connect(self.on_menu_clicked)

    def on_menu_clicked(self, item):
        """메뉴 아이템을 클릭했을 때 호출"""
        index = self.menu.row(item)
        self.stacked_widget.setCurrentIndex(index)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()