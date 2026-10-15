"""dialogs.py - Modern minimalist arayüzlü planlama, ünite ve oturum iletişim pencereleri."""
from __future__ import annotations

import json
from datetime import date, time, timedelta
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
    QTableWidget, QTextEdit, QVBoxLayout, QWidget
)

from engine import (
    AvailabilityType, PlannerService, RecallResult, RecurrenceKind,
    RecurringRule, SchoolLesson, SessionView, TaskClass, Unit
)
from ui_common import (
    AVAIL_LABEL, CLASS_LABEL, WEEKDAYS, fmt_date,
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


# ==============================================================================
# 🎨 DİYALOG YARDIMCILARI & MODERN STİL BİLEŞENLERİ
# ==============================================================================

DIALOG_STYLESHEET = """
QDialog {
    background-color: #FFFFFF;
}
QLabel {
    color: #1E293B;
}
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QTextEdit {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 7px 10px;
    color: #0F172A;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QTextEdit:focus {
    background-color: #FFFFFF;
    border: 1.5px solid #1A73E8;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    outline: none;
}
QListWidget {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 6px;
    outline: none;
}
QListWidget::item {
    padding: 7px 10px;
    border-radius: 6px;
    color: #1E293B;
    margin-bottom: 2px;
}
QListWidget::item:hover {
    background-color: #F1F5F9;
}
QListWidget::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
    font-weight: 600;
}
QCheckBox {
    font-size: 13px;
    color: #334155;
    spacing: 8px;
}
QGroupBox {
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 700;
    font-size: 13px;
    color: #0F172A;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #475569;
}
QPushButton {
    background-color: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
    color: #334155;
}
QPushButton:hover {
    background-color: #E2E8F0;
    color: #0F172A;
}
QPushButton[primary="true"] {
    background-color: #18181B;
    border: 1px solid #18181B;
    color: #FFFFFF;
}
QPushButton[primary="true"]:hover {
    background-color: #27272A;
}
"""


def create_dialog_header(title: str, subtitle: str, badge_text: str = "") -> QWidget:
    """Diyalog pencereleri için şık üst başlık bandı oluşturur."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(3)

    top_row = QHBoxLayout()
    lbl_title = QLabel(title)
    lbl_title.setStyleSheet("font-size: 17px; font-weight: 800; color: #0F172A; border: none;")
    top_row.addWidget(lbl_title)

    if badge_text:
        badge = QLabel(badge_text)
        badge.setStyleSheet("""
            background-color: #EFF6FF;
            color: #1D4ED8;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            border: 1px solid #DBEAFE;
        """)
        top_row.addWidget(badge)

    top_row.addStretch(1)
    layout.addLayout(top_row)

    lbl_sub = QLabel(subtitle)
    lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; border: none;")
    layout.addWidget(lbl_sub)

    div = QFrame()
    div.setFrameShape(QFrame.Shape.HLine)
    div.setStyleSheet("color: #F1F5F9; margin-top: 6px;")
    layout.addWidget(div)

    return container


def create_dialog_buttons(dialog: QDialog, save_text: str = "Kaydet", cancel_text: str = "Vazgeç") -> QHBoxLayout:
    """Modern Vazgeç ve Kaydet butonları satırı oluşturur."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 12, 0, 0)
    row.setSpacing(8)

    btn_cancel = QPushButton(cancel_text)
    btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_cancel.clicked.connect(dialog.reject)

    btn_save = QPushButton(save_text)
    btn_save.setProperty("primary", True)
    btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_save.clicked.connect(dialog.accept)

    row.addStretch(1)
    row.addWidget(btn_cancel)
    row.addWidget(btn_save)
    return row


# ==============================================================================
# 1. ÜNİTE DİYALOĞU (UnitDialog)
# ==============================================================================

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
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle("Üniteyi Düzenle" if self.unit else "Yeni Ünite Ekle")
        self.resize(400, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        header = create_dialog_header(
            "Üniteyi Düzenle" if self.unit else "Yeni Ünite Ekle",
            "Müfredat konularınızı tarihli üniteler altında toplayın."
        )
        root.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Örn: 2. Ünite - Fonksiyonlar")
        if self.unit:
            self.name_edit.setText(self.unit.name)
        form.addRow("Ünite Adı", self.name_edit)

        self.order_spin = QSpinBox()
        self.order_spin.setRange(1, 99)
        if self.unit:
            self.order_spin.setValue(self.unit.order_no)
        else:
            existing = self.service.list_units(self.subject_id)
            next_order = max((u.order_no for u in existing), default=0) + 1
            self.order_spin.setValue(next_order)
        form.addRow("Sıra No", self.order_spin)

        self.start_check = QCheckBox("Başlangıç tarihi")
        init_start = self.unit.start_date if self.unit and self.unit.start_date else date.today()
        self.start_edit = make_date_edit(init_start)
        self.start_check.setChecked(bool(self.unit and self.unit.start_date))
        self.start_edit.setEnabled(self.start_check.isChecked())
        self.start_check.toggled.connect(self.start_edit.setEnabled)

        row_s = QHBoxLayout()
        row_s.addWidget(self.start_check)
        row_s.addWidget(self.start_edit)
        form.addRow("Başlangıç", row_s)

        self.end_check = QCheckBox("Bitiş tarihi")
        init_end = self.unit.end_date if self.unit and self.unit.end_date else date.today() + timedelta(days=30)
        self.end_edit = make_date_edit(init_end)
        self.end_check.setChecked(bool(self.unit and self.unit.end_date))
        self.end_edit.setEnabled(self.end_check.isChecked())
        self.end_check.toggled.connect(self.end_edit.setEnabled)

        row_e = QHBoxLayout()
        row_e.addWidget(self.end_check)
        row_e.addWidget(self.end_edit)
        form.addRow("Bitiş", row_e)

        root.addLayout(form)
        root.addLayout(create_dialog_buttons(self, "Kaydet", "Vazgeç"))

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


# ==============================================================================
# 2. ÖĞRENME KAYDI & KAZANIM SEÇİM DİYALOĞU (LearningEventDialog)
# ==============================================================================

class LearningEventDialog(QDialog):
    """Derste işlenen ünite, konu, alt konu ve kazanımları kaydetme penceresi."""

    def __init__(
        self,
        service: PlannerService,
        lesson: SchoolLesson,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.lesson = lesson
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle("Derste İşlenen Konuyu Kaydet")
        self.resize(500, 600)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        header = create_dialog_header(
            "Derste İşlenen Konuyu Kaydet",
            f"{lesson.subject_name} • {fmt_date(lesson.lesson_date)} (Bu haftaki {lesson.subject_lesson_no}. ders)",
            badge_text=f"{lesson.period_no}. Saat"
        )
        root.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        # 1. Ünite Seçimi
        self.unit_combo = QComboBox()
        self.unit_combo.setEditable(True)
        self.unit_combo.addItem("— Ünitesiz / Genel —", None)
        units = self.service.list_units(lesson.subject_id)
        for u in units:
            self.unit_combo.addItem(f"{u.order_no}. Ünite: {u.name}", u.id)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        form.addRow("Ünite", self.unit_combo)

        # 2. Ana Konu Seçimi
        self.topic_combo = QComboBox()
        self.topic_combo.setEditable(True)
        self.topic_combo.currentIndexChanged.connect(self._on_topic_changed)
        form.addRow("Konu", self.topic_combo)

        # 3. Alt Konu Seçimi
        self.subtopic_combo = QComboBox()
        self.subtopic_combo.setEditable(True)
        self.subtopic_combo.currentIndexChanged.connect(self._on_subtopic_changed)
        form.addRow("Alt Konu", self.subtopic_combo)

        # 4. Not
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("İsteğe bağlı ders notu veya sayfa aralığı...")
        form.addRow("Ders Notu", self.notes_edit)
        root.addLayout(form)

        # 5. Kazanımlar Kontrol Listesi (Checklist)
        box_outcomes = QGroupBox("Bu Derste İşlenen Kazanımlar / Beceriler")
        box_layout = QVBoxLayout(box_outcomes)
        box_layout.setContentsMargins(10, 14, 10, 10)
        box_layout.setSpacing(6)

        self.outcomes_list = QListWidget()
        self.outcomes_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        box_layout.addWidget(self.outcomes_list, 1)

        btn_add_outcome = QPushButton("+ Yeni Kazanım Tanımla…")
        btn_add_outcome.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        btn_add_outcome.clicked.connect(self._prompt_add_outcome)
        box_layout.addWidget(btn_add_outcome)

        root.addWidget(box_outcomes, 1)

        # Butonlar
        root.addLayout(create_dialog_buttons(self, "Dersi Kaydet", "Vazgeç"))

        self._reload_topics()

    def _on_unit_changed(self) -> None:
        self._reload_topics()

    def _reload_topics(self) -> None:
        self.topic_combo.clear()
        unit_id = self.unit_combo.currentData()
        topics = self.service.list_topics(self.lesson.subject_id, unit_id=unit_id)
        for t in topics:
            self.topic_combo.addItem(t.name, t.id)
        self._reload_subtopics()

    def _on_topic_changed(self) -> None:
        self._reload_subtopics()

    def _reload_subtopics(self) -> None:
        self.subtopic_combo.clear()
        topic_id = self.topic_combo.currentData()
        if topic_id:
            subtopics = self.service.list_subtopics(topic_id)
            for st in subtopics:
                self.subtopic_combo.addItem(st.name, st.id)
        self._reload_outcomes()

    def _on_subtopic_changed(self) -> None:
        self._reload_outcomes()

    def _reload_outcomes(self) -> None:
        self.outcomes_list.clear()
        subtopic_id = self.subtopic_combo.currentData()
        if not subtopic_id:
            return

        outcomes = self.service.list_outcomes(subtopic_id)
        for o in outcomes:
            code_str = f"[{o.code}] " if o.code else ""
            item = QListWidgetItem(f"{code_str}{o.description}")
            item.setData(Qt.ItemDataRole.UserRole, o.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.outcomes_list.addItem(item)

    def _prompt_add_outcome(self) -> None:
        subtopic_id = self.subtopic_combo.currentData()
        if not subtopic_id:
            QMessageBox.information(self, "Bilgi", "Önce bir alt konu seçin veya oluşturun.")
            return

        desc, ok = QInputDialog.getText(self, "Yeni Kazanım Ekle", "Kazanım / Öğrenme Çıktısı Açıklaması:")
        if ok and desc.strip():
            self.service.add_outcome(subtopic_id, desc.strip())
            self._reload_outcomes()

    def accept(self) -> None:
        topic_name = self.topic_combo.currentText().strip()
        if not topic_name:
            show_error(self, ValueError("Lütfen işlenen konu adını girin."))
            return

        # Ünite ID
        unit_id = self.unit_combo.currentData()
        unit_raw = self.unit_combo.currentText().strip()
        if unit_id is None and unit_raw and not unit_raw.startswith("—"):
            unit = self.service.get_or_create_unit(self.lesson.subject_id, unit_raw)
            unit_id = unit.id

        subtopic_name = self.subtopic_combo.currentText().strip() or None

        # İşaretlenen kazanımlar
        selected_outcome_ids = []
        for i in range(self.outcomes_list.count()):
            it = self.outcomes_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                selected_outcome_ids.append(it.data(Qt.ItemDataRole.UserRole))

        try:
            self.service.add_learning_event(
                subject_id=self.lesson.subject_id,
                event_date=self.lesson.lesson_date,
                topic_name=topic_name,
                period_start=self.lesson.period_no,
                notes=self.notes_edit.text(),
                unit_id=unit_id,
                subtopic_name=subtopic_name,
                outcome_ids=selected_outcome_ids
            )
        except Exception as exc:
            show_error(self, exc)
            return

        super().accept()


# ==============================================================================
# 3. GÖREV EKLEME DİYALOĞU (TaskDialog)
# ==============================================================================

class TaskDialog(QDialog):
    """Yeni teslim görevi, tekrarlayan rutin veya tekrar ekleme penceresi."""

    def __init__(
        self,
        service: PlannerService,
        mode: str,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service, self.mode = service, mode
        self.setStyleSheet(DIALOG_STYLESHEET)

        titles = {
            "deadline": ("Yeni Teslim Görevi", "Belirli bir son tarihi olan proje, ödev veya çalışma görevi.", "TESLİM"),
            "recurring": ("Yeni Tekrarlayan Görev", "Belirli günlerde tekrarlanan rutin çalışma veya alışkanlık.", "RUTİN"),
            "review": ("Yeni Manuel Tekrar", "Hafıza motorundan bağımsız özel bir tekrar görevi planlayın.", "TEKRAR")
        }
        title_txt, sub_txt, badge = titles.get(self.mode, ("Görev Ekle", "", ""))
        self.setWindowTitle(title_txt)
        self.resize(480, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        root.addWidget(create_dialog_header(title_txt, sub_txt, badge))

        form = QFormLayout()
        form.setSpacing(10)

        self.title = QLineEdit()
        self.title.setPlaceholderText("Örn: Limit & Süreklilik Soru Çözümü")
        form.addRow("Başlık", self.title)

        self.duration = QSpinBox()
        self.duration.setRange(5, 1440)
        self.duration.setValue(45)
        self.duration.setSuffix(" dk")
        form.addRow("Süre", self.duration)

        self.priority = QSpinBox()
        self.priority.setRange(1, 10)
        self.priority.setValue(5)
        form.addRow("Öncelik (1-10)", self.priority)

        self.tags = QLineEdit()
        self.tags.setPlaceholderText("#YKS, #Okul, #SoruBankası")
        form.addRow("Etiketler", self.tags)

        # Modlara Özel Alanlar
        if self.mode == "deadline":
            self.deadline = make_date_edit(date.today() + timedelta(days=7))
            self.splittable = QCheckBox("Parçalara bölünebilir (uzun görevler için)")
            self.splittable.setChecked(True)
            self.min_session = QSpinBox()
            self.min_session.setRange(15, 240)
            self.min_session.setValue(30)
            self.min_session.setSuffix(" dk")
            form.addRow("Son Tarih", self.deadline)
            form.addRow(self.splittable)
            form.addRow("Min. Oturum", self.min_session)

        elif self.mode == "recurring":
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
            form.addRow("Kaç Gün", self.times)

        else:
            self.ideal = make_date_edit(date.today() + timedelta(days=1))
            self.topics = QListWidget()
            self.topics.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            for subj in self.service.list_subjects():
                units_map = {u.id: u.name for u in self.service.list_units(subj.id) if u.id is not None}
                for t in self.service.list_topics(subj.id):
                    unit_str = f" [{units_map[t.unit_id]}]" if t.unit_id and t.unit_id in units_map else ""
                    item = QListWidgetItem(f"{subj.name}{unit_str} / {t.name}")
                    item.setData(Qt.ItemDataRole.UserRole, t.id)
                    self.topics.addItem(item)
            form.addRow("İdeal Tarih", self.ideal)
            form.addRow("Konular", self.topics)

        root.addLayout(form)
        root.addLayout(create_dialog_buttons(self, "Görevi Oluştur", "Vazgeç"))

    def _tags(self) -> list[str]:
        return [t.strip() for t in self.tags.text().split(",") if t.strip()]

    def accept(self) -> None:
        title_val = self.title.text().strip()
        if not title_val:
            show_error(self, ValueError("Lütfen görev başlığı girin."))
            return

        try:
            if self.mode == "deadline":
                self.service.add_deadline_task(
                    title=title_val,
                    duration=self.duration.value(),
                    deadline=self.deadline.date().toPython(),
                    priority=self.priority.value(),
                    splittable=self.splittable.isChecked(),
                    minimum_session=self.min_session.value() if self.splittable.isChecked() else None,
                    tags=self._tags()
                )
            elif self.mode == "recurring":
                idx = self.rule.currentIndex()
                chosen = tuple(i for i, cb in enumerate(self.days) if cb.isChecked())
                rule = (
                    RecurringRule(RecurrenceKind.DAILY) if idx == 0 else
                    RecurringRule(RecurrenceKind.WEEKDAYS, weekdays=chosen) if idx == 1 else
                    RecurringRule(RecurrenceKind.TIMES_PER_WEEK, times_per_week=self.times.value())
                )
                self.service.add_recurring_task(
                    title=title_val,
                    duration=self.duration.value(),
                    rule=rule,
                    priority=self.priority.value(),
                    tags=self._tags()
                )
            else:
                ids = [it.data(Qt.ItemDataRole.UserRole) for it in self.topics.selectedItems()]
                self.service.add_manual_review(
                    title=title_val,
                    topic_ids=ids,
                    ideal_date=self.ideal.date().toPython(),
                    duration=self.duration.value(),
                    priority=self.priority.value(),
                    tags=self._tags()
                )
        except Exception as exc:
            show_error(self, exc)
            return

        super().accept()


# ==============================================================================
# 4. ÇALIŞMA ZAMANLARI DİYALOĞU (AvailabilityDialog)
# ==============================================================================

class AvailabilityDialog(QDialog):
    """Müsaitlik aralıklarını yönetme penceresi."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle("Çalışma Zamanları (Müsaitlik)")
        self.resize(680, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        root.addWidget(create_dialog_header(
            "Çalışma Zamanları & Müsaitlik",
            "Dinamik planlayıcının size çalışma seansları atayabileceği serbest saatleri belirleyin."
        ))

        # Blok Ekle Kartı
        box = QGroupBox("Yeni Müsaitlik Bloğu Ekle")
        form = QFormLayout(box)
        form.setSpacing(8)

        self.start_date = make_date_edit(date.today())
        self.end_date = make_date_edit(date.today() + timedelta(days=13))
        row_d = QHBoxLayout()
        row_d.addWidget(self.start_date)
        row_d.addWidget(QLabel("—"))
        row_d.addWidget(self.end_date)
        form.addRow("Tarih Aralığı", row_d)

        self.days = [QCheckBox(n[:3]) for n in WEEKDAYS]
        day_row = QHBoxLayout()
        for cb in self.days:
            cb.setChecked(True)
            day_row.addWidget(cb)
        form.addRow("Günler", day_row)

        self.start_time = make_time_edit(time(17, 0))
        self.end_time = make_time_edit(time(22, 0))
        row_t = QHBoxLayout()
        row_t.addWidget(self.start_time)
        row_t.addWidget(QLabel("—"))
        row_t.addWidget(self.end_time)
        form.addRow("Saat Aralığı", row_t)

        self.kind = QComboBox()
        for k in AvailabilityType:
            self.kind.addItem(AVAIL_LABEL[k], k)
        form.addRow("Blok Türü", self.kind)

        add_btn = QPushButton("+ Müsaitlik Bloğunu Ekle")
        add_btn.setProperty("primary", True)
        add_btn.clicked.connect(self._add)
        form.addRow("", add_btn)

        root.addWidget(box)

        # Tablo
        self.table = make_table(["Tarih", "Başlangıç", "Bitiş", "Tür"])
        root.addWidget(self.table, 1)

        bottom_row = QHBoxLayout()
        delete_btn = QPushButton("Seçili Bloğu Sil")
        delete_btn.clicked.connect(self._delete)
        bottom_row.addWidget(delete_btn)
        bottom_row.addStretch(1)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(close_btn)

        root.addLayout(bottom_row)
        self._reload()

    def _reload(self) -> None:
        blocks = self.service.list_availability(date.today(), date.today() + timedelta(days=27))
        self.table.setRowCount(len(blocks))
        for r, b in enumerate(blocks):
            set_row(
                self.table, r,
                [
                    f"{fmt_date(b.block_date)} {WEEKDAYS[b.block_date.weekday()][:3]}",
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
                [i for i, cb in enumerate(self.days) if cb.isChecked()],
                self.start_time.time().toPython(),
                self.end_time.time().toPython(),
                self.kind.currentData()
            )
        except Exception as exc:
            show_error(self, exc)
            return

        self._reload()
        if n == 0:
            QMessageBox.information(self, "Bilgi", "Seçilen tarih aralığında işaretlenen gün bulunamadı.")

    def _delete(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.delete_availability(key)
            self._reload()


# ==============================================================================
# 5. DERS PROGRAMI JSON İÇE AKTARMA DİYALOĞU (TimetableImportDialog)
# ==============================================================================

class TimetableImportDialog(QDialog):
    """JSON formatındaki haftalık ders programını inceleyip içe aktaran pencere."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle("Ders Programını JSON'dan İçe Aktar")
        self.resize(600, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        root.addWidget(create_dialog_header(
            "Ders Programını JSON'dan İçe Aktar",
            "Haftalık okul ders programı JSON dosyasını seçin veya metin alanına yapıştırın."
        ))

        btn_row = QHBoxLayout()
        pick_btn = QPushButton("📁 JSON Dosyası Seç…")
        pick_btn.clicked.connect(self._pick_file)
        btn_row.addWidget(pick_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText('{\n  "program": [\n    {\n      "gun": "Pazartesi",\n      "dersler": [\n        {"saat_no": 1, "baslangic": "08:20", "bitis": "09:00", "ders": "Matematik"}\n      ]\n    }\n  ]\n}')
        root.addWidget(self.text_edit, 1)

        self.chk_clear = QCheckBox("İçe aktarmadan önce mevcut programı tamamen temizle")
        self.chk_clear.setChecked(True)
        root.addWidget(self.chk_clear)

        root.addLayout(create_dialog_buttons(self, "Programı İçe Aktar", "Vazgeç"))

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "JSON Dosyası Seç", "", "JSON (*.json);;Tüm Dosyalar (*)")
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.text_edit.setPlainText(f.read())
            except Exception as exc:
                show_error(self, exc)

    def accept(self) -> None:
        content = self.text_edit.toPlainText().strip()
        if not content:
            show_error(self, ValueError("Lütfen JSON verisi yapıştırın veya dosya seçin."))
            return

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            sep = chr(125) + chr(123)
            idx = content.find(sep)
            if idx != -1:
                data = json.loads(content[:idx + 1])
            else:
                show_error(self, ValueError("Geçersiz JSON sözdizimi."))
                return

        days_list = data.get("program") or data.get("gunler") or (data if isinstance(data, list) else [])
        if not days_list:
            show_error(self, ValueError("JSON içerisinde 'program' listesi bulunamadı."))
            return

        if self.chk_clear.isChecked():
            for e in self.service.list_timetable():
                self.service.delete_timetable_entry(e.id)

        existing_subjects = {s.name.strip().lower(): s.id for s in self.service.list_subjects() if s.id is not None}
        imported = 0
        new_subjects = 0

        for day_entry in days_list:
            if not isinstance(day_entry, dict):
                continue
            gun_raw = str(day_entry.get("gun") or day_entry.get("day") or "").strip().lower()
            w_idx = DAY_MAP.get(gun_raw)
            if w_idx is None:
                continue

            lessons = day_entry.get("dersler") or day_entry.get("lessons") or []
            for item in lessons:
                if not isinstance(item, dict):
                    continue
                d_name = str(item.get("ders") or item.get("subject") or "").strip()
                if not d_name:
                    continue

                try:
                    p_no = int(item.get("saat_no", 1) or item.get("period", 1))
                    s_str = str(item.get("baslangic") or item.get("start", ""))
                    e_str = str(item.get("bitis") or item.get("end", ""))
                    s_t = parse_time_str(s_str)
                    e_t = parse_time_str(e_str)
                except Exception:
                    continue

                d_key = d_name.lower()
                if d_key not in existing_subjects:
                    try:
                        self.service.add_subject(d_name)
                        new_subjects += 1
                        existing_subjects = {s.name.strip().lower(): s.id for s in self.service.list_subjects() if s.id is not None}
                    except Exception:
                        pass

                sid = existing_subjects.get(d_key)
                if sid is not None:
                    self.service.set_timetable_entry(w_idx, p_no, s_t, e_t, sid)
                    imported += 1

        msg = f"Ders programı başarıyla yüklendi!\n\n• Toplam {imported} ders saati aktarıldı."
        if new_subjects > 0:
            msg += f"\n• {new_subjects} yeni ders otomatik olarak oluşturuldu."
        QMessageBox.information(self, "Başarılı", msg)
        super().accept()


# ==============================================================================
# 6. OKUL DERS PROGRAMI DİYALOĞU (TimetableDialog)
# ==============================================================================

class TimetableDialog(QDialog):
    """Haftalık okul ders programı penceresi."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle("Okul Ders Programı")
        self.resize(620, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        root.addWidget(create_dialog_header(
            "Okul Ders Programı",
            "Haftalık sabit ders çizelgenizi oluşturun veya JSON formatında içe aktarın."
        ))

        form = QFormLayout()
        form.setSpacing(8)

        self.weekday = QComboBox()
        self.weekday.addItems(WEEKDAYS)
        form.addRow("Gün", self.weekday)

        self.period = QSpinBox()
        self.period.setRange(1, 14)
        form.addRow("Ders Saati No", self.period)

        self.start_time = make_time_edit(time(8, 20))
        self.end_time = make_time_edit(time(9, 0))
        row_t = QHBoxLayout()
        row_t.addWidget(self.start_time)
        row_t.addWidget(QLabel("—"))
        row_t.addWidget(self.end_time)
        form.addRow("Saat Aralığı", row_t)

        self.subject = QComboBox()
        self._reload_subjects()
        form.addRow("Ders", self.subject)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Ekle / Güncelle")
        add_btn.clicked.connect(self._add)

        import_btn = QPushButton("📥 JSON'dan İçe Aktar…")
        import_btn.setProperty("primary", True)
        import_btn.clicked.connect(self._open_import)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(import_btn)
        root.addLayout(btn_row)

        self.table = make_table(["Gün", "Saat No", "Başlangıç", "Bitiş", "Ders"])
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        del_btn = QPushButton("Seçiliyi Sil")
        del_btn.clicked.connect(self._delete)

        clear_btn = QPushButton("Tüm Programı Temizle")
        clear_btn.setStyleSheet("color: #DC2626;")
        clear_btn.clicked.connect(self._clear_all)

        bottom.addWidget(del_btn)
        bottom.addWidget(clear_btn)
        bottom.addStretch(1)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self._reload()

    def _reload_subjects(self) -> None:
        self.subject.clear()
        for s in self.service.list_subjects():
            self.subject.addItem(s.name, s.id)

    def _reload(self) -> None:
        self._reload_subjects()
        names = {s.id: s.name for s in self.service.list_subjects()}
        entries = self.service.list_timetable()
        self.table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            set_row(
                self.table, r,
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
            show_error(self, ValueError("Önce Dersler sekmesinden ders ekleyin."))
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
        if QMessageBox.question(self, "Tüm Programı Sil", "Haftalık tüm ders saatleri silinecek. Emin misiniz?") == QMessageBox.StandardButton.Yes:
            for e in self.service.list_timetable():
                self.service.delete_timetable_entry(e.id)
            self._reload()

    def _open_import(self) -> None:
        dlg = TimetableImportDialog(self.service, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()


# ==============================================================================
# 7. SINAVLAR DİYALOĞU (ExamDialog)
# ==============================================================================

class ExamDialog(QDialog):
    """Sınav tanımlama ve konu kapsamı seçme penceresi."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle("Sınavlar")
        self.resize(600, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        root.addWidget(create_dialog_header(
            "Sınavlar ve Yazılılar",
            "Sınav tarihlerini ve kapsadığı konuları belirleyin. Planlayıcı bu konuları öne çeker."
        ))

        form = QFormLayout()
        form.setSpacing(8)

        self.title = QLineEdit()
        self.title.setPlaceholderText("Örn: 1. Dönem 1. Matematik Yazılısı")
        form.addRow("Başlık", self.title)

        self.date = make_date_edit(date.today() + timedelta(days=14))
        form.addRow("Tarih", self.date)

        self.topics = QListWidget()
        self.topics.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._reload_topics_list()
        form.addRow("Kapsadığı Konular", self.topics)

        add_btn = QPushButton("+ Sınavı Kaydet")
        add_btn.setProperty("primary", True)
        add_btn.clicked.connect(self._add)
        form.addRow("", add_btn)

        root.addLayout(form)

        self.table = make_table(["Sınav", "Tarih", "Konu Sayısı"])
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        del_btn = QPushButton("Seçili Sınavı Sil")
        del_btn.clicked.connect(self._delete)
        bottom.addWidget(del_btn)
        bottom.addStretch(1)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self._reload()

    def _reload_topics_list(self) -> None:
        self.topics.clear()
        for subj in self.service.list_subjects():
            units_map = {u.id: u.name for u in self.service.list_units(subj.id) if u.id is not None}
            for t in self.service.list_topics(subj.id):
                unit_str = f" [{units_map[t.unit_id]}]" if t.unit_id and t.unit_id in units_map else ""
                item = QListWidgetItem(f"{subj.name}{unit_str} / {t.name}")
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self.topics.addItem(item)

    def _reload(self) -> None:
        exams = self.service.list_exams()
        self.table.setRowCount(len(exams))
        for r, e in enumerate(exams):
            set_row(
                self.table, r,
                [e.title, fmt_date(e.exam_date), str(len(e.topic_ids))],
                e.id
            )

    def _add(self) -> None:
        title_txt = self.title.text().strip()
        if not title_txt:
            show_error(self, ValueError("Sınav başlığı boş olamaz."))
            return

        ids = [it.data(Qt.ItemDataRole.UserRole) for it in self.topics.selectedItems()]
        try:
            self.service.add_exam(title_txt, self.date.date().toPython(), topic_ids=ids)
        except Exception as exc:
            show_error(self, exc)
            return

        self.title.clear()
        self.topics.clearSelection()
        self._reload()

    def _delete(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.delete_exam(key)
            self._reload()


# ==============================================================================
# 8. OTURUM DETAYI & DEĞERLENDİRME DİYALOĞU (SessionDialog)
# ==============================================================================

class SessionDialog(QDialog):
    """Çalışma seansı detayı, hatırlama puanlaması ve tamamlama penceresi."""

    def __init__(
        self,
        service: PlannerService,
        view: SessionView,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service, self.view = service, view
        s = view.session
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setWindowTitle(view.title)
        self.resize(500, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        # Başlık ve Rozet
        badge = CLASS_LABEL.get(view.task_class, "GÖREV")
        header = create_dialog_header(
            view.title,
            f"{fmt_date(s.session_date)} • {s.start_time:%H:%M}–{s.end_time:%H:%M} ({s.planned_minutes} dk)",
            badge_text=badge
        )
        root.addWidget(header)

        # Planlayıcı Açıklaması
        box_why = QGroupBox("Planlayıcı Neden Bu Zamanı Seçti?")
        layout_why = QVBoxLayout(box_why)
        why_txt = QTextEdit(s.explanation or "Öncelik ve aciliyet dengesi gözetilerek yerleştirildi.")
        why_txt.setReadOnly(True)
        why_txt.setMaximumHeight(80)
        layout_why.addWidget(why_txt)
        root.addWidget(box_why)

        # Seans Girişleri
        form = QFormLayout()
        form.setSpacing(8)

        self.actual = QSpinBox()
        self.actual.setRange(1, 1440)
        self.actual.setValue(s.planned_minutes)
        self.actual.setSuffix(" dk")
        form.addRow("Gerçekleşen Süre", self.actual)

        self.finished = QCheckBox("Görev tamamen bitti (kalan süreyi sıfırla)")
        form.addRow("", self.finished)
        root.addLayout(form)

        # FSRS Hatırlama Puanlaması (Yalnızca REVIEW görevlerinde)
        self.rows: dict[int, tuple[QSpinBox, QSpinBox]] = {}
        task = self.service.get_task(s.task_id)

        if view.task_class is TaskClass.REVIEW and task and task.topic_ids:
            box_recall = QGroupBox("Hatırlama & Kavrama Değerlendirmesi")
            grid = QFormLayout(box_recall)
            grid.setSpacing(6)

            for tid, label in zip(task.topic_ids, self.service.topic_labels(task.topic_ids)):
                obj = QSpinBox()
                obj.setRange(0, 100)
                obj.setValue(75)
                obj.setSuffix(" %")

                sub = QSpinBox()
                sub.setRange(1, 10)
                sub.setValue(7)

                row_sc = QHBoxLayout()
                row_sc.addWidget(QLabel("Başarı:"))
                row_sc.addWidget(obj)
                row_sc.addWidget(QLabel("Öznel (1-10):"))
                row_sc.addWidget(sub)

                grid.addRow(label, row_sc)
                self.rows[tid] = (obj, sub)

            root.addWidget(box_recall)

        root.addStretch(1)

        # Alt Butonlar
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        btn_skip = QPushButton("Atla (Yapılmadı)")
        btn_skip.clicked.connect(self._skip)
        bottom.addWidget(btn_skip)

        bottom.addStretch(1)

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(btn_close)

        btn_done = QPushButton("✓ Seansı Tamamla")
        btn_done.setProperty("primary", True)
        btn_done.clicked.connect(self._complete)
        btn_done.setEnabled(s.status.value != "COMPLETED")
        bottom.addWidget(btn_done)

        root.addLayout(bottom)

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
        except Exception as exc:
            show_error(self, exc)
            return

        self.accept()

    def _skip(self) -> None:
        self.service.skip_session(self.view.session.id)
        self.accept()