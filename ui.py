"""ui.py - PySide6 user interface.

Only user input, service calls and result display live here.  No SQL, no memory
formulas and no scheduling logic: everything goes through engine.PlannerService.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QPointF, QRectF, Qt, QTime, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QTimeEdit, QVBoxLayout, QWidget)

from engine import (AvailabilityBlock, AvailabilityType, PlannerService, RecallResult, RecurrenceKind,
                    RecurringRule, SchedulePlan, SessionView, Task, TaskClass, TaskStatus)

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
CLASS_LABEL = {TaskClass.REVIEW: "Tekrar", TaskClass.DEADLINE_TASK: "Teslim görevi",
               TaskClass.RECURRING_TASK: "Tekrarlayan"}
CLASS_COLOR = {TaskClass.REVIEW: "#7E57C2", TaskClass.DEADLINE_TASK: "#EF6C00", TaskClass.RECURRING_TASK: "#00897B"}
STATUS_LABEL = {TaskStatus.PENDING: "Bekliyor", TaskStatus.COMPLETED: "Tamamlandı",
                TaskStatus.CANCELLED: "İptal", TaskStatus.MISSED: "Kaçırıldı"}
AVAIL_LABEL = {AvailabilityType.PRIMARY: "Birincil (PRIMARY)", AvailabilityType.RESERVE: "Yedek (RESERVE)",
               AvailabilityType.UNAVAILABLE: "Kullanılamaz"}


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


def set_row(table: QTableWidget, row: int, values: list[str], key: int | None = None) -> None:
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
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


# ================================================================ dialogs
class LearningEventDialog(QDialog):
    """Date + school periods + topic (existing or new) + optional note."""

    def __init__(self, service: PlannerService, subject_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yeni öğrenme kaydı")
        self.service, self.subject_id = service, subject_id
        form = QFormLayout(self)
        self.date = make_date_edit(date.today())
        self.p_start, self.p_end = QSpinBox(), QSpinBox()
        for sp in (self.p_start, self.p_end):
            sp.setRange(0, 14)
            sp.setSpecialValueText("-")
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self.topic.addItems([t.name for t in service.list_topics(subject_id)])
        self.topic.setCurrentText("")
        self.notes = QLineEdit()
        form.addRow("Tarih", self.date)
        form.addRow("Ders saati (başlangıç)", self.p_start)
        form.addRow("Ders saati (bitiş)", self.p_end)
        form.addRow("Konu (seç ya da yeni yaz)", self.topic)
        form.addRow("Not", self.notes)
        form.addRow(buttons(self))

    def accept(self) -> None:
        try:
            self.service.add_learning_event(
                self.subject_id, self.date.date().toPython(), self.topic.currentText(),
                self.p_start.value() or None, self.p_end.value() or None, self.notes.text())
        except ValueError as exc:
            show_error(self, exc)
            return
        super().accept()


class TaskDialog(QDialog):
    """Create a deadline task, a recurring task or a manual review."""

    def __init__(self, service: PlannerService, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.mode = service, mode
        self.setWindowTitle({"deadline": "Yeni teslim görevi", "recurring": "Yeni tekrarlayan görev",
                             "review": "Yeni manuel tekrar"}[mode])
        form = QFormLayout(self)
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

        if mode == "deadline":
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
        elif mode == "recurring":
            self.rule = QComboBox()
            self.rule.addItems(["Her gün", "Seçili günler", "Haftada N gün"])
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
        else:
            self.ideal = make_date_edit(date.today() + timedelta(days=1))
            self.topics = QListWidget()
            self.topics.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            for subj in service.list_subjects():
                for t in service.list_topics(subj.id):
                    item = QListWidgetItem(f"{subj.name} / {t.name}")
                    item.setData(Qt.ItemDataRole.UserRole, t.id)
                    self.topics.addItem(item)
            form.addRow("İdeal tarih", self.ideal)
            form.addRow("Konular (birden fazla seçilebilir)", self.topics)
        form.addRow(buttons(self))

    def _tags(self) -> list[str]:
        return [t.strip() for t in self.tags.text().split(",") if t.strip()]

    def accept(self) -> None:
        try:
            if self.mode == "deadline":
                self.service.add_deadline_task(
                    title=self.title.text(), duration=self.duration.value(),
                    deadline=self.deadline.date().toPython(), priority=self.priority.value(),
                    splittable=self.splittable.isChecked(),
                    minimum_session=self.min_session.value() if self.splittable.isChecked() else None,
                    tags=self._tags())
            elif self.mode == "recurring":
                idx = self.rule.currentIndex()
                chosen = tuple(i for i, cb in enumerate(self.days) if cb.isChecked())
                rule = (RecurringRule(RecurrenceKind.DAILY) if idx == 0 else
                        RecurringRule(RecurrenceKind.WEEKDAYS, weekdays=chosen) if idx == 1 else
                        RecurringRule(RecurrenceKind.TIMES_PER_WEEK, times_per_week=self.times.value()))
                self.service.add_recurring_task(
                    title=self.title.text(), duration=self.duration.value(), rule=rule,
                    priority=self.priority.value(), tags=self._tags())
            else:
                ids = [it.data(Qt.ItemDataRole.UserRole) for it in self.topics.selectedItems()]
                self.service.add_manual_review(
                    title=self.title.text() or "Manuel tekrar", topic_ids=ids,
                    ideal_date=self.ideal.date().toPython(), duration=self.duration.value(),
                    priority=self.priority.value(), tags=self._tags())
        except ValueError as exc:
            show_error(self, exc)
            return
        super().accept()


class AvailabilityDialog(QDialog):
    """Add PRIMARY / RESERVE / UNAVAILABLE blocks for a date range and chosen weekdays."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Çalışma zamanları (müsaitlik)")
        self.resize(640, 560)
        self.service = service
        root = QVBoxLayout(self)
        box = QGroupBox("Blok ekle")
        form = QFormLayout(box)
        self.start_date = make_date_edit(date.today())
        self.end_date = make_date_edit(date.today() + timedelta(days=13))
        self.days = [QCheckBox(n[:3]) for n in WEEKDAYS]
        day_row = QHBoxLayout()
        for cb in self.days:
            cb.setChecked(True)
            day_row.addWidget(cb)
        self.start_time, self.end_time = make_time_edit(time(17, 0)), make_time_edit(time(22, 0))
        self.kind = QComboBox()
        for k in AvailabilityType:
            self.kind.addItem(AVAIL_LABEL[k], k)
        add = QPushButton("Ekle")
        add.clicked.connect(self._add)
        form.addRow("Başlangıç tarihi", self.start_date)
        form.addRow("Bitiş tarihi", self.end_date)
        form.addRow("Günler", day_row)
        form.addRow("Saat (başlangıç)", self.start_time)
        form.addRow("Saat (bitiş)", self.end_time)
        form.addRow("Tür", self.kind)
        form.addRow(add)
        root.addWidget(box)
        self.table = make_table(["Tarih", "Başlangıç", "Bitiş", "Tür"])
        root.addWidget(self.table)
        delete = QPushButton("Seçili bloğu sil")
        delete.clicked.connect(self._delete)
        root.addWidget(delete)
        self._reload()

    def _reload(self) -> None:
        blocks = self.service.list_availability(date.today(), date.today() + timedelta(days=27))
        self.table.setRowCount(len(blocks))
        for r, b in enumerate(blocks):
            set_row(self.table, r, [f"{fmt_date(b.block_date)} {WEEKDAYS[b.block_date.weekday()][:3]}",
                                    b.start_time.strftime("%H:%M"), b.end_time.strftime("%H:%M"),
                                    AVAIL_LABEL[b.block_type]], b.id)

    def _add(self) -> None:
        try:
            n = self.service.add_availability_range(
                self.start_date.date().toPython(), self.end_date.date().toPython(),
                [i for i, cb in enumerate(self.days) if cb.isChecked()],
                self.start_time.time().toPython(), self.end_time.time().toPython(), self.kind.currentData())
        except ValueError as exc:
            show_error(self, exc)
            return
        self._reload()
        if n == 0:
            QMessageBox.information(self, "Bilgi", "Seçilen aralıkta uygun gün bulunamadı.")

    def _delete(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.delete_availability(key)
            self._reload()


class TimetableDialog(QDialog):
    """Weekly school timetable (kept separate from LearningEvents)."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Okul ders programı")
        self.resize(560, 520)
        self.service = service
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.weekday = QComboBox()
        self.weekday.addItems(WEEKDAYS)
        self.period = QSpinBox()
        self.period.setRange(1, 14)
        self.start_time, self.end_time = make_time_edit(time(8, 30)), make_time_edit(time(9, 10))
        self.subject = QComboBox()
        for s in service.list_subjects():
            self.subject.addItem(s.name, s.id)
        add = QPushButton("Ekle / güncelle")
        add.clicked.connect(self._add)
        form.addRow("Gün", self.weekday)
        form.addRow("Ders saati no", self.period)
        form.addRow("Başlangıç", self.start_time)
        form.addRow("Bitiş", self.end_time)
        form.addRow("Ders", self.subject)
        form.addRow(add)
        root.addLayout(form)
        self.table = make_table(["Gün", "Saat no", "Başlangıç", "Bitiş", "Ders"])
        root.addWidget(self.table)
        delete = QPushButton("Seçiliyi sil")
        delete.clicked.connect(self._delete)
        root.addWidget(delete)
        self._reload()

    def _reload(self) -> None:
        names = {s.id: s.name for s in self.service.list_subjects()}
        entries = self.service.list_timetable()
        self.table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            set_row(self.table, r, [WEEKDAYS[e.weekday], str(e.period_no), e.start_time.strftime("%H:%M"),
                                    e.end_time.strftime("%H:%M"), names.get(e.subject_id, "?")], e.id)

    def _add(self) -> None:
        if self.subject.currentData() is None:
            QMessageBox.information(self, "Bilgi", "Önce Dersler sekmesinden ders ekleyin.")
            return
        self.service.set_timetable_entry(self.weekday.currentIndex(), self.period.value(),
                                         self.start_time.time().toPython(), self.end_time.time().toPython(),
                                         self.subject.currentData())
        self._reload()

    def _delete(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.delete_timetable_entry(key)
            self._reload()


class ExamDialog(QDialog):
    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sınavlar")
        self.resize(600, 560)
        self.service = service
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit()
        self.date = make_date_edit(date.today() + timedelta(days=14))
        self.topics = QListWidget()
        self.topics.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for subj in service.list_subjects():
            for t in service.list_topics(subj.id):
                item = QListWidgetItem(f"{subj.name} / {t.name}")
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self.topics.addItem(item)
        add = QPushButton("Sınav ekle")
        add.clicked.connect(self._add)
        form.addRow("Başlık", self.title)
        form.addRow("Tarih", self.date)
        form.addRow("Kapsadığı konular", self.topics)
        form.addRow(add)
        root.addLayout(form)
        self.table = make_table(["Sınav", "Tarih", "Konu sayısı"])
        root.addWidget(self.table)
        delete = QPushButton("Seçili sınavı sil")
        delete.clicked.connect(self._delete)
        root.addWidget(delete)
        self._reload()

    def _reload(self) -> None:
        exams = self.service.list_exams()
        self.table.setRowCount(len(exams))
        for r, e in enumerate(exams):
            set_row(self.table, r, [e.title, fmt_date(e.exam_date), str(len(e.topic_ids))], e.id)

    def _add(self) -> None:
        try:
            ids = [it.data(Qt.ItemDataRole.UserRole) for it in self.topics.selectedItems()]
            self.service.add_exam(self.title.text(), self.date.date().toPython(), topic_ids=ids)
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

    def __init__(self, service: PlannerService, view: SessionView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.view = service, view
        s = view.session
        self.setWindowTitle(view.title)
        self.resize(520, 520)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"<b>{view.title}</b> — {CLASS_LABEL[view.task_class]}<br>"
                              f"{fmt_date(s.session_date)} {s.start_time:%H:%M}–{s.end_time:%H:%M} "
                              f"({s.planned_minutes} dk, {s.slot_kind.value}) — durum: {s.status.value}"))
        why = QTextEdit(s.explanation or "-")
        why.setReadOnly(True)
        why.setMaximumHeight(110)
        root.addWidget(QLabel("Planlayıcı neden bu zamanı seçti?"))
        root.addWidget(why)
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
        task = service.get_task(s.task_id)
        if view.task_class is TaskClass.REVIEW and task is not None:
            box = QGroupBox("Hatırlama sonuçları (review tamamlanırsa gerekli)")
            grid = QFormLayout(box)
            for tid, label in zip(task.topic_ids, service.topic_labels(task.topic_ids)):
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
        bar = QHBoxLayout()
        done = QPushButton("Tamamlandı")
        skip = QPushButton("Atla")
        close = QPushButton("Kapat")
        done.clicked.connect(self._complete)
        skip.clicked.connect(self._skip)
        close.clicked.connect(self.reject)
        for b in (done, skip, close):
            bar.addWidget(b)
        done.setEnabled(s.status.value != "COMPLETED")
        root.addLayout(bar)

    def _complete(self) -> None:
        results = {tid: RecallResult(o.value() / 100.0, s.value()) for tid, (o, s) in self.rows.items()}
        try:
            self.service.complete_session(self.view.session.id, self.actual.value(), results or None,
                                          self.finished.isChecked())
        except ValueError as exc:
            show_error(self, exc)
            return
        self.accept()

    def _skip(self) -> None:
        self.service.skip_session(self.view.session.id)
        self.accept()


# ================================================================ calendar
class WeekCanvas(QWidget):
    """Custom-painted weekly time grid (7 day columns, hours as rows)."""
    sessionClicked = Signal(int)

    HOUR_START, HOUR_END, HOUR_H, LEFT, HEADER = 6, 24, 46, 54, 30

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.week_start = date.today()
        self.sessions: list[SessionView] = []
        self.blocks: list[AvailabilityBlock] = []
        self.now = datetime.now()
        self._hits: list[tuple[QRectF, SessionView]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(self.HEADER + (self.HOUR_END - self.HOUR_START) * self.HOUR_H + 4)

    def set_data(self, week_start: date, sessions: list[SessionView], blocks: list[AvailabilityBlock]) -> None:
        self.week_start, self.sessions, self.blocks, self.now = week_start, sessions, blocks, datetime.now()
        self.update()

    def _y(self, minute: float) -> float:
        return self.HEADER + (minute - self.HOUR_START * 60) / 60.0 * self.HOUR_H

    def _col_w(self) -> float:
        return (self.width() - self.LEFT) / 7.0

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.window())
        text_color, grid = pal.text().color(), QColor(128, 128, 128, 70)
        col_w = self._col_w()
        small = QFont(self.font())
        small.setPointSize(max(7, self.font().pointSize() - 1))
        p.setFont(small)

        for i in range(7):                                    # day headers + today highlight
            d = self.week_start + timedelta(days=i)
            x = self.LEFT + i * col_w
            if d == date.today():
                p.fillRect(QRectF(x, 0, col_w, self.height()), QColor(79, 124, 172, 22))
            p.setPen(text_color)
            p.drawText(QRectF(x, 0, col_w, self.HEADER), Qt.AlignmentFlag.AlignCenter,
                       f"{WEEKDAYS[i][:3]} {d.day} {MONTHS[d.month - 1][:3]}")
        for h in range(self.HOUR_START, self.HOUR_END + 1):   # hour grid
            y = self._y(h * 60)
            p.setPen(QPen(grid, 1))
            p.drawLine(int(self.LEFT), int(y), self.width(), int(y))
            p.setPen(text_color)
            p.drawText(QRectF(0, y - 8, self.LEFT - 6, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{h:02d}:00")
        for i in range(8):
            x = self.LEFT + i * col_w
            p.setPen(QPen(grid, 1))
            p.drawLine(int(x), self.HEADER, int(x), self.height())

        tint = {AvailabilityType.PRIMARY: QColor(76, 175, 80, 40), AvailabilityType.RESERVE: QColor(255, 193, 7, 55),
                AvailabilityType.UNAVAILABLE: QColor(120, 120, 120, 70)}
        for b in self.blocks:                                 # availability background
            i = (b.block_date - self.week_start).days
            if 0 <= i < 7:
                y1 = self._y(b.start_time.hour * 60 + b.start_time.minute)
                y2 = self._y(b.end_time.hour * 60 + b.end_time.minute)
                p.fillRect(QRectF(self.LEFT + i * col_w + 1, y1, col_w - 2, y2 - y1), tint[b.block_type])

        self._hits = []
        for v in self.sessions:                               # study sessions
            s = v.session
            i = (s.session_date - self.week_start).days
            if not 0 <= i < 7:
                continue
            y1 = self._y(s.start_time.hour * 60 + s.start_time.minute)
            y2 = self._y(s.end_time.hour * 60 + s.end_time.minute)
            rect = QRectF(self.LEFT + i * col_w + 3, y1 + 1, col_w - 6, max(14.0, y2 - y1 - 2))
            state = v.display_state(self.now)
            color = QColor(CLASS_COLOR[v.task_class])
            if state == "completed":
                color = QColor(120, 144, 156)
                color.setAlpha(150)
            elif state == "overdue":
                color.setAlpha(110)
            p.setBrush(color)
            p.setPen(QPen(QColor("#D32F2F"), 2) if state == "overdue" else Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 5, 5)
            p.setPen(QColor("white"))
            mark = "✓ " if state == "completed" else "! " if state == "overdue" else ""
            p.drawText(rect.adjusted(4, 2, -3, -2), Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                       f"{mark}{v.title}\n{s.start_time:%H:%M}–{s.end_time:%H:%M}")
            self._hits.append((rect, v))

        if self.week_start <= self.now.date() <= self.week_start + timedelta(days=6):   # now line
            i = (self.now.date() - self.week_start).days
            y = self._y(self.now.hour * 60 + self.now.minute)
            p.setPen(QPen(QColor("#E53935"), 2))
            p.drawLine(int(self.LEFT + i * col_w), int(y), int(self.LEFT + (i + 1) * col_w), int(y))
        p.end()

    def _hit(self, pos: QPointF) -> SessionView | None:
        for rect, v in reversed(self._hits):
            if rect.contains(pos):
                return v
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        v = self._hit(event.position())
        if v is not None and v.session.id is not None:
            self.sessionClicked.emit(v.session.id)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        v = self._hit(event.position())
        self.setToolTip("" if v is None else f"{v.title}\n{v.session.explanation}")


class CalendarView(QWidget):
    plan_changed = Signal()

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        prev_b, today_b, next_b = QPushButton("◀"), QPushButton("Bugün"), QPushButton("▶")
        self.label = QLabel()
        self.label.setStyleSheet("font-weight: 600; font-size: 15px;")
        plan_b = QPushButton("Planla / Yeniden planla")
        prev_b.clicked.connect(lambda: self._shift(-7))
        next_b.clicked.connect(lambda: self._shift(7))
        today_b.clicked.connect(self._go_today)
        plan_b.clicked.connect(self.replan)
        for w in (prev_b, today_b, next_b, self.label):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(plan_b)
        root.addLayout(bar)
        legend = QLabel(
            "<span style='color:#7E57C2'>■</span> Tekrar &nbsp; <span style='color:#EF6C00'>■</span> Teslim görevi &nbsp; "
            "<span style='color:#00897B'>■</span> Tekrarlayan &nbsp; <span style='color:#78909C'>■</span> Tamamlanan &nbsp; "
            "<span style='color:#D32F2F'>■</span> Gecikmiş/kaçırılan &nbsp;|&nbsp; "
            "<span style='color:#4CAF50'>▒</span> PRIMARY &nbsp; <span style='color:#FFC107'>▒</span> RESERVE "
            "&nbsp; <span style='color:#777'>▒</span> Kullanılamaz")
        root.addWidget(legend)
        self.summary = QLabel()
        root.addWidget(self.summary)
        self.canvas = WeekCanvas()
        self.canvas.sessionClicked.connect(self._open_session)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        root.addWidget(scroll, 1)
        self.refresh()

    def _shift(self, days: int) -> None:
        self.week_start += timedelta(days=days)
        self.refresh()

    def _go_today(self) -> None:
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())
        self.refresh()

    def refresh(self) -> None:
        end = self.week_start + timedelta(days=6)
        self.label.setText(f"{fmt_date(self.week_start)} – {fmt_date(end)} {end.year}")
        self.canvas.set_data(self.week_start, self.service.list_sessions(self.week_start, end),
                             self.service.list_availability(self.week_start, end))

    def replan(self) -> None:
        try:
            plan = self.service.replan()
        except Exception as exc:  # surfaced to the user, never silently swallowed
            show_error(self, exc)
            return
        self._show_summary(plan)
        self.refresh()
        self.plan_changed.emit()
        if plan.warnings or plan.unscheduled:
            lines = list(plan.warnings)
            lines += [f"• {u.title}: {u.minutes} dk yerleştirilemedi ({u.detail})" for u in plan.unscheduled[:12]]
            if len(plan.unscheduled) > 12:
                lines.append(f"… ve {len(plan.unscheduled) - 12} kalem daha")
            QMessageBox.information(self, "Plan uyarıları", "\n".join(lines))

    def _show_summary(self, plan: SchedulePlan) -> None:
        total = sum(s.minutes for s in plan.sessions)
        reserve = sum(s.minutes for s in plan.sessions if s.kind.value == "RESERVE")
        self.summary.setText(f"Plan: {len(plan.sessions)} oturum, {total} dk (RESERVE: {reserve} dk), "
                             f"yerleştirilemeyen: {len(plan.unscheduled)}")

    def _open_session(self, session_id: int) -> None:
        view = self.service.get_session(session_id)
        if view is None:
            return
        if SessionDialog(self.service, view, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.plan_changed.emit()
            if QMessageBox.question(self, "Yeniden planla", "Kalan planı güncel duruma göre yeniden hesaplayayım mı?"
                                    ) == QMessageBox.StandardButton.Yes:
                self.replan()


# ================================================================ subjects
class SubjectsView(QWidget):
    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("<b>Dersler</b>"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._load_subject())
        lv.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Ekle", self._add), ("Düzenle", self._rename), ("Sil", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lv.addLayout(row)

        right = QWidget()
        rv = QVBoxLayout(right)
        self.title = QLabel("Bir ders seçin")
        self.title.setStyleSheet("font-size: 18px; font-weight: 600;")
        rv.addWidget(self.title)
        head = QHBoxLayout()
        head.addWidget(QLabel("Öğrenme geçmişi (kronolojik)"))
        head.addStretch(1)
        new_b, del_b = QPushButton("Yeni öğrenme kaydı"), QPushButton("Kaydı sil")
        new_b.clicked.connect(self._new_event)
        del_b.clicked.connect(self._delete_event)
        head.addWidget(new_b)
        head.addWidget(del_b)
        rv.addLayout(head)
        self.events = make_table(["Tarih", "Ders saati", "Konu", "Not"])
        rv.addWidget(self.events, 3)
        rv.addWidget(QLabel("Konu hafıza durumu (bir sonraki ideal tekrar)"))
        self.memory = make_table(["Konu", "Aşama", "Stabilite (gün)", "Zorluk", "Son çalışma", "İdeal tekrar", "Tekrar sayısı"])
        rv.addWidget(self.memory, 2)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 760])
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        self.refresh()

    def current_subject_id(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def refresh(self) -> None:
        keep = self.current_subject_id()
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
        self._load_subject()

    def _load_subject(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            self.title.setText("Bir ders seçin")
            self.events.setRowCount(0)
            self.memory.setRowCount(0)
            return
        self.title.setText(self.list.currentItem().text())
        events = self.service.list_learning_events(sid)
        self.events.setRowCount(len(events))
        for r, v in enumerate(events):
            e = v.event
            period = "-" if e.period_start is None else (
                str(e.period_start) if e.period_end in (None, e.period_start) else f"{e.period_start}-{e.period_end}")
            set_row(self.events, r, [fmt_date(e.event_date), period, v.topic_name, e.notes], e.id)
        mem = self.service.list_memory(sid)
        self.memory.setRowCount(len(mem))
        for r, m in enumerate(mem):
            st = m.state
            set_row(self.memory, r, [m.topic_name, st.phase.value, f"{st.stability_days:.1f}", f"{st.difficulty:.2f}",
                                     fmt_date(st.last_review_date), fmt_date(st.next_review_date), str(st.review_count)])

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "Yeni ders", "Ders adı:")
        if ok:
            try:
                self.service.add_subject(name)
            except Exception as exc:
                show_error(self, ValueError("Ders eklenemedi (aynı isimde ders olabilir): " + str(exc)))
            self.refresh()

    def _rename(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            return
        name, ok = QInputDialog.getText(self, "Dersi düzenle", "Ders adı:", text=self.list.currentItem().text())
        if ok:
            try:
                self.service.rename_subject(sid, name)
            except Exception as exc:
                show_error(self, ValueError(str(exc)))
            self.refresh()

    def _delete(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            return
        if QMessageBox.question(self, "Dersi sil", "Dersin tüm konuları, öğrenme kayıtları ve tekrar görevleri "
                                "silinecek. Emin misiniz?") == QMessageBox.StandardButton.Yes:
            self.service.delete_subject(sid)
            self.refresh()

    def _new_event(self) -> None:
        sid = self.current_subject_id()
        if sid is None:
            QMessageBox.information(self, "Bilgi", "Önce bir ders seçin.")
            return
        if LearningEventDialog(self.service, sid, self).exec() == QDialog.DialogCode.Accepted:
            self._load_subject()

    def _delete_event(self) -> None:
        key = selected_key(self.events)
        if key is not None:
            self.service.delete_learning_event(key)
            self._load_subject()


# ================================================================== tasks
class TasksView(QWidget):
    FILTERS = [("Tümü", "all"), ("Tekrar", "review"), ("Teslim görevi", "deadline"),
               ("Tekrarlayan", "recurring"), ("Gecikmiş", "overdue"), ("Tamamlanan", "completed")]

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._tasks: dict[int, Task] = {}
        root = QVBoxLayout(self)
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
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = make_table(["Başlık", "Tür", "Kalan / süre", "Son tarih / ideal", "Öncelik", "Durum"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.table)
        detail = QGroupBox("Görev detayı")
        self.form = QFormLayout(detail)
        self.fields = {k: QLabel("-") for k in ("title", "type", "duration", "remaining", "priority", "deadline",
                                                 "ideal", "topics", "tags", "status")}
        for key, label in (("title", "Başlık"), ("type", "Tür"), ("duration", "Süre"), ("remaining", "Kalan süre"),
                           ("priority", "Öncelik"), ("deadline", "Son tarih"), ("ideal", "İdeal tekrar tarihi"),
                           ("topics", "Konular"), ("tags", "Etiketler"), ("status", "Durum")):
            self.fields[key].setWordWrap(True)
            self.form.addRow(label, self.fields[key])
        cancel_b, delete_b = QPushButton("Görevi iptal et"), QPushButton("Görevi sil")
        cancel_b.clicked.connect(self._cancel)
        delete_b.clicked.connect(self._delete)
        self.form.addRow(cancel_b)
        self.form.addRow(delete_b)
        split.addWidget(detail)
        split.setSizes([700, 320])
        root.addWidget(split, 1)
        self.refresh()

    def refresh(self) -> None:
        tasks = self.service.list_tasks(self.filter.currentData(), date.today())
        self._tasks = {t.id: t for t in tasks if t.id is not None}
        self.table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            overdue = t.is_overdue(date.today())
            when = fmt_date(t.deadline) if t.deadline else fmt_date(t.ideal_date) if t.ideal_date else (
                t.recurring_rule.describe() if t.recurring_rule else "-")
            set_row(self.table, r, [t.title, CLASS_LABEL[t.task_class],
                                    f"{t.remaining_duration}/{t.duration} dk", when, str(t.priority),
                                    "Gecikmiş" if overdue else STATUS_LABEL[t.status]], t.id)
            if overdue:
                for c in range(self.table.columnCount()):
                    self.table.item(r, c).setForeground(QColor("#D32F2F"))
        self._show_detail()

    def _show_detail(self) -> None:
        key = selected_key(self.table)
        t = self._tasks.get(key) if key is not None else None
        f = self.fields
        if t is None:
            for lab in f.values():
                lab.setText("-")
            return
        f["title"].setText(t.title)
        f["type"].setText(CLASS_LABEL[t.task_class] + (f" ({t.review_source.value.lower()})" if t.review_source else ""))
        f["duration"].setText(f"{t.duration} dk" + ("  (bölünebilir, min " + str(t.minimum_session) + " dk)"
                                                    if t.splittable else ""))
        f["remaining"].setText(f"{t.remaining_duration} dk")
        f["priority"].setText(str(t.priority))
        f["deadline"].setText(fmt_date(t.deadline))
        ideal = fmt_date(t.ideal_date)
        if t.earliest_date and t.latest_date:
            ideal += f"  (pencere: {fmt_date(t.earliest_date)} – {fmt_date(t.latest_date)})"
        f["ideal"].setText(ideal if t.ideal_date else "-")
        f["topics"].setText(", ".join(self.service.topic_labels(t.topic_ids)) or "-")
        f["tags"].setText(", ".join(t.tags) or "-")
        f["status"].setText("Gecikmiş" if t.is_overdue(date.today()) else STATUS_LABEL[t.status])

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
        if key is not None and QMessageBox.question(self, "Sil", "Görev kalıcı olarak silinsin mi?"
                                                    ) == QMessageBox.StandardButton.Yes:
            self.service.delete_task(key)
            self.refresh()


# ============================================================== main window
class MainWindow(QMainWindow):
    def __init__(self, service: PlannerService) -> None:
        super().__init__()
        self.service = service
        self.setWindowTitle("Dinamik Akademik Çalışma Planlayıcı")
        self.resize(1200, 780)
        self.calendar = CalendarView(service)
        self.subjects = SubjectsView(service)
        self.tasks = TasksView(service)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.calendar, "Takvim")
        self.tabs.addTab(self.subjects, "Dersler")
        self.tabs.addTab(self.tasks, "Görevler")
        self.tabs.currentChanged.connect(self._on_tab)
        self.setCentralWidget(self.tabs)
        self.calendar.plan_changed.connect(self.tasks.refresh)

        menu = self.menuBar().addMenu("Planlama")
        menu.addAction("Yeniden planla", self.calendar.replan)
        menu.addSeparator()
        menu.addAction("Çalışma zamanları (müsaitlik)…", lambda: self._dialog(AvailabilityDialog))
        menu.addAction("Okul ders programı…", lambda: self._dialog(TimetableDialog))
        menu.addAction("Sınavlar…", lambda: self._dialog(ExamDialog))
        self.statusBar().showMessage("Hazır")

    def _dialog(self, cls: type[QDialog]) -> None:
        cls(self.service, self).exec()
        self.calendar.refresh()

    def _on_tab(self, index: int) -> None:
        (self.calendar, self.subjects, self.tasks)[index].refresh()
