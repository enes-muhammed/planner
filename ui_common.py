"""ui_common.py - Ortak stiller, temalar (Light & Dark), sabitler ve UI yardımcıları."""
from __future__ import annotations

from datetime import date, time

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QDialog, QDialogButtonBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QTimeEdit, QWidget
)

from engine import AvailabilityType, TaskClass, TaskStatus

# ================================================================== ÖLÇÜLER

MAIN_MARGIN_H = 18
MAIN_MARGIN_TOP = 12
MAIN_MARGIN_BOTTOM = 18

TAB_CONTENT_GAP = 10
TAB_CONTENT_MARGIN_H = 8
TAB_CONTENT_MARGIN_TOP = 6
TAB_CONTENT_MARGIN_BOTTOM = 8

TAB_BAR_TOP_PADDING = 4
TAB_BAR_BOTTOM_PADDING = 4
TAB_BAR_SIDE_PADDING = 0
TAB_HORIZONTAL_PADDING = 15
TAB_VERTICAL_PADDING = 5
TAB_RADIUS = 6

BUTTON_RADIUS = 6
INPUT_RADIUS = 6
GROUP_RADIUS = 8
TABLE_RADIUS = 7


def get_stylesheet(theme: str = "dark") -> str:
    """Açık (Light) ve Koyu (Dark) mod için modern stil şablonu."""
    if theme == "light":
        return f"""
        QMainWindow {{
            background-color: #F8FAFC;
        }}
        QWidget {{
            color: #0F172A;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        QTabWidget::pane {{
            border: 1px solid #E2E8F0;
            border-radius: {GROUP_RADIUS}px;
            background-color: #FFFFFF;
            margin-top: {TAB_CONTENT_GAP}px;
        }}
        QTabBar {{
            background: transparent;
            padding-top: {TAB_BAR_TOP_PADDING}px;
            padding-bottom: {TAB_BAR_BOTTOM_PADDING}px;
        }}
        QTabBar::tab {{
            padding: {TAB_VERTICAL_PADDING}px {TAB_HORIZONTAL_PADDING}px;
            margin-right: 4px;
            border: 1px solid transparent;
            border-radius: {TAB_RADIUS}px;
            background: transparent;
            color: #0F172A;
            font-weight: 500;
            font-size: 13px;
        }}
        QTabBar::tab:hover {{
            background-color: #E2E8F0;
        }}
        QTabBar::tab:selected {{
            background-color: #0F172A;
            color: #FFFFFF;
            font-weight: 600;
        }}
        QPushButton {{
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: {BUTTON_RADIUS}px;
            padding: 6px 14px;
            font-weight: 500;
            color: #0F172A;
        }}
        QPushButton:hover {{
            background-color: #F1F5F9;
            border-color: #94A3B8;
        }}
        QPushButton:pressed {{
            background-color: #E2E8F0;
        }}
        QPushButton[primary="true"] {{
            background-color: #0F172A;
            color: #FFFFFF;
            border: 1px solid #0F172A;
            font-weight: 600;
        }}
        QPushButton[primary="true"]:hover {{
            background-color: #1E293B;
        }}
        QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit {{
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: {INPUT_RADIUS}px;
            padding: 5px 8px;
            min-height: 24px;
            color: #0F172A;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {{
            border: 1.5px solid #2563EB;
        }}
        QGroupBox {{
            border: 1px solid #E2E8F0;
            border-radius: {GROUP_RADIUS}px;
            margin-top: 10px;
            padding: 10px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: #475569;
        }}
        QTableWidget {{
            border: 1px solid #E2E8F0;
            border-radius: {TABLE_RADIUS}px;
            gridline-color: #F1F5F9;
            background-color: #FFFFFF;
            alternate-background-color: #F8FAFC;
        }}
        QTableWidget::item:selected {{
            background-color: #E0E7FF;
            color: #1E1B4B;
        }}
        QListWidget, QTextEdit {{
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: {TABLE_RADIUS}px;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        #calendarLegend, #calendarSummary {{
            color: #475569;
            font-size: 11px;
            font-weight: 500;
        }}
        """

    # DARK MODE
    return f"""
    QMainWindow {{
        background-color: #0F172A;
    }}
    QWidget {{
        color: #F8FAFC;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    QTabWidget::pane {{
        border: 1px solid #334155;
        border-radius: {GROUP_RADIUS}px;
        background-color: #1E293B;
        margin-top: {TAB_CONTENT_GAP}px;
    }}
    QTabBar {{
        background: transparent;
        padding-top: {TAB_BAR_TOP_PADDING}px;
        padding-bottom: {TAB_BAR_BOTTOM_PADDING}px;
    }}
    QTabBar::tab {{
        padding: {TAB_VERTICAL_PADDING}px {TAB_HORIZONTAL_PADDING}px;
        margin-right: 4px;
        border: 1px solid transparent;
        border-radius: {TAB_RADIUS}px;
        background: transparent;
        color: #E2E8F0;
        font-weight: 500;
        font-size: 13px;
    }}
    QTabBar::tab:hover {{
        background-color: #334155;
    }}
    QTabBar::tab:selected {{
        background-color: #FFFFFF;
        color: #0F172A;
        font-weight: 600;
    }}
    QPushButton {{
        background-color: #1E293B;
        border: 1px solid #475569;
        border-radius: {BUTTON_RADIUS}px;
        padding: 6px 14px;
        font-weight: 500;
        color: #F8FAFC;
    }}
    QPushButton:hover {{
        background-color: #334155;
        border-color: #64748B;
    }}
    QPushButton:pressed {{
        background-color: #0F172A;
    }}
    QPushButton[primary="true"] {{
        background-color: #38BDF8;
        color: #0F172A;
        border: 1px solid #38BDF8;
        font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{
        background-color: #0EA5E9;
    }}
    QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit {{
        background-color: #1E293B;
        border: 1px solid #475569;
        border-radius: {INPUT_RADIUS}px;
        padding: 5px 8px;
        min-height: 24px;
        color: #F8FAFC;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {{
        border: 1.5px solid #38BDF8;
    }}
    QGroupBox {{
        border: 1px solid #334155;
        border-radius: {GROUP_RADIUS}px;
        margin-top: 10px;
        padding: 10px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: #94A3B8;
    }}
    QTableWidget {{
        border: 1px solid #334155;
        border-radius: {TABLE_RADIUS}px;
        gridline-color: #334155;
        background-color: #1E293B;
        alternate-background-color: #172554;
    }}
    QTableWidget::item:selected {{
        background-color: #0284C7;
        color: #FFFFFF;
    }}
    QListWidget, QTextEdit {{
        background-color: #1E293B;
        border: 1px solid #475569;
        border-radius: {TABLE_RADIUS}px;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    #calendarLegend, #calendarSummary {{
        color: #94A3B8;
        font-size: 11px;
        font-weight: 500;
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


# ----------------------------------------------------------------- Yardımcı Fonksiyonlar

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