from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class FederationTool(QWidget):
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout()
        
        label = QLabel("공단 도구")
        layout.addWidget(label)
        
        layout.addStretch()
        
        self.setLayout(layout)
