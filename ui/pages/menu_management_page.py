"""Edit groups and placement of registered pages without creating pages."""

import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from menu_layout import save_layout, validate_groups


class MenuManagementPage(QWidget):
    layout_saved = Signal(object)

    def __init__(self):
        super().__init__()
        self.path = None
        self.registry = {}
        layout = QVBoxLayout(self)
        description = QLabel(
            "대메뉴를 추가·이름 변경·삭제하고 기존 메뉴를 배치합니다.\n"
            "하위 메뉴를 선택한 뒤 이동할 대메뉴를 고르세요. 위/아래 버튼으로 순서를 바꿀 수 있습니다.\n"
            "대메뉴 삭제 시 하위 메뉴는 다른 대메뉴로 이동합니다. 저장하면 왼쪽 메뉴에 적용됩니다."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("메뉴 구성")
        layout.addWidget(self.tree)
        buttons = QHBoxLayout()
        for title, callback in [("대메뉴 추가", self.add_group), ("대메뉴명 수정", self.rename_group),
                                ("대메뉴 삭제", self.delete_group),
                                ("위로", lambda: self.move_order(-1)),
                                ("아래로", lambda: self.move_order(1))]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        move = QHBoxLayout()
        move.addWidget(QLabel("이동할 대메뉴"))
        self.destination = QComboBox()
        move.addWidget(self.destination, 1)
        button = QPushButton("선택 메뉴 이동")
        button.clicked.connect(self.move_page)
        move.addWidget(button)
        layout.addLayout(move)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.save_button = QPushButton("메뉴 구성 저장")
        self.save_button.clicked.connect(self.save)
        layout.addWidget(self.save_button)

    def configure(self, path, registry, groups, error=""):
        self.path, self.registry = path, registry
        self.tree.clear()
        for group in groups:
            item = QTreeWidgetItem(self.tree, [group['name']])
            item.setData(0, Qt.UserRole, group['id'])
            for key in group['pages']:
                child = QTreeWidgetItem(item, [registry[key]['label']])
                child.setData(0, Qt.UserRole, key)
        self.tree.expandAll()
        self.refresh_destinations()
        self.status.setText(error)
        self.save_button.setEnabled(not error)

    def groups(self):
        return [dict(id=g.data(0, Qt.UserRole), name=g.text(0),
                     pages=[g.child(j).data(0, Qt.UserRole) for j in range(g.childCount())])
                for g in self.group_items()]

    def group_items(self):
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    def selected_group(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.parent() or item

    def refresh_destinations(self):
        selected = self.destination.currentData()
        self.destination.clear()
        for group in self.group_items():
            self.destination.addItem(group.text(0), group.data(0, Qt.UserRole))
        index = self.destination.findData(selected)
        if index >= 0:
            self.destination.setCurrentIndex(index)

    def ask_name(self, current=""):
        name, accepted = QInputDialog.getText(self, "대메뉴", "대메뉴 이름", text=current)
        if not accepted:
            return None
        name = name.strip()
        if not name or any(g.text(0) == name and g.text(0) != current for g in self.group_items()):
            self.status.setText("대메뉴 이름을 비워 두거나 중복해서 사용할 수 없습니다.")
            return None
        return name

    def add_group(self):
        name = self.ask_name()
        if name is not None:
            item = QTreeWidgetItem(self.tree, [name])
            item.setData(0, Qt.UserRole, 'custom_' + uuid.uuid4().hex)
            self.tree.setCurrentItem(item)
            self.refresh_destinations()

    def rename_group(self):
        group = self.selected_group()
        if group is None:
            return
        name = self.ask_name(group.text(0))
        if name is not None:
            group.setText(0, name)
            self.refresh_destinations()

    def delete_group(self):
        group = self.selected_group()
        if group is None:
            return
        others = [g for g in self.group_items() if g is not group]
        if not others:
            self.status.setText("대메뉴는 하나 이상 유지해야 합니다.")
            return
        target = next((g for g in others if g.data(0, Qt.UserRole) == self.destination.currentData()), others[0])
        while group.childCount():
            target.addChild(group.takeChild(0))
        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(group))
        target.setExpanded(True)
        self.tree.setCurrentItem(target)
        self.refresh_destinations()
        self.status.setText(f"하위 메뉴를 '{target.text(0)}' 대메뉴로 이동했습니다. 저장하면 적용됩니다.")

    def move_page(self):
        item = self.tree.currentItem()
        if item is None or item.parent() is None:
            self.status.setText("이동할 하위 메뉴를 선택하세요.")
            return
        target = next(g for g in self.group_items() if g.data(0, Qt.UserRole) == self.destination.currentData())
        parent = item.parent()
        if parent is target:
            return
        parent.takeChild(parent.indexOfChild(item))
        target.addChild(item)
        target.setExpanded(True)
        self.tree.setCurrentItem(item)

    def move_order(self, offset):
        item = self.tree.currentItem()
        if item is None:
            return
        parent = item.parent()
        index = parent.indexOfChild(item) if parent else self.tree.indexOfTopLevelItem(item)
        count = parent.childCount() if parent else self.tree.topLevelItemCount()
        if not 0 <= index + offset < count:
            return
        if parent:
            parent.takeChild(index)
            parent.insertChild(index + offset, item)
        else:
            self.tree.takeTopLevelItem(index)
            self.tree.insertTopLevelItem(index + offset, item)
            self.refresh_destinations()
        self.tree.setCurrentItem(item)

    def save(self):
        try:
            groups = self.groups()
            validate_groups(groups)
            registered = set(self.registry)
            if {p for g in groups for p in g['pages']} != registered:
                raise ValueError("등록된 모든 페이지를 배치해야 합니다.")
            save_layout(self.path, groups)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "메뉴 저장 실패", str(exc))
            return
        self.layout_saved.emit(groups)
        self.status.setText("메뉴 구성을 저장하고 적용했습니다.")
