"""dialogs.py - Planlama girdileri ve oturum tamamlama iletişim pencereleri."""
from __future__ import annotations

from datetime import date, time, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget
)

from engine import (
    AvailabilityType, PlannerService, RecallResult, RecurrenceKind,
    RecurringRule, SchoolLesson, SessionView, TaskClass
)
from ui_common import (
    AVAIL_LABEL, CLASS_LABEL, WEEKDAYS, buttons, fmt_date,
    make_date_edit, make_table, make_time_edit, selected_key, set_row, show_error
)


class LearningEventDialog(QDialog):
    """Derste işlenen konuyu kaydetme penceresi."""

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
    """Görev ekleme penceresi (deadline, recurring veya manual review)."""

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
    """Müsaitlik aralıklarını yönetme penceresi."""

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
    """Haftalık okul ders programı penceresi."""

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
    """Sınav tanımlama penceresi."""

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
    """Oturum detayı ve sonuç kaydetme penceresi."""

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

        root.addWidget(QLabel("Planlayıcı neden bu zamanı seçti?"))
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

        box = QGroupBox("Hatırlama sonuçları (review tamamlanırsa gerekli)")
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

        done.setEnabled(s.status.value != "COMPLETED")
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