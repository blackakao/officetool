import json
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton


class LoginTool(QWidget):
    def __init__(self):
        super().__init__()
        
        self.data_file = Path(__file__).resolve().parents[2] / "data" / "branches.json"
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        
        self.refresh_buttons()
    
    def refresh_buttons(self):
        """버튼 목록 새로고침"""
        # 기존 레이아웃 삭제
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # 그리드 레이아웃 생성 (5개씩 배치)
        grid_layout = QGridLayout()
        
        # branches.json에서 지점 목록 읽기
        branches = self._load_branches()
        
        # 버튼 생성 (5개씩 행으로 배치)
        for index, branch in enumerate(branches):
            row = index // 5  # 행 계산 (5개씩)
            col = index % 5   # 열 계산
            
            button = QPushButton(branch["branch_name"])
            grid_layout.addWidget(button, row, col)
        
        self.main_layout.addLayout(grid_layout)
        self.main_layout.addStretch()
    
    def showEvent(self, event):
        """페이지가 보여질 때마다 새로고침"""
        super().showEvent(event)
        self.refresh_buttons()
    
    def _load_branches(self):
        """branches.json에서 지점 목록 읽기"""
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

