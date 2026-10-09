"""ui.py - PySide6 ana kullanıcı arayüzü ve penceresi.

Sadece kullanıcı girdisi, servis çağrıları ve sunum yer alır.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from calendar_view import CalendarView
from dialogs import AvailabilityDialog, ExamDialog, TimetableDialog
from engine import PlannerService
from ui_common import (
    MAIN_MARGIN_BOTTOM, MAIN_MARGIN_H, MAIN_MARGIN_TOP, UI_STYLESHEET
)
from views import SubjectsView, TasksView


class MainWindow(QMainWindow):
    """Ana uygulama penceresi."""

    def __init__(self, service: PlannerService) -> None:
        super().__init__()
        self.service = service
        self._setup_window()
        self._setup_views()
        self._setup_tabs()
        self._setup_central_widget()
        self._connect_views()
        self._setup_menu()
        self.statusBar().showMessage("Hazır")

    def _setup_window(self) -> None:
        self.setWindowTitle("Dinamik Akademik Çalışma Planlayıcı")
        self.resize(1200, 780)
        self.setStyleSheet(UI_STYLESHEET)

    def _setup_views(self) -> None:
        self.calendar = CalendarView(self.service)
        self.subjects = SubjectsView(self.service)
        self.tasks = TasksView(self.service)

    def _setup_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.addTab(self.calendar, "Takvim")
        self.tabs.addTab(self.subjects, "Dersler")
        self.tabs.addTab(self.tasks, "Görevler")
        self.tabs.currentChanged.connect(self._on_tab)

    def _setup_central_widget(self) -> None:
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(
            MAIN_MARGIN_H,
            MAIN_MARGIN_TOP,
            MAIN_MARGIN_H,
            MAIN_MARGIN_BOTTOM
        )
        central_layout.setSpacing(0)
        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central)

    def _connect_views(self) -> None:
        self.calendar.plan_changed.connect(self.tasks.refresh)

    def _setup_menu(self) -> None:
        menu = self.menuBar().addMenu("Planlama")
        menu.addAction("Yeniden planla", self.calendar.replan)
        menu.addSeparator()
        menu.addAction(
            "Çalışma zamanları (müsaitlik)…",
            lambda: self._dialog(AvailabilityDialog)
        )
        menu.addAction(
            "Okul ders programı…",
            lambda: self._dialog(TimetableDialog)
        )
        menu.addAction(
            "Sınavlar…",
            lambda: self._dialog(ExamDialog)
        )

    def _dialog(self, cls: type[QDialog]) -> None:
        cls(self.service, self).exec()
        self.calendar.refresh()

    def _on_tab(self, index: int) -> None:
        (self.calendar, self.subjects, self.tasks)[index].refresh()