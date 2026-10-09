"""ui_common.py - Saf Açık Tema (Light Mode), borderless modern stil ve UI yardımcıları."""
from __future__ import annotations

from datetime import date, time

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QDialog, QDialogButtonBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QTimeEdit, QWidget
)

from engine import AvailabilityType, TaskClass, TaskStatus

# ================================================================== ÖLÇÜLER

MAIN_MARGIN_H = 18
MAIN_MARGIN_TOP = 12
MAIN_MARGIN_BOTTOM = 18

TAB_CONTENT_GAP = 12
TAB_CONTENT_MARGIN_H = 8
TAB_CONTENT_MARGIN_TOP = 6
TAB_CONTENT_MARGIN_BOTTOM = 8

TAB_BAR_TOP_PADDING = 4
TAB_BAR_BOTTOM_PADDING = 4
TAB_BAR_SIDE_PADDING = 6
TAB_HORIZONTAL_PADDING = 16
TAB_VERTICAL_PADDING = 6
TAB_RADIUS = 6

BUTTON_RADIUS = 6
INPUT_RADIUS = 6
GROUP_RADIUS = 8
TABLE_RADIUS = 8


def create_light_palette() -> QPalette:
    """İşletim sistemi Dark Mode olsa bile Qt'nin koyu renk çekmesini engelleyen palet."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#F8F9FA"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#202124"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8F9FA"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#202124"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#202124"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#F1F3F4"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#202124"))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Link, QColor("#1A73E8"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#1A73E8"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#70757A"))
    pal.setColor(QPalette.ColorRole.Mid, QColor("#DADCE0"))
    pal.setColor(QPalette.ColorRole.Midlight, QColor("#E8EAED"))
    pal.setColor(QPalette.ColorRole.Dark, QColor("#BDC1C6"))
    return pal


UI_STYLESHEET = f"""
QMainWindow {{
    background-color: #F8F9FA;
}}

QWidget {{
    color: #202124;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}

QDialog {{
    background-color: #FFFFFF;
    color: #202124;
}}

/* YALNIZCA EN DIŞTAKİ BÜYÜK KAPSAYICI ÇERÇEVELİDİR */
QTabWidget::pane {{
    border: 1px solid #E2E8F0;
    border-radius: {GROUP_RADIUS}px;
    background-color: #FFFFFF;
    margin-top: {TAB_CONTENT_GAP}px;
}}

/* SİYAH TAB BAR (Segmented Control Tarzı) */
QTabBar {{
    background-color: #000000;
    border-radius: 8px;
    padding-top: {TAB_BAR_TOP_PADDING}px;
    padding-bottom: {TAB_BAR_BOTTOM_PADDING}px;
    padding-left: {TAB_BAR_SIDE_PADDING}px;
    padding-right: {TAB_BAR_SIDE_PADDING}px;
}}

QTabBar::tab {{
    padding: {TAB_VERTICAL_PADDING}px {TAB_HORIZONTAL_PADDING}px;
    margin-right: 4px;
    border: none;
    border-radius: {TAB_RADIUS}px;
    background: transparent;
    color: #9CA3AF;
    font-weight: 500;
    font-size: 13px;
}}

QTabBar::tab:hover {{
    background-color: #27272A;
    color: #F3F4F6;
}}

QTabBar::tab:selected {{
    background-color: #FFFFFF;
    color: #000000;
    font-weight: 600;
}}

/* BORDERLESS MODERN BUTONLAR */
QPushButton {{
    background-color: #F1F3F4;
    border: none;
    border-radius: {BUTTON_RADIUS}px;
    padding: 7px 14px;
    font-weight: 500;
    color: #202124;
}}

QPushButton:hover {{
    background-color: #E8EAED;
}}

QPushButton:pressed {{
    background-color: #DADCE0;
}}

QPushButton[primary="true"] {{
    background-color: #1A73E8;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}

QPushButton[primary="true"]:hover {{
    background-color: #1557B0;
}}

/* BORDERLESS INPUT ELEMANLARI */
QLineEdit,
QComboBox,
QSpinBox,
QDateEdit,
QTimeEdit {{
    background-color: #F1F3F4;
    border: none;
    border-radius: {INPUT_RADIUS}px;
    padding: 6px 10px;
    min-height: 24px;
    color: #202124;
}}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDateEdit:focus,
QTimeEdit:focus {{
    background-color: #E8F0FE;
    color: #1A73E8;
}}

/* DROPDOWN LİSTE ELEMANLARI */
QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    color: #202124;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #E8F0FE;
    selection-color: #1A73E8;
    outline: none;
}}

/* BORDERLESS GRUP KUTULARI */
QGroupBox {{
    border: none;
    background: transparent;
    margin-top: 14px;
    padding: 6px 0px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 0px;
    padding: 0 4px;
    color: #3C4043;
    font-size: 13px;
}}

/* BORDERLESS TABLOLAR */
QTableWidget {{
    border: none;
    background-color: #FFFFFF;
    alternate-background-color: #F8F9FA;
    border-radius: {TABLE_RADIUS}px;
}}

QHeaderView::section {{
    background-color: #F8F9FA;
    color: #5F6368;
    border: none;
    border-bottom: 1px solid #E8EAED;
    padding: 6px 8px;
    font-weight: 600;
    font-size: 12px;
}}

QTableWidget::item {{
    padding: 6px 8px;
    border: none;
    color: #202124;
}}

QTableWidget::item:selected {{
    background-color: #E8F0FE;
    color: #1A73E8;
}}

/* DİĞER LİSTE VE METİN ALANLARI */
QListWidget {{
    border: none;
    background-color: #F8F9FA;
    border-radius: {TABLE_RADIUS}px;
    padding: 4px;
}}

QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
    color: #202124;
}}

QListWidget::item:selected {{
    background-color: #E8F0FE;
    color: #1A73E8;
}}

QTextEdit {{
    border: none;
    background-color: #F8F9FA;
    border-radius: {TABLE_RADIUS}px;
    padding: 8px;
    color: #202124;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

/* AÇILIR MENÜLER */
QMenu {{
    background-color: #FFFFFF;
    color: #202124;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
    color: #202124;
}}

QMenu::item:selected {{
    background-color: #F1F3F4;
    color: #1A73E8;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: #DADCE0;
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: #BDC1C6;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
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


# ----------------------------------------------------------------- Yardımcılar

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
    t.setShowGrid(False)
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