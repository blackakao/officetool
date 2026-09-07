import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget,
)


class AttendanceAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.root = Path(__file__).resolve().parents[2]
        self.dataset_dir = self.root / "dataset"
        self.process = None

        layout = QVBoxLayout(self)
        title = QLabel("<h2>출근부 분석</h2>")
        description = QLabel(
            "dataset/files의 스캔 이미지와 dataset/labels의 같은 이름 XLSX를 이용해 "
            "출근부 분석 모델을 학습합니다."
        )
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)

        form = QFormLayout()
        self.status_label = QLabel()
        form.addRow("데이터셋", self.status_label)
        self.image_edit = QLineEdit()
        image_button = QPushButton("이미지 선택")
        image_button.clicked.connect(self._select_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_edit, 1)
        image_row.addWidget(image_button)
        form.addRow("분석 이미지", image_row)
        self.checkpoint_edit = QLineEdit(str(self.root / "attendance_analysis" / "outputs" / "best.pt"))
        checkpoint_button = QPushButton("모델 선택")
        checkpoint_button.clicked.connect(self._select_checkpoint)
        checkpoint_row = QHBoxLayout()
        checkpoint_row.addWidget(self.checkpoint_edit, 1)
        checkpoint_row.addWidget(checkpoint_button)
        form.addRow("모델 파일", checkpoint_row)
        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(1, 10000)
        self.epochs_spin.setValue(30)
        form.addRow("학습 횟수", self.epochs_spin)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        refresh_button = QPushButton("데이터 확인")
        refresh_button.clicked.connect(self.refresh_status)
        train_button = QPushButton("학습 시작")
        train_button.clicked.connect(self.start_training)
        predict_button = QPushButton("이미지 분석")
        predict_button.clicked.connect(self.start_prediction)
        buttons.addWidget(refresh_button)
        buttons.addWidget(train_button)
        buttons.addWidget(predict_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console, 1)
        self.refresh_status()

    def refresh_status(self):
        image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
        files_dir = self.dataset_dir / "files"
        labels_dir = self.dataset_dir / "labels"
        images = {path.stem for path in files_dir.iterdir() if path.suffix.lower() in image_extensions}
        labels = {
            path.stem for path in labels_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".xlsx", ".json"}
        } if labels_dir.exists() else set()
        self.status_label.setText(f"이미지 {len(images)}개 / 정답 엑셀·JSON {len(labels)}개 / 학습 가능 쌍 {len(images & labels)}개")

    def _select_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "출근부 이미지", str(self.dataset_dir / "files"), "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if path:
            self.image_edit.setText(path)

    def _select_checkpoint(self):
        path, _ = QFileDialog.getOpenFileName(self, "학습 모델", str(self.root / "attendance_analysis" / "outputs"), "PyTorch (*.pt *.pth)")
        if path:
            self.checkpoint_edit.setText(path)

    def _run(self, arguments):
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "실행 중", "이미 실행 중인 작업이 있습니다.")
            return
        self.console.clear()
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.root))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(lambda code, _status: self.console.appendPlainText(f"\n종료 코드: {code}"))
        self.process.start(sys.executable, arguments)

    def _read_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.console.insertPlainText(text)

    def start_training(self):
        self._run(["-m", "attendance_analysis.train", "--dataset", str(self.dataset_dir), "--epochs", str(self.epochs_spin.value())])

    def start_prediction(self):
        image_path = Path(self.image_edit.text().strip())
        checkpoint_path = Path(self.checkpoint_edit.text().strip())
        if not image_path.is_file() or not checkpoint_path.is_file():
            QMessageBox.warning(self, "파일 확인", "분석 이미지와 학습된 모델 파일을 선택해 주세요.")
            return
        default_path = image_path.with_name(f"{image_path.stem}_분석결과.xlsx")
        output_path, _ = QFileDialog.getSaveFileName(
            self, "분석 결과 엑셀 저장", str(default_path), "Excel Files (*.xlsx)"
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".xlsx"):
            output_path += ".xlsx"
        self._run([
            "-m", "attendance_analysis.predict", str(image_path),
            "--checkpoint", str(checkpoint_path), "--output", output_path,
        ])
