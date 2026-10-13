"""calendar_view.py - Modern minimalist haftalık takvim bileşeni."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from dialogs import LearningEventDialog, SessionDialog
from engine import (
    AvailabilityBlock, AvailabilityType, PlannerService,
    SchedulePlan, SchoolLesson, SessionView, TaskClass
)
from ui_common import (
    MONTHS, TAB_CONTENT_MARGIN_BOTTOM, TAB_CONTENT_MARGIN_H,
    TAB_CONTENT_MARGIN_TOP, WEEKDAYS, fmt_date, show_error
)

# ==============================================================================
# ⚙️ TAKVİM YAPILANDIRMA DEĞİŞKENLERİ (İstediğiniz gibi özelleştirebilirsiniz)
# ==============================================================================
HOUR_HEIGHT = 130              # 60 dakikanın piksel yüksekliği (Büyük ve ferah)
INTERVAL_GRID_ENABLED = True   # True: Kılavuz çizgileri görünsün, False: Sadece saat çizgileri
GRID_INTERVAL_MINUTES = 30     # Kılavuz çizgisi sıklığı (dk cinsinden: 15, 30, 60 vb.)

EVENT_PADDING_H = 6            # Event kutusunun sağ ve sol gün çizgilerine mesafesi (px)
EVENT_PADDING_V = 6            # Event kutusunun alt ve üst saat çizgilerine mesafesi (px)
EVENT_CORNER_RADIUS = 5        # Event kutularının köşe yumuşatması (border-radius)

GUTTER_WIDTH = 72              # Sol saat sütunu genişliği (px)
GUTTER_COLOR = QColor(250, 250, 250)  # Sol saat sütunu arka plan rengi: #FAFAFA

START_HOUR = 0                 # Takvim başlangıç saati
END_HOUR = 24                  # Takvim bitiş saati
CALENDAR_BOTTOM_PADDING = 10   # 24:00 çizgisinin altındaki rahatlatıcı boşluk (px)

VERTICAL_LINE_WIDTH = 1        # Dikey gün ayırıcı çizgi kalınlığı (px)
HORIZONTAL_LINE_WIDTH = 1      # Yatay saat çizgisi kalınlığı (px)
VERTICAL_LINE_COLOR = QColor(215, 217, 222)    # Dikey gün ayırıcı çizgi rengi: #D7D9DE
HORIZONTAL_LINE_COLOR = QColor(215, 217, 222)  # Yatay saat ve kılavuz çizgisi rengi: #D7D9DE

HEADER_CALENDAR_GAP = 36       # Üst araç çubuğu (Header) ile Takvim arasındaki boşluk (px)
THICK_SUB_LINES = True         # True: Ara kılavuz çizgileri kalın, False: İnce
DAY_HEADER_WIDGET_HEIGHT = 45  # Gün başlık çubuğu yüksekliği (px)
TODAY_HIGHLIGHT_ENABLED = False  # Bugünün sütunu hafif gri ile vurgulansın mı?
DIVIDER_LINE_COLOR = QColor(151, 157, 166)  # Üst ve alt kenar çizgisi rengi

NOTIFICATION_DOT_ENABLED = True  # Sağ üst köşede bildirim noktası

# Çok hafif müsaitlik renkleri
AVAIL_PRIMARY_COLOR = QColor(244, 252, 246)      # Çok hafif yumuşak yeşil
AVAIL_RESERVE_COLOR = QColor(255, 251, 240)      # Çok hafif yumuşak sarı
AVAIL_UNAVAILABLE_COLOR = QColor(247, 248, 250)  # Çok hafif nötr gri

WeekdayNames = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

# ==============================================================================
# 🎨 DERSLER İÇİN SAKİN VE SOLUK PALET (Muted Nordic / Paper Shades)
# ==============================================================================
LESSON_PALETTES = [
    # (zemin rengi, çerçeve rengi, başlık rengi, konu rengi)
    (QColor("#F3F5F8"), QColor("#CBD5E1"), QColor("#334155"), QColor("#64748B")),  # Slate Fog (Muted Gri-Mavi)
    (QColor("#F2F6F4"), QColor("#CCDCD2"), QColor("#2D4A3E"), QColor("#5A7367")),  # Sage (Muted Adaçayı)
    (QColor("#F7F5F1"), QColor("#E0DDD3"), QColor("#4A4438"), QColor("#7A7365")),  # Sand (Muted Keten / Kum)
    (QColor("#F4F3F8"), QColor("#D6D5E5"), QColor("#3D3B54"), QColor("#6D6A87")),  # Lavender Mist (Muted Lavanta)
    (QColor("#F7F2F3"), QColor("#E3D5D7"), QColor("#523C40"), QColor("#82686C")),  # Dusty Rose (Muted Gül Kurusu)
    (QColor("#F1F6F8"), QColor("#C9DCE2"), QColor("#26444E"), QColor("#4F727D")),  # Glacier (Muted Buz Mavisi)
    (QColor("#F5F6F1"), QColor("#D5DCB8"), QColor("#3F472B"), QColor("#697350")),  # Olive Mist (Muted Zeytin)
    (QColor("#F6F4F1"), QColor("#DED7CE"), QColor("#484137"), QColor("#756C60")),  # Warm Stone (Muted Sıcak Taş)
]


class CalendarIconManager:
    """Takvim kartları için SVG ikon yöneticisi (Assets klasöründen okur, yoksa vektör fallback kullanır)."""

    def __init__(self, assets_dir: Path) -> None:
        self.assets_dir = assets_dir
        self.renderers: dict[str, QSvgRenderer] = {}
        self._load_icons()

    def _load_icons(self) -> None:
        icon_definitions = {
            "repeat": (
                "repeat.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#6D28D9" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">'
                b'<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
                b'<path d="M3 3v5h5"/>'
                b'<path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>'
                b'<path d="M16 16h5v5"/>'
                b'</svg>'
            ),
            "deadline": (
                "deadline.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#B45309" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">'
                b'<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>'
                b'<line x1="4" y1="22" x2="4" y2="15"/>'
                b'</svg>'
            ),
            "recurring": (
                "recurring.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#15803D" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">'
                b'<polyline points="23 4 23 10 17 10"/>'
                b'<polyline points="1 20 1 14 7 14"/>'
                b'<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
                b'</svg>'
            ),
            "lesson": (
                "lesson.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
                b'<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
                b'<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'
                b'</svg>'
            ),
        }

        for key, (filename, fallback_bytes) in icon_definitions.items():
            file_path = self.assets_dir / filename
            if file_path.exists():
                renderer = QSvgRenderer(str(file_path))
            else:
                renderer = QSvgRenderer(QByteArray(fallback_bytes))
            self.renderers[key] = renderer

    def render(self, key: str, p: QPainter, rect: QRectF) -> bool:
        renderer = self.renderers.get(key)
        if renderer and renderer.isValid():
            renderer.render(p, rect)
            return True
        return False


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
    """Gün adı ve numarasını yan yana çizen başlık barı."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.week_start = date.today()
        self.setFixedHeight(DAY_HEADER_WIDGET_HEIGHT)

    def set_week_start(self, week_start: date) -> None:
        self.week_start = week_start
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        col_w = (self.width() - GUTTER_WIDTH) / 7.0
        today = date.today()

        p.fillRect(self.rect(), QColor("#FFFFFF"))

        horiz_pen = QPen(HORIZONTAL_LINE_COLOR, 2)
        p.setPen(horiz_pen)
        p.drawLine(0, 0, self.width(), 0)

        horiz_pen = QPen(HORIZONTAL_LINE_COLOR, 1)
        p.setPen(horiz_pen)
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        vert_pen = QPen(VERTICAL_LINE_COLOR, VERTICAL_LINE_WIDTH)
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            x = GUTTER_WIDTH + i * col_w
            is_today = (d == today)

            self._draw_day_header(p, i, d, x, col_w, is_today)

            p.setPen(vert_pen)
            p.drawLine(int(x), 0, int(x), self.height() - 1)

        p.end()

    def _draw_day_header(
        self,
        p: QPainter,
        index: int,
        day: date,
        x: float,
        col_w: float,
        is_today: bool
    ) -> None:
        day_name = WeekdayNames[index]
        day_num = str(day.day)

        font = QFont(self.font())
        font.setPointSize(10)
        p.setFont(font)

        center_x = x + col_w / 2.0
        center_y = self.height() / 2.0

        if is_today:
            font.setBold(True)
            p.setFont(font)

            badge_size = 24.0
            padding_x = 8.0
            spacing = 6.0

            day_name_width = p.fontMetrics().horizontalAdvance(day_name)
            day_num_width = p.fontMetrics().horizontalAdvance(day_num)

            badge_width = (
                padding_x * 2
                + day_name_width
                + spacing
                + day_num_width
            )

            badge_height = badge_size
            badge_x = center_x - badge_width / 2.0
            badge_y = center_y - badge_height / 2.0

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#18181B"))
            p.drawRoundedRect(
                QRectF(badge_x - 1, badge_y, badge_width - 2, badge_height - 2),
                5, 5
            )

            p.setPen(QColor("#FFFFFF"))
            day_name_rect = QRectF(
                badge_x + padding_x,
                badge_y - 2,
                day_name_width,
                badge_height
            )
            p.drawText(
                day_name_rect,
                Qt.AlignmentFlag.AlignCenter,
                day_name
            )

            day_num_rect = QRectF(
                badge_x + padding_x + day_name_width + spacing,
                badge_y - 2,
                day_num_width,
                badge_height
            )
            p.drawText(
                day_num_rect,
                Qt.AlignmentFlag.AlignCenter,
                day_num
            )
        else:
            font.setBold(False)
            p.setFont(font)
            p.setPen(QColor("#6B7280"))
            p.drawText(
                QRectF(x, -2, col_w / 2.0 - 4, self.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                day_name
            )

            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor("#1F2937"))
            p.drawText(
                QRectF(center_x + 4, -2, col_w / 2.0 - 2, self.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                day_num
            )


class WeekGridCanvas(QWidget):
    """Zaman ızgarasını ve zengin içerikli modern event bloklarını çizen kanvas."""

    sessionClicked = Signal(int)
    schoolLessonClicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service: PlannerService | None = None
        self.subjects_by_id: dict = {}
        self.topic_to_subject: dict = {}
        self._initialize_data()
        self._initialize_interaction()

        self.icon_manager = CalendarIconManager(Path(__file__).parent / "assets")

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
        lessons: list[SchoolLesson],
        service: PlannerService | None = None
    ) -> None:
        self.week_start = week_start
        self.sessions = sessions
        self.blocks = blocks
        self.lessons = lessons
        if service is not None:
            self.service = service
        self._build_subject_cache()
        self.now = datetime.now()
        self.setFixedHeight((END_HOUR - START_HOUR) * HOUR_HEIGHT + CALENDAR_BOTTOM_PADDING)
        self.update()

    def _build_subject_cache(self) -> None:
        if not self.service:
            return
        try:
            self.subjects_by_id = {s.id: s for s in self.service.list_subjects()}
            self.topic_to_subject = {}
            for s in self.subjects_by_id.values():
                for t in self.service.list_topics(s.id):
                    self.topic_to_subject[t.id] = s
        except Exception:
            pass

    def _get_subject_color(self, subject_id: int) -> QColor:
        if subject_id in self.subjects_by_id:
            s = self.subjects_by_id[subject_id]
            if s.color:
                return QColor(s.color)
        return QColor.fromHsv((subject_id * 65) % 360, 160, 195)

    def _get_lesson_style(self, subject_id: int) -> tuple[QColor, QColor, QColor, QColor]:
        """Dersler için sakin, soluk ve şık pastel palet döndürür."""
        return LESSON_PALETTES[subject_id % len(LESSON_PALETTES)]

    def _get_session_subject(self, sv: SessionView) -> tuple[str, QColor] | None:
        if not self.service:
            return None
        try:
            task = self.service.get_task(sv.session.task_id)
            if task and task.topic_ids:
                subj = self.topic_to_subject.get(task.topic_ids[0])
                if subj:
                    color = self._get_subject_color(subj.id)
                    return subj.name, color
        except Exception:
            pass
        return None

    def _col_w(self) -> float:
        return (self.width() - GUTTER_WIDTH) / 7.0

    def _y_for_minute(self, minute: float) -> float:
        return (minute - START_HOUR * 60) / 60.0 * HOUR_HEIGHT

    def _layout_items(self) -> list[_CalendarItem]:
        items_by_day: dict[int, list[_CalendarItem]] = {i: [] for i in range(7)}

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

        all_items: list[_CalendarItem] = []
        for day_items in items_by_day.values():
            if not day_items:
                continue

            day_items.sort(key=lambda x: (x.start_min, -(x.end_min - x.start_min)))
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

            for cluster in clusters:
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

            all_items.extend(day_items)

        return all_items

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        col_w = self._col_w()
        today = date.today()

        p.fillRect(self.rect(), QColor("#FFFFFF"))
        p.fillRect(QRectF(0, 0, GUTTER_WIDTH, self.height()), GUTTER_COLOR)

        if TODAY_HIGHLIGHT_ENABLED:
            for i in range(7):
                d = self.week_start + timedelta(days=i)
                if d == today:
                    col_x = GUTTER_WIDTH + i * col_w
                    p.fillRect(
                        QRectF(col_x, 0, col_w, (END_HOUR - START_HOUR) * HOUR_HEIGHT),
                        QColor(248, 250, 252)
                    )

        self._draw_availability(p, col_w)
        self._draw_grid_lines(p)

        h_max = (END_HOUR - START_HOUR) * HOUR_HEIGHT
        day_pen = QPen(VERTICAL_LINE_COLOR, VERTICAL_LINE_WIDTH)
        p.setPen(day_pen)
        for i in range(8):
            x = GUTTER_WIDTH + i * col_w
            p.drawLine(int(x), 0, int(x), int(h_max))

        self._draw_calendar_items(p, col_w)
        self._draw_current_time(p, col_w)

        p.end()

    def _draw_grid_lines(self, p: QPainter) -> None:
        time_font = QFont(self.font())
        time_font.setPointSize(8)
        p.setFont(time_font)

        hour_pen = QPen(HORIZONTAL_LINE_COLOR, HORIZONTAL_LINE_WIDTH)

        if THICK_SUB_LINES:
            sub_pen = QPen(HORIZONTAL_LINE_COLOR, HORIZONTAL_LINE_WIDTH)
        else:
            sub_pen = QPen(QColor(243, 244, 246), 1, Qt.PenStyle.SolidLine)

        sub_intervals = [
            m for m in range(GRID_INTERVAL_MINUTES, 60, GRID_INTERVAL_MINUTES)
        ] if GRID_INTERVAL_MINUTES < 60 else []

        for h in range(START_HOUR, END_HOUR + 1):
            y = (h - START_HOUR) * HOUR_HEIGHT

            p.setPen(hour_pen)
            if h != START_HOUR:
                p.drawLine(int(GUTTER_WIDTH), int(y), self.width(), int(y))

            if h < END_HOUR and INTERVAL_GRID_ENABLED:
                p.setPen(sub_pen)
                for minute in sub_intervals:
                    sub_y = y + HOUR_HEIGHT * (minute / 60.0)
                    p.drawLine(int(GUTTER_WIDTH), int(sub_y), self.width(), int(sub_y))

            if h > START_HOUR:
                p.setPen(QColor(156, 163, 175))
                hour = h % 12
                if hour == 0:
                    hour = 12
                period = "AM" if h < 12 or h == 24 else "PM"
                p.drawText(
                    QRectF(0, y - 8, GUTTER_WIDTH - 8, 16),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{hour} {period}"
                )

    def _draw_availability(self, p: QPainter, col_w: float) -> None:
        tint_map = {
            AvailabilityType.PRIMARY: AVAIL_PRIMARY_COLOR,
            AvailabilityType.RESERVE: AVAIL_RESERVE_COLOR,
            AvailabilityType.UNAVAILABLE: AVAIL_UNAVAILABLE_COLOR
        }

        for b in self.blocks:
            day_idx = (b.block_date - self.week_start).days
            if 0 <= day_idx < 7:
                s_min = b.start_time.hour * 60 + b.start_time.minute
                e_min = b.end_time.hour * 60 + b.end_time.minute
                y1 = self._y_for_minute(s_min)
                y2 = self._y_for_minute(e_min)
                x = GUTTER_WIDTH + day_idx * col_w
                p.fillRect(
                    QRectF(x, y1, col_w, max(2.0, y2 - y1)),
                    tint_map[b.block_type]
                )

    def _item_rect(self, item: _CalendarItem, col_w: float) -> QRectF:
        col_x = GUTTER_WIDTH + item.day_idx * col_w
        available_w = col_w - (2 * EVENT_PADDING_H)
        slot_w = available_w / item.total_cols

        card_x = col_x + EVENT_PADDING_H + item.col * slot_w
        card_w = max(24.0, slot_w - (2 if item.total_cols > 1 else 0))

        y1 = self._y_for_minute(item.start_min)
        y2 = self._y_for_minute(item.end_min)

        card_y = y1 + EVENT_PADDING_V
        card_h = max(24.0, (y2 - y1) - (2 * EVENT_PADDING_V))

        return QRectF(card_x, card_y, card_w, card_h)

    def _draw_calendar_items(self, p: QPainter, col_w: float) -> None:
        self._hits = []
        items = self._layout_items()

        for it in items:
            rect = self._item_rect(it, col_w)
            self._hits.append((rect, it))

            if it.lesson is not None:
                self._draw_lesson_card(p, rect, it.lesson)
            elif it.session is not None:
                self._draw_session_card(p, rect, it.session)

    def _draw_lesson_card(self, p: QPainter, rect: QRectF, lesson: SchoolLesson) -> None:
        """Ders programı bloğu: Sakin & soluk İskandinav stili zemin; çizgisiz ve noktasız; ders ikonuyla."""
        bg_color, border_color, text_color, topic_color = self._get_lesson_style(lesson.subject_id)

        # 1. Sakin, soluk pastel zemin ve zarif 1px çerçeve
        p.setBrush(bg_color)
        p.setPen(QPen(border_color, 1))
        p.drawRoundedRect(rect, EVENT_CORNER_RADIUS, EVENT_CORNER_RADIUS)

        # 2. İkon ve Başlık Alanı
        title_font = QFont(self.font())
        title_font.setPointSize(9)
        title_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(text_color)

        pad = rect.adjusted(8, 7, -8, -6)

        # Ders ikonu (assets/lesson.svg veya vektörel kitap)
        icon_size = 11.0
        icon_gap = 5.0
        icon_rect = QRectF(pad.x(), pad.y() + 2, icon_size, icon_size)
        has_icon = self.icon_manager.render("lesson", p, icon_rect)

        title_x = pad.x() + (icon_size + icon_gap if has_icon else 0)
        title_w = max(0.0, pad.width() - (icon_size + icon_gap if has_icon else 0))
        title_rect = QRectF(title_x, pad.y(), title_w, pad.height())

        fm = QFontMetrics(title_font)
        title_text = fm.elidedText(lesson.subject_name, Qt.TextElideMode.ElideRight, int(title_rect.width()))
        p.drawText(title_rect, Qt.AlignmentFlag.AlignTop, title_text)

        # 3. Konu varsa hafifçe yaz, yoksa hiçbir şey yapma (saat yok)
        if lesson.recorded_topic and rect.height() > 32:
            topic_font = QFont(self.font())
            topic_font.setPointSize(8)
            topic_pad = QRectF(rect.x() + 8, pad.y() + 16, rect.width() - 16, rect.height() - 22)
            self._draw_smart_text(p, lesson.recorded_topic, topic_pad, topic_font, topic_color)

    def _draw_session_card(self, p: QPainter, rect: QRectF, sv: SessionView) -> None:
        """Tekrar, rutin ve teslim görevleri bloğu: Üst çizgisiz, sağ üstte bildirim noktası ve türe özel ikon."""
        s = sv.session
        state = sv.display_state(self.now)
        bg_col, bdr_col, txt_col = self._get_session_style(sv.task_class, state)

        # 1. Zemin ve çerçeve (Üst çizgi tamamen yok)
        p.setBrush(bg_col)
        p.setPen(QPen(bdr_col, 1))
        p.drawRoundedRect(rect, EVENT_CORNER_RADIUS, EVENT_CORNER_RADIUS)

        # 2. Sağ Üst Köşe Bildirim Noktası (Kırmızı: Overdue, Yeşil: Completed, Sarı: Deadline)
        dot_color = None
        if state == "overdue":
            dot_color = QColor("#EF4444")
        elif state == "completed":
            dot_color = QColor("#10B981")
        elif sv.task_class == TaskClass.DEADLINE_TASK:
            dot_color = QColor("#F59E0B")

        if NOTIFICATION_DOT_ENABLED and dot_color is not None:
            self._draw_notification_dot(p, rect.right() - 10.0, rect.top() + 10.0, dot_color)

        # 3. Görev türüne özel ikon ve Başlık Alanı
        p.setPen(txt_col)
        title_font = QFont(self.font())
        title_font.setPointSize(9)
        title_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(title_font)

        clean_title = re.sub(
            r"^(Tekrar|Manuel Tekrar)\s*[:\-–]?\s*", "",
            sv.title, flags=re.IGNORECASE
        ).strip() or sv.title

        right_pad = -18 if (NOTIFICATION_DOT_ENABLED and dot_color is not None) else -8
        pad = rect.adjusted(8, 7, right_pad, -6)

        if sv.task_class == TaskClass.REVIEW:
            icon_key = "repeat"
        elif sv.task_class == TaskClass.DEADLINE_TASK:
            icon_key = "deadline"
        elif sv.task_class == TaskClass.RECURRING_TASK:
            icon_key = "recurring"
        else:
            icon_key = "repeat"

        icon_size = 11.0
        icon_gap = 5.0
        icon_rect = QRectF(pad.x(), pad.y() + 2, icon_size, icon_size)
        has_icon = self.icon_manager.render(icon_key, p, icon_rect)

        title_x = pad.x() + (icon_size + icon_gap if has_icon else 0)
        title_w = max(0.0, pad.width() - (icon_size + icon_gap if has_icon else 0))
        title_rect = QRectF(title_x, pad.y(), title_w, pad.height())

        fm = QFontMetrics(title_font)
        rendered_title = fm.elidedText(clean_title, Qt.TextElideMode.ElideRight, int(title_rect.width()))
        p.drawText(title_rect, Qt.AlignmentFlag.AlignTop, rendered_title)

        # 4. Alt bilgi: Saat ve aidiyet dersi
        if rect.height() > 38:
            sub_font = QFont(self.font())
            sub_font.setPointSize(8)
            p.setFont(sub_font)
            p.setPen(QColor("#64748B"))

            time_str = f"{s.start_time:%H:%M} - {s.end_time:%H:%M}"
            subj_info = self._get_session_subject(sv)
            if subj_info and rect.width() > 90:
                subj_name, _ = subj_info
                time_str = f"{time_str} • {subj_name}"

            time_rect = QRectF(rect.x() + 8, pad.y() + 16, rect.width() - 16, rect.height() - 22)
            elided_time = QFontMetrics(sub_font).elidedText(time_str, Qt.TextElideMode.ElideRight, int(time_rect.width()))
            p.drawText(time_rect, Qt.AlignmentFlag.AlignTop, elided_time)

    def _draw_notification_dot(self, p: QPainter, x: float, y: float, color: QColor) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(x, y), 3.0, 3.0)

    def _draw_smart_text(self, p: QPainter, text: str, rect: QRectF, font: QFont, color: QColor) -> None:
        fm = QFontMetrics(font)
        p.setFont(font)
        p.setPen(color)

        line_h = fm.lineSpacing()
        max_lines = max(1, int(rect.height() / line_h))

        if max_lines == 1:
            elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
            p.drawText(rect, Qt.AlignmentFlag.AlignTop, elided)
            return

        words = text.split(" ")
        lines = []
        cur_line = ""

        for word in words:
            test_line = f"{cur_line} {word}".strip()
            if fm.horizontalAdvance(test_line) <= rect.width():
                cur_line = test_line
            else:
                if cur_line:
                    lines.append(cur_line)
                cur_line = word
                if len(lines) >= max_lines - 1:
                    break

        if cur_line:
            lines.append(cur_line)

        for i, line in enumerate(lines[:max_lines]):
            line_rect = QRectF(rect.x(), rect.y() + i * line_h, rect.width(), line_h)
            if i == max_lines - 1 and len(lines) > max_lines:
                line = fm.elidedText(line, Qt.TextElideMode.ElideRight, int(rect.width()))
            p.drawText(line_rect, Qt.AlignmentFlag.AlignTop, line)

    def _get_session_style(self, task_class: TaskClass, state: str) -> tuple[QColor, QColor, QColor]:
        if state == "completed":
            return QColor("#F1F5F9"), QColor("#CBD5E1"), QColor("#475569")
        if state == "overdue":
            return QColor("#FEF2F2"), QColor("#FECACA"), QColor("#B91C1C")

        if task_class == TaskClass.REVIEW:
            return QColor("#F5F3FF"), QColor("#DDD6FE"), QColor("#6D28D9")
        elif task_class == TaskClass.DEADLINE_TASK:
            return QColor("#FFFBEB"), QColor("#FDE68A"), QColor("#B45309")
        elif task_class == TaskClass.RECURRING_TASK:
            return QColor("#F0FDF4"), QColor("#BBF7D0"), QColor("#15803D")

        return QColor("#EFF6FF"), QColor("#BFDBFE"), QColor("#1D4ED8")

    def _draw_current_time(self, p: QPainter, col_w: float) -> None:
        if not (self.week_start <= self.now.date() <= self.week_start + timedelta(days=6)):
            return

        now_min = self.now.hour * 60 + self.now.minute
        now_y = self._y_for_minute(now_min)

        p.setPen(QPen(QColor(156, 163, 175), 1, Qt.PenStyle.DotLine))
        p.drawLine(int(GUTTER_WIDTH), int(now_y), int(self.width()), int(now_y))

        p.setBrush(QColor("#1F2937"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(GUTTER_WIDTH - 2, now_y), 2.5, 2.5)

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
                f"{sv.session.planned_minutes} dk<br>"
                f"<i>{sv.session.explanation or ''}</i>"
            )
        elif it.lesson is not None:
            les = it.lesson
            tip = f"<b>{les.subject_name}</b><br>Haftanın {les.subject_lesson_no}. dersi"
            if les.recorded_topic:
                tip += f"<br><b>İşlenen Konu:</b> {les.recorded_topic}"
            else:
                tip += "<br><i>Konuyu girmek için tıklayın</i>"
            self.setToolTip(tip)


class CalendarView(QWidget):
    """Görseldeki üst bar ve ferah takvim konteyneri."""

    plan_changed = Signal()

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self._initialize_week()

        # Alt iki köşenin kesilmesini önlemek için alttan 8px güvenli kenar boşluğu
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)

        self._setup_toolbar(root)
        if HEADER_CALENDAR_GAP > 0:
            root.addSpacing(HEADER_CALENDAR_GAP)
        self._setup_calendar(root)
        self.refresh()
        self._scroll_to_hour(8)

    def _initialize_week(self) -> None:
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())

    def _setup_toolbar(self, root: QVBoxLayout) -> None:
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 12, 16, 0)
        top_bar.setSpacing(12)

        # 1. Sol Rozet (Week 43)
        self.week_badge = QFrame()
        self.week_badge.setFixedSize(54, 44)
        self.week_badge.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        badge_layout = QVBoxLayout(self.week_badge)
        badge_layout.setContentsMargins(0, 4, 0, 4)
        badge_layout.setSpacing(0)

        lbl_week_tag = QLabel("WEEK")
        lbl_week_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_week_tag.setStyleSheet("font-size: 9px; font-weight: 700; color: #9CA3AF; border: none;")

        self.lbl_week_num = QLabel("01")
        self.lbl_week_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_week_num.setStyleSheet("font-size: 14px; font-weight: 800; color: #111827; border: none;")

        badge_layout.addWidget(lbl_week_tag)
        badge_layout.addWidget(self.lbl_week_num)
        top_bar.addWidget(self.week_badge)

        # 2. Ay Başlığı ve Tarih Aralığı
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 17px; font-weight: 700; color: #111827;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #6B7280;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        top_bar.addLayout(title_box)

        top_bar.addStretch(1)

        # 3. [ ◀ | Bugün | ▶ ] Birleşik Kontrol Grubu
        nav_group = QFrame()
        nav_group.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                font-size: 13px;
                color: #374151;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #F9FAFB;
            }
        """)
        nav_layout = QHBoxLayout(nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(32)
        today_btn = QPushButton("Bugün")
        today_btn.setStyleSheet("font-weight: 600; border-left: 1px solid #E5E7EB; border-right: 1px solid #E5E7EB;")
        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(32)

        prev_btn.clicked.connect(lambda: self._shift(-7))
        today_btn.clicked.connect(self._go_today)
        next_btn.clicked.connect(lambda: self._shift(7))

        nav_layout.addWidget(prev_btn)
        nav_layout.addWidget(today_btn)
        nav_layout.addWidget(next_btn)
        top_bar.addWidget(nav_group)

        # 4. Siyah "+ Planla / Yeniden Planla" Butonu
        plan_btn = QPushButton("+ Planla / Yeniden Planla")
        plan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plan_btn.setStyleSheet("""
            QPushButton {
                background-color: #18181B;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #27272A;
            }
        """)
        plan_btn.setFixedHeight(today_btn.sizeHint().height() + 11)
        plan_btn.clicked.connect(self.replan)
        top_bar.addWidget(plan_btn)

        root.addLayout(top_bar)

    def _setup_calendar(self, root: QVBoxLayout) -> None:
        cal_container = QFrame()
        cal_container.setFrameShape(QFrame.Shape.NoFrame)
        cal_container.setStyleSheet("background: transparent; border: none;")

        cal_layout = QVBoxLayout(cal_container)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.setSpacing(0)

        self.header = DayHeaderWidget()
        cal_layout.addWidget(self.header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

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
        self._update_header_info(end)
        self.header.set_week_start(self.week_start)
        sessions, blocks, lessons = self._load_calendar_data(end)
        self.grid.set_data(self.week_start, sessions, blocks, lessons, self.service)

    def _week_end(self) -> date:
        return self.week_start + timedelta(days=6)

    def _update_header_info(self, end: date) -> None:
        week_number = self.week_start.isocalendar()[1]
        self.lbl_week_num.setText(f"{week_number:02d}")

        month_str = MONTHS[self.week_start.month - 1]
        self.title_label.setText(f"{month_str} {self.week_start.year}")
        self.subtitle_label.setText(
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
        try:
            plan = self.service.replan()
        except Exception as exc:
            show_error(self, exc)
            return

        self.refresh()
        self.plan_changed.emit()

        if plan.warnings or plan.unscheduled:
            lines = list(plan.warnings)
            lines += [f"• {u.title}: {u.minutes} dk yerleştirilemedi" for u in plan.unscheduled[:10]]
            QMessageBox.information(self, "Plan Uyarıları", "\n".join(lines))

    def _open_session(self, session_id: int) -> None:
        view = self.service.get_session(session_id)
        if view is None:
            return

        if SessionDialog(self.service, view, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.plan_changed.emit()

    def _open_school_lesson(self, lesson: SchoolLesson) -> None:
        if lesson.recorded_topic:
            QMessageBox.information(
                self,
                "Konu Kayıtlı",
                f"{lesson.subject_name} dersinin konusu “{lesson.recorded_topic}” olarak kayıtlı."
            )
            return

        if LearningEventDialog(self.service, lesson, self).exec() == QDialog.DialogCode.Accepted:
            self.replan()