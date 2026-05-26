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

        layout.addWidget(self.menu)
        # self.menu_widget = QWidget()
        # self.menu_widget.setFixedWidth(240)
        # self.menu_widget.setStyleSheet("""
        #     background-color: #2b2d31;
        # """)

        # menu_layout = QVBoxLayout()
        # menu_layout.setContentsMargins(10, 20, 10, 20)
        # menu_layout.setSpacing(10)

        # self.menu_widget.setLayout(menu_layout)

        # # ===== 타이틀 =====
        # title = QLabel("업무 관리 시스템")
        # title.setStyleSheet("""
        #     color: white;
        #     font-size: 20px;
        #     font-weight: bold;
        #     padding: 10px;
        # """)

        # menu_layout.addWidget(title)

        # # ===== 메뉴 리스트 =====
        # self.menu_list = QListWidget()

        # self.menu_list.setStyleSheet("""
        #     QListWidget {
        #         background-color: transparent;
        #         border: none;
        #         color: white;
        #         font-size: 15px;
        #     }

        #     QListWidget::item {
        #         padding: 14px;
        #         border-radius: 8px;
        #     }

        #     QListWidget::item:selected {
        #         background-color: #4c8bf5;
        #     }

        #     QListWidget::item:hover {
        #         background-color: #3a3d42;
        #     }
        # """)

        # menus = [
        #     "공단 감시",
        #     "공단 편의",
        #     "문서 작성",
        #     "웹 로그인",
        #     "설정",
        #     "각종목록",
        # ]

        # for menu in menus:
        #     item = QListWidgetItem(menu)
        #     self.menu_list.addItem(item)

        # menu_layout.addWidget(self.menu_list)

        # =========================================================
        # 우측 페이지 영역
        # =========================================================
        self.stack = QStackedWidget()

        # self.stack.addWidget(self.create_page("공단 감시 페이지"))
        # self.stack.addWidget(self.create_page("공단 편의 페이지"))
        # self.stack.addWidget(self.create_page("문서 작성 페이지"))
        # self.stack.addWidget(self.create_page("웹 로그인 페이지"))
        # self.stack.addWidget(self.create_page("설정 페이지"))
        # self.stack.addWidget(self.create_page("각종 목록 페이지"))

        # =========================================================
        # 페이지 추가
        # =========================================================

        self.branch_page = BranchPage()

        self.stack.addWidget(self.branch_page)

        
        # ===== 메뉴 클릭 이벤트 =====
        # self.menu_list.currentRowChanged.connect(
        #     self.stack.setCurrentIndex
        # )

        # self.menu_list.setCurrentRow(0)
        self.menu.currentRowChanged.connect(
            self.stack.setCurrentIndex
        )

        self.menu.setCurrentRow(0)


        # =========================================================
        # 레이아웃 추가
        # =========================================================
        layout.addWidget(self.stack)

    def create_page(self, text):
        page = QWidget()

        layout = QVBoxLayout()
        page.setLayout(layout)

        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)

        label.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
        """)

        layout.addWidget(label)

        return page

pass

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()