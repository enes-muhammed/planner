"""ui.py - PySide6 ana penceresi ve tema yöneticisi."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMainWindow, QPushButton, QTabWidget,
    QVBoxLayout, QWidget
)

from calendar_view import CalendarView
from dialogs import AvailabilityDialog, ExamDialog, TimetableDialog
from engine import PlannerService
from ui_common import (
    MAIN_MARGIN_BOTTOM, MAIN_MARGIN_H, MAIN_MARGIN_TOP, get_stylesheet
)
from views import SubjectsView, TasksView


class MainWindow(QMainWindow):
    """Ana uygulama penceresi."""

    def __init__(self, service: PlannerService) -> None:
        super().__init__()
        self.service = service
        self.current_theme = "dark"  # Varsayılan mod

        self._setup_window()
        self._setup_views()
        self._setup_tabs()
        self._setup_central_widget()
        self._connect_views()
        self._setup_menu()
        self._apply_theme()
        self.statusBar().showMessage("Hazır")

    def _setup_window(self) -> None:
        self.setWindowTitle("Dinamik Akademik Çalışma Planlayıcı")
        self.resize(1240, 800)

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

        # Tab bar'ın sağ üst köşesine hızlı tema değiştirici buton
        self.theme_btn = QPushButton("☀️ Açık Mod")
        self.theme_btn.setFixedHeight(28)
        self.theme_btn.clicked.connect(self._toggle_theme)
        self.tabs.setCornerWidget(self.theme_btn)

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
        plan_menu = self.menuBar().addMenu("Planlama")
        plan_menu.addAction("Yeniden planla", self.calendar.replan)
        plan_menu.addSeparator()
        plan_menu.addAction("Çalışma zamanları (müsaitlik)…", lambda: self._dialog(AvailabilityDialog))
        plan_menu.addAction("Okul ders programı…", lambda: self._dialog(TimetableDialog))
        plan_menu.addAction("Sınavlar…", lambda: self._dialog(ExamDialog))

        view_menu = self.menuBar().addMenu("Görünüm")
        view_menu.addAction("Açık Mod", lambda: self._set_theme("light"))
        view_menu.addAction("Koyu Mod", lambda: self._set_theme("dark"))

    def _toggle_theme(self) -> None:
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._set_theme(new_theme)

    def _set_theme(self, theme: str) -> None:
        self.current_theme = theme
        self._apply_theme()

    def _apply_theme(self) -> None:
        is_dark = (self.current_theme == "dark")
        self.setStyleSheet(get_stylesheet(self.current_theme))
        self.theme_btn.setText("☀️ Açık Mod" if is_dark else "🌙 Koyu Mod")

        self.calendar.set_theme_mode(is_dark)
        self.calendar.refresh()
        self.subjects.refresh()
        self.tasks.refresh()

    def _dialog(self, cls: type[QDialog]) -> None:
        cls(self.service, self).exec()
        self.calendar.refresh()

    def _on_tab(self, index: int) -> None:
        (self.calendar, self.subjects, self.tasks)[index].refresh()