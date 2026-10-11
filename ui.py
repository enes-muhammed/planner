"""ui.py - 3 Katmanlı Modern Arayüz Düzeni."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QInputDialog,
    QMainWindow, QStackedWidget, QWidget
)

from calendar_view import CalendarView
from dialogs import AvailabilityDialog, ExamDialog, TimetableDialog
from engine import PlannerService
from sidebar import ExpandedSidebar, LeftNavRail
from ui_common import UI_STYLESHEET, create_light_palette
from views import SubjectsView, TasksView


class MainWindow(QMainWindow):
    """Görseldeki tasarımı birebir yansıtan modern ana pencere."""

    def __init__(self, service: PlannerService) -> None:
        super().__init__()
        self.service = service

        self._setup_palette()
        self._setup_window()
        self._setup_components()
        self._setup_layout()
        self._connect_signals()

        # Varsayılan olarak Takvim sekmesini aç (Context sidebar gizlenir)
        self._on_tab_switched(0)

    def _setup_palette(self) -> None:
        light_pal = create_light_palette()
        self.setPalette(light_pal)
        app = QApplication.instance()
        if app:
            app.setPalette(light_pal)

    def _setup_window(self) -> None:
        self.setWindowTitle("Dinamik Akademik Çalışma Planlayıcı")
        self.resize(1300, 840)
        self.setStyleSheet(UI_STYLESHEET)

    def _setup_components(self) -> None:
        # 1. Katman: Sol Dar Siyah Navigasyon Çubuğu
        self.nav_rail = LeftNavRail(self)

        # 2. Katman: Arkaplanla Birebir Aynı Şeffaf Genişletilmiş Sidebar
        self.expanded_sidebar = ExpandedSidebar(self.service, self)

        # 3. Katman: Sağdaki Büyük Beyaz Kart (Çizgilerin sınıra dayanabilmesi için padding: 0px)
        self.main_stack = QStackedWidget()
        self.main_stack.setStyleSheet("""
            QStackedWidget {
                background-color: #FFFFFF;
                border: 1px solid #D7DAE0;
                border-radius: 10px;
                padding: 0px;
            }""")

        # İç Görünümler
        self.calendar_view = CalendarView(self.service)
        self.subjects_view = SubjectsView(self.service)
        self.tasks_view = TasksView(self.service)

        self.main_stack.addWidget(self.calendar_view)
        self.main_stack.addWidget(self.subjects_view)
        self.main_stack.addWidget(self.tasks_view)

    def _setup_layout(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(7)

        layout.addWidget(self.nav_rail)
        layout.addWidget(self.expanded_sidebar)
        layout.addWidget(self.main_stack, 1)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        # Tab değişimi
        self.nav_rail.tab_changed.connect(self._on_tab_switched)

        # Sol rail'deki planlama işlemleri
        self.nav_rail.planning_triggered.connect(self._on_planning_action)

        # Sidebar seçimleri
        self.expanded_sidebar.subject_selected.connect(self.subjects_view.select_subject)
        self.expanded_sidebar.subject_add_requested.connect(self._add_subject)
        self.expanded_sidebar.task_filter_selected.connect(self.tasks_view.set_filter)

        # Ders güncellendiğinde sidebar'ı da tazele
        self.subjects_view.subject_changed.connect(
            lambda: self.expanded_sidebar.update_view(1, self.subjects_view.current_sid)
        )

        # Takvim planı değişince görevleri tazele
        self.calendar_view.plan_changed.connect(self.tasks_view.refresh)

    def _on_tab_switched(self, index: int) -> None:
        self.main_stack.setCurrentIndex(index)
        self.nav_rail.set_current_index(index)
        self.expanded_sidebar.update_view(index, self.subjects_view.current_sid)

        # İlgili sayfayı tazele
        if index == 0:
            self.calendar_view.refresh()
        elif index == 1:
            self.subjects_view.refresh()
        elif index == 2:
            self.tasks_view.refresh()

    def _add_subject(self) -> None:
        name, ok = QInputDialog.getText(self, "Yeni Ders", "Ders adı:")
        if ok and name.strip():
            self.service.add_subject(name.strip())
            self.expanded_sidebar.update_view(1, self.subjects_view.current_sid)
            self.subjects_view.refresh()

    def _on_planning_action(self, action: str) -> None:
        if action == "replan":
            self.calendar_view.replan()
        elif action == "availability":
            self._open_dialog(AvailabilityDialog)
        elif action == "timetable":
            self._open_dialog(TimetableDialog)
        elif action == "exams":
            self._open_dialog(ExamDialog)

    def _open_dialog(self, dialog_cls: type[QDialog]) -> None:
        dialog_cls(self.service, self).exec()
        self.calendar_view.refresh()