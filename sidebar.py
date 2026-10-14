"""sidebar.py - Minimalist sol dark rail ve dinamik context sidebar."""
from __future__ import annotations

import os
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget
)

from engine import PlannerService


def load_icon_or_fallback(icon_name: str, fallback_text: str, size: int = 20) -> QIcon:
    """assets/ klasöründe ikon arar, yoksa şık bir canvas çizimi üretir."""
    for ext in (".svg", ".png"):
        path = os.path.join("assets", f"{icon_name}{ext}")
        if os.path.exists(path):
            return QIcon(path)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", int(size * 0.45), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, fallback_text)
    painter.end()
    return QIcon(pixmap)


class NavRailButton(QPushButton):
    """Sol siyah sütundaki minimalist ikon butonu."""

    def __init__(self, icon_name: str, fallback_char: str, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setIcon(load_icon_or_fallback(icon_name, fallback_char, 20))
        self.setIconSize(QSize(20, 20))
        self.setCheckable(True)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #27282D;
            }
            QPushButton:checked {
                background-color: #32343B;
            }
        """)


class LeftNavRail(QFrame):
    """Sol dar siyah navigasyon çubuğu."""

    tab_changed = Signal(int)
    planning_triggered = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(80)
        self.setStyleSheet("""
            QFrame {
                background-color: #17181C;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # 1. Logo
        self.logo_btn = QPushButton()
        self.logo_btn.setFixedSize(44, 44)
        self.logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_btn.setIcon(load_icon_or_fallback("logo", "⬡", 24))
        self.logo_btn.setIconSize(QSize(24, 24))
        self.logo_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 20px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.logo_btn)

        layout.addSpacing(16)

        # 2. Sayfa İkonları
        self.btn_calendar = NavRailButton("calendar", "📅", "Takvim")
        self.btn_subjects = NavRailButton("subjects", "💼", "Dersler")
        self.btn_tasks = NavRailButton("tasks", "🎯", "Görevler")

        self.buttons = [self.btn_calendar, self.btn_subjects, self.btn_tasks]
        for i, btn in enumerate(self.buttons):
            btn.clicked.connect(lambda _, idx=i: self._on_button_clicked(idx))
            layout.addWidget(btn)

        self.btn_calendar.setChecked(True)

        layout.addStretch(1)

        # 3. Planlama & Hızlı İşlemler Butonu
        self.btn_plan = NavRailButton("planning", "⚡", "Planlama & Menü")
        self.btn_plan.clicked.connect(self._open_planning_menu)
        layout.addWidget(self.btn_plan)

        # 4. Ayarlar / Müsaitlik
        self.btn_settings = NavRailButton("settings", "⚙", "Çalışma Zamanları")
        self.btn_settings.clicked.connect(lambda: self.planning_triggered.emit("availability"))
        layout.addWidget(self.btn_settings)

    def _on_button_clicked(self, index: int) -> None:
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)
        self.tab_changed.emit(index)

    def set_current_index(self, index: int) -> None:
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)

    def _open_planning_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("⚡ Yeniden Planla", lambda: self.planning_triggered.emit("replan"))
        menu.addSeparator()
        menu.addAction("🕒 Çalışma Zamanları (Müsaitlik)…", lambda: self.planning_triggered.emit("availability"))
        menu.addAction("🏫 Okul Ders Programı…", lambda: self.planning_triggered.emit("timetable"))
        menu.addAction("📝 Sınavlar…", lambda: self.planning_triggered.emit("exams"))
        menu.exec(self.btn_plan.mapToGlobal(QPoint(self.width() + 6, 0)))


class SidebarItemWidget(QPushButton):
    """Genişletilmiş bardaki satır öğesi (İsim + Sayı rozeti)."""

    def __init__(self, title: str, count: int | str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)

        self.lbl_title = QLabel(title)
        self.lbl_count = QLabel(str(count) if count != "" else "")

        layout.addWidget(self.lbl_title)
        layout.addStretch(1)
        layout.addWidget(self.lbl_count)

        self._update_style(False)

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self._update_style(active)

    def _update_style(self, active: bool) -> None:
        if active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #E2E4E8;
                    border: none;
                    border-radius: 8px;
                }
            """)
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #000000; background: transparent; border: none;")
            self.lbl_count.setStyleSheet("font-size: 12px; font-weight: 600; color: #555555; background: transparent; border: none;")
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #EAEBED;
                }
            """)
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 500; color: #3C4043; background: transparent; border: none;")
            self.lbl_count.setStyleSheet("font-size: 12px; font-weight: 500; color: #70757A; background: transparent; border: none;")


class ExpandedSidebar(QWidget):
    """Arkaplanla aynı renkte olan dinamik genişletilmiş sidebar."""

    subject_selected = Signal(int)
    subject_add_requested = Signal()
    task_filter_selected = Signal(str)

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setFixedWidth(210)
        self.setStyleSheet("background: transparent;")

        self.subject_buttons: dict[int, SidebarItemWidget] = {}
        self.filter_buttons: list[SidebarItemWidget] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 18, 10, 16)
        self.main_layout.setSpacing(10)

        self.content_area = QVBoxLayout()
        self.content_area.setSpacing(4)
        self.main_layout.addLayout(self.content_area)
        self.main_layout.addStretch(1)

    def clear_content(self) -> None:
        self.subject_buttons.clear()
        self.filter_buttons.clear()
        while self.content_area.count():
            item = self.content_area.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def update_view(self, tab_index: int, active_subject_id: int | None = None) -> None:
        self.clear_content()

        # Tab 0: Takvim -> Genişletilmiş sidebar tamamen gizlenir
        if tab_index == 0:
            self.setVisible(False)
            return

        self.setVisible(True)

        if tab_index == 1:
            self._build_subjects_sidebar(active_subject_id)
        elif tab_index == 2:
            self._build_tasks_sidebar()

    def _build_subjects_sidebar(self, active_id: int | None) -> None:
        title = QLabel("Dersler")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #17181C; margin-bottom: 8px;")
        self.content_area.addWidget(title)

        subjects = self.service.list_subjects()

        # Aktif ders belirtilmemişse ilk dersi seç
        if active_id is None and subjects and subjects[0].id is not None:
            active_id = subjects[0].id

        self.subject_buttons = {}
        for s in subjects:
            if s.id is None:
                continue
            item = SidebarItemWidget(s.name, "")
            is_active = (s.id == active_id)
            item.set_active(is_active)
            item.clicked.connect(lambda _, sid=s.id, it=item: self._on_subject_clicked(sid, it))
            self.subject_buttons[s.id] = item
            self.content_area.addWidget(item)

        btn_add = QPushButton("+ Ders Ekle")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #70757A;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                padding-left: 10px;
                margin-top: 10px;
            }
            QPushButton:hover {
                color: #1A73E8;
            }
        """)
        btn_add.clicked.connect(self.subject_add_requested.emit)
        self.content_area.addWidget(btn_add)

    def _on_subject_clicked(self, sid: int, selected_item: SidebarItemWidget) -> None:
        """Ders tıklandığında seçili butonun stilini günceller ve sinyali iletir."""
        for btn in self.subject_buttons.values():
            btn.set_active(btn is selected_item)
        self.subject_selected.emit(sid)

    def set_active_subject(self, sid: int) -> None:
        """Dışarıdan çağrıldığında ilgili ders butonunu aktif yapar."""
        for s_id, btn in self.subject_buttons.items():
            btn.set_active(s_id == sid)

    def _build_tasks_sidebar(self) -> None:
        title = QLabel("Görevler")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #17181C; margin-bottom: 8px;")
        self.content_area.addWidget(title)

        filters = [
            ("Tümü", "all"),
            ("Tekrar", "review"),
            ("Teslim Görevi", "deadline"),
            ("Tekrarlayan", "recurring"),
            ("Gecikmiş", "overdue"),
            ("Tamamlanan", "completed")
        ]

        self.filter_buttons = []
        for i, (label, key) in enumerate(filters):
            item = SidebarItemWidget(label, "")
            item.set_active(i == 0)
            item.clicked.connect(lambda _, k=key, it=item: self._on_task_filter_clicked(k, it))
            self.filter_buttons.append(item)
            self.content_area.addWidget(item)

    def _on_task_filter_clicked(self, filter_key: str, selected_item: SidebarItemWidget) -> None:
        for btn in self.filter_buttons:
            btn.set_active(btn is selected_item)
        self.task_filter_selected.emit(filter_key)