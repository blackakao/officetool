import json
import sys
import subprocess
import tempfile
import importlib
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Mm
from docx.text.paragraph import Paragraph

from PySide6.QtCore import QDate, QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QPushButton, QDialog, QLabel, QFormLayout, QLineEdit, QMessageBox, QHeaderView, QScrollArea,
    QComboBox, QCheckBox, QDateEdit
)
from ui.pages.logging_util import log


FIELD_TYPES = {
    "text": "텍스트",
    "date": "날짜",
    "amount": "숫자",
    "branch_select": "지점 목록",
    "branch_select_2": "지점 목록 2",
    "branch_value": "지점의 값",
}

BRANCH_SOURCE_TYPES = {
    "branch_select": "지점 목록",
    "branch_select_2": "지점 목록 2",
}

DATE_FORMATS = {
    "yyyy-MM-dd": "yyyy-mm-dd",
    "yyyy년 MM월 dd일": "yyyy년 mm월 dd일",
    "yyyy.MM.dd": "yyyy.mm.dd",
}

STANDARD_BRANCH_VALUE_FIELDS = {
    "organization_code": "기관기호",
    "organization_name": "기관명",
    "branch_name": "지점명",
    "corporation_name": "법인명",
    "owner_name": "대표자명",
    "address": "주소",
}


def read_json_file(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_file(path, data):
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


class DocumentTool(QWidget):
    def __init__(self):
        super().__init__()
        
        self.document_folder = Path(__file__).resolve().parents[2] / "document"
        self.document_folder.mkdir(exist_ok=True)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 타이틀
        title = QLabel("문서 작성 도구")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["파일명", "작업"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        
        self.setLayout(layout)
        self.load_documents()
    
    def load_documents(self):
        """document 폴더의 .docx 파일 로드"""
        self.table.setRowCount(0)
        
        if not self.document_folder.exists():
            return
        
        docx_files = list(self.document_folder.glob("*.docx"))
        self.table.setRowCount(len(docx_files))
        
        for row, file_path in enumerate(docx_files):
            # 파일명
            filename_item = QTableWidgetItem(file_path.name)
            filename_item.setFlags(filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, filename_item)
            
            # 작업 버튼
            btn = QPushButton("열기")
            btn.clicked.connect(lambda _, f=file_path: self.open_document(f))
            self.table.setCellWidget(row, 1, btn)
    
    def open_document(self, file_path):
        """문서 팝업 열기"""
        log("DocumentTool", f"문서 열기 시도: {file_path.name}", level="INFO")
        try:
            doc = Document(file_path)
            dialog = ContentControlDialog(self, doc, file_path)
            dialog.exec()
            self.load_documents()
            log("DocumentTool", f"문서 열기 완료: {file_path.name}", level="INFO")
        except Exception as e:
            log("DocumentTool", f"문서 열기 실패: {e}", level="ERROR")
            QMessageBox.critical(self, "오류", f"문서를 열 수 없습니다: {e}")
    
    def showEvent(self, event):
        """페이지가 보여질 때마다 새로고침"""
        super().showEvent(event)
        self.load_documents()



class ContentControlDialog(QDialog):
    def __init__(self, parent, doc, file_path):
        super().__init__(parent)
        self.setWindowTitle(f"{file_path.stem} 수정")
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)
        
        self.doc = doc
        self.file_path = file_path
        self.root = Path(__file__).resolve().parents[2]
        self.settings_path = self.root / "data" / "document_field_settings.json"
        self.branches_path = self.root / "data" / "branches.json"
        self.branch_fields_path = self.root / "data" / "branch_fields.json"
        self.settings = read_json_file(self.settings_path, {"version": 1, "fields": {}})
        self.branches = [
            branch
            for branch in read_json_file(self.branches_path, [])
            if branch.get("active", True)
        ]
        self.branch_fields = read_json_file(self.branch_fields_path, [])
        self.controls = {}
        self.field_widgets = {}
        
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        
        for field_key, control in self._collect_controls(doc).items():
            self.controls[field_key] = control
            self._add_field_row(form_layout, field_key, control)
        self._refresh_type_combo_options()
        self._refresh_branch_value_source_options()

        self.branch_summary_label = QLabel()
        self.branch_summary_label.setStyleSheet("font-weight: bold; color: #333;")
        self._update_branch_summary()
        layout.addWidget(self.branch_summary_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setLayout(form_layout)
        scroll.setWidget(container)

        layout.addWidget(scroll)
        
        # 버튼
        button_layout = QHBoxLayout()
        create_button = QPushButton("생성")
        save_settings_button = QPushButton("설정 저장")
        cancel_button = QPushButton("취소")

        create_button.clicked.connect(self.create_from_controls)
        save_settings_button.clicked.connect(self.save_field_settings)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_settings_button)
        button_layout.addWidget(create_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _collect_controls(self, doc):
        controls = {}
        sdt_list = doc.element.findall('.//' + qn('w:sdt'))
        for idx, sdt in enumerate(sdt_list):
            info = self._content_control_info(sdt, idx)
            if not info:
                continue
            key = info["tag"] or info["alias"] or f"필드 {idx + 1}"
            control = controls.setdefault(key, {
                "tag": key,
                "alias": info["alias"],
                "placeholder": info["placeholder"],
                "current_text": info["current_text"],
                "indices": [],
            })
            control["indices"].append(idx)
            if not control["current_text"] and info["current_text"]:
                control["current_text"] = info["current_text"]
            if not control["alias"] and info["alias"]:
                control["alias"] = info["alias"]
            if not control["placeholder"] and info["placeholder"]:
                control["placeholder"] = info["placeholder"]
        return controls

    def _content_control_info(self, sdt, idx):
        sdt_pr = sdt.find(qn('w:sdtPr'))
        if sdt_pr is None:
            return None

        tag_elem = sdt_pr.find(qn('w:tag'))
        tag = tag_elem.get(qn('w:val')) if tag_elem is not None else f"필드 {idx + 1}"

        alias_elem = sdt_pr.find(qn('w:alias'))
        alias = alias_elem.get(qn('w:val')) if alias_elem is not None else ""

        placeholder_elem = sdt_pr.find(qn('w:placeholder'))
        placeholder = ""
        if placeholder_elem is not None:
            placeholder_text = placeholder_elem.find(qn('w:docPart'))
            if placeholder_text is not None:
                placeholder = placeholder_text.get(qn('w:val')) or ""

        current_text = self._sdt_text(sdt)
        return {
            "tag": tag,
            "alias": alias,
            "placeholder": placeholder,
            "current_text": current_text,
        }

    def _sdt_text(self, sdt):
        sdt_content = sdt.find(qn('w:sdtContent'))
        if sdt_content is None:
            return ""
        t_list = sdt_content.findall('.//' + qn('w:t'))
        return ''.join([t.text for t in t_list if t.text])

    def _add_field_row(self, form_layout, field_key, control):
        setting = self.settings.setdefault("fields", {}).setdefault(field_key, {"type": "text"})

        display_name = field_key
        if len(control["indices"]) > 1:
            display_name = f"{field_key}({len(control['indices'])})"
        title_label = QLabel(f"<b>{display_name}</b>")
        description_texts = []
        if len(control["indices"]) > 1:
            description_texts.append(f"동일 이름 {len(control['indices'])}개 동시 수정")
        if control["alias"]:
            description_texts.append(f"별칭: {control['alias']}")
        if control["placeholder"]:
            description_texts.append(f"설명: {control['placeholder']}")
        description_label = QLabel(" | ".join(description_texts))
        description_label.setStyleSheet("color: gray; font-size: 10px;")

        type_combo = QComboBox()
        for type_key, label in FIELD_TYPES.items():
            type_combo.addItem(label, type_key)
        type_index = type_combo.findData(setting.get("type", "text"))
        type_combo.setCurrentIndex(type_index if type_index >= 0 else 0)

        input_container = QWidget()
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_container.setLayout(input_layout)

        self.field_widgets[field_key] = {
            "type_combo": type_combo,
            "input_container": input_container,
            "input_layout": input_layout,
            "setting": setting,
        }
        self._refresh_type_combo_options(field_key)
        type_combo.currentIndexChanged.connect(lambda _, key=field_key: self._on_field_type_changed(key))

        form_layout.addRow(title_label, None)
        form_layout.addRow("형태", type_combo)
        form_layout.addRow("값", input_container)
        if description_texts:
            form_layout.addRow("", description_label)
        form_layout.addRow("", QLabel(""))
        self._rebuild_field_input(field_key)

    def _on_field_type_changed(self, field_key):
        self._rebuild_field_input(field_key)
        self._refresh_type_combo_options()
        self._refresh_branch_combo_options(skip_field=field_key)
        self._refresh_branch_value_source_options(skip_field=field_key)
        self._update_branch_value_fields()
        self._update_branch_summary()

    def _refresh_type_combo_options(self, target_field_key=None):
        occupied_types = {
            widgets["type_combo"].currentData()
            for key, widgets in self.field_widgets.items()
            if key != target_field_key and widgets["type_combo"].currentData() in BRANCH_SOURCE_TYPES
        }
        targets = (
            [target_field_key]
            if target_field_key
            else list(self.field_widgets.keys())
        )
        for field_key in targets:
            widgets = self.field_widgets.get(field_key)
            if not widgets:
                continue
            type_combo = widgets["type_combo"]
            current_type = type_combo.currentData() or widgets["setting"].get("type", "text")
            type_combo.blockSignals(True)
            type_combo.clear()
            for type_key, label in FIELD_TYPES.items():
                if type_key in BRANCH_SOURCE_TYPES and type_key in occupied_types and type_key != current_type:
                    continue
                type_combo.addItem(label, type_key)
            type_index = type_combo.findData(current_type)
            type_combo.setCurrentIndex(type_index if type_index >= 0 else 0)
            type_combo.blockSignals(False)

    def _refresh_branch_value_source_options(self, skip_field=None):
        for field_key, widgets in self.field_widgets.items():
            if field_key == skip_field or widgets["type_combo"].currentData() != "branch_value":
                continue
            source_combo = widgets.get("source_combo")
            if not source_combo:
                continue
            current_source = source_combo.currentData()
            source_combo.blockSignals(True)
            source_combo.clear()
            for source_type, label in self._branch_source_options(field_key):
                source_combo.addItem(label, source_type)
            source_index = source_combo.findData(current_source)
            if source_index < 0:
                source_index = source_combo.findData(widgets["setting"].get("source_field", "branch_select"))
            source_combo.setCurrentIndex(source_index if source_index >= 0 else 0)
            source_combo.blockSignals(False)
            self._update_branch_value_field(field_key)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_field_input(self, field_key):
        widgets = self.field_widgets[field_key]
        layout = widgets["input_layout"]
        self._clear_layout(layout)

        field_type = widgets["type_combo"].currentData() or "text"
        control = self.controls[field_key]
        setting = widgets["setting"]
        setting["type"] = field_type

        if field_type == "date":
            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setDate(self._parse_date(control["current_text"]))

            format_combo = QComboBox()
            for value, label in DATE_FORMATS.items():
                format_combo.addItem(label, value)
            format_combo.setCurrentText(setting.get("date_format", "yyyy-MM-dd"))
            index = format_combo.findData(setting.get("date_format", "yyyy-MM-dd"))
            format_combo.setCurrentIndex(index if index >= 0 else 0)

            layout.addWidget(date_edit)
            layout.addWidget(format_combo)
            widgets["value_widget"] = date_edit
            widgets["format_combo"] = format_combo
            return

        if field_type == "amount":
            amount_edit = QLineEdit()
            amount_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d*")))
            amount_edit.setText(''.join(ch for ch in control["current_text"] if ch.isdigit()))
            comma_check = QCheckBox("1000단위 쉼표")
            comma_check.setChecked(bool(setting.get("use_comma", True)))
            layout.addWidget(amount_edit)
            layout.addWidget(comma_check)
            widgets["value_widget"] = amount_edit
            widgets["comma_check"] = comma_check
            return

        if field_type in {"branch_select", "branch_select_2"}:
            branch_combo = QComboBox()
            self._populate_branch_combo(field_key, branch_combo, setting.get("branch_name") or control["current_text"])
            branch_combo.currentIndexChanged.connect(lambda _, key=field_key: self._on_branch_selection_changed(key))
            layout.addWidget(branch_combo)
            widgets["value_widget"] = branch_combo
            return

        if field_type == "branch_value":
            source_combo = QComboBox()
            for source_type, label in self._branch_source_options(field_key):
                source_combo.addItem(label, source_type)
            source_index = source_combo.findData(self._source_type_from_setting(setting))
            source_combo.setCurrentIndex(source_index if source_index >= 0 else 0)

            value_combo = QComboBox()
            for value_key, label in self._branch_value_field_options().items():
                value_combo.addItem(label, value_key)
            value_index = value_combo.findData(setting.get("branch_value_key", "organization_code"))
            value_combo.setCurrentIndex(value_index if value_index >= 0 else 0)

            preview = QLineEdit()
            preview.setReadOnly(True)
            source_combo.currentIndexChanged.connect(lambda _: self._update_branch_value_field(field_key))
            value_combo.currentIndexChanged.connect(lambda _: self._update_branch_value_field(field_key))

            layout.addWidget(source_combo)
            layout.addWidget(value_combo)
            layout.addWidget(preview)
            widgets["source_combo"] = source_combo
            widgets["value_key_combo"] = value_combo
            widgets["value_widget"] = preview
            self._update_branch_value_field(field_key)
            return

        text_edit = QLineEdit()
        text_edit.setText(control["current_text"])
        text_edit.setPlaceholderText(control["placeholder"] or control["alias"] or "입력하세요")
        layout.addWidget(text_edit)
        widgets["value_widget"] = text_edit

    def _parse_date(self, text):
        digits = ''.join(ch if ch.isdigit() else '-' for ch in str(text or "")).strip('-')
        parts = [part for part in digits.split('-') if part]
        if len(parts) >= 3:
            date = QDate(int(parts[0]), int(parts[1]), int(parts[2]))
            if date.isValid():
                return date
        return QDate.currentDate()

    def _branch_key(self, branch):
        if not branch:
            return ""
        return str(branch.get("organization_code") or branch.get("branch_name") or "")

    def _branch_name(self, branch):
        return branch.get("branch_name", "") if branch else ""

    def _branch_combo_current_key(self, combo):
        return self._branch_key(combo.currentData()) if combo else ""

    def _selected_branch_keys(self, exclude_field_key=None):
        selected = set()
        for field_key, widgets in self.field_widgets.items():
            if field_key == exclude_field_key:
                continue
            if widgets["type_combo"].currentData() not in BRANCH_SOURCE_TYPES:
                continue
            key = self._branch_combo_current_key(widgets.get("value_widget"))
            if key:
                selected.add(key)
        return selected

    def _populate_branch_combo(self, field_key, combo, preferred_branch_name=None):
        preferred_branch_name = preferred_branch_name or self._branch_name(combo.currentData())
        excluded_keys = self._selected_branch_keys(exclude_field_key=field_key)

        combo.blockSignals(True)
        combo.clear()
        for branch in self.branches:
            branch_key = self._branch_key(branch)
            if branch_key in excluded_keys:
                continue
            combo.addItem(branch.get("branch_name", ""), branch)
        self._select_branch_combo(combo, preferred_branch_name)
        combo.blockSignals(False)

    def _branch_value_field_options(self):
        options = dict(STANDARD_BRANCH_VALUE_FIELDS)
        for field in self.branch_fields:
            key = field.get("key")
            label = field.get("label", key)
            if key and label:
                options[key] = label
        return options

    def _branch_field_definition(self, key):
        for field in self.branch_fields:
            if field.get("key") == key:
                return field
        return None

    def _branch_value(self, branch, key):
        if not branch:
            return ""
        if key in STANDARD_BRANCH_VALUE_FIELDS:
            return str(branch.get(key, ""))

        field = self._branch_field_definition(key)
        custom_value = branch.get("custom_fields", {}).get(key, {})
        if not isinstance(custom_value, dict):
            return str(custom_value)
        if field and field.get("type") == "image":
            path_text = custom_value.get("path", "")
            if not path_text:
                return {"type": "image", "path": "", "width": 30, "height": 30}
            path = Path(path_text)
            if path_text and not path.is_absolute():
                path = self.root / path_text
            return {
                "type": "image",
                "path": str(path),
                "width": int(custom_value.get("width", 30) or 30),
                "height": int(custom_value.get("height", 30) or 30),
            }
        return str(custom_value.get("value", ""))

    def _select_branch_combo(self, combo, branch_name):
        for index in range(combo.count()):
            branch = combo.itemData(index)
            if branch and branch.get("branch_name") == branch_name:
                combo.setCurrentIndex(index)
                return

    def _refresh_branch_combo_options(self, skip_field=None):
        for field_key, widgets in self.field_widgets.items():
            if field_key == skip_field or widgets["type_combo"].currentData() not in BRANCH_SOURCE_TYPES:
                continue
            combo = widgets.get("value_widget")
            if not isinstance(combo, QComboBox):
                continue
            self._populate_branch_combo(field_key, combo, self._branch_name(combo.currentData()))
            branch = combo.currentData()
            widgets["setting"]["branch_name"] = self._branch_name(branch)

    def _on_branch_selection_changed(self, field_key):
        widgets = self.field_widgets.get(field_key)
        if not widgets:
            return
        combo = widgets.get("value_widget")
        branch = combo.currentData() if isinstance(combo, QComboBox) else None
        widgets["setting"]["branch_name"] = self._branch_name(branch)
        self._refresh_branch_combo_options(skip_field=field_key)
        self._refresh_branch_value_source_options()
        self._update_branch_value_fields()
        self._update_branch_summary()

    def _update_branch_summary(self):
        if not hasattr(self, "branch_summary_label"):
            return
        parts = []
        for source_type, label in BRANCH_SOURCE_TYPES.items():
            branch = self._selected_branch_from_source_type(source_type)
            if branch:
                parts.append(f"{label}: {self._branch_name(branch)}")
        self.branch_summary_label.setText(" | ".join(parts) if parts else "선택된 지점 없음")

    def _branch_source_options(self, current_field_key=None):
        source_types = {
            widgets["type_combo"].currentData()
            for key, widgets in self.field_widgets.items()
            if key != current_field_key and widgets["type_combo"].currentData() in BRANCH_SOURCE_TYPES
        }
        options = []
        for source_type, label in BRANCH_SOURCE_TYPES.items():
            if source_type not in source_types:
                continue
            branch = self._selected_branch_from_source_type(source_type)
            branch_name = self._branch_name(branch)
            option_label = f"{branch_name} ({label})" if branch_name else label
            options.append((source_type, option_label))
        return options

    def _source_type_from_setting(self, setting):
        source = setting.get("source_field", "branch_select")
        if source in BRANCH_SOURCE_TYPES:
            return source
        widgets = self.field_widgets.get(source)
        if widgets and widgets["type_combo"].currentData() in BRANCH_SOURCE_TYPES:
            return widgets["type_combo"].currentData()
        return "branch_select"

    def _selected_branch_from_source_type(self, source_type):
        for widgets in self.field_widgets.values():
            if widgets["type_combo"].currentData() != source_type:
                continue
            value_widget = widgets.get("value_widget")
            if isinstance(value_widget, QComboBox):
                return value_widget.currentData()
        return None

    def _update_branch_value_fields(self):
        for field_key, widgets in self.field_widgets.items():
            if widgets["type_combo"].currentData() == "branch_value":
                self._update_branch_value_field(field_key)

    def _update_branch_value_field(self, field_key):
        widgets = self.field_widgets.get(field_key, {})
        source_combo = widgets.get("source_combo")
        value_key_combo = widgets.get("value_key_combo")
        preview = widgets.get("value_widget")
        if not source_combo or not value_key_combo or not preview:
            return
        branch = self._selected_branch_from_source_type(source_combo.currentData())
        value = ""
        if branch:
            value = self._branch_value(branch, value_key_combo.currentData())
            if isinstance(value, dict):
                value = value.get("path", "")
        preview.setText(value)

    def _field_value(self, field_key):
        widgets = self.field_widgets[field_key]
        field_type = widgets["type_combo"].currentData() or "text"
        value_widget = widgets.get("value_widget")

        if field_type == "date":
            return value_widget.date().toString(widgets["format_combo"].currentData())
        if field_type == "amount":
            text = value_widget.text()
            if widgets["comma_check"].isChecked() and text:
                return f"{int(text):,}"
            return text
        if field_type in {"branch_select", "branch_select_2"}:
            branch = value_widget.currentData()
            return branch.get("branch_name", "") if branch else ""
        if field_type == "branch_value":
            branch = self._selected_branch_from_source_type(widgets["source_combo"].currentData())
            return self._branch_value(branch, widgets["value_key_combo"].currentData())
        return value_widget.text() if value_widget else ""

    def _collect_field_settings(self):
        fields = {}
        for field_key, widgets in self.field_widgets.items():
            field_type = widgets["type_combo"].currentData() or "text"
            setting = {"type": field_type}
            if field_type == "date":
                setting["date_format"] = widgets["format_combo"].currentData()
            elif field_type == "amount":
                setting["use_comma"] = widgets["comma_check"].isChecked()
            elif field_type in {"branch_select", "branch_select_2"}:
                branch = widgets["value_widget"].currentData()
                setting["branch_name"] = branch.get("branch_name", "") if branch else ""
            elif field_type == "branch_value":
                setting["source_field"] = widgets["source_combo"].currentData()
                setting["branch_value_key"] = widgets["value_key_combo"].currentData()
            fields[field_key] = setting
        return {"version": 1, "fields": fields}

    def save_field_settings(self):
        self.settings = self._collect_field_settings()
        write_json_file(self.settings_path, self.settings)
        QMessageBox.information(self, "저장 완료", "필드 설정을 저장했습니다.")
    
    def _load_docx2pdf(self):
        try:
            return importlib.import_module('docx2pdf')
        except ImportError:
            return None

    def _install_docx2pdf(self):
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'docx2pdf'])
            importlib.invalidate_caches()
            return importlib.import_module('docx2pdf')
        except Exception as e:
            raise RuntimeError(f"docx2pdf 설치 실패: {e}") from e

    def create_from_controls(self):
        """입력한 값으로 새 문서를 생성(PDF 변환). 원본은 변경하지 않음."""
        log("DocumentTool", f"문서 생성 시도: {self.file_path.name}", level="INFO")
        try:
            self.settings = self._collect_field_settings()
            write_json_file(self.settings_path, self.settings)

            # 새 Document 로드 (원본 보존)
            new_doc = Document(self.file_path)
            
            # 사용자 입력값 수집
            values_dict = {}
            for field_key in self.controls:
                values_dict[field_key] = self._field_value(field_key)
            
            # 콘텐츠 컨트롤 업데이트
            sdt_list = new_doc.element.findall('.//' + qn('w:sdt'))
            for idx, sdt in enumerate(sdt_list):
                info = self._content_control_info(sdt, idx)
                if not info:
                    continue
                field_key = info["tag"] or info["alias"] or f"필드 {idx + 1}"
                if field_key not in values_dict:
                    continue
                
                new_value = values_dict[field_key]
                sdt_content = sdt.find(qn('w:sdtContent'))
                if sdt_content is None:
                    continue

                if isinstance(new_value, dict) and new_value.get("type") == "image":
                    self._set_sdt_image(new_doc, sdt_content, new_value)
                    continue
                
                # 모든 w:t 요소에서 텍스트 업데이트
                t_list = sdt_content.findall('.//' + qn('w:t'))
                if t_list:
                    # 첫 번째 텍스트 요소에 값 할당
                    t_list[0].text = str(new_value)
                    # 나머지는 제거
                    for t in t_list[1:]:
                        parent = t.getparent()
                        try:
                            parent.remove(t)
                        except Exception:
                            pass
                else:
                    # w:t 요소가 없으면 생성
                    run = OxmlElement('w:r')
                    t = OxmlElement('w:t')
                    t.text = str(new_value)
                    run.append(t)
                    sdt_content.append(run)
            
            maked_folder = self.file_path.parent / "maked"
            maked_folder.mkdir(exist_ok=True)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
                temp_docx_path = Path(tmp_file.name)
            try:
                new_doc.save(str(temp_docx_path))

                # PDF 변환 시도
                docx2pdf = self._load_docx2pdf()
                if docx2pdf is None:
                    install_answer = QMessageBox.question(
                        self,
                        'docx2pdf 설치',
                        'docx2pdf 패키지가 설치되어 있지 않습니다. 설치하시겠습니까?',
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if install_answer == QMessageBox.Yes:
                        try:
                            docx2pdf = self._install_docx2pdf()
                        except Exception as e:
                            log("DocumentTool", f"docx2pdf 설치 실패: {e}", level="ERROR")
                            QMessageBox.warning(
                                self,
                                '경고',
                                f'docx2pdf 설치에 실패했습니다:\n{e}\nPDF 생성이 취소되었습니다.',
                            )
                            self.accept()
                            return
                    else:
                        log("DocumentTool", "docx2pdf 설치 거부됨; PDF 생성 취소", level="WARNING")
                        QMessageBox.warning(
                            self,
                            '경고',
                            'docx2pdf 라이브러리가 설치되지 않았습니다. PDF 파일 생성이 취소되었습니다.',
                        )
                        self.accept()
                        return

                try:
                    out_pdf = maked_folder / (self.file_path.stem + '_filled.pdf')
                    docx2pdf.convert(str(temp_docx_path), str(out_pdf))
                    log("DocumentTool", f"PDF 생성 완료: {out_pdf}", level="INFO")
                    QMessageBox.information(self, '완료', f'PDF 생성 완료:\n{out_pdf}\n\n원본 파일은 변경되지 않았습니다')
                except Exception as e:
                    log("DocumentTool", f"PDF 변환 실패: {e}", level="ERROR")
                    QMessageBox.warning(self, '경고', f'PDF 변환 실패:\n{e}')
            finally:
                try:
                    if temp_docx_path.exists():
                        temp_docx_path.unlink()
                except Exception:
                    pass

            self.accept()
        except Exception as e:
            log("DocumentTool", f"문서 생성 오류: {e}", level="ERROR")
            QMessageBox.critical(self, "오류", f"생성 중 오류: {e}")

    def _set_sdt_image(self, doc, sdt_content, value):
        image_path = Path(value.get("path", ""))
        if not value.get("path") or not image_path.exists():
            return

        for child in list(sdt_content):
            sdt_content.remove(child)

        paragraph_element = OxmlElement('w:p')
        sdt_content.append(paragraph_element)
        paragraph = Paragraph(paragraph_element, doc)
        run = paragraph.add_run()
        run.add_picture(
            str(image_path),
            width=Mm(int(value.get("width", 30) or 30)),
            height=Mm(int(value.get("height", 30) or 30)),
        )
