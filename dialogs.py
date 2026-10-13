"""dialogs.py - Planlama girdileri, oturum tamamlama ve ünite iletişim pencereleri."""
from __future__ import annotations

import json
from datetime import date, time, timedelta
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget
)

from engine import (
    AvailabilityType, PlannerService, RecallResult, RecurrenceKind,
    RecurringRule, SchoolLesson, SessionView, TaskClass, Unit
)
from ui_common import (
    AVAIL_LABEL, CLASS_LABEL, WEEKDAYS, buttons, fmt_date,
    make_date_edit, make_table, make_time_edit, selected_key, set_row, show_error
)

DAY_MAP = {
    "pazartesi": 0, "pzt": 0, "monday": 0, "mon": 0,
    "salı": 1, "sali": 1, "sal": 1, "tuesday": 1, "tue": 1,
    "çarşamba": 2, "carsamba": 2, "çar": 2, "car": 2, "wednesday": 2, "wed": 2,
    "perşembe": 3, "persembe": 3, "per": 3, "thursday": 3, "thu": 3,
    "cuma": 4, "cum": 4, "friday": 4, "fri": 4,
    "cumartesi": 5, "cmt": 5, "saturday": 5, "sat": 5,
    "pazar": 6, "paz": 6, "sunday": 6, "sun": 6,
}


def parse_time_str(time_str: str) -> time:
    """Saat metnini time nesnesine donusturur."""
    parts = [int(p) for p in time_str.strip().split(":")[:2]]
    return time(parts[0], parts[1])


class UnitDialog(QDialog):
    """Yeni ünite ekleme veya mevcut üniteyi düzenleme penceresi."""

    def __init__(
        self,
        service: PlannerService,
        subject_id: int,
        unit: Unit | None = None,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.subject_id = subject_id
        self.unit = unit
        self._setup_window()
        self._setup_form()
        self._setup_buttons()

    def _setup_window(self) -> None:
        title = "Üniteyi Düzenle" if self.unit else "Yeni Ünite Ekle"
        self.setWindowTitle(title)
        self.resize(380, 220)

    def _setup_form(self) -> None:
        self._form = QFormLayout(self)
        self.name_edit = QLineEdit()
        if self.unit:
            self.name_edit.setText(self.unit.name)
        self._form.addRow("Ünite Adı", self.name_edit)

        self.order_spin = QSpinBox()
        self.order_spin.setRange(1, 99)
        if self.unit:
            self.order_spin.setValue(self.unit.order_no)
        else:
            existing = self.service.list_units(self.subject_id)
            next_order = max((u.order_no for u in existing), default=0) + 1
            self.order_spin.setValue(next_order)
        self._form.addRow("Sıra No", self.order_spin)

        # Başlangıç ve Bitiş tarihleri (isteğe bağlı)
        self.start_check = QCheckBox("Başlangıç tarihi belirt")
        initial_start = self.unit.start_date if self.unit and self.unit.start_date else date.today()
        self.start_edit = make_date_edit(initial_start)
        self.start_check.setChecked(bool(self.unit and self.unit.start_date))
        self.start_edit.setEnabled(self.start_check.isChecked())
        self.start_check.toggled.connect(self.start_edit.setEnabled)

        row_start = QHBoxLayout()
        row_start.addWidget(self.start_check)
        row_start.addWidget(self.start_edit)
        self._form.addRow("Başlangıç", row_start)

        self.end_check = QCheckBox("Bitiş tarihi belirt")
        initial_end = self.unit.end_date if self.unit and self.unit.end_date else date.today() + timedelta(days=30)
        self.end_edit = make_date_edit(initial_end)
        self.end_check.setChecked(bool(self.unit and self.unit.end_date))
        self.end_edit.setEnabled(self.end_check.isChecked())
        self.end_check.toggled.connect(self.end_edit.setEnabled)

        row_end = QHBoxLayout()
        row_end.addWidget(self.end_check)
        row_end.addWidget(self.end_edit)
        self._form.addRow("Bitiş", row_end)

    def _setup_buttons(self) -> None:
        self._form.addRow(buttons(self))

    def accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            show_error(self, ValueError("Ünite adı boş olamaz."))
            return

        start_d = self.start_edit.date().toPython() if self.start_check.isChecked() else None
        end_d = self.end_edit.date().toPython() if self.end_check.isChecked() else None
        order = self.order_spin.value()

        try:
            if self.unit and self.unit.id is not None:
                self.service.update_unit(
                    self.unit.id,
                    name=name,
                    order_no=order,
                    start_date=start_d,
                    end_date=end_d
                )
            else:
                self.service.add_unit(
                    self.subject_id,
                    name=name,
                    order_no=order,
                    start_date=start_d,
                    end_date=end_d
                )
        except Exception as exc:
            show_error(self, exc)
            return

        super().accept()


class LearningEventDialog(QDialog):
    """Derste işlenen konuyu kaydetme penceresi (Ünite ve Alt Konu seçimiyle)."""

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
        self.resize(420, 260)

    def _setup_form(self) -> None:
        self._form = QFormLayout(self)

    def _setup_fields(self, lesson: SchoolLesson) -> None:
        self._setup_labels(lesson)
        self._setup_unit(lesson)
        self._setup_topic(lesson)
        self._setup_notes()
        self._add_field_rows()

    def _setup_labels(self, lesson: SchoolLesson) -> None:
        self.date_label = QLabel(fmt_date(lesson.lesson_date))
        self.subject_label = QLabel(lesson.subject_name)
        self.ordinal_label = QLabel(
            f"Bu haftaki {lesson.subject_lesson_no}. {lesson.subject_name} dersi"
        )

    def _setup_unit(self, lesson: SchoolLesson) -> None:
        self.unit = QComboBox()
        self.unit.setEditable(True)
        self.unit.addItem("", None)
        units = self.service.list_units(lesson.subject_id)
        for u in units:
            self.unit.addItem(u.name, u.id)
        self.unit.setCurrentText("")
        self.unit.currentTextChanged.connect(self._on_unit_changed)

    def _setup_topic(self, lesson: SchoolLesson) -> None:
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self._reload_topics()
        self.topic.setCurrentText("")

    def _reload_topics(self) -> None:
        self.topic.clear()
        selected_unit_id = self.unit.currentData()
        topics = self.service.list_topics(self.lesson.subject_id, unit_id=selected_unit_id)
        self.topic.addItems([t.name for t in topics])

    def _on_unit_changed(self, text: str) -> None:
        curr_topic = self.topic.currentText()
        self._reload_topics()
        self.topic.setCurrentText(curr_topic)

    def _setup_notes(self) -> None:
        self.notes = QLineEdit()

    def _add_field_rows(self) -> None:
        self._form.addRow("Tarih", self.date_label)
        self._form.addRow("Ders", self.subject_label)
        self._form.addRow("Haftalık sıra", self.ordinal_label)
        self._form.addRow("Ünite (seç ya da yeni yaz)", self.unit)
        self._form.addRow("Konu (seç ya da yeni yaz)", self.topic)
        self._form.addRow("Not", self.notes)

    def _setup_buttons(self) -> None:
        self._form.addRow(buttons(self))

    def accept(self) -> None:
        topic_name = self.topic.currentText().strip()
        if not topic_name:
            show_error(self, ValueError("Konu adı boş olamaz."))
            return

        unit_name = self.unit.currentText().strip()
        unit_id = None
        if unit_name:
            try:
                unit = self.service.get_or_create_unit(self.lesson.subject_id, unit_name)
                unit_id = unit.id
            except Exception as exc:
                show_error(self, exc)
                return

        try:
            self.service.add_learning_event(
                self.lesson.subject_id,
                self.lesson.lesson_date,
                topic_name,
                self.lesson.subject_lesson_no,
                notes=self.notes.text(),
                unit_id=unit_id
            )
        except ValueError as exc:
            show_error(self, exc)
            return

        super().accept()


class TaskDialog(QDialog):
    """Görev ekleme penceresi."""

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
            units_map = {u.id: u.name for u in self.service.list_units(subj.id) if u.id is not None}
            for t in self.service.list_topics(subj.id):
                unit_str = f" [{units_map[t.unit_id]}]" if t.unit_id and t.unit_id in units_map else ""
                item = QListWidgetItem(f"{subj.name}{unit_str} / {t.name}")
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


class TimetableImportDialog(QDialog):
    """JSON formatındaki ders programını içe aktarma penceresi."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Ders Programını JSON'dan İçe Aktar")
        self.resize(620, 500)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        info_lbl = QLabel(
            "<b>Ders programı JSON dosyasını seçin</b> veya içeriğini metin alanına yapıştırın:"
        )
        info_lbl.setWordWrap(True)
        root.addWidget(info_lbl)

        btn_row = QHBoxLayout()
        pick_file_btn = QPushButton("📁 JSON Dosyası Seç…")
        pick_file_btn.clicked.connect(self._pick_file)
        btn_row.addWidget(pick_file_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.text_edit = QTextEdit()
        placeholder = (
            "Örnek format:\n"
            '{\n'
            '  "program": [\n'
            '    {\n'
            '      "gun": "Pazartesi",\n'
            '      "dersler": [\n'
            '        {"saat_no": 1, "baslangic": "08:20", "bitis": "09:00", "ders": "Matematik"}\n'
            '      ]\n'
            '    }\n'
            '  ]\n'
            '}'
        )
        self.text_edit.setPlaceholderText(placeholder)
        root.addWidget(self.text_edit, 1)

        self.chk_clear_existing = QCheckBox("İçe aktarmadan önce mevcut programı temizle")
        self.chk_clear_existing.setChecked(True)
        root.addWidget(self.chk_clear_existing)

        bottom_buttons = QHBoxLayout()
        btn_import = QPushButton("Programı İçe Aktar")
        btn_import.setProperty("primary", True)
        btn_import.clicked.connect(self._do_import)

        btn_cancel = QPushButton("Vazgeç")
        btn_cancel.clicked.connect(self.reject)

        bottom_buttons.addStretch(1)
        bottom_buttons.addWidget(btn_cancel)
        bottom_buttons.addWidget(btn_import)
        root.addLayout(bottom_buttons)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Ders Programı JSON Dosyası Seç",
            "",
            "JSON Dosyaları (*.json);;Tüm Dosyalar (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.text_edit.setPlainText(content)
        except Exception as exc:
            show_error(self, exc)

    def _do_import(self) -> None:
        content = self.text_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir JSON dosyası seçin veya JSON metnini yapıştırın.")
            return

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            sep = chr(125) + chr(123)
            idx = content.find(sep)
            if idx != -1:
                try:
                    data = json.loads(content[:idx + 1])
                except Exception as exc:
                    show_error(self, ValueError(f"JSON sözdizimi hatalı: {exc}"))
                    return
            else:
                show_error(self, ValueError("Geçerli bir JSON formatı bulunamadı."))
                return

        days_list: list = []
        if isinstance(data, dict):
            days_list = data.get("program") or data.get("gunler") or []
        elif isinstance(data, list):
            days_list = data

        if not days_list:
            QMessageBox.warning(self, "Uyarı", "JSON içerisinde program listesi bulunamadı.")
            return

        if self.chk_clear_existing.isChecked():
            existing_entries = self.service.list_timetable()
            for e in existing_entries:
                self.service.delete_timetable_entry(e.id)

        existing_subjects = {s.name.strip().lower(): s.id for s in self.service.list_subjects() if s.id is not None}

        imported_count = 0
        new_subjects_added = 0

        for day_entry in days_list:
            if not isinstance(day_entry, dict):
                continue

            gun_raw = str(day_entry.get("gun", "") or day_entry.get("day", "")).strip().lower()
            weekday_idx = DAY_MAP.get(gun_raw)
            if weekday_idx is None:
                continue

            lessons = day_entry.get("dersler", []) or day_entry.get("lessons", [])
            for item in lessons:
                if not isinstance(item, dict):
                    continue

                ders_name = str(item.get("ders", "") or item.get("subject", "") or item.get("name", "")).strip()
                if not ders_name:
                    continue

                try:
                    period_no = int(item.get("saat_no", 1) or item.get("period", 1))
                    start_str = str(item.get("baslangic", "") or item.get("start", ""))
                    end_str = str(item.get("bitis", "") or item.get("end", ""))
                    start_t = parse_time_str(start_str)
                    end_t = parse_time_str(end_str)
                except Exception:
                    continue

                ders_key = ders_name.lower()
                if ders_key not in existing_subjects:
                    try:
                        self.service.add_subject(ders_name)
                        new_subjects_added += 1
                        existing_subjects = {s.name.strip().lower(): s.id for s in self.service.list_subjects() if s.id is not None}
                    except Exception:
                        pass

                subj_id = existing_subjects.get(ders_key)
                if subj_id is None:
                    continue

                self.service.set_timetable_entry(
                    weekday_idx,
                    period_no,
                    start_t,
                    end_t,
                    subj_id
                )
                imported_count += 1

        msg = f"Ders programı başarıyla yüklendi!\n\n• Toplam {imported_count} ders saati işlendi."
        if new_subjects_added > 0:
            msg += f"\n• {new_subjects_added} yeni ders sisteminize otomatik eklendi."

        QMessageBox.information(self, "Başarılı", msg)
        self.accept()


class TimetableDialog(QDialog):
    """Haftalık okul ders programı penceresi."""

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Okul ders programı")
        self.resize(600, 540)
        self.service = service

        root = QVBoxLayout(self)
        self._setup_form(root)
        self._setup_table(root)
        self._setup_bottom_buttons(root)
        self._reload()

    def _setup_form(self, root: QVBoxLayout) -> None:
        form = QFormLayout()
        self._setup_schedule_fields(form)
        self._setup_subject_field(form)
        root.addLayout(form)
        self._setup_schedule_button(root)

    def _setup_schedule_fields(self, form: QFormLayout) -> None:
        self.weekday = QComboBox()
        self.weekday.addItems(WEEKDAYS)

        self.period = QSpinBox()
        self.period.setRange(1, 14)

        self.start_time = make_time_edit(time(8, 20))
        self.end_time = make_time_edit(time(9, 0))

        form.addRow("Gün", self.weekday)
        form.addRow("Ders saati no", self.period)
        form.addRow("Başlangıç", self.start_time)
        form.addRow("Bitiş", self.end_time)

    def _setup_subject_field(self, form: QFormLayout) -> None:
        self.subject = QComboBox()
        self._reload_subjects()
        form.addRow("Ders", self.subject)

    def _reload_subjects(self) -> None:
        self.subject.clear()
        for s in self.service.list_subjects():
            self.subject.addItem(s.name, s.id)

    def _setup_schedule_button(self, root: QVBoxLayout) -> None:
        btn_row = QHBoxLayout()

        add = QPushButton("Ekle / güncelle")
        add.clicked.connect(self._add)

        import_btn = QPushButton("📥 JSON'dan İçe Aktar…")
        import_btn.setProperty("primary", True)
        import_btn.clicked.connect(self._open_import_dialog)

        btn_row.addWidget(add)
        btn_row.addWidget(import_btn)
        root.addLayout(btn_row)

    def _setup_table(self, root: QVBoxLayout) -> None:
        self.table = make_table([
            "Gün", "Saat no", "Başlangıç", "Bitiş", "Ders"
        ])
        root.addWidget(self.table)

    def _setup_bottom_buttons(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()

        delete = QPushButton("Seçiliyi sil")
        delete.clicked.connect(self._delete)

        clear_all = QPushButton("Tüm Programı Temizle")
        clear_all.setStyleSheet("color: #DC2626;")
        clear_all.clicked.connect(self._clear_all)

        row.addWidget(delete)
        row.addStretch(1)
        row.addWidget(clear_all)
        root.addLayout(row)

    def _reload(self) -> None:
        self._reload_subjects()
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

    def _clear_all(self) -> None:
        entries = self.service.list_timetable()
        if not entries:
            return

        if QMessageBox.question(
            self,
            "Tüm Programı Sil",
            "Tüm haftalık ders programı silinecek. Emin misiniz?"
        ) == QMessageBox.StandardButton.Yes:
            for e in entries:
                self.service.delete_timetable_entry(e.id)
            self._reload()

    def _open_import_dialog(self) -> None:
        dlg = TimetableImportDialog(self.service, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
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
            units_map = {u.id: u.name for u in self.service.list_units(subj.id) if u.id is not None}
            for t in self.service.list_topics(subj.id):
                unit_str = f" [{units_map[t.unit_id]}]" if t.unit_id and t.unit_id in units_map else ""
                item = QListWidgetItem(f"{subj.name}{unit_str} / {t.name}")
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