"""views.py - Yeni sol sidebar ile entegre Dersler ve Görevler detay görünümleri."""
from __future__ import annotations

from datetime import date
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QMenu, QMessageBox, QPushButton, QSplitter,
    QVBoxLayout, QWidget
)

from dialogs import TaskDialog
from engine import PlannerService, Task
from ui_common import (
    CLASS_LABEL, STATUS_LABEL, fmt_date, make_table,
    selected_key, set_row, show_error
)


class SubjectsView(QWidget):
    """Genişletilmiş sol sidebar ile çalışan ders detay görünümü."""

    subject_changed = Signal()

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._current_sid: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Üst Başlık ve İşlemler
        head = QHBoxLayout()
        self.title = QLabel("Bir ders seçin")
        self.title.setStyleSheet("font-size: 20px; font-weight: 700; color: #17181C;")
        head.addWidget(self.title)
        head.addStretch(1)

        btn_rename = QPushButton("Dersi Düzenle")
        btn_rename.clicked.connect(self._rename)
        btn_delete = QPushButton("Dersi Sil")
        btn_delete.clicked.connect(self._delete)
        head.addWidget(btn_rename)
        head.addWidget(btn_delete)
        layout.addLayout(head)

        # Öğrenme Geçmişi
        hist_head = QHBoxLayout()
        hist_head.addWidget(QLabel("<b>Öğrenme Geçmişi (Kronolojik)</b>"))
        hist_head.addStretch(1)
        btn_del_event = QPushButton("Seçili Kaydı Sil")
        btn_del_event.clicked.connect(self._delete_event)
        hist_head.addWidget(btn_del_event)
        layout.addLayout(hist_head)

        self.events = make_table(["Tarih", "Haftalık Ders Sırası", "Konu", "Not"])
        layout.addWidget(self.events, 3)

        # Hafıza Durumu
        layout.addWidget(QLabel("<b>Konu Hafıza Durumu (Bir sonraki ideal tekrar)</b>"))
        self.memory = make_table([
            "Konu", "Aşama", "Stabilite (gün)", "Zorluk",
            "Son Çalışma", "İdeal Tekrar", "Tekrar Sayısı"
        ])
        layout.addWidget(self.memory, 2)

    @property
    def current_sid(self) -> int | None:
        return self._current_sid

    def select_subject(self, sid: int) -> None:
        """Sol sidebardan bir ders seçildiğinde çağrılır."""
        self._current_sid = sid
        self.refresh()

    def refresh(self) -> None:
        subjects = self.service.list_subjects()
        if not subjects:
            self.title.setText("Henüz ders eklenmemiş")
            self.events.setRowCount(0)
            self.memory.setRowCount(0)
            self._current_sid = None
            return

        if self._current_sid is None or not any(s.id == self._current_sid for s in subjects):
            self._current_sid = subjects[0].id

        subject = next((s for s in subjects if s.id == self._current_sid), None)
        if subject:
            self.title.setText(subject.name)
            self._load_learning_events(subject.id)
            self._load_memory(subject.id)

    def _load_learning_events(self, sid: int) -> None:
        events = self.service.list_learning_events(sid)
        self.events.setRowCount(len(events))
        for r, v in enumerate(events):
            e = v.event
            period = "-" if e.period_start is None else f"{e.period_start}. ders"
            set_row(self.events, r, [fmt_date(e.event_date), period, v.topic_name, e.notes], e.id)

    def _load_memory(self, sid: int) -> None:
        mem = self.service.list_memory(sid)
        self.memory.setRowCount(len(mem))
        for r, m in enumerate(mem):
            st = m.state
            set_row(
                self.memory, r,
                [
                    m.topic_name, st.phase.value, f"{st.stability_days:.1f}",
                    f"{st.difficulty:.2f}", fmt_date(st.last_review_date),
                    fmt_date(st.next_review_date), str(st.review_count)
                ]
            )

    def _rename(self) -> None:
        if self._current_sid is None:
            return
        name, ok = QInputDialog.getText(self, "Dersi Düzenle", "Yeni ders adı:", text=self.title.text())
        if ok and name.strip():
            self.service.rename_subject(self._current_sid, name.strip())
            self.refresh()
            self.subject_changed.emit()

    def _delete(self) -> None:
        if self._current_sid is None:
            return
        if QMessageBox.question(self, "Dersi Sil", "Ders ve tüm kayıtları silinecek. Emin misiniz?") == QMessageBox.StandardButton.Yes:
            self.service.delete_subject(self._current_sid)
            self._current_sid = None
            self.refresh()
            self.subject_changed.emit()

    def _delete_event(self) -> None:
        key = selected_key(self.events)
        if key is not None:
            self.service.delete_learning_event(key)
            if self._current_sid:
                self._load_learning_events(self._current_sid)


class TasksView(QWidget):
    """Genişletilmiş sol sidebar ile filtrelenen Görevler sekmesi."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._current_filter = "all"
        self._tasks: dict[int, Task] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Üst Araç Çubuğu
        top = QHBoxLayout()
        lbl_head = QLabel("Görev Listesi")
        lbl_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #17181C;")
        top.addWidget(lbl_head)
        top.addStretch(1)

        btn_new = QPushButton("Yeni Görev +")
        btn_new.setProperty("primary", True)
        menu = QMenu(btn_new)
        menu.addAction("Teslim Görevi…", lambda: self._new("deadline"))
        menu.addAction("Tekrarlayan Görev…", lambda: self._new("recurring"))
        menu.addAction("Manuel Tekrar…", lambda: self._new("review"))
        btn_new.setMenu(menu)
        top.addWidget(btn_new)
        root.addLayout(top)

        # Tablo & Detay Ayrımı
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = make_table(["Başlık", "Tür", "Kalan / Süre", "Son Tarih / İdeal", "Öncelik", "Durum"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.table)

        self._detail = QGroupBox("Görev Detayı")
        form = QVBoxLayout(self._detail)
        self.fields = {k: QLabel("-") for k in ("title", "type", "duration", "remaining", "priority", "deadline", "ideal", "status")}
        for k, lbl in self.fields.items():
            form.addWidget(QLabel(f"<b>{k.capitalize()}:</b>"))
            form.addWidget(lbl)

        btn_cancel = QPushButton("Görevi İptal Et")
        btn_delete = QPushButton("Görevi Sil")
        btn_cancel.clicked.connect(self._cancel)
        btn_delete.clicked.connect(self._delete)
        form.addWidget(btn_cancel)
        form.addWidget(btn_delete)
        form.addStretch(1)

        split.addWidget(self._detail)
        split.setSizes([650, 300])
        root.addWidget(split, 1)

        self.refresh()

    def set_filter(self, filter_key: str) -> None:
        """Sol sidebardaki filtre seçildiğinde çağrılır."""
        self._current_filter = filter_key
        self.refresh()

    def refresh(self) -> None:
        tasks = self.service.list_tasks(self._current_filter, date.today())
        self._tasks = {t.id: t for t in tasks if t.id is not None}
        self.table.setRowCount(len(tasks))

        for r, t in enumerate(tasks):
            overdue = t.is_overdue(date.today())
            when = fmt_date(t.deadline) if t.deadline else fmt_date(t.ideal_date) if t.ideal_date else "-"
            set_row(
                self.table, r,
                [
                    t.title, CLASS_LABEL[t.task_class],
                    f"{t.remaining_duration}/{t.duration} dk", when,
                    str(t.priority), "Gecikmiş" if overdue else STATUS_LABEL[t.status]
                ],
                t.id
            )
            if overdue:
                for c in range(self.table.columnCount()):
                    self.table.item(r, c).setForeground(QColor("#D32F2F"))

    def _show_detail(self) -> None:
        key = selected_key(self.table)
        t = self._tasks.get(key) if key is not None else None
        if not t:
            for l in self.fields.values():
                l.setText("-")
            return

        self.fields["title"].setText(t.title)
        self.fields["type"].setText(CLASS_LABEL[t.task_class])
        self.fields["duration"].setText(f"{t.duration} dk")
        self.fields["remaining"].setText(f"{t.remaining_duration} dk")
        self.fields["priority"].setText(str(t.priority))
        self.fields["deadline"].setText(fmt_date(t.deadline) if t.deadline else "-")
        self.fields["ideal"].setText(fmt_date(t.ideal_date) if t.ideal_date else "-")
        self.fields["status"].setText("Gecikmiş" if t.is_overdue(date.today()) else STATUS_LABEL[t.status])

    def _new(self, mode: str) -> None:
        if TaskDialog(self.service, mode, self).exec():
            self.refresh()

    def _cancel(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.cancel_task(key)
            self.refresh()

    def _delete(self) -> None:
        key = selected_key(self.table)
        if key is not None and QMessageBox.question(self, "Sil", "Görev silinsin mi?") == QMessageBox.StandardButton.Yes:
            self.service.delete_task(key)
            self.refresh()