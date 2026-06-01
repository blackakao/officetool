import json
import sys
import subprocess
import tempfile
import importlib
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QPushButton, QDialog, QLabel, QFormLayout, QLineEdit, QMessageBox, QHeaderView, QScrollArea
)


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
        try:
            doc = Document(file_path)
            dialog = ContentControlDialog(self, doc, file_path)
            dialog.exec()
            self.load_documents()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"문서를 열 수 없습니다: {e}")
    
    def showEvent(self, event):
        """페이지가 보여질 때마다 새로고침"""
        super().showEvent(event)
        self.load_documents()



class ContentControlDialog(QDialog):
    def __init__(self, parent, doc, file_path):
        super().__init__(parent)
        self.setWindowTitle(f"{file_path.stem} 수정")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        
        self.doc = doc
        self.file_path = file_path
        self.controls = {}  # {sdt_element: (tag, alias, placeholder, text_edit, description_label)}
        
        layout = QVBoxLayout()

        # 폼 레이아웃을 스크롤 가능한 영역으로 감싼다
        form_layout = QFormLayout()

        # 문서의 모든 콘텐츠 컨트롤(sdt) 추출
        sdt_list = doc.element.findall('.//' + qn('w:sdt'))
        
        for idx, sdt in enumerate(sdt_list):
            # sdt 속성 추출
            sdt_pr = sdt.find(qn('w:sdtPr'))
            if sdt_pr is None:
                continue
            
            # 태그(제목) 추출
            tag_elem = sdt_pr.find(qn('w:tag'))
            tag = tag_elem.get(qn('w:val')) if tag_elem is not None else f"필드 {idx+1}"
            
            # 별칭 추출
            alias_elem = sdt_pr.find(qn('w:alias'))
            alias = alias_elem.get(qn('w:val')) if alias_elem is not None else ""
            
            # 플레이스홀더 추출
            placeholder_elem = sdt_pr.find(qn('w:placeholder'))
            placeholder = ""
            if placeholder_elem is not None:
                placeholder_text = placeholder_elem.find(qn('w:docPart'))
                if placeholder_text is not None:
                    placeholder = placeholder_text.get(qn('w:val')) or ""
            
            # 현재 텍스트 추출
            sdt_content = sdt.find(qn('w:sdtContent'))
            current_text = ""
            if sdt_content is not None:
                t_list = sdt_content.findall('.//' + qn('w:t'))
                if t_list:
                    current_text = ''.join([t.text for t in t_list if t.text])
            
            # 제목 라벨 (콘텐츠 컨트롤 제목)
            title_label = QLabel(f"<b>{tag}</b>")
            
            # 입력 필드
            text_edit = QLineEdit()
            text_edit.setText(current_text)
            text_edit.setPlaceholderText(placeholder or alias or "입력하세요")
            
            # 설명 라벨 (태그, 별칭 등 정보)
            description_texts = []
            if alias:
                description_texts.append(f"별칭: {alias}")
            if placeholder:
                description_texts.append(f"설명: {placeholder}")
            description_text = " | ".join(description_texts) if description_texts else ""
            
            description_label = QLabel(description_text)
            description_label.setStyleSheet("color: gray; font-size: 10px;")
            
            # 폼 레이아웃에 추가
            form_layout.addRow(title_label, None)  # 제목 라인
            form_layout.addRow("  ", text_edit)    # 입력 필드
            if description_text:
                form_layout.addRow("  ", description_label)  # 설명 라인
            form_layout.addRow("", None)  # 간격
            
            self.controls[idx] = {
                'sdt': sdt,
                'tag': tag,
                'text_edit': text_edit,
                'sdt_content': sdt_content
            }

        # 스크롤 영역에 폼을 넣어서 팝업 내부에서 스크롤 가능하게 함
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setLayout(form_layout)
        scroll.setWidget(container)

        layout.addWidget(scroll)
        
        # 버튼
        button_layout = QHBoxLayout()
        create_button = QPushButton("생성")
        cancel_button = QPushButton("취소")

        create_button.clicked.connect(self.create_from_controls)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(create_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
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
        try:
            # 새 Document 로드 (원본 보존)
            new_doc = Document(self.file_path)
            
            # 사용자 입력값 수집
            values_dict = {}
            for idx, ctrl_info in self.controls.items():
                values_dict[idx] = ctrl_info['text_edit'].text()
            
            # 콘텐츠 컨트롤 업데이트
            sdt_list = new_doc.element.findall('.//' + qn('w:sdt'))
            for idx, sdt in enumerate(sdt_list):
                if idx not in values_dict:
                    continue
                
                new_text = values_dict[idx]
                sdt_content = sdt.find(qn('w:sdtContent'))
                if sdt_content is None:
                    continue
                
                # 모든 w:t 요소에서 텍스트 업데이트
                t_list = sdt_content.findall('.//' + qn('w:t'))
                if t_list:
                    # 첫 번째 텍스트 요소에 값 할당
                    t_list[0].text = new_text
                    # 나머지는 제거
                    for t in t_list[1:]:
                        parent = t.getparent()
                        try:
                            parent.remove(t)
                        except Exception:
                            pass
                else:
                    # w:t 요소가 없으면 생성
                    from docx.oxml import OxmlElement
                    run = OxmlElement('w:r')
                    t = OxmlElement('w:t')
                    t.text = new_text
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
                            QMessageBox.warning(
                                self,
                                '경고',
                                f'docx2pdf 설치에 실패했습니다:\n{e}\nPDF 생성이 취소되었습니다.',
                            )
                            self.accept()
                            return
                    else:
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
                    QMessageBox.information(self, '완료', f'PDF 생성 완료:\n{out_pdf}\n\n원본 파일은 변경되지 않았습니다')
                except Exception as e:
                    QMessageBox.warning(self, '경고', f'PDF 변환 실패:\n{e}')
            finally:
                try:
                    if temp_docx_path.exists():
                        temp_docx_path.unlink()
                except Exception:
                    pass

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"생성 중 오류: {e}")
