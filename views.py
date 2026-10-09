"""views.py - Dersler ve Görevler ana görünümleri."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
    QSplitter, QVBoxLayout, QWidget, QFormLayout
)

from dialogs import TaskDialog
from engine import PlannerService, Task
from ui_common import (
    CLASS_LABEL, STATUS_LABEL, TAB_CONTENT_MARGIN_BOTTOM,
    TAB_CONTENT_MARGIN_H, TAB_CONTENT_MARGIN_TOP, fmt_date,
    make_table, selected_key, set_row, show_error
)


class SubjectsView(QWidget):
    """Dersler ve hafıza takibi yönetim sekmesi."""

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service

        split = QSplitter(Qt.Orientation.Horizontal)
        left = self._build_left_panel()
        right = self._build_right_panel()

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 760])

        self._setup_main_layout(split)
        self.refresh()

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        layout = QVBoxLayout(left)

        layout.addWidget(QLabel("<b>Dersler</b>"))

        self.list = QListWidget()
        self.list.currentItemChanged.connect(
            lambda *_: self._load_subject()
        )
        layout.addWidget(self.list)

        row = QHBoxLayout()
        for text, fn in (
            ("Ekle", self._add),
            ("Düzenle", self._rename),
            ("Sil", self._delete)
        ):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)

        layout.addLayout(row)
        return left

    def _build_right_panel(self) -> QWidget:
        right = QWidget()
        layout = QVBoxLayout(right)

        self.title = QLabel("Bir ders seçin")
        self.title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(self.title)

        self._setup_event_header(layout)

        self.events = make_table([
            "Tarih", "Haftalık ders sırası", "Konu", "Not"
        ])
        layout.addWidget(self.events, 3)

        layout.addWidget(
            QLabel("Konu hafıza durumu (bir sonraki ideal tekrar)")
        )

        self.memory = make_table([
            "Konu", "Aşama", "Stabilite (gün)", "Zorluk",
            "Son çalışma", "İdeal tekrar", "Tekrar sayısı"
        ])
        layout.addWidget(self.memory, 2)
        return right

    def _setup_event_header(self, layout: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.addWidget(QLabel("Öğrenme geçmişi (kronolojik)"))
        head.addStretch(1)

        delete_button = QPushButton("Kaydı sil")
        delete_button.clicked.connect(self._delete_event)
        head.addWidget(delete_button)

        layout.addLayout(head)

    def _setup_main_layout(self, split: QSplitter) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_TOP,
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_BOTTOM
        )
        layout.addWidget(split)

    def current_subject_id(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def refresh(self) -> None:
        keep = self.current_subject_id()
        self._reload_subject_list(keep)
        self._load_subject()

    def _reload_subject_list(self, keep: int | None) -> None:
        self.list.blockSignals(True)
        self.list.clear()

        for s in self.service.list_subjects():
            item = QListWidgetItem(s.name)
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            item.setForeground(QColor(s.color))
            self.list.addItem(item)

            if s.id == keep:
                self.list.setCurrentItem(item)

        self.list.blockSignals(False)

    def _load_subject(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            self._clear_subject_details()
            return

        self._set_subject_title()
        self._load_learning_events(sid)
        self._load_memory(sid)

    def _clear_subject_details(self) -> None:
        self.title.setText("Bir ders seçin")
        self.events.setRowCount(0)
        self.memory.setRowCount(0)

    def _set_subject_title(self) -> None:
        self.title.setText(self.list.currentItem().text())

    def _load_learning_events(self, sid: int) -> None:
        events = self.service.list_learning_events(sid)
        self.events.setRowCount(len(events))

        for r, v in enumerate(events):
            e = v.event
            period = "-" if e.period_start is None else f"{e.period_start}. ders"
            set_row(
                self.events,
                r,
                [fmt_date(e.event_date), period, v.topic_name, e.notes],
                e.id
            )

    def _load_memory(self, sid: int) -> None:
        mem = self.service.list_memory(sid)
        self.memory.setRowCount(len(mem))

        for r, m in enumerate(mem):
            st = m.state
            set_row(
                self.memory,
                r,
                [
                    m.topic_name,
                    st.phase.value,
                    f"{st.stability_days:.1f}",
                    f"{st.difficulty:.2f}",
                    fmt_date(st.last_review_date),
                    fmt_date(st.next_review_date),
                    str(st.review_count)
                ]
            )

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "Yeni ders", "Ders adı:")
        if ok:
            self._add_subject(name)
            self.refresh()

    def _add_subject(self, name: str) -> None:
        try:
            self.service.add_subject(name)
        except Exception as exc:
            show_error(
                self,
                ValueError(f"Ders eklenemedi (aynı isimde ders olabilir): {exc}")
            )

    def _rename(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            return

        name, ok = QInputDialog.getText(
            self,
            "Dersi düzenle",
            "Ders adı:",
            text=self.list.currentItem().text()
        )
        if ok:
            self._rename_subject(sid, name)
            self.refresh()

    def _rename_subject(self, sid: int, name: str) -> None:
        try:
            self.service.rename_subject(sid, name)
        except Exception as exc:
            show_error(self, ValueError(str(exc)))

    def _delete(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            return

        if self._confirm_subject_delete():
            self.service.delete_subject(sid)
            self.refresh()

    def _confirm_subject_delete(self) -> bool:
        return (
            QMessageBox.question(
                self,
                "Dersi sil",
                "Dersin tüm konuları, öğrenme kayıtları ve tekrar görevleri "
                "silinecek. Emin misiniz?"
            )
            == QMessageBox.StandardButton.Yes
        )

    def _delete_event(self) -> None:
        key = selected_key(self.events)
        if key is not None:
            self.service.delete_learning_event(key)
            self._load_subject()


class TasksView(QWidget):
    """Görevleri listeleme ve yönetme sekmesi."""

    FILTERS = [
        ("Tümü", "all"),
        ("Tekrar", "review"),
        ("Teslim görevi", "deadline"),
        ("Tekrarlayan", "recurring"),
        ("Gecikmiş", "overdue"),
        ("Tamamlanan", "completed")
    ]

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self._tasks: dict[int, Task] = {}

        root = self._create_root_layout()
        self._setup_toolbar(root)
        self._setup_task_split(root)
        root.addWidget(self._split, 1)
        self.refresh()

    def _create_root_layout(self) -> QVBoxLayout:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_TOP,
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_BOTTOM
        )
        return root

    def _setup_toolbar(self, root: QVBoxLayout) -> None:
        bar = QHBoxLayout()

        self.filter = QComboBox()
        for label, key in self.FILTERS:
            self.filter.addItem(label, key)

        self.filter.currentIndexChanged.connect(lambda *_: self.refresh())

        new_b = QPushButton("Yeni görev ▾")
        menu = QMenu(new_b)
        menu.addAction("Teslim görevi…", lambda: self._new("deadline"))
        menu.addAction("Tekrarlayan görev…", lambda: self._new("recurring"))
        menu.addAction("Manuel tekrar…", lambda: self._new("review"))
        new_b.setMenu(menu)

        bar.addWidget(QLabel("Filtre:"))
        bar.addWidget(self.filter)
        bar.addStretch(1)
        bar.addWidget(new_b)

        root.addLayout(bar)

    def _setup_task_split(self, root: QVBoxLayout) -> None:
        self._split = QSplitter(Qt.Orientation.Horizontal)
        self._setup_task_table()
        self._setup_task_detail()

        self._split.addWidget(self.table)
        self._split.addWidget(self._detail)
        self._split.setSizes([700, 320])

    def _setup_task_table(self) -> None:
        self.table = make_table([
            "Başlık", "Tür", "Kalan / süre", "Son tarih / ideal",
            "Öncelik", "Durum"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._show_detail)

    def _setup_task_detail(self) -> None:
        self._detail = QGroupBox("Görev detayı")
        self.form = QFormLayout(self._detail)

        self.fields = {
            k: QLabel("-")
            for k in (
                "title", "type", "duration", "remaining", "priority",
                "deadline", "ideal", "topics", "tags", "status"
            )
        }

        self._add_detail_fields()
        self._add_detail_actions()

    def _add_detail_fields(self) -> None:
        for key, label in (
            ("title", "Başlık"),
            ("type", "Tür"),
            ("duration", "Süre"),
            ("remaining", "Kalan süre"),
            ("priority", "Öncelik"),
            ("deadline", "Son tarih"),
            ("ideal", "İdeal tekrar tarihi"),
            ("topics", "Konular"),
            ("tags", "Etiketler"),
            ("status", "Durum")
        ):
            self.fields[key].setWordWrap(True)
            self.form.addRow(label, self.fields[key])

    def _add_detail_actions(self) -> None:
        cancel_b = QPushButton("Görevi iptal et")
        delete_b = QPushButton("Görevi sil")

        cancel_b.clicked.connect(self._cancel)
        delete_b.clicked.connect(self._delete)

        self.form.addRow(cancel_b)
        self.form.addRow(delete_b)

    def refresh(self) -> None:
        tasks = self._load_tasks()
        self._tasks = {t.id: t for t in tasks if t.id is not None}
        self._fill_task_table(tasks)
        self._show_detail()

    def _load_tasks(self) -> list[Task]:
        return self.service.list_tasks(self.filter.currentData(), date.today())

    def _fill_task_table(self, tasks: list[Task]) -> None:
        self.table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            self._fill_task_row(r, t)

    def _fill_task_row(self, row: int, task: Task) -> None:
        overdue = task.is_overdue(date.today())
        when = self._task_when(task)

        set_row(
            self.table,
            row,
            [
                task.title,
                CLASS_LABEL[task.task_class],
                f"{task.remaining_duration}/{task.duration} dk",
                when,
                str(task.priority),
                "Gecikmiş" if overdue else STATUS_LABEL[task.status]
            ],
            task.id
        )

        if overdue:
            self._mark_overdue_row(row)

    def _task_when(self, task: Task) -> str:
        if task.deadline:
            return fmt_date(task.deadline)
        if task.ideal_date:
            return fmt_date(task.ideal_date)
        if task.recurring_rule:
            return task.recurring_rule.describe()
        return "-"

    def _mark_overdue_row(self, row: int) -> None:
        for c in range(self.table.columnCount()):
            self.table.item(row, c).setForeground(QColor("#D32F2F"))

    def _show_detail(self) -> None:
        key = selected_key(self.table)
        t = self._tasks.get(key) if key is not None else None

        if t is None:
            self._clear_detail()
            return

        self._show_basic_detail(t)
        self._show_date_detail(t)
        self._show_extra_detail(t)
        self._show_status_detail(t)

    def _clear_detail(self) -> None:
        for lab in self.fields.values():
            lab.setText("-")

    def _show_basic_detail(self, task: Task) -> None:
        f = self.fields
        f["title"].setText(task.title)
        f["type"].setText(
            CLASS_LABEL[task.task_class]
            + (f" ({task.review_source.value.lower()})" if task.review_source else "")
        )
        f["duration"].setText(
            f"{task.duration} dk"
            + (f"  (bölünebilir, min {task.minimum_session} dk)" if task.splittable else "")
        )
        f["remaining"].setText(f"{task.remaining_duration} dk")
        f["priority"].setText(str(task.priority))

    def _show_date_detail(self, task: Task) -> None:
        f = self.fields
        f["deadline"].setText(fmt_date(task.deadline))

        ideal = fmt_date(task.ideal_date)
        if task.earliest_date and task.latest_date:
            ideal += f"  (pencere: {fmt_date(task.earliest_date)} – {fmt_date(task.latest_date)})"

        f["ideal"].setText(ideal if task.ideal_date else "-")

    def _show_extra_detail(self, task: Task) -> None:
        f = self.fields
        f["topics"].setText(", ".join(self.service.topic_labels(task.topic_ids)) or "-")
        f["tags"].setText(", ".join(task.tags) or "-")

    def _show_status_detail(self, task: Task) -> None:
        self.fields["status"].setText(
            "Gecikmiş" if task.is_overdue(date.today()) else STATUS_LABEL[task.status]
        )

    def _new(self, mode: str) -> None:
        if TaskDialog(self.service, mode, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _cancel(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.cancel_task(key)
            self.refresh()

    def _delete(self) -> None:
        key = selected_key(self.table)
        if (
            key is not None
            and QMessageBox.question(
                self,
                "Sil",
                "Görev kalıcı olarak silinsin mi?"
            ) == QMessageBox.StandardButton.Yes
        ):
            self.service.delete_task(key)
            self.refresh()