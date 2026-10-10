"""calendar_view.py - Modern minimalist haftalık takvim bileşeni."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
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

EVENT_PADDING_H = 7            # Event kutusunun sağ ve sol gün çizgilerine mesafesi (px)
EVENT_PADDING_V = 6            # Event kutusunun alt ve üst saat çizgilerine mesafesi (px)
EVENT_CORNER_RADIUS = 7        # Event kutularının köşe yumuşatması (border-radius)

GUTTER_WIDTH = 72              # Sol saat sütunu genişliği (px)
GUTTER_COLOR = QColor(250, 250, 250)  # Sol saat sütunu arka plan rengi: #FAFAFA

START_HOUR = 0                 # Takvim başlangıç saati
END_HOUR = 24                  # Takvim bitiş saati
CALENDAR_BOTTOM_PADDING = 10   # 24:00 çizgisinin altındaki rahatlatıcı boşluk (px)

VERTICAL_LINE_WIDTH = 1        # Dikey gün ayırıcı çizgi kalınlığı (px)
HORIZONTAL_LINE_WIDTH = 1      # Yatay saat çizgisi kalınlığı (px)
VERTICAL_LINE_COLOR = QColor(215, 217, 222)    # Dikey gün ayırıcı çizgi rengi: #D7D9DE
HORIZONTAL_LINE_COLOR = QColor(215, 217, 222)  # Yatay saat ve kılavuz çizgisi rengi: #D7D9DE

HEADER_CALENDAR_GAP = 24     # Üst araç çubuğu (Header) ile Takvim arasındaki boşluk (px)
THICK_SUB_LINES = True         # True: Ara kılavuz çizgileri kalın, False: İnce
DAY_HEADER_WIDGET_HEIGHT = 38           # Gün başlık çubuğu yüksekliği (px)
TODAY_HIGHLIGHT_ENABLED = False  # Bugünün sütunu hafif gri ile vurgulansın mı?
DIVIDER_LINE_COLOR = QColor(151, 157, 166)  # Üst ve alt kenar çizgisi rengi:#979da6;

# Çok hafif müsaitlik renkleri (Bugünün sütunu gibi ferah ve pastel)
AVAIL_PRIMARY_COLOR = QColor(244, 252, 246)      # Çok hafif yumuşak yeşil
AVAIL_RESERVE_COLOR = QColor(255, 251, 240)      # Çok hafif yumuşak sarı
AVAIL_UNAVAILABLE_COLOR = QColor(247, 248, 250)  # Çok hafif nötr gri

WeekdayNames = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


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
    """Gün adı ve numarasını yan yana çizen, üst ve alt çizgisi kartı ikiye bölen başlık barı."""

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

        # 1. Beyaz temiz zemin
        p.fillRect(self.rect(), QColor("#FFFFFF"))

        # 2. Üst kenar çizgisi (Kartın en solundan en sağına kadar kesintisiz uzanır)
        horiz_pen = QPen(DIVIDER_LINE_COLOR, 1)
        p.setPen(horiz_pen)
        p.drawLine(0, 0, self.width(), 0)

        # 3. Alt kenar çizgisi (Day Header ile Canvas arasını kart boyunca ikiye böler)
        horiz_pen = QPen(HORIZONTAL_LINE_COLOR, 1)
        p.setPen(horiz_pen)
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        # 4. Gün başlıkları ve dikey ayırıcılar
        vert_pen = QPen(VERTICAL_LINE_COLOR, VERTICAL_LINE_WIDTH)
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            x = GUTTER_WIDTH + i * col_w
            is_today = (d == today)

            self._draw_day_header(p, i, d, x, col_w, is_today)

            # Dikey gün ayırıcı çizgi (üst çizgi ile alt çizgi arasında)
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

            # Siyah rozet arka planı
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#18181B"))
            p.drawRoundedRect(
                QRectF(badge_x-1, badge_y, badge_width-2, badge_height-2),
                5, 5
            )

            # Gün adı: beyaz
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

            # Gün numarası: beyaz
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
            # Diğer günler: "Pzt 6" şeklinde yan yana
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
            # yaznın biraz sağında çizilmesi için +2 px offset
            p.drawText(
                QRectF(center_x + 4, -2, col_w / 2.0 - 2, self.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                day_num
            )

class WeekGridCanvas(QWidget):
    """Zaman ızgarasını ve event bloklarını çizen kanvas."""

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
        self.setFixedHeight((END_HOUR - START_HOUR) * HOUR_HEIGHT + CALENDAR_BOTTOM_PADDING)
        self.update()

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

        # 1. Zemin
        p.fillRect(self.rect(), QColor("#FFFFFF"))

        # 1.5. Sol Saat Sütunu (Gutter) Arka Planı
        p.fillRect(QRectF(0, 0, GUTTER_WIDTH, self.height()), GUTTER_COLOR)

        # 2. Bugün Sütun Gölgelendirmesi
        if TODAY_HIGHLIGHT_ENABLED:
            for i in range(7):
                d = self.week_start + timedelta(days=i)
                if d == today:
                    col_x = GUTTER_WIDTH + i * col_w
                    p.fillRect(
                        QRectF(col_x, 0, col_w, (END_HOUR - START_HOUR) * HOUR_HEIGHT),
                        QColor(248, 250, 252)
                    )

        # 3. Müsaitlik Blokları (Çizgilerin altına çizilir ki çizgiler üstte net görünsün)
        self._draw_availability(p, col_w)

        # 4. Yatay Saat ve Kılavuz Çizgileri (Müsaitlik alanlarının üzerinden geçer)
        self._draw_grid_lines(p)

        # 5. Dikey Gün Ayırıcıları (Müsaitlik alanlarının üzerinden geçer)
        h_max = (END_HOUR - START_HOUR) * HOUR_HEIGHT
        day_pen = QPen(VERTICAL_LINE_COLOR, VERTICAL_LINE_WIDTH)
        p.setPen(day_pen)
        for i in range(8):
            x = GUTTER_WIDTH + i * col_w
            p.drawLine(int(x), 0, int(x), int(h_max))

        # 6. Event Kartları
        self._draw_calendar_items(p, col_w)

        # 7. Canlı Zaman Çizgisi
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

        # Sadece ilk çizgiyi çizmemesi gerekiyor
        for h in range(START_HOUR, END_HOUR + 1):
            y = (h - START_HOUR) * HOUR_HEIGHT

            # Tam saat çizgisi
            p.setPen(hour_pen)
            if h != START_HOUR:
                p.drawLine(int(GUTTER_WIDTH), int(y), self.width(), int(y))

            # Ara kılavuz çizgileri
            if h < END_HOUR and INTERVAL_GRID_ENABLED:
                p.setPen(sub_pen)
                for minute in sub_intervals:
                    sub_y = y + HOUR_HEIGHT * (minute / 60.0)
                    p.drawLine(int(GUTTER_WIDTH), int(sub_y), self.width(), int(sub_y))

            # Sol saat etiketleri (9 AM, 10 AM)
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
        """Kutuyu sağdan, soldan, alttan ve üstten tam eşit boşlukla ortalar."""
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
                self._draw_card(
                    p, rect,
                    title=it.lesson.subject_name,
                    time_str=f"{it.lesson.start_time:%H:%M}",
                    bg_color=QColor.fromHsv((it.lesson.subject_id * 65) % 360, 18, 253),
                    border_color=QColor.fromHsv((it.lesson.subject_id * 65) % 360, 60, 230),
                    text_color=QColor.fromHsv((it.lesson.subject_id * 65) % 360, 200, 140)
                )
            elif it.session is not None:
                s = it.session.session
                state = it.session.display_state(self.now)
                bg_col, bdr_col, txt_col = self._get_session_style(it.session.task_class, state)
                self._draw_card(
                    p, rect,
                    title=it.session.title,
                    time_str=f"{s.start_time:%H:%M}\n{s.end_time:%H:%M}",
                    bg_color=bg_col,
                    border_color=bdr_col,
                    text_color=txt_col
                )

    def _get_session_style(self, task_class: TaskClass, state: str) -> tuple[QColor, QColor, QColor]:
        """Tam opak pastel renk paleti."""
        if state == "completed":
            return QColor("#F3F4F6"), QColor("#E5E7EB"), QColor("#4B5563")
        if state == "overdue":
            return QColor("#FEF2F2"), QColor("#FECACA"), QColor("#B91C1C")

        if task_class == TaskClass.REVIEW:
            return QColor("#F5F3FF"), QColor("#DDD6FE"), QColor("#6D28D9")
        elif task_class == TaskClass.DEADLINE_TASK:
            return QColor("#FFFBEB"), QColor("#FDE68A"), QColor("#B45309")
        elif task_class == TaskClass.RECURRING_TASK:
            return QColor("#F0FDF4"), QColor("#BBF7D0"), QColor("#15803D")

        return QColor("#EFF6FF"), QColor("#BFDBFE"), QColor("#1D4ED8")

    def _draw_card(
        self,
        p: QPainter,
        rect: QRectF,
        title: str,
        time_str: str,
        bg_color: QColor,
        border_color: QColor,
        text_color: QColor
    ) -> None:
        p.setBrush(bg_color)
        p.setPen(QPen(border_color, 1))
        p.drawRoundedRect(rect, EVENT_CORNER_RADIUS, EVENT_CORNER_RADIUS)

        p.setPen(text_color)
        title_font = QFont(self.font())
        title_font.setPointSize(9)
        title_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(title_font)

        pad = rect.adjusted(8, 6, -6, -6)
        p.drawText(
            pad,
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            title
        )

        if rect.height() > 36:
            sub_font = QFont(self.font())
            sub_font.setPointSize(8)
            p.setFont(sub_font)
            time_rect = QRectF(pad.x(), pad.y() + 15, pad.width(), pad.height() - 15)
            p.drawText(
                time_rect,
                Qt.AlignmentFlag.AlignTop,
                time_str
            )

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
                tip += f"<br>Konu: {les.recorded_topic}"
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

        # Çizgilerin widget kenarlarına tam yapışması için 0 margin
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
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
        """Görseldeki [Week 43] rozeti, Başlık ve [◀ | Bugün | ▶] kontrol barı."""
        top_bar = QHBoxLayout()
        # Üst bar öğeleri için kenarlardan temiz 16px iç boşluk
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

        cal_layout = QVBoxLayout(cal_container)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.setSpacing(0)

        self.header = DayHeaderWidget()
        cal_layout.addWidget(self.header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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
        self.grid.set_data(self.week_start, sessions, blocks, lessons)

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