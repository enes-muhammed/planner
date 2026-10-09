"""ui_common.py - Ortak stiller, sabitler ve yardımcı arayüz fonksiyonları."""
from __future__ import annotations

from datetime import date, time

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QDialog, QDialogButtonBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QTimeEdit, QWidget
)

from engine import AvailabilityType, TaskClass, TaskStatus

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