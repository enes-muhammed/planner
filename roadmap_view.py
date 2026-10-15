"""roadmap_view.py - 2026-2027 MEB & Diyanet Yıllık Takvim Matrisi ve Gün Çekmecesi."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget
)

from engine import (
    AcademicCalendarEvent, AcademicEventType, AvailabilityBlock,
    DayStatus, PlannerService, SchoolLesson, SessionView
)
from ui_common import MONTHS, WEEKDAYS, fmt_date, show_error

# ==============================================================================
# ⚙️ YILLIK TAKVİM VE GÜN ÇEKMECESİ YAPILANDIRMA DEĞİŞKENLERİ
# ==============================================================================
# 1. Ölçüler
START_DATE = date(2026, 9, 14)       # Okul açılış tarihi (Pazartesi)
END_DATE = date(2027, 6, 25)         # Okul kapanış tarihi (Cuma)

ROW_HEIGHT = 100                     # Her haftalık satırın piksel yüksekliği
GUTTER_WIDTH = 100                   # Sol hafta sütunu genişliği (px)
HEADER_HEIGHT = 42                   # Üst gün isimleri çubuğu yüksekliği (px)
DRAWER_WIDTH = 340                   # Sağdan açılan gün çekmecesi genişliği (px)
DRAWER_HOUR_HEIGHT = 65              # Çekmecedeki 1 saatin piksel yüksekliği

CELL_PADDING_H = 4                   # Hücre içi sağ-sol boşluk (px)
CELL_PADDING_V = 4                   # Hücre içi üst-alt boşluk (px)
CELL_CORNER_RADIUS = 6                      # Gün hücrelerinin köşe yuvarlaklığı

SNAP_SCROLL_ENABLED = True           # True: Fare tekerleğiyle tam satır satır zıplar

# 2. Renk Paleti (Hafif, Pastel ve Göz Yormayan Tonlar)
CANVAS_BG = QColor("#FFFFFF")
GUTTER_BG = QColor("#FAFAFA")
WEEKEND_BG = QColor("#F8FAFC")
NORMAL_DAY_BG = QColor("#FFFFFF")

# Tatil ve Yarım Gün Renkleri (Hücreyi kapatmaz, arka plan tonu verir)
HOLIDAY_BG = QColor("#FEF2F2")       # Okul yok / Tatil günü hafif kırmızımsı pastel
HOLIDAY_BORDER = QColor("#FECACA")
HALF_DAY_BG = QColor("#FFFBEB")      # Yarım gün (arife) hafif sarımsı pastel
HALF_DAY_BORDER = QColor("#FDE68A")

TODAY_BORDER_COLOR = QColor("#18181B")
GRID_LINE_COLOR = QColor("#E5E7EB")
SUB_LINE_COLOR = QColor("#F1F5F9")

# Rozet ve Çip Renkleri
EXAM_CHIP_BG = QColor("#FEE2E2")
EXAM_CHIP_TEXT = QColor("#DC2626")

TASK_CHIP_BG = QColor("#FFFBEB")
TASK_CHIP_TEXT = QColor("#B45309")

LESSON_CHIP_BG = QColor("#F1F5F9")
LESSON_CHIP_TEXT = QColor("#475569")

REVIEW_CHIP_BG = QColor("#F5F3FF")
REVIEW_CHIP_TEXT = QColor("#6D28D9")


@dataclass
class _WeekInfo:
    week_idx: int
    start_date: date
    end_date: date
    special_tag: str = ""
    is_break_week: bool = False


class YearMatrixHeader(QWidget):
    """Pazartesi - Pazar gün isimleri üst çubuğu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(HEADER_HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.fillRect(self.rect(), CANVAS_BG)
        p.fillRect(QRectF(0, 0, GUTTER_WIDTH, self.height()), GUTTER_BG)

        # Alt ayırıcı çizgi
        p.setPen(QPen(GRID_LINE_COLOR, 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        # Gutter başlığı
        font_g = QFont(self.font())
        font_g.setPointSize(8)
        font_g.setBold(True)
        p.setFont(font_g)
        p.setPen(QColor("#9CA3AF"))
        p.drawText(QRectF(0, 0, GUTTER_WIDTH - 6, self.height()), Qt.AlignmentFlag.AlignCenter, "HAFTA")

        # Gün isimleri
        col_w = (self.width() - GUTTER_WIDTH) / 7.0
        font_d = QFont(self.font())
        font_d.setPointSize(9)
        font_d.setBold(True)
        p.setFont(font_d)

        for i in range(7):
            x = GUTTER_WIDTH + i * col_w
            is_weekend = (i >= 5)
            p.setPen(QColor("#64748B") if not is_weekend else QColor("#94A3B8"))
            p.drawText(QRectF(x, 0, col_w, self.height()), Qt.AlignmentFlag.AlignCenter, WEEKDAYS[i][:3].upper())

            # Dikey çizgi
            p.setPen(QPen(GRID_LINE_COLOR, 1))
            p.drawLine(int(x), 0, int(x), self.height() - 1)

        p.end()


class YearMatrixCanvas(QWidget):
    """41 haftalık kesintisiz yıllık takvim matrisini çizen kanvas."""

    day_clicked = Signal(object)
    day_double_clicked = Signal(object)
    zoom_week_requested = Signal(object)

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setMouseTracking(True)

        self.weeks: list[_WeekInfo] = []
        self._build_weeks_structure()

        self.setFixedHeight(len(self.weeks) * ROW_HEIGHT)

        self.academic_events: list[AcademicCalendarEvent] = []
        self.school_lessons: list[SchoolLesson] = []
        self.sessions: list[SessionView] = []
        self.exams: list = []

        self.selected_date: date = date.today()

    def _build_weeks_structure(self) -> None:
        """14 Eylül 2026'dan 25 Haziran 2027'ye kadarki 41 takvim haftasını oluşturur."""
        self.weeks.clear()
        cur_monday = START_DATE - timedelta(days=START_DATE.weekday())
        w_idx = 1

        while cur_monday <= END_DATE:
            cur_sunday = cur_monday + timedelta(days=6)

            # Özel tatil haftaları tespiti
            tag = ""
            is_break = False
            if date(2026, 11, 16) <= cur_monday <= date(2026, 11, 20):
                tag = "1. Ara Tatil"
                is_break = True
            elif date(2027, 1, 25) <= cur_monday <= date(2027, 2, 5):
                tag = "Sömestr"
                is_break = True
            elif date(2027, 3, 8) <= cur_monday <= date(2027, 3, 12):
                tag = "2. Ara Tatil"
                is_break = True
            elif date(2027, 5, 17) <= cur_monday <= date(2027, 5, 19):
                tag = "Kurban Bayr."

            self.weeks.append(_WeekInfo(w_idx, cur_monday, cur_sunday, tag, is_break))
            cur_monday += timedelta(days=7)
            w_idx += 1

    def set_data(
        self,
        academic_events: list[AcademicCalendarEvent],
        school_lessons: list[SchoolLesson],
        sessions: list[SessionView],
        exams: list
    ) -> None:
        self.academic_events = academic_events
        self.school_lessons = school_lessons
        self.sessions = sessions
        self.exams = exams
        self.update()

    def _col_w(self) -> float:
        return (self.width() - GUTTER_WIDTH) / 7.0

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        col_w = self._col_w()
        today = date.today()

        p.fillRect(self.rect(), CANVAS_BG)
        p.fillRect(QRectF(0, 0, GUTTER_WIDTH, self.height()), GUTTER_BG)

        for row_idx, winfo in enumerate(self.weeks):
            y = row_idx * ROW_HEIGHT

            # 1. Gutter / Hafta Bilgisi Çizimi
            self._draw_gutter_cell(p, row_idx, winfo, y)

            # 2. Haftanın 7 Günü (Hücreler)
            for d_idx in range(7):
                cur_d = winfo.start_date + timedelta(days=d_idx)
                x = GUTTER_WIDTH + d_idx * col_w
                cell_rect = QRectF(x, y, col_w, ROW_HEIGHT)

                self._draw_day_cell(p, cur_d, cell_rect, today)

                # Dikey sütun çizgisi
                p.setPen(QPen(GRID_LINE_COLOR, 1))
                p.drawLine(int(x), int(y), int(x), int(y + ROW_HEIGHT))

            # Yatay satır çizgisi
            p.setPen(QPen(GRID_LINE_COLOR, 1))
            p.drawLine(0, int(y + ROW_HEIGHT), self.width(), int(y + ROW_HEIGHT))

        p.end()

    def _draw_gutter_cell(self, p: QPainter, row_idx: int, winfo: _WeekInfo, y: float) -> None:
        """Sol hafta bilgi hücresini ve zoom butonunu çizer."""
        rect = QRectF(0, y, GUTTER_WIDTH, ROW_HEIGHT)

        # Ara tatil veya sömestr ise sol sütunda yumuşak vurgu
        if winfo.is_break_week:
            p.fillRect(rect, QColor(254, 242, 242, 120))

        # Hafta Numarası
        p.setPen(QColor("#0F172A"))
        f_num = QFont(self.font())
        f_num.setPointSize(10)
        f_num.setBold(True)
        p.setFont(f_num)
        p.drawText(QRectF(8, y + 10, GUTTER_WIDTH - 16, 18), Qt.AlignmentFlag.AlignLeft, f"H.{winfo.week_idx:02d}")

        # Hafta Tarih Aralığı (Örn: 14 – 20 Eyl)
        p.setPen(QColor("#64748B"))
        f_date = QFont(self.font())
        f_date.setPointSize(8)
        p.setFont(f_date)
        s_str = f"{winfo.start_date.day} {MONTHS[winfo.start_date.month - 1][:3]}"
        e_str = f"{winfo.end_date.day} {MONTHS[winfo.end_date.month - 1][:3]}"
        p.drawText(QRectF(8, y + 30, GUTTER_WIDTH - 16, 16), Qt.AlignmentFlag.AlignLeft, f"{s_str} – {e_str}")

        # Özel Tatil Rozeti (Varsa)
        if winfo.special_tag:
            p.setBrush(QColor("#FEE2E2"))
            p.setPen(Qt.PenStyle.NoPen)
            tag_rect = QRectF(6, y + 50, GUTTER_WIDTH - 12, 18)
            p.drawRoundedRect(tag_rect, 4, 4)

            p.setPen(QColor("#DC2626"))
            f_tag = QFont(self.font())
            f_tag.setPointSize(7)
            f_tag.setBold(True)
            p.setFont(f_tag)
            p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, winfo.special_tag)

        # Zoom İkonu Butonu (Sağ altta)
        p.setPen(QColor("#94A3B8"))
        f_zoom = QFont(self.font())
        f_zoom.setPointSize(9)
        p.setFont(f_zoom)
        p.drawText(QRectF(GUTTER_WIDTH - 22, y + ROW_HEIGHT - 22, 18, 18), Qt.AlignmentFlag.AlignCenter, "🔍")

    def _draw_day_cell(self, p: QPainter, cur_d: date, cell_rect: QRectF, today: date) -> None:
        """Tek bir gün hücresini çizer (Ders çalışmaları engellenmeden gösterilir)."""
        inner = cell_rect.adjusted(CELL_PADDING_H, CELL_PADDING_V, -CELL_PADDING_H, -CELL_PADDING_V)

        # 1. Gün Durumu Tespiti (Tatil, Yarım Gün, Hafta Sonu, Bugün)
        status, ev_title = self._get_day_status(cur_d)
        is_weekend = (cur_d.weekday() >= 5)
        is_today = (cur_d == today)
        is_selected = (cur_d == self.selected_date)

        # Arka Plan Rengi
        if status is DayStatus.CLOSED:
            bg_col = HOLIDAY_BG
            bdr_col = HOLIDAY_BORDER
        elif status is DayStatus.HALF_DAY:
            bg_col = HALF_DAY_BG
            bdr_col = HALF_DAY_BORDER
        elif is_weekend:
            bg_col = WEEKEND_BG
            bdr_col = GRID_LINE_COLOR
        else:
            bg_col = NORMAL_DAY_BG
            bdr_col = GRID_LINE_COLOR

        p.setBrush(bg_col)
        # Seçili gün ise kalın koyu border
        if is_selected:
            p.setPen(QPen(QColor("#0F172A"), 1.8))
        else:
            p.setPen(QPen(bdr_col, 1))

        p.drawRoundedRect(inner, CELL_CORNER_RADIUS, CELL_CORNER_RADIUS)

        # 2. Üst Satır: Gün Numarası ve Tatil/Özel Gün Mikro Rozeti
        num_str = str(cur_d.day)
        if is_today:
            # Bugün: Siyah daire rozet
            p.setBrush(TODAY_BORDER_COLOR)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(inner.x() + 5, inner.y() + 5, 20, 20))
            p.setPen(QColor("#FFFFFF"))
            f_num = QFont(self.font())
            f_num.setPointSize(8)
            f_num.setBold(True)
            p.setFont(f_num)
            p.drawText(QRectF(inner.x() + 5, inner.y() + 5, 20, 20), Qt.AlignmentFlag.AlignCenter, num_str)
        else:
            p.setPen(QColor("#0F172A") if not is_weekend else QColor("#94A3B8"))
            f_num = QFont(self.font())
            f_num.setPointSize(9)
            f_num.setBold(True)
            p.setFont(f_num)
            p.drawText(QRectF(inner.x() + 6, inner.y() + 6, 24, 16), Qt.AlignmentFlag.AlignLeft, num_str)

        # Sağ Üst Tatil / Durum Mikro Etiketi (Hücreyi doldurmaz, zarifçe köşede durur)
        if status is DayStatus.CLOSED and ev_title:
            self._draw_micro_tag(p, inner, ev_title, QColor("#FEE2E2"), QColor("#DC2626"))
        elif status is DayStatus.HALF_DAY:
            self._draw_micro_tag(p, inner, "Yarım Gün", QColor("#FEF3C7"), QColor("#B45309"))

        # 3. Hücre İçi Kompakt Göstergeler (Sınav, Görevler, Dersler, Tekrarlar)
        content_y = inner.y() + 26
        max_y = inner.bottom() - 4

        # A. Sınav Rozeti (Varsa en üstte kırmızı parlar)
        day_exams = [e for e in self.exams if e.exam_date == cur_d]
        if day_exams and content_y + 16 <= max_y:
            ex_title = day_exams[0].title
            self._draw_chip(p, inner.x() + 4, content_y, inner.width() - 8, 16, f"🔴 {ex_title}", EXAM_CHIP_BG, EXAM_CHIP_TEXT)
            content_y += 18

        # B. Okul Ders Özeti (Varsa)
        day_lessons = [l for l in self.school_lessons if l.lesson_date == cur_d]
        if day_lessons and content_y + 15 <= max_y:
            self._draw_chip(p, inner.x() + 4, content_y, inner.width() - 8, 15, f"🏫 {len(day_lessons)} Ders Saati", LESSON_CHIP_BG, LESSON_CHIP_TEXT)
            content_y += 17

        # C. Çalışma Seansları ve Tekrarlar (Kompakt mini noktalar / sayaç)
        day_sessions = [s for s in self.sessions if s.session.session_date == cur_d]
        if day_sessions and content_y + 15 <= max_y:
            rev_count = sum(1 for s in day_sessions if s.task_class.value == "REVIEW")
            other_count = len(day_sessions) - rev_count

            parts = []
            if rev_count > 0:
                parts.append(f"⟳ {rev_count} Tekrar")
            if other_count > 0:
                parts.append(f"⚡ {other_count} Görev")

            summary_txt = " • ".join(parts)
            self._draw_chip(p, inner.x() + 4, content_y, inner.width() - 8, 15, summary_txt, REVIEW_CHIP_BG, REVIEW_CHIP_TEXT)

    def _draw_micro_tag(self, p: QPainter, inner: QRectF, text: str, bg: QColor, fg: QColor) -> None:
        """Hücrenin sağ üstüne mikro durum rozeti basar."""
        fm = QFontMetrics(QFont(self.font()))
        short_txt = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(inner.width() - 36))
        w = fm.horizontalAdvance(short_txt) + 8
        tag_r = QRectF(inner.right() - w - 2, inner.y() + 4, w, 15)

        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(tag_r, 3, 3)

        p.setPen(fg)
        f = QFont(self.font())
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)
        p.drawText(tag_r, Qt.AlignmentFlag.AlignCenter, short_txt)

    def _draw_chip(self, p: QPainter, x: float, y: float, w: float, h: float, text: str, bg: QColor, fg: QColor) -> None:
        """Hücre içi tek satırlık kompakt rozet çizer."""
        rect = QRectF(x, y, w, h)
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 3, 3)

        p.setPen(fg)
        f = QFont(self.font())
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)

        fm = QFontMetrics(f)
        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(w - 6))
        p.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

    def _get_day_status(self, d: date) -> tuple[DayStatus, str]:
        """Tarihin tatil/yarım gün durumunu döner."""
        d_iso = d.isoformat()
        for ev in self.academic_events:
            if ev.start_date.isoformat() <= d_iso <= ev.end_date.isoformat():
                return ev.day_status, ev.title
        return DayStatus.OPEN, ""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        col_w = self._col_w()

        # Sol Gutter'a tıklandıysa (Zoom butonu veya Hafta no)
        if pos.x() < GUTTER_WIDTH:
            row_idx = int(pos.y() // ROW_HEIGHT)
            if 0 <= row_idx < len(self.weeks):
                monday = self.weeks[row_idx].start_date
                self.zoom_week_requested.emit(monday)
            return

        # Bir gün hücresine tıklandıysa
        col_idx = int((pos.x() - GUTTER_WIDTH) // col_w)
        row_idx = int(pos.y() // ROW_HEIGHT)

        if 0 <= row_idx < len(self.weeks) and 0 <= col_idx < 7:
            clicked_date = self.weeks[row_idx].start_date + timedelta(days=col_idx)
            self.selected_date = clicked_date
            self.update()
            self.day_clicked.emit(clicked_date)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        col_w = self._col_w()
        if pos.x() >= GUTTER_WIDTH:
            row_idx = int(pos.y() // ROW_HEIGHT)
            if 0 <= row_idx < len(self.weeks):
                monday = self.weeks[row_idx].start_date
                self.zoom_week_requested.emit(monday)


class SnapScrollArea(QScrollArea):
    """Fare tekerleğiyle kaydırırken tam satır satır zıplayan akıllı scroll alanı."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.verticalScrollBar().setSingleStep(ROW_HEIGHT)
        # Scrollbar'ı gizle (yalnızca fare tekerleğiyle kaydırma)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not SNAP_SCROLL_ENABLED:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        # Tam olarak ROW_HEIGHT (1 satır) kaydır
        cur = self.verticalScrollBar().value()
        step = -ROW_HEIGHT if delta > 0 else ROW_HEIGHT
        target = round((cur + step) / ROW_HEIGHT) * ROW_HEIGHT
        self.verticalScrollBar().setValue(int(target))
        event.accept()


# ==============================================================================
# 🚪 SAĞDAN AÇILAN GÜN ÇEKMECESİ (1 Sütunlu Mini CalendarView)
# ==============================================================================

class DayDetailDrawer(QFrame):
    """Seçilen günün 08:00 - 22:00 saatlik dikey akışını gösteren çekmece."""

    close_requested = Signal()
    open_week_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(DRAWER_WIDTH)
        self.setStyleSheet("""
            DayDetailDrawer {
                background-color: #FFFFFF;
                border-left: 1px solid #E2E8F0;
            }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(10)

        # 1. Çekmece Üst Başlığı & Kapatma Butonu
        head = QHBoxLayout()
        self.lbl_title = QLabel("Gün Detayı")
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #0F172A;")
        head.addWidget(self.lbl_title)
        head.addStretch(1)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748B;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                color: #0F172A;
            }
        """)
        btn_close.clicked.connect(self.close_requested.emit)
        head.addWidget(btn_close)
        self.layout.addLayout(head)

        # 2. Alt Bilgi Satırı & Durum Rozeti
        info_row = QHBoxLayout()
        self.lbl_status = QLabel("Okul Açık")
        self.lbl_status.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            color: #15803D;
            background-color: #F0FDF4;
            border-radius: 4px;
            padding: 2px 7px;
        """)
        info_row.addWidget(self.lbl_status)
        info_row.addStretch(1)

        self.btn_zoom = QPushButton("7 Günlük Takvimde Aç ↗")
        self.btn_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #1A73E8;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.btn_zoom.clicked.connect(self._on_zoom_clicked)
        info_row.addWidget(self.btn_zoom)
        self.layout.addLayout(info_row)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #F1F5F9;")
        self.layout.addWidget(div)

        # 3. Kaydırılabilir Gün Akışı (Timeline)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")

        self.stream_widget = QWidget()
        self.stream_layout = QVBoxLayout(self.stream_widget)
        self.stream_layout.setContentsMargins(0, 0, 0, 0)
        self.stream_layout.setSpacing(6)

        self.scroll.setWidget(self.stream_widget)
        self.layout.addWidget(self.scroll, 1)

        self.current_date: date = date.today()

    def update_day(
        self,
        target_date: date,
        day_status: DayStatus,
        status_desc: str,
        lessons: list[SchoolLesson],
        sessions: list[SessionView],
        exams: list
    ) -> None:
        self.current_date = target_date
        day_name = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][target_date.weekday()]
        self.lbl_title.setText(f"{target_date.day} {MONTHS[target_date.month - 1]} {day_name}")

        # Durum Rozeti
        if day_status is DayStatus.CLOSED:
            self.lbl_status.setText(f"❌ {status_desc or 'Tatil'}")
            self.lbl_status.setStyleSheet("color: #DC2626; background-color: #FEE2E2; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 7px;")
        elif day_status is DayStatus.HALF_DAY:
            self.lbl_status.setText(f"🟡 {status_desc or 'Yarım Gün'}")
            self.lbl_status.setStyleSheet("color: #B45309; background-color: #FEF3C7; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 7px;")
        else:
            self.lbl_status.setText("✅ Okul Açık")
            self.lbl_status.setStyleSheet("color: #15803D; background-color: #F0FDF4; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 7px;")

        # Akışı Temizle
        while self.stream_layout.count():
            item = self.stream_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # A. Sınavlar
        day_exams = [e for e in exams if e.exam_date == target_date]
        for ex in day_exams:
            ex_box = QFrame()
            ex_box.setStyleSheet("background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 8px;")
            l_ex = QVBoxLayout(ex_box)
            l_ex.setContentsMargins(6, 4, 6, 4)
            lbl_ex = QLabel(f"🔴 <b>{ex.title}</b>")
            lbl_ex.setStyleSheet("color: #DC2626; font-size: 12px; border: none;")
            l_ex.addWidget(lbl_ex)
            self.stream_layout.addWidget(ex_box)

        # B. Okul Dersleri ve Etüt Seanslarını Zaman Sırasına Göre Birleştir
        timeline_items = []
        for les in lessons:
            timeline_items.append(("LESSON", les.start_time, les))
        for ses in sessions:
            timeline_items.append(("SESSION", ses.session.start_time, ses))

        timeline_items.sort(key=lambda x: x[1])

        if not timeline_items and not day_exams:
            lbl_empty = QLabel("Bu güne ait planlanmış okul dersi veya çalışma görevi bulunmuyor.")
            lbl_empty.setWordWrap(True)
            lbl_empty.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic; padding: 10px 0;")
            self.stream_layout.addWidget(lbl_empty)
            self.stream_layout.addStretch(1)
            return

        for kind, st_time, obj in timeline_items:
            if kind == "LESSON":
                self._add_lesson_card(obj)
            else:
                self._add_session_card(obj)

        self.stream_layout.addStretch(1)

    def _add_lesson_card(self, les: SchoolLesson) -> None:
        card = QFrame()
        card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(2)

        t_row = QHBoxLayout()
        lbl_n = QLabel(f"<b>{les.subject_name}</b>")
        lbl_n.setStyleSheet("font-size: 12px; color: #1E293B; border: none;")
        t_row.addWidget(lbl_n)
        t_row.addStretch(1)
        lbl_p = QLabel(f"{les.period_no}. Ders ({les.start_time:%H:%M})")
        lbl_p.setStyleSheet("font-size: 10px; color: #64748B; border: none;")
        t_row.addWidget(lbl_p)
        l.addLayout(t_row)

        if les.recorded_topic:
            lbl_topic = QLabel(f"• {les.recorded_topic}")
            lbl_topic.setStyleSheet("font-size: 11px; color: #475569; font-weight: 500; border: none;")
            l.addWidget(lbl_topic)

        self.stream_layout.addWidget(card)

    def _add_session_card(self, sv: SessionView) -> None:
        card = QFrame()
        # Görev sınıfına göre soluk pastel arka plan
        is_rev = (sv.task_class.value == "REVIEW")
        bg_col = "#F5F3FF" if is_rev else "#FFFBEB"
        bdr_col = "#DDD6FE" if is_rev else "#FDE68A"
        txt_col = "#6D28D9" if is_rev else "#B45309"

        card.setStyleSheet(f"background-color: {bg_col}; border: 1px solid {bdr_col}; border-radius: 8px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(2)

        t_row = QHBoxLayout()
        prefix = "⟳ " if is_rev else "⚡ "
        lbl_title = QLabel(f"<b>{prefix}{sv.title}</b>")
        lbl_title.setStyleSheet(f"font-size: 12px; color: {txt_col}; border: none;")
        t_row.addWidget(lbl_title)
        t_row.addStretch(1)

        lbl_dur = QLabel(f"{sv.session.planned_minutes} dk")
        lbl_dur.setStyleSheet("font-size: 10px; color: #64748B; border: none;")
        t_row.addWidget(lbl_dur)
        l.addLayout(t_row)

        lbl_time = QLabel(f"{sv.session.start_time:%H:%M} – {sv.session.end_time:%H:%M}")
        lbl_time.setStyleSheet("font-size: 10px; color: #64748B; border: none;")
        l.addWidget(lbl_time)

        self.stream_layout.addWidget(card)

    def _on_zoom_clicked(self) -> None:
        monday = self.current_date - timedelta(days=self.current_date.weekday())
        self.open_week_requested.emit(monday)


# ==============================================================================
# 🏛️ ANA ROADMAP GÖRÜNÜMÜ (RoadmapView)
# ==============================================================================

class RoadmapView(QWidget):
    """41 Haftalık Kesintisiz Matris ve Sağ Çekmeceli Ana Görünüm."""

    zoom_week_requested = Signal(object)
    plan_changed = Signal()

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(0)

        # Sol Alan: Header + Snap-Scroll Matris
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.header = YearMatrixHeader(self)
        left_layout.addWidget(self.header)

        self.scroll_area = SnapScrollArea(self)
        self.canvas = YearMatrixCanvas(self.service, self)
        self.canvas.day_clicked.connect(self._on_day_clicked)
        self.canvas.zoom_week_requested.connect(self.zoom_week_requested.emit)
        self.scroll_area.setWidget(self.canvas)
        left_layout.addWidget(self.scroll_area, 1)

        main_layout.addWidget(left_container, 1)

        # Sağ Alan: Gün Çekmecesi (Side Drawer)
        self.drawer = DayDetailDrawer(self)
        self.drawer.close_requested.connect(lambda: self.drawer.setVisible(False))
        self.drawer.open_week_requested.connect(self.zoom_week_requested.emit)
        self.drawer.setVisible(False)  # Başlangıçta kapalı
        main_layout.addWidget(self.drawer)

        self.refresh()

    def jump_to_week(self, week_index: int) -> None:
        """Sol sidebardaki çeyrek tıklandığında ilgili haftaya anında kaydırır."""
        target_y = (week_index - 1) * ROW_HEIGHT
        self.scroll_area.verticalScrollBar().setValue(target_y)

    def refresh(self) -> None:
        # 14 Eylül 2026 - 25 Haziran 2027 verilerini çek
        events = self.service.list_academic_events(START_DATE, END_DATE)
        lessons = self.service.list_school_lessons(START_DATE, END_DATE)
        sessions = self.service.list_sessions(START_DATE, END_DATE)
        exams = self.service.list_exams()

        self.canvas.set_data(events, lessons, sessions, exams)

        # Çekmece açıksa güncel günü tazele
        if self.drawer.isVisible():
            self._on_day_clicked(self.drawer.current_date)

    def _on_day_clicked(self, clicked_date: date) -> None:
        """Matriste bir güne tıklandığında sağ çekmeceyi açar/günceller."""
        self.drawer.setVisible(True)

        status, desc = self.canvas._get_day_status(clicked_date)
        day_lessons = [l for l in self.canvas.school_lessons if l.lesson_date == clicked_date]
        day_sessions = [s for s in self.canvas.sessions if s.session.session_date == clicked_date]
        day_exams = [e for e in self.canvas.exams if e.exam_date == clicked_date]

        self.drawer.update_day(clicked_date, status, desc, day_lessons, day_sessions, day_exams)