"""ui.py - PySide6 user interface.

Only user input, service calls and result display live here.  No SQL, no memory
formulas and no scheduling logic: everything goes through engine.PlannerService.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTime, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QTimeEdit, QVBoxLayout, QWidget
)

from engine import (
    AvailabilityBlock, AvailabilityType, PlannerService, RecallResult, RecurrenceKind,
    RecurringRule, SchedulePlan, SchoolLesson, SessionView, Task, TaskClass, TaskStatus
)
from ui2 import CALENDAR_BOTTOM_PADDING


# ================================================================== UI STYLE

MAIN_MARGIN_H = 18
MAIN_MARGIN_TOP = 12
MAIN_MARGIN_BOTTOM = 18

TAB_CONTENT_GAP = 12
TAB_CONTENT_MARGIN_H = 8
TAB_CONTENT_MARGIN_TOP = 6
TAB_CONTENT_MARGIN_BOTTOM = 8

TAB_BAR_TOP_PADDING = 8
TAB_BAR_BOTTOM_PADDING = 8
TAB_BAR_SIDE_PADDING = 4
TAB_HORIZONTAL_PADDING = 20
TAB_VERTICAL_PADDING = 9
TAB_RADIUS = 8

BUTTON_RADIUS = 5
INPUT_RADIUS = 6
GROUP_RADIUS = 8
TABLE_RADIUS = 7

CALENDAR_BOTTOM_PADDING = 5


UI_STYLESHEET = f"""
QMainWindow {{
    background: palette(window);
}}

QTabWidget {{
    background: transparent;
}}

QTabWidget::pane {{
    border: 1px solid palette(mid);
    border-radius: {GROUP_RADIUS}px;
    background: palette(base);
    margin-top: {TAB_CONTENT_GAP}px;
}}

QTabBar {{
    background: transparent;
    padding-top: {TAB_BAR_TOP_PADDING}px;
    padding-bottom: {TAB_BAR_BOTTOM_PADDING}px;
    padding-left: {TAB_BAR_SIDE_PADDING}px;
    padding-right: {TAB_BAR_SIDE_PADDING}px;
}}

QTabBar::tab {{
    padding: {TAB_VERTICAL_PADDING}px {TAB_HORIZONTAL_PADDING}px;
    margin-left: 2px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-radius: {TAB_RADIUS}px;
    background: transparent;
    color: palette(text);
}}

QTabBar::tab:hover {{
    background: palette(alternate-base);
}}

QTabBar::tab:selected {{
    background: palette(highlight);
    color: palette(highlighted-text);
    border-color: palette(highlight);
}}

QPushButton {{
    border: 1px solid palette(mid);
    border-radius: {BUTTON_RADIUS}px;
    padding: 7px 13px;
}}

QPushButton:hover {{
    background: palette(alternate-base);
}}

QPushButton:pressed {{
    background: palette(midlight);
}}

QLineEdit,
QComboBox,
QSpinBox,
QDateEdit,
QTimeEdit {{
    border: 1px solid palette(mid);
    border-radius: {INPUT_RADIUS}px;
    padding: 5px 7px;
    min-height: 24px;
}}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDateEdit:focus,
QTimeEdit:focus {{
    border: 1px solid palette(highlight);
}}

QGroupBox {{
    border: 1px solid palette(mid);
    border-radius: {GROUP_RADIUS}px;
    margin-top: 10px;
    padding: 10px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

QTableWidget {{
    border: 1px solid palette(mid);
    border-radius: {TABLE_RADIUS}px;
    gridline-color: palette(midlight);
    background: palette(base);
}}

QTableWidget::item {{
    padding: 5px;
}}

QTableWidget::item:selected {{
    background: palette(highlight);
    color: palette(highlighted-text);
}}

QListWidget {{
    border: 1px solid palette(mid);
    border-radius: {TABLE_RADIUS}px;
}}

QTextEdit {{
    border: 1px solid palette(mid);
    border-radius: {TABLE_RADIUS}px;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}
"""

MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]

WEEKDAYS = [
    "Pazartesi", "Salı", "Çarşamba", "Perşembe",
    "Cuma", "Cumartesi", "Pazar"
]

CLASS_LABEL = {
    TaskClass.REVIEW: "Tekrar",
    TaskClass.DEADLINE_TASK: "Teslim görevi",
    TaskClass.RECURRING_TASK: "Tekrarlayan"
}

CLASS_COLOR = {
    TaskClass.REVIEW: "#7E57C2",
    TaskClass.DEADLINE_TASK: "#EF6C00",
    TaskClass.RECURRING_TASK: "#00897B"
}

STATUS_LABEL = {
    TaskStatus.PENDING: "Bekliyor",
    TaskStatus.COMPLETED: "Tamamlandı",
    TaskStatus.CANCELLED: "İptal",
    TaskStatus.MISSED: "Kaçırıldı"
}

AVAIL_LABEL = {
    AvailabilityType.PRIMARY: "Birincil (PRIMARY)",
    AvailabilityType.RESERVE: "Yedek (RESERVE)",
    AvailabilityType.UNAVAILABLE: "Kullanılamaz"
}


# ----------------------------------------------------------------- helpers

def fmt_date(d: date | None) -> str:
    return "-" if d is None else f"{d.day} {MONTHS[d.month - 1]}"


def to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def to_qtime(t: time) -> QTime:
    return QTime(t.hour, t.minute)


def make_date_edit(d: date) -> QDateEdit:
    w = QDateEdit(to_qdate(d))
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd.MM.yyyy")
    return w


def make_time_edit(t: time) -> QTimeEdit:
    w = QTimeEdit(to_qtime(t))
    w.setDisplayFormat("HH:mm")
    return w


def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    return t


def set_row(
    table: QTableWidget,
    row: int,
    values: list[str],
    key: int | None = None
) -> None:
    for col, text in enumerate(values):
        item = QTableWidgetItem(text)
        if col == 0 and key is not None:
            item.setData(Qt.ItemDataRole.UserRole, key)
        table.setItem(row, col, item)


def selected_key(table: QTableWidget) -> int | None:
    rows = table.selectionModel().selectedRows()
    if not rows:
        return None
    item = table.item(rows[0].row(), 0)
    return None if item is None else item.data(Qt.ItemDataRole.UserRole)


def show_error(parent: QWidget, exc: Exception) -> None:
    QMessageBox.warning(parent, "Hata", str(exc))


def buttons(dialog: QDialog, ok_text: str = "Kaydet") -> QDialogButtonBox:
    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel
    )
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


# ================================================================ dialogs

class LearningEventDialog(QDialog):
    """Record the topic taught in a dated lesson from the weekly timetable."""

    def __init__(
        self,
        service: PlannerService,
        lesson: SchoolLesson,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._setup_window(service, lesson)
        self._setup_form()
        self._setup_fields(lesson)
        self._setup_buttons()

    def _setup_window(self, service: PlannerService, lesson: SchoolLesson) -> None:
        self.setWindowTitle("Derste işlenen konuyu kaydet")
        self.service, self.lesson = service, lesson

    def _setup_form(self) -> None:
        self._form = QFormLayout(self)

    def _setup_fields(self, lesson: SchoolLesson) -> None:
        self._setup_labels(lesson)
        self._setup_topic(lesson)
        self._setup_notes()
        self._add_field_rows()

    def _setup_labels(self, lesson: SchoolLesson) -> None:
        self.date_label = QLabel(fmt_date(lesson.lesson_date))
        self.subject_label = QLabel(lesson.subject_name)
        self.ordinal_label = QLabel(
            f"Bu haftaki {lesson.subject_lesson_no}. {lesson.subject_name} dersi"
        )

    def _setup_topic(self, lesson: SchoolLesson) -> None:
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self.topic.addItems(
            [t.name for t in self.service.list_topics(lesson.subject_id)]
        )
        self.topic.setCurrentText("")

    def _setup_notes(self) -> None:
        self.notes = QLineEdit()

    def _add_field_rows(self) -> None:
        self._form.addRow("Tarih", self.date_label)
        self._form.addRow("Ders", self.subject_label)
        self._form.addRow("Haftalık sıra", self.ordinal_label)
        self._form.addRow("Konu (seç ya da yeni yaz)", self.topic)
        self._form.addRow("Not", self.notes)

    def _setup_buttons(self) -> None:
        self._form.addRow(buttons(self))

    def accept(self) -> None:
        try:
            self.service.add_learning_event(
                self.lesson.subject_id,
                self.lesson.lesson_date,
                self.topic.currentText(),
                self.lesson.subject_lesson_no,
                notes=self.notes.text()
            )
        except ValueError as exc:
            show_error(self, exc)
            return

        super().accept()


class TaskDialog(QDialog):
    """Create a deadline task, a recurring task or a manual review."""

    def __init__(
        self,
        service: PlannerService,
        mode: str,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service, self.mode = service, mode
        self._setup_window()
        form = self._create_form()
        self._setup_common_fields(form)
        self._setup_mode_fields(form)
        self._setup_buttons(form)

    def _setup_window(self) -> None:
        self.setWindowTitle({
            "deadline": "Yeni teslim görevi",
            "recurring": "Yeni tekrarlayan görev",
            "review": "Yeni manuel tekrar"
        }[self.mode])

    def _create_form(self) -> QFormLayout:
        return QFormLayout(self)

    def _setup_common_fields(self, form: QFormLayout) -> None:
        self.title = QLineEdit()

        self.duration = QSpinBox()
        self.duration.setRange(1, 1440)
        self.duration.setValue(60)
        self.duration.setSuffix(" dk")

        self.priority = QSpinBox()
        self.priority.setRange(1, 10)
        self.priority.setValue(5)

        self.tags = QLineEdit()
        self.tags.setPlaceholderText("#TYT, #Okul")

        form.addRow("Başlık", self.title)
        form.addRow("Süre", self.duration)
        form.addRow("Öncelik (1-10)", self.priority)
        form.addRow("Etiketler", self.tags)

    def _setup_mode_fields(self, form: QFormLayout) -> None:
        if self.mode == "deadline":
            self._setup_deadline_fields(form)
        elif self.mode == "recurring":
            self._setup_recurring_fields(form)
        else:
            self._setup_review_fields(form)

    def _setup_deadline_fields(self, form: QFormLayout) -> None:
        self.deadline = make_date_edit(date.today() + timedelta(days=7))

        self.splittable = QCheckBox("Bölünebilir")
        self.splittable.setChecked(True)

        self.min_session = QSpinBox()
        self.min_session.setRange(5, 240)
        self.min_session.setValue(30)
        self.min_session.setSuffix(" dk")

        form.addRow("Son tarih", self.deadline)
        form.addRow(self.splittable)
        form.addRow("Minimum oturum", self.min_session)

    def _setup_recurring_fields(self, form: QFormLayout) -> None:
        self.rule = QComboBox()
        self.rule.addItems([
            "Her gün",
            "Seçili günler",
            "Haftada N gün"
        ])

        self.days = [QCheckBox(n[:3]) for n in WEEKDAYS]
        day_row = QHBoxLayout()

        for cb in self.days:
            day_row.addWidget(cb)

        self.times = QSpinBox()
        self.times.setRange(1, 7)
        self.times.setValue(3)

        form.addRow("Sıklık", self.rule)
        form.addRow("Günler", day_row)
        form.addRow("Haftada kaç gün", self.times)

    def _setup_review_fields(self, form: QFormLayout) -> None:
        self.ideal = make_date_edit(date.today() + timedelta(days=1))

        self.topics = QListWidget()
        self.topics.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )

        for subj in self.service.list_subjects():
            for t in self.service.list_topics(subj.id):
                item = QListWidgetItem(f"{subj.name} / {t.name}")
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self.topics.addItem(item)

        form.addRow("İdeal tarih", self.ideal)
        form.addRow("Konular (birden fazla seçilebilir)", self.topics)

    def _setup_buttons(self, form: QFormLayout) -> None:
        form.addRow(buttons(self))

    def _tags(self) -> list[str]:
        return [
            t.strip()
            for t in self.tags.text().split(",")
            if t.strip()
        ]

    def accept(self) -> None:
        try:
            if self.mode == "deadline":
                self._accept_deadline()
            elif self.mode == "recurring":
                self._accept_recurring()
            else:
                self._accept_review()
        except ValueError as exc:
            show_error(self, exc)
            return

        super().accept()

    def _accept_deadline(self) -> None:
        self.service.add_deadline_task(
            title=self.title.text(),
            duration=self.duration.value(),
            deadline=self.deadline.date().toPython(),
            priority=self.priority.value(),
            splittable=self.splittable.isChecked(),
            minimum_session=(
                self.min_session.value()
                if self.splittable.isChecked()
                else None
            ),
            tags=self._tags()
        )

    def _accept_recurring(self) -> None:
        idx = self.rule.currentIndex()
        chosen = tuple(
            i for i, cb in enumerate(self.days)
            if cb.isChecked()
        )

        rule = (
            RecurringRule(RecurrenceKind.DAILY)
            if idx == 0 else
            RecurringRule(
                RecurrenceKind.WEEKDAYS,
                weekdays=chosen
            )
            if idx == 1 else
            RecurringRule(
                RecurrenceKind.TIMES_PER_WEEK,
                times_per_week=self.times.value()
            )
        )

        self.service.add_recurring_task(
            title=self.title.text(),
            duration=self.duration.value(),
            rule=rule,
            priority=self.priority.value(),
            tags=self._tags()
        )

    def _accept_review(self) -> None:
        ids = [
            it.data(Qt.ItemDataRole.UserRole)
            for it in self.topics.selectedItems()
        ]

        self.service.add_manual_review(
            title=self.title.text() or "Manuel tekrar",
            topic_ids=ids,
            ideal_date=self.ideal.date().toPython(),
            duration=self.duration.value(),
            priority=self.priority.value(),
            tags=self._tags()
        )


class AvailabilityDialog(QDialog):
    """Add PRIMARY / RESERVE / UNAVAILABLE blocks for a date range and chosen weekdays."""

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self._setup_window()
        root = self._create_layout()
        self._setup_form(root)
        self._setup_table(root)
        self._setup_delete_button(root)
        self._reload()

    def _setup_window(self) -> None:
        self.setWindowTitle("Çalışma zamanları (müsaitlik)")
        self.resize(640, 560)

    def _create_layout(self) -> QVBoxLayout:
        return QVBoxLayout(self)

    def _setup_form(self, root: QVBoxLayout) -> None:
        box = QGroupBox("Blok ekle")
        form = QFormLayout(box)

        self._setup_dates(form)
        self._setup_days(form)
        self._setup_times(form)
        self._setup_kind(form)
        self._setup_add_button(form)

        root.addWidget(box)

    def _setup_dates(self, form: QFormLayout) -> None:
        self.start_date = make_date_edit(date.today())
        self.end_date = make_date_edit(date.today() + timedelta(days=13))
        form.addRow("Başlangıç tarihi", self.start_date)
        form.addRow("Bitiş tarihi", self.end_date)

    def _setup_days(self, form: QFormLayout) -> None:
        self.days = [QCheckBox(n[:3]) for n in WEEKDAYS]
        day_row = QHBoxLayout()

        for cb in self.days:
            cb.setChecked(True)
            day_row.addWidget(cb)

        form.addRow("Günler", day_row)

    def _setup_times(self, form: QFormLayout) -> None:
        self.start_time = make_time_edit(time(17, 0))
        self.end_time = make_time_edit(time(22, 0))
        form.addRow("Saat (başlangıç)", self.start_time)
        form.addRow("Saat (bitiş)", self.end_time)

    def _setup_kind(self, form: QFormLayout) -> None:
        self.kind = QComboBox()
        for k in AvailabilityType:
            self.kind.addItem(AVAIL_LABEL[k], k)
        form.addRow("Tür", self.kind)

    def _setup_add_button(self, form: QFormLayout) -> None:
        add = QPushButton("Ekle")
        add.clicked.connect(self._add)
        form.addRow(add)

    def _setup_table(self, root: QVBoxLayout) -> None:
        self.table = make_table([
            "Tarih", "Başlangıç", "Bitiş", "Tür"
        ])
        root.addWidget(self.table)

    def _setup_delete_button(self, root: QVBoxLayout) -> None:
        delete = QPushButton("Seçili bloğu sil")
        delete.clicked.connect(self._delete)
        root.addWidget(delete)

    def _reload(self) -> None:
        blocks = self.service.list_availability(
            date.today(),
            date.today() + timedelta(days=27)
        )

        self.table.setRowCount(len(blocks))

        for r, b in enumerate(blocks):
            set_row(
                self.table,
                r,
                [
                    f"{fmt_date(b.block_date)} "
                    f"{WEEKDAYS[b.block_date.weekday()][:3]}",
                    b.start_time.strftime("%H:%M"),
                    b.end_time.strftime("%H:%M"),
                    AVAIL_LABEL[b.block_type]
                ],
                b.id
            )

    def _add(self) -> None:
        try:
            n = self.service.add_availability_range(
                self.start_date.date().toPython(),
                self.end_date.date().toPython(),
                [
                    i for i, cb in enumerate(self.days)
                    if cb.isChecked()
                ],
                self.start_time.time().toPython(),
                self.end_time.time().toPython(),
                self.kind.currentData()
            )

        except ValueError as exc:
            show_error(self, exc)
            return

        self._reload()

        if n == 0:
            QMessageBox.information(
                self,
                "Bilgi",
                "Seçilen aralıkta uygun gün bulunamadı."
            )

    def _delete(self) -> None:
        key = selected_key(self.table)

        if key is not None:
            self.service.delete_availability(key)
            self._reload()


class TimetableDialog(QDialog):
    """Weekly school timetable (kept separate from LearningEvents)."""

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Okul ders programı")
        self.resize(560, 520)
        self.service = service

        root = QVBoxLayout(self)
        self._setup_form(root)
        self._setup_table(root)
        self._setup_delete_button(root)
        self._reload()

    def _setup_form(self, root: QVBoxLayout) -> None:
        form = QFormLayout()
        self._setup_schedule_fields(form)
        self._setup_subject_field(form)
        self._setup_schedule_button(form)
        root.addLayout(form)

    def _setup_schedule_fields(self, form: QFormLayout) -> None:
        self.weekday = QComboBox()
        self.weekday.addItems(WEEKDAYS)

        self.period = QSpinBox()
        self.period.setRange(1, 14)

        self.start_time = make_time_edit(time(8, 30))
        self.end_time = make_time_edit(time(9, 10))

        form.addRow("Gün", self.weekday)
        form.addRow("Ders saati no", self.period)
        form.addRow("Başlangıç", self.start_time)
        form.addRow("Bitiş", self.end_time)

    def _setup_subject_field(self, form: QFormLayout) -> None:
        self.subject = QComboBox()
        for s in self.service.list_subjects():
            self.subject.addItem(s.name, s.id)
        form.addRow("Ders", self.subject)

    def _setup_schedule_button(self, form: QFormLayout) -> None:
        add = QPushButton("Ekle / güncelle")
        add.clicked.connect(self._add)
        form.addRow(add)

    def _setup_table(self, root: QVBoxLayout) -> None:
        self.table = make_table([
            "Gün", "Saat no", "Başlangıç", "Bitiş", "Ders"
        ])
        root.addWidget(self.table)

    def _setup_delete_button(self, root: QVBoxLayout) -> None:
        delete = QPushButton("Seçiliyi sil")
        delete.clicked.connect(self._delete)
        root.addWidget(delete)

    def _reload(self) -> None:
        names = {
            s.id: s.name
            for s in self.service.list_subjects()
        }

        entries = self.service.list_timetable()
        self.table.setRowCount(len(entries))

        for r, e in enumerate(entries):
            set_row(
                self.table,
                r,
                [
                    WEEKDAYS[e.weekday],
                    str(e.period_no),
                    e.start_time.strftime("%H:%M"),
                    e.end_time.strftime("%H:%M"),
                    names.get(e.subject_id, "?")
                ],
                e.id
            )

    def _add(self) -> None:
        if self.subject.currentData() is None:
            QMessageBox.information(
                self,
                "Bilgi",
                "Önce Dersler sekmesinden ders ekleyin."
            )
            return

        self.service.set_timetable_entry(
            self.weekday.currentIndex(),
            self.period.value(),
            self.start_time.time().toPython(),
            self.end_time.time().toPython(),
            self.subject.currentData()
        )

        self._reload()

    def _delete(self) -> None:
        key = selected_key(self.table)

        if key is not None:
            self.service.delete_timetable_entry(key)
            self._reload()


class ExamDialog(QDialog):

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sınavlar")
        self.resize(600, 560)
        self.service = service

        root = QVBoxLayout(self)
        self._setup_form(root)
        self._setup_table(root)
        self._setup_delete_button(root)
        self._reload()

    def _setup_form(self, root: QVBoxLayout) -> None:
        form = QFormLayout()
        self._setup_exam_fields(form)
        self._setup_exam_topics(form)
        self._setup_exam_button(form)
        root.addLayout(form)

    def _setup_exam_fields(self, form: QFormLayout) -> None:
        self.title = QLineEdit()
        self.date = make_date_edit(date.today() + timedelta(days=14))
        form.addRow("Başlık", self.title)
        form.addRow("Tarih", self.date)

    def _setup_exam_topics(self, form: QFormLayout) -> None:
        self.topics = QListWidget()
        self.topics.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )

        for subj in self.service.list_subjects():
            for t in self.service.list_topics(subj.id):
                item = QListWidgetItem(f"{subj.name} / {t.name}")
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self.topics.addItem(item)

        form.addRow("Kapsadığı konular", self.topics)

    def _setup_exam_button(self, form: QFormLayout) -> None:
        add = QPushButton("Sınav ekle")
        add.clicked.connect(self._add)
        form.addRow(add)

    def _setup_table(self, root: QVBoxLayout) -> None:
        self.table = make_table([
            "Sınav", "Tarih", "Konu sayısı"
        ])
        root.addWidget(self.table)

    def _setup_delete_button(self, root: QVBoxLayout) -> None:
        delete = QPushButton("Seçili sınavı sil")
        delete.clicked.connect(self._delete)
        root.addWidget(delete)

    def _reload(self) -> None:
        exams = self.service.list_exams()
        self.table.setRowCount(len(exams))

        for r, e in enumerate(exams):
            set_row(
                self.table,
                r,
                [
                    e.title,
                    fmt_date(e.exam_date),
                    str(len(e.topic_ids))
                ],
                e.id
            )

    def _add(self) -> None:
        try:
            ids = [
                it.data(Qt.ItemDataRole.UserRole)
                for it in self.topics.selectedItems()
            ]

            self.service.add_exam(
                self.title.text(),
                self.date.date().toPython(),
                topic_ids=ids
            )

        except ValueError as exc:
            show_error(self, exc)
            return

        self.title.clear()
        self._reload()

    def _delete(self) -> None:
        key = selected_key(self.table)

        if key is not None:
            self.service.delete_exam(key)
            self._reload()


class SessionDialog(QDialog):
    """Session detail + recording the actual result."""

    def __init__(
        self,
        service: PlannerService,
        view: SessionView,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service, self.view = service, view
        s = view.session

        self.setWindowTitle(view.title)
        self.resize(520, 520)

        root = QVBoxLayout(self)
        self._setup_session_summary(root, view, s)
        self._setup_result_form(root, s)
        self._setup_recall_form(root, view, s)
        self._setup_action_bar(root, s)

    def _setup_session_summary(
        self,
        root: QVBoxLayout,
        view: SessionView,
        s
    ) -> None:
        root.addWidget(
            QLabel(
                f"<b>{view.title}</b> — "
                f"{CLASS_LABEL[view.task_class]}<br>"
                f"{fmt_date(s.session_date)} "
                f"{s.start_time:%H:%M}–{s.end_time:%H:%M} "
                f"({s.planned_minutes} dk, {s.slot_kind.value}) — "
                f"durum: {s.status.value}"
            )
        )

        why = QTextEdit(s.explanation or "-")
        why.setReadOnly(True)
        why.setMaximumHeight(110)

        root.addWidget(
            QLabel("Planlayıcı neden bu zamanı seçti?")
        )
        root.addWidget(why)

    def _setup_result_form(self, root: QVBoxLayout, s) -> None:
        self.rows: dict[int, tuple[QSpinBox, QSpinBox]] = {}

        form = QFormLayout()

        self.actual = QSpinBox()
        self.actual.setRange(1, 1440)
        self.actual.setValue(s.planned_minutes)
        self.actual.setSuffix(" dk")

        self.finished = QCheckBox("Görev tamamen bitti")

        form.addRow("Gerçek süre", self.actual)
        form.addRow(self.finished)

        root.addLayout(form)

    def _setup_recall_form(
        self,
        root: QVBoxLayout,
        view: SessionView,
        s
    ) -> None:
        task = self.service.get_task(s.task_id)

        if view.task_class is not TaskClass.REVIEW or task is None:
            return

        box = QGroupBox(
            "Hatırlama sonuçları (review tamamlanırsa gerekli)"
        )
        grid = QFormLayout(box)

        for tid, label in zip(
            task.topic_ids,
            self.service.topic_labels(task.topic_ids)
        ):
            obj, sub = QSpinBox(), QSpinBox()

            obj.setRange(0, 100)
            obj.setValue(70)
            obj.setSuffix(" %")

            sub.setRange(1, 10)
            sub.setValue(6)

            row = QHBoxLayout()
            row.addWidget(QLabel("Objektif:"))
            row.addWidget(obj)
            row.addWidget(QLabel("Öznel (1-10):"))
            row.addWidget(sub)

            grid.addRow(label, row)
            self.rows[tid] = (obj, sub)

        root.addWidget(box)

    def _setup_action_bar(self, root: QVBoxLayout, s) -> None:
        bar = QHBoxLayout()

        done = QPushButton("Tamamlandı")
        skip = QPushButton("Atla")
        close = QPushButton("Kapat")

        done.clicked.connect(self._complete)
        skip.clicked.connect(self._skip)
        close.clicked.connect(self.reject)

        for b in (done, skip, close):
            bar.addWidget(b)

        done.setEnabled(
            s.status.value != "COMPLETED"
        )

        root.addLayout(bar)

    def _complete(self) -> None:
        results = {
            tid: RecallResult(o.value() / 100.0, s.value())
            for tid, (o, s) in self.rows.items()
        }

        try:
            self.service.complete_session(
                self.view.session.id,
                self.actual.value(),
                results or None,
                self.finished.isChecked()
            )

        except ValueError as exc:
            show_error(self, exc)
            return

        self.accept()

    def _skip(self) -> None:
        self.service.skip_session(self.view.session.id)
        self.accept()


# ================================================================ calendar

GUTTER_WIDTH = 58
HOUR_HEIGHT = 60
START_HOUR = 0
END_HOUR = 24


@dataclass
class _CalendarItem:
    day_idx: int
    start_min: int
    end_min: int
    session: SessionView | None = None
    lesson: SchoolLesson | None = None
    col: int = 0
    total_cols: int = 1


class DayHeaderWidget(QWidget):
    """Fixed top header displaying day names and date badges."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.week_start = date.today()
        self.setFixedHeight(50)

    def set_week_start(self, week_start: date) -> None:
        self.week_start = week_start
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._create_painter()
        pal = self.palette()
        col_w = (self.width() - GUTTER_WIDTH) / 7.0
        today = date.today()
        text_color = pal.text().color()

        self._draw_background(p, pal, self.width())
        self._draw_days(p, col_w, today, text_color)
        p.end()

    def _create_painter(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    def _draw_background(self, p: QPainter, pal, width: int) -> None:
        p.fillRect(self.rect(), pal.window())
        p.setPen(QPen(QColor(128, 128, 128, 50), 1))
        p.drawLine(0, self.height() - 1, width, self.height() - 1)

    def _draw_days(
        self,
        p: QPainter,
        col_w: float,
        today: date,
        text_color
    ) -> None:
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            x = GUTTER_WIDTH + i * col_w
            is_today = (d == today)
            self._draw_day_name(p, i, x, col_w, is_today)
            self._draw_day_number(p, d, x, col_w, is_today, text_color)
            self._draw_day_separator(p, x)

    def _draw_day_name(
        self,
        p: QPainter,
        index: int,
        x: float,
        col_w: float,
        is_today: bool
    ) -> None:
        name_font = QFont(self.font())
        name_font.setPointSize(8)
        name_font.setWeight(QFont.Weight.Medium)
        p.setFont(name_font)
        p.setPen(QColor("#1A73E8") if is_today else QColor(128, 128, 128))
        p.drawText(
            QRectF(x, 4, col_w, 16),
            Qt.AlignmentFlag.AlignCenter,
            WEEKDAYS[index][:3].upper()
        )

    def _draw_day_number(
        self,
        p: QPainter,
        day: date,
        x: float,
        col_w: float,
        is_today: bool,
        text_color
    ) -> None:
        num_font = QFont(self.font())
        num_font.setPointSize(11)
        num_font.setBold(True)
        p.setFont(num_font)

        num_str = str(day.day)
        num_rect = QRectF(x, 22, col_w, 24)

        if is_today:
            self._draw_today_badge(p, x, col_w, num_str)
        else:
            p.setPen(text_color)
            p.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, num_str)

    def _draw_today_badge(
        self,
        p: QPainter,
        x: float,
        col_w: float,
        num_str: str
    ) -> None:
        badge_size = 24.0
        badge_x = x + (col_w - badge_size) / 2.0
        badge_y = 22.0

        p.setBrush(QColor("#1A73E8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(badge_x, badge_y, badge_size, badge_size))

        p.setPen(QColor("white"))
        p.drawText(
            QRectF(badge_x, badge_y, badge_size, badge_size),
            Qt.AlignmentFlag.AlignCenter,
            num_str
        )

    def _draw_day_separator(self, p: QPainter, x: float) -> None:
        p.setPen(QPen(QColor(128, 128, 128, 35), 1))
        p.drawLine(int(x), 0, int(x), self.height())


class WeekGridCanvas(QWidget):
    """Scrollable 24-hour time grid with modern event cards and live time line."""

    sessionClicked = Signal(int)
    schoolLessonClicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initialize_data()
        self._initialize_interaction()

    def _initialize_data(self) -> None:
        self.week_start = date.today()
        self.sessions: list[SessionView] = []
        self.lessons: list[SchoolLesson] = []
        self.blocks: list[AvailabilityBlock] = []
        self.now = datetime.now()
        self._hits: list[tuple[QRectF, _CalendarItem]] = []

    def _initialize_interaction(self) -> None:
        self.setMouseTracking(True)
        self.setFixedHeight((END_HOUR - START_HOUR) * HOUR_HEIGHT + CALENDAR_BOTTOM_PADDING)

    def set_data(
        self,
        week_start: date,
        sessions: list[SessionView],
        blocks: list[AvailabilityBlock],
        lessons: list[SchoolLesson]
    ) -> None:
        self.week_start = week_start
        self.sessions = sessions
        self.blocks = blocks
        self.lessons = lessons
        self.now = datetime.now()
        self.update()

    def _col_w(self) -> float:
        return (self.width() - GUTTER_WIDTH) / 7.0

    def _y_for_minute(self, minute: float) -> float:
        return (minute - START_HOUR * 60) / 60.0 * HOUR_HEIGHT

    def _layout_items(self) -> list[_CalendarItem]:
        items_by_day = self._create_items_by_day()
        all_items: list[_CalendarItem] = []

        for day_items in items_by_day.values():
            if not day_items:
                continue

            self._sort_day_items(day_items)
            clusters = self._build_clusters(day_items)

            for cluster in clusters:
                self._assign_columns(cluster)

            all_items.extend(day_items)

        return all_items

    def _create_items_by_day(self) -> dict[int, list[_CalendarItem]]:
        items_by_day: dict[int, list[_CalendarItem]] = {i: [] for i in range(7)}
        self._add_lesson_items(items_by_day)
        self._add_session_items(items_by_day)
        return items_by_day

    def _add_lesson_items(
        self,
        items_by_day: dict[int, list[_CalendarItem]]
    ) -> None:
        for lesson in self.lessons:
            day_idx = (lesson.lesson_date - self.week_start).days
            if 0 <= day_idx < 7:
                s_min = lesson.start_time.hour * 60 + lesson.start_time.minute
                e_min = lesson.end_time.hour * 60 + lesson.end_time.minute
                items_by_day[day_idx].append(
                    _CalendarItem(
                        day_idx=day_idx,
                        start_min=s_min,
                        end_min=max(e_min, s_min + 15),
                        lesson=lesson
                    )
                )

    def _add_session_items(
        self,
        items_by_day: dict[int, list[_CalendarItem]]
    ) -> None:
        for sv in self.sessions:
            s = sv.session
            day_idx = (s.session_date - self.week_start).days
            if 0 <= day_idx < 7:
                s_min = s.start_time.hour * 60 + s.start_time.minute
                e_min = s.end_time.hour * 60 + s.end_time.minute
                items_by_day[day_idx].append(
                    _CalendarItem(
                        day_idx=day_idx,
                        start_min=s_min,
                        end_min=max(e_min, s_min + 15),
                        session=sv
                    )
                )

    def _sort_day_items(self, day_items: list[_CalendarItem]) -> None:
        day_items.sort(
            key=lambda x: (x.start_min, -(x.end_min - x.start_min))
        )

    def _build_clusters(
        self,
        day_items: list[_CalendarItem]
    ) -> list[list[_CalendarItem]]:
        clusters: list[list[_CalendarItem]] = []
        curr_cluster: list[_CalendarItem] = []
        cluster_end = -1

        for item in day_items:
            if not curr_cluster or item.start_min < cluster_end:
                curr_cluster.append(item)
                cluster_end = max(cluster_end, item.end_min)
            else:
                clusters.append(curr_cluster)
                curr_cluster = [item]
                cluster_end = item.end_min

        if curr_cluster:
            clusters.append(curr_cluster)

        return clusters

    def _assign_columns(self, cluster: list[_CalendarItem]) -> None:
        cols: list[list[_CalendarItem]] = []

        for item in cluster:
            placed = False

            for c_idx, c_list in enumerate(cols):
                if c_list[-1].end_min <= item.start_min:
                    c_list.append(item)
                    item.col = c_idx
                    placed = True
                    break

            if not placed:
                item.col = len(cols)
                cols.append([item])

        total_c = len(cols)

        for item in cluster:
            item.total_cols = total_c

    def paintEvent(self, event) -> None:  # noqa: N802
        p, col_w, today, text_color, grid_pen, sub_grid_pen = (
            self._prepare_paint()
        )

        self._draw_today_column(p, col_w, today)
        self._draw_time_grid(p, grid_pen, sub_grid_pen)
        self._draw_day_columns(p, col_w, grid_pen)
        self._draw_availability(p, col_w)
        self._draw_calendar_items(p, col_w, text_color)
        self._draw_current_time(p, col_w)

        p.end()

    def _prepare_paint(
        self
    ) -> tuple[QPainter, float, date, object, QPen, QPen]:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = self.palette()
        p.fillRect(self.rect(), pal.base())

        grid_color = pal.mid().color()
        grid_color.setAlpha(90)
        quarter_color = pal.midlight().color()
        quarter_color.setAlpha(75)
        return (
            p,
            self._col_w(),
            date.today(),
            pal.text().color(),
            QPen(grid_color, 1),
            QPen(quarter_color, 1)
        )

    def _draw_today_column(
        self,
        p: QPainter,
        col_w: float,
        today: date
    ) -> None:
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            if d == today:
                col_x = GUTTER_WIDTH + i * col_w
                p.fillRect(
                    QRectF(col_x, 0, col_w, self.height()),
                    QColor(26, 115, 232, 10)
                )

    def _draw_time_grid(
        self,
        p: QPainter,
        grid_pen: QPen,
        sub_grid_pen: QPen
    ) -> None:
        time_font = QFont(self.font())
        time_font.setPointSize(8)
        p.setFont(time_font)
        time_color = self.palette().placeholderText().color()

        for h in range(START_HOUR, END_HOUR + 1):
            y = (h - START_HOUR) * HOUR_HEIGHT

            p.setPen(grid_pen)
            p.drawLine(int(GUTTER_WIDTH), int(y), self.width(), int(y))

            if h < END_HOUR:
                for quarter in (15, 30, 45):
                    quarter_y = y + HOUR_HEIGHT * quarter / 60.0
                    p.setPen(sub_grid_pen if quarter != 30 else grid_pen)
                    p.drawLine(
                        int(GUTTER_WIDTH),
                        int(quarter_y),
                        self.width(),
                        int(quarter_y)
                    )

            if h > START_HOUR:
                p.setPen(time_color)
                hour = h % 12
                if hour == 0:
                    hour = 12
                period = "AM" if h < 12 or h == 24 else "PM"
                p.drawText(
                    QRectF(0, y + 3, GUTTER_WIDTH - 9, 17),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{hour} {period}"
                )

    def _draw_day_columns(
        self,
        p: QPainter,
        col_w: float,
        grid_pen: QPen
    ) -> None:
        for i in range(8):
            x = GUTTER_WIDTH + i * col_w
            p.setPen(grid_pen)
            p.drawLine(int(x), 0, int(x), self.height())

    def _draw_availability(
        self,
        p: QPainter,
        col_w: float
    ) -> None:
        tint_map = {
            AvailabilityType.PRIMARY: QColor(76, 175, 80, 35),
            AvailabilityType.RESERVE: QColor(255, 193, 7, 45),
            AvailabilityType.UNAVAILABLE: QColor(120, 120, 120, 60)
        }

        for b in self.blocks:
            day_idx = (b.block_date - self.week_start).days
            if 0 <= day_idx < 7:
                s_min = b.start_time.hour * 60 + b.start_time.minute
                e_min = b.end_time.hour * 60 + b.end_time.minute
                y1 = self._y_for_minute(s_min)
                y2 = self._y_for_minute(e_min)
                x = GUTTER_WIDTH + day_idx * col_w + 1
                p.fillRect(
                    QRectF(x, y1, col_w - 2, max(6.0, y2 - y1)),
                    tint_map[b.block_type]
                )

    def _draw_calendar_items(
        self,
        p: QPainter,
        col_w: float,
        text_color
    ) -> None:
        self._hits = []
        items = self._layout_items()

        for it in items:
            rect = self._item_rect(it, col_w)
            self._hits.append((rect, it))

            if it.lesson is not None:
                self._draw_lesson_card(p, rect, it.lesson, text_color)
            elif it.session is not None:
                self._draw_session_card(p, rect, it.session, text_color)

    def _item_rect(
        self,
        item: _CalendarItem,
        col_w: float
    ) -> QRectF:
        day_x = GUTTER_WIDTH + item.day_idx * col_w
        sub_w = (col_w - 6.0) / item.total_cols
        card_x = day_x + 3.0 + item.col * sub_w
        y1 = self._y_for_minute(item.start_min)
        y2 = self._y_for_minute(item.end_min)
        card_h = max(20.0, y2 - y1 - 2.0)
        card_w = max(18.0, sub_w - 3.0)
        return QRectF(card_x, y1 + 1.0, card_w, card_h)

    def _draw_lesson_card(
        self,
        p: QPainter,
        rect: QRectF,
        lesson: SchoolLesson,
        text_color
    ) -> None:
        base_color = QColor.fromHsv(
            (lesson.subject_id * 53) % 360,
            160,
            170
        )
        bg_color = QColor(base_color)
        bg_color.setAlpha(72)

        self._draw_card_background(p, rect, bg_color, None)
        p.setBrush(base_color)
        p.drawRoundedRect(
            QRectF(rect.x(), rect.y(), 4, rect.height()),
            2,
            2
        )

        p.setPen(text_color)
        title_font = QFont(self.font())
        title_font.setPointSize(8)
        title_font.setBold(True)
        p.setFont(title_font)

        text_pad = rect.adjusted(10, 2, -3, -2)
        p.drawText(
            text_pad,
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            lesson.subject_name
        )

        if rect.height() > 32:
            self._draw_lesson_time(p, text_pad, lesson)

    def _draw_lesson_time(
        self,
        p: QPainter,
        text_pad: QRectF,
        lesson: SchoolLesson
    ) -> None:
        sub_font = QFont(self.font())
        sub_font.setPointSize(7)
        p.setFont(sub_font)
        p.setPen(self.palette().placeholderText().color())
        p.drawText(
            QRectF(
                text_pad.x(),
                text_pad.y() + 13,
                text_pad.width(),
                text_pad.height() - 13
            ),
            Qt.AlignmentFlag.AlignTop,
            f"{lesson.start_time:%H:%M} - {lesson.end_time:%H:%M}"
        )

    def _draw_session_card(
        self,
        p: QPainter,
        rect: QRectF,
        sv: SessionView,
        text_color
    ) -> None:
        s = sv.session
        state = sv.display_state(self.now)
        main_color, bg_color = self._session_colors(sv, state)

        self._draw_card_background(
            p,
            rect,
            bg_color,
            QPen(QColor("#D32F2F"), 1.5)
            if state == "overdue"
            else None
        )

        p.setBrush(main_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(
            QRectF(rect.x(), rect.y(), 4, rect.height()),
            2,
            2
        )

        p.setPen(text_color)
        title_font = QFont(self.font())
        title_font.setPointSize(8)
        title_font.setBold(True)
        p.setFont(title_font)

        text_pad = rect.adjusted(10, 2, -3, -2)
        mark = (
            "✓ " if state == "completed"
            else "! " if state == "overdue"
            else ""
        )
        p.drawText(
            text_pad,
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            f"{mark}{sv.title}"
        )

        if rect.height() > 30:
            self._draw_session_time(p, text_pad, s)

    def _session_colors(
        self,
        sv: SessionView,
        state: str
    ) -> tuple[QColor, QColor]:
        main_color = QColor(CLASS_COLOR[sv.task_class])

        if state == "completed":
            main_color = QColor("#607D8B")
            alpha = 60
        elif state == "overdue":
            main_color = QColor("#D32F2F")
            alpha = 70
        else:
            alpha = 70

        bg_color = QColor(main_color)
        bg_color.setAlpha(alpha)
        return main_color, bg_color

    def _draw_card_background(
        self,
        p: QPainter,
        rect: QRectF,
        bg_color: QColor,
        border: QPen | None
    ) -> None:
        p.setBrush(bg_color)
        p.setPen(border if border is not None else Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 5, 5)

    def _draw_session_time(
        self,
        p: QPainter,
        text_pad: QRectF,
        session
    ) -> None:
        sub_font = QFont(self.font())
        sub_font.setPointSize(7)
        p.setFont(sub_font)
        p.setPen(self.palette().placeholderText().color())
        p.drawText(
            QRectF(
                text_pad.x(),
                text_pad.y() + 13,
                text_pad.width(),
                text_pad.height() - 13
            ),
            Qt.AlignmentFlag.AlignTop,
            f"{session.start_time:%H:%M} - {session.end_time:%H:%M} ({session.planned_minutes}m)"
        )

    def _draw_current_time(
        self,
        p: QPainter,
        col_w: float
    ) -> None:
        if not (
            self.week_start
            <= self.now.date()
            <= self.week_start + timedelta(days=6)
        ):
            return

        today_idx = (self.now.date() - self.week_start).days
        now_min = self.now.hour * 60 + self.now.minute
        now_y = self._y_for_minute(now_min)
        line_x = GUTTER_WIDTH + today_idx * col_w

        p.setPen(QPen(QColor("#EA4335"), 2))
        p.drawLine(
            int(line_x),
            int(now_y),
            int(line_x + col_w),
            int(now_y)
        )

        p.setBrush(QColor("#EA4335"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(line_x, now_y), 4, 4)

    def _hit_test(self, pos: QPointF) -> _CalendarItem | None:
        for rect, it in reversed(self._hits):
            if rect.contains(pos):
                return it
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        it = self._hit_test(event.position())
        if it is None:
            return

        if it.session is not None and it.session.session.id is not None:
            self.sessionClicked.emit(it.session.session.id)
        elif it.lesson is not None:
            self.schoolLessonClicked.emit(it.lesson)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        it = self._hit_test(event.position())
        if it is None:
            self.setToolTip("")
            return

        if it.session is not None:
            sv = it.session
            self.setToolTip(
                f"<b>{sv.title}</b><br>"
                f"{CLASS_LABEL[sv.task_class]} — {sv.session.planned_minutes} dk<br>"
                f"<i>{sv.session.explanation or ''}</i>"
            )
        elif it.lesson is not None:
            les = it.lesson
            tip = (
                f"<b>{les.subject_name}</b><br>"
                f"Haftanın {les.subject_lesson_no}. dersi<br>"
            )
            if les.recorded_topic:
                tip += f"Konu: {les.recorded_topic}"
            else:
                tip += "<i>Konuyu kaydetmek için tıklayın</i>"
            self.setToolTip(tip)

class CalendarView(QWidget):
    """Full-featured modern calendar widget matching the calendar_view_example repository."""

    plan_changed = Signal()

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self._initialize_week()
        root = self._create_root_layout()
        self._setup_toolbar(root)
        self._setup_legend(root)
        self._setup_calendar(root)
        self.refresh()
        self._scroll_to_hour(8)

    def _initialize_week(self) -> None:
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())

    def _create_root_layout(self) -> QVBoxLayout:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_TOP,
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_BOTTOM
        )
        root.setSpacing(5)
        return root

    def _setup_toolbar(self, root: QVBoxLayout) -> None:
        top_bar = QHBoxLayout()

        today_btn = QPushButton("Bugün")
        prev_btn = QPushButton("◀")
        next_btn = QPushButton("▶")

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 600; font-size: 15px;")

        plan_btn = QPushButton("Planla / Yeniden planla")
        plan_btn.setProperty("primary", True)

        today_btn.clicked.connect(self._go_today)
        prev_btn.clicked.connect(lambda: self._shift(-7))
        next_btn.clicked.connect(lambda: self._shift(7))
        plan_btn.clicked.connect(self.replan)

        top_bar.addWidget(today_btn)
        top_bar.addWidget(prev_btn)
        top_bar.addWidget(next_btn)
        top_bar.addWidget(self.title_label)
        top_bar.addStretch(1)
        top_bar.addWidget(plan_btn)

        root.addLayout(top_bar)

    def _setup_legend(self, root: QVBoxLayout) -> None:
        legend = QLabel(
            "<span style='color:#5C6BC0'>■</span> Okul dersi &nbsp;&nbsp;"
            "<span style='color:#7E57C2'>■</span> Tekrar &nbsp;&nbsp;"
            "<span style='color:#EF6C00'>■</span> Teslim görevi &nbsp;&nbsp;"
            "<span style='color:#00897B'>■</span> Tekrarlayan &nbsp;&nbsp;"
            "<span style='color:#607D8B'>■</span> Tamamlanan &nbsp;&nbsp;"
            "<span style='color:#D32F2F'>■</span> Gecikmiş &nbsp;|&nbsp; "
            "<span style='color:#4CAF50'>▒</span> PRIMARY &nbsp;&nbsp;"
            "<span style='color:#FFC107'>▒</span> RESERVE &nbsp;&nbsp;"
            "<span style='color:#757575'>▒</span> UNAVAILABLE"
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setProperty("secondary", True)
        root.addWidget(legend)

        self.summary = QLabel()
        self.summary.setProperty("secondary", True)
        root.addWidget(self.summary)

    def _setup_calendar(self, root: QVBoxLayout) -> None:
        cal_container = QFrame()
        cal_container.setObjectName("calendarContainer")
        cal_container.setProperty("card", True)
        cal_container.setFrameShape(QFrame.Shape.NoFrame)

        cal_layout = QVBoxLayout(cal_container)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.setSpacing(0)

        self.header = DayHeaderWidget()
        cal_layout.addWidget(self.header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.grid = WeekGridCanvas()
        self.grid.sessionClicked.connect(self._open_session)
        self.grid.schoolLessonClicked.connect(self._open_school_lesson)

        self.scroll_area.setWidget(self.grid)
        cal_layout.addWidget(self.scroll_area, 1)

        root.addWidget(cal_container, 1)

    def _scroll_to_hour(self, hour: int) -> None:
        target_y = int(hour * HOUR_HEIGHT)
        self.scroll_area.verticalScrollBar().setValue(target_y)

    def _shift(self, days: int) -> None:
        self.week_start += timedelta(days=days)
        self.refresh()

    def _go_today(self) -> None:
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())
        self.refresh()
        now_hour = max(0, datetime.now().hour - 1)
        self._scroll_to_hour(now_hour)

    def refresh(self) -> None:
        end = self._week_end()
        self._update_title(end)
        self.header.set_week_start(self.week_start)
        sessions, blocks, lessons = self._load_calendar_data(end)
        self.grid.set_data(
            self.week_start,
            sessions,
            blocks,
            lessons
        )

    def _week_end(self) -> date:
        return self.week_start + timedelta(days=6)

    def _update_title(self, end: date) -> None:
        self.title_label.setText(
            f"{fmt_date(self.week_start)} – {fmt_date(end)} {end.year}"
        )

    def _load_calendar_data(
        self,
        end: date
    ) -> tuple[list[SessionView], list[AvailabilityBlock], list[SchoolLesson]]:
        sessions = self.service.list_sessions(self.week_start, end)
        blocks = self.service.list_availability(self.week_start, end)
        lessons = self.service.list_school_lessons(self.week_start, end)
        return sessions, blocks, lessons

    def replan(self) -> None:
        plan = self._run_replan()
        if plan is None:
            return

        self._show_summary(plan)
        self.refresh()
        self.plan_changed.emit()
        self._show_plan_warnings(plan)

    def _run_replan(self) -> SchedulePlan | None:
        try:
            return self.service.replan()
        except Exception as exc:
            show_error(self, exc)
            return None

    def _show_plan_warnings(self, plan: SchedulePlan) -> None:
        if not (plan.warnings or plan.unscheduled):
            return

        lines = list(plan.warnings)
        lines += [
            f"• {u.title}: {u.minutes} dk yerleştirilemedi ({u.detail})"
            for u in plan.unscheduled[:12]
        ]

        if len(plan.unscheduled) > 12:
            lines.append(
                f"… ve {len(plan.unscheduled) - 12} kalem daha"
            )

        QMessageBox.information(
            self,
            "Plan uyarıları",
            "\n".join(lines)
        )

    def _show_summary(self, plan: SchedulePlan) -> None:
        total = sum(s.minutes for s in plan.sessions)
        reserve = sum(s.minutes for s in plan.sessions if s.kind.value == "RESERVE")

        self.summary.setText(
            f"Plan: {len(plan.sessions)} oturum, {total} dk "
            f"(RESERVE: {reserve} dk), yerleştirilemeyen: {len(plan.unscheduled)}"
        )

    def _open_session(self, session_id: int) -> None:
        view = self.service.get_session(session_id)
        if view is None:
            return

        if SessionDialog(self.service, view, self).exec() == QDialog.DialogCode.Accepted:
            self._after_session_update()

    def _after_session_update(self) -> None:
        self.refresh()
        self.plan_changed.emit()

        if self._ask_replan():
            self.replan()

    def _ask_replan(self) -> bool:
        return (
            QMessageBox.question(
                self,
                "Yeniden planla",
                "Kalan planı güncel duruma göre yeniden hesaplayayım mı?"
            )
            == QMessageBox.StandardButton.Yes
        )

    def _open_school_lesson(self, lesson: SchoolLesson) -> None:
        if lesson.recorded_topic:
            QMessageBox.information(
                self,
                "Konu zaten kaydedilmiş",
                f"{lesson.subject_name} dersinin konusu "
                f"“{lesson.recorded_topic}” olarak kayıtlı. "
                "Değiştirmek için Dersler sekmesindeki öğrenme geçmişinden kaydı silip yeniden girin."
            )
            return

        if LearningEventDialog(self.service, lesson, self).exec() == QDialog.DialogCode.Accepted:
            self.replan()


# ================================================================ subjects

class SubjectsView(QWidget):

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
        self.title.setStyleSheet(
            "font-size: 18px; font-weight: 600;"
        )
        layout.addWidget(self.title)

        self._setup_event_header(layout)

        self.events = make_table([
            "Tarih",
            "Haftalık ders sırası",
            "Konu",
            "Not"
        ])
        layout.addWidget(self.events, 3)

        layout.addWidget(
            QLabel(
                "Konu hafıza durumu "
                "(bir sonraki ideal tekrar)"
            )
        )

        self.memory = make_table([
            "Konu",
            "Aşama",
            "Stabilite (gün)",
            "Zorluk",
            "Son çalışma",
            "İdeal tekrar",
            "Tekrar sayısı"
        ])
        layout.addWidget(self.memory, 2)

        return right

    def _setup_event_header(self, layout: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.addWidget(
            QLabel("Öğrenme geçmişi (kronolojik)")
        )
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

        return (
            None
            if item is None
            else item.data(Qt.ItemDataRole.UserRole)
        )

    def refresh(self) -> None:
        keep = self.current_subject_id()
        self._reload_subject_list(keep)
        self._load_subject()

    def _reload_subject_list(self, keep: int | None) -> None:
        self.list.blockSignals(True)
        self.list.clear()

        for s in self.service.list_subjects():
            item = QListWidgetItem(s.name)
            item.setData(
                Qt.ItemDataRole.UserRole,
                s.id
            )
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
        self.title.setText(
            self.list.currentItem().text()
        )

    def _load_learning_events(self, sid: int) -> None:
        events = self.service.list_learning_events(sid)
        self.events.setRowCount(len(events))

        for r, v in enumerate(events):
            e = v.event
            period = (
                "-"
                if e.period_start is None
                else f"{e.period_start}. ders"
            )

            set_row(
                self.events,
                r,
                [
                    fmt_date(e.event_date),
                    period,
                    v.topic_name,
                    e.notes
                ],
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
        name, ok = QInputDialog.getText(
            self,
            "Yeni ders",
            "Ders adı:"
        )

        if ok:
            self._add_subject(name)
            self.refresh()

    def _add_subject(self, name: str) -> None:
        try:
            self.service.add_subject(name)
        except Exception as exc:
            show_error(
                self,
                ValueError(
                    "Ders eklenemedi "
                    "(aynı isimde ders olabilir): "
                    + str(exc)
                )
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
            self.service.rename_subject(
                sid,
                name
            )
        except Exception as exc:
            show_error(
                self,
                ValueError(str(exc))
            )

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
                "Dersin tüm konuları, öğrenme "
                "kayıtları ve tekrar görevleri "
                "silinecek. Emin misiniz?"
            )
            == QMessageBox.StandardButton.Yes
        )

    def _delete_event(self) -> None:
        key = selected_key(self.events)

        if key is not None:
            self.service.delete_learning_event(key)
            self._load_subject()


# ================================================================== tasks

class TasksView(QWidget):

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

        self.filter.currentIndexChanged.connect(
            lambda *_: self.refresh()
        )

        new_b = QPushButton("Yeni görev ▾")
        menu = QMenu(new_b)
        menu.addAction(
            "Teslim görevi…",
            lambda: self._new("deadline")
        )
        menu.addAction(
            "Tekrarlayan görev…",
            lambda: self._new("recurring")
        )
        menu.addAction(
            "Manuel tekrar…",
            lambda: self._new("review")
        )
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
            "Başlık",
            "Tür",
            "Kalan / süre",
            "Son tarih / ideal",
            "Öncelik",
            "Durum"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(
            self._show_detail
        )

    def _setup_task_detail(self) -> None:
        self._detail = QGroupBox("Görev detayı")
        self.form = QFormLayout(self._detail)

        self.fields = {
            k: QLabel("-")
            for k in (
                "title",
                "type",
                "duration",
                "remaining",
                "priority",
                "deadline",
                "ideal",
                "topics",
                "tags",
                "status"
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
            self.form.addRow(
                label,
                self.fields[key]
            )

    def _add_detail_actions(self) -> None:
        cancel_b = QPushButton("Görevi iptal et")
        delete_b = QPushButton("Görevi sil")

        cancel_b.clicked.connect(self._cancel)
        delete_b.clicked.connect(self._delete)

        self.form.addRow(cancel_b)
        self.form.addRow(delete_b)

    def refresh(self) -> None:
        tasks = self._load_tasks()
        self._tasks = {
            t.id: t
            for t in tasks
            if t.id is not None
        }

        self._fill_task_table(tasks)
        self._show_detail()

    def _load_tasks(self) -> list[Task]:
        return self.service.list_tasks(
            self.filter.currentData(),
            date.today()
        )

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
                (
                    "Gecikmiş"
                    if overdue
                    else STATUS_LABEL[task.status]
                )
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
            self.table.item(row, c).setForeground(
                QColor("#D32F2F")
            )

    def _show_detail(self) -> None:
        key = selected_key(self.table)
        t = (
            self._tasks.get(key)
            if key is not None
            else None
        )

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
            + (
                f" ({task.review_source.value.lower()})"
                if task.review_source
                else ""
            )
        )
        f["duration"].setText(
            f"{task.duration} dk"
            + (
                "  (bölünebilir, min "
                + str(task.minimum_session)
                + " dk)"
                if task.splittable
                else ""
            )
        )
        f["remaining"].setText(
            f"{task.remaining_duration} dk"
        )
        f["priority"].setText(str(task.priority))

    def _show_date_detail(self, task: Task) -> None:
        f = self.fields
        f["deadline"].setText(fmt_date(task.deadline))

        ideal = fmt_date(task.ideal_date)
        if task.earliest_date and task.latest_date:
            ideal += (
                f"  (pencere: "
                f"{fmt_date(task.earliest_date)} – "
                f"{fmt_date(task.latest_date)})"
            )

        f["ideal"].setText(
            ideal if task.ideal_date else "-"
        )

    def _show_extra_detail(self, task: Task) -> None:
        f = self.fields

        f["topics"].setText(
            ", ".join(
                self.service.topic_labels(task.topic_ids)
            ) or "-"
        )
        f["tags"].setText(
            ", ".join(task.tags) or "-"
        )

    def _show_status_detail(self, task: Task) -> None:
        self.fields["status"].setText(
            "Gecikmiş"
            if task.is_overdue(date.today())
            else STATUS_LABEL[task.status]
        )

    def _new(self, mode: str) -> None:
        if (
            TaskDialog(
                self.service,
                mode,
                self
            ).exec()
            == QDialog.DialogCode.Accepted
        ):
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
            and
            QMessageBox.question(
                self,
                "Sil",
                "Görev kalıcı olarak silinsin mi?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.service.delete_task(key)
            self.refresh()


# ============================================================== main window

class MainWindow(QMainWindow):

    def __init__(
        self,
        service: PlannerService
    ) -> None:
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
        self.setWindowTitle(
            "Dinamik Akademik Çalışma Planlayıcı"
        )
        self.resize(1200, 780)
        self.setStyleSheet(UI_STYLESHEET)

    def _setup_views(self) -> None:
        self.calendar = CalendarView(self.service)
        self.subjects = SubjectsView(self.service)
        self.tasks = TasksView(self.service)

    def _setup_tabs(self) -> None:
        self.tabs = QTabWidget()

        self.tabs.addTab(
            self.calendar,
            "Takvim"
        )
        self.tabs.addTab(
            self.subjects,
            "Dersler"
        )
        self.tabs.addTab(
            self.tasks,
            "Görevler"
        )

        self.tabs.currentChanged.connect(
            self._on_tab
        )

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
        self.calendar.plan_changed.connect(
            self.tasks.refresh
        )

    def _setup_menu(self) -> None:
        menu = self.menuBar().addMenu("Planlama")

        menu.addAction(
            "Yeniden planla",
            self.calendar.replan
        )
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

    def _dialog(
        self,
        cls: type[QDialog]
    ) -> None:
        cls(
            self.service,
            self
        ).exec()

        self.calendar.refresh()

    def _on_tab(self, index: int) -> None:
        (
            self.calendar,
            self.subjects,
            self.tasks
        )[index].refresh()
