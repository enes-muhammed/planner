"""calendar_view.py - Haftalık interaktif takvim bileşenleri ve görünümü."""
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
    SchedulePlan, SchoolLesson, SessionView
)
from ui_common import (
    CLASS_COLOR, CLASS_LABEL, TAB_CONTENT_MARGIN_BOTTOM,
    TAB_CONTENT_MARGIN_H, TAB_CONTENT_MARGIN_TOP, WEEKDAYS,
    fmt_date, show_error
)

GUTTER_WIDTH = 64
HOUR_HEIGHT = 60
START_HOUR = 0
END_HOUR = 24
CALENDAR_BOTTOM_PADDING = 28  # 24.00 etiketinin yarım kalmaması için alt boşluk


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
    """Haftanın gün isimlerini ve tarih rozetlerini çizen üst başlık."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.week_start = date.today()
        self.setFixedHeight(50)
        self.is_dark = True

    def set_week_start(self, week_start: date) -> None:
        self.week_start = week_start
        self.update()

    def set_theme_mode(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._create_painter()
        pal = self.palette()
        col_w = (self.width() - GUTTER_WIDTH) / 7.0
        today = date.today()
        text_color = pal.text().color()

        self._draw_background(p, pal, self.width())
        self._draw_days(p, col_w, today, text_color)
        p.end()

    def _create_painter(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    def _draw_background(self, p: QPainter, pal, width: int) -> None:
        p.fillRect(self.rect(), pal.window())
        border_col = QColor(255, 255, 255, 30) if self.is_dark else QColor(0, 0, 0, 20)
        p.setPen(QPen(border_col, 1))
        p.drawLine(0, self.height() - 1, width, self.height() - 1)

    def _draw_days(
        self,
        p: QPainter,
        col_w: float,
        today: date,
        text_color
    ) -> None:
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            x = GUTTER_WIDTH + i * col_w
            is_today = (d == today)
            self._draw_day_name(p, i, x, col_w, is_today)
            self._draw_day_number(p, d, x, col_w, is_today, text_color)
            self._draw_day_separator(p, x)

    def _draw_day_name(
        self,
        p: QPainter,
        index: int,
        x: float,
        col_w: float,
        is_today: bool
    ) -> None:
        name_font = QFont(self.font())
        name_font.setPointSize(8)
        name_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(name_font)
        p.setPen(QColor("#38BDF8") if is_today else QColor(148, 163, 184))
        p.drawText(
            QRectF(x, 4, col_w, 16),
            Qt.AlignmentFlag.AlignCenter,
            WEEKDAYS[index][:3].upper()
        )

    def _draw_day_number(
        self,
        p: QPainter,
        day: date,
        x: float,
        col_w: float,
        is_today: bool,
        text_color
    ) -> None:
        num_font = QFont(self.font())
        num_font.setPointSize(11)
        num_font.setBold(True)
        p.setFont(num_font)

        num_str = str(day.day)
        num_rect = QRectF(x, 22, col_w, 24)

        if is_today:
            self._draw_today_badge(p, x, col_w, num_str)
        else:
            p.setPen(text_color)
            p.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, num_str)

    def _draw_today_badge(
        self,
        p: QPainter,
        x: float,
        col_w: float,
        num_str: str
    ) -> None:
        badge_size = 24.0
        badge_x = x + (col_w - badge_size) / 2.0
        badge_y = 22.0

        p.setBrush(QColor("#38BDF8" if self.is_dark else "#0F172A"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(badge_x, badge_y, badge_size, badge_size))

        p.setPen(QColor("#0F172A" if self.is_dark else "#FFFFFF"))
        p.drawText(
            QRectF(badge_x, badge_y, badge_size, badge_size),
            Qt.AlignmentFlag.AlignCenter,
            num_str
        )

    def _draw_day_separator(self, p: QPainter, x: float) -> None:
        sep_col = QColor(255, 255, 255, 20) if self.is_dark else QColor(0, 0, 0, 15)
        p.setPen(QPen(sep_col, 1))
        p.drawLine(int(x), 0, int(x), self.height())


class WeekGridCanvas(QWidget):
    """Saat ızgarasını, dersleri ve blokları çizen modern kanvas."""

    sessionClicked = Signal(int)
    schoolLessonClicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_dark = True
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
        # 24:00 yazısının ve son saatlerin kesilmemesi için padding eklendi
        self.setFixedHeight((END_HOUR - START_HOUR) * HOUR_HEIGHT + CALENDAR_BOTTOM_PADDING)

    def set_theme_mode(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self.update()

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
        self.update()

    def _col_w(self) -> float:
        return (self.width() - GUTTER_WIDTH) / 7.0

    def _y_for_minute(self, minute: float) -> float:
        return (minute - START_HOUR * 60) / 60.0 * HOUR_HEIGHT

    def _layout_items(self) -> list[_CalendarItem]:
        items_by_day = self._create_items_by_day()
        all_items: list[_CalendarItem] = []

        for day_items in items_by_day.values():
            if not day_items:
                continue

            self._sort_day_items(day_items)
            clusters = self._build_clusters(day_items)

            for cluster in clusters:
                self._assign_columns(cluster)

            all_items.extend(day_items)

        return all_items

    def _create_items_by_day(self) -> dict[int, list[_CalendarItem]]:
        items_by_day: dict[int, list[_CalendarItem]] = {i: [] for i in range(7)}
        self._add_lesson_items(items_by_day)
        self._add_session_items(items_by_day)
        return items_by_day

    def _add_lesson_items(
        self,
        items_by_day: dict[int, list[_CalendarItem]]
    ) -> None:
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

    def _add_session_items(
        self,
        items_by_day: dict[int, list[_CalendarItem]]
    ) -> None:
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

    def _sort_day_items(self, day_items: list[_CalendarItem]) -> None:
        day_items.sort(
            key=lambda x: (x.start_min, -(x.end_min - x.start_min))
        )

    def _build_clusters(
        self,
        day_items: list[_CalendarItem]
    ) -> list[list[_CalendarItem]]:
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

        return clusters

    def _assign_columns(self, cluster: list[_CalendarItem]) -> None:
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

    def paintEvent(self, event) -> None:  # noqa: N802
        p, col_w, today, text_color, grid_pen, sub_grid_pen = (
            self._prepare_paint()
        )

        self._draw_today_column(p, col_w, today)
        self._draw_time_grid(p, grid_pen, sub_grid_pen)
        self._draw_day_columns(p, col_w, grid_pen)
        self._draw_availability(p, col_w)
        self._draw_calendar_items(p, col_w, text_color)
        self._draw_current_time(p, col_w)

        p.end()

    def _prepare_paint(
        self
    ) -> tuple[QPainter, float, date, object, QPen, QPen]:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = self.palette()
        p.fillRect(self.rect(), pal.base())

        if self.is_dark:
            grid_col = QColor(255, 255, 255, 30)
            sub_grid_col = QColor(255, 255, 255, 14)
        else:
            grid_col = QColor(0, 0, 0, 25)
            sub_grid_col = QColor(0, 0, 0, 12)

        return (
            p,
            self._col_w(),
            date.today(),
            pal.text().color(),
            QPen(grid_col, 1),
            QPen(sub_grid_col, 1, Qt.PenStyle.DashLine)
        )

    def _draw_today_column(
        self,
        p: QPainter,
        col_w: float,
        today: date
    ) -> None:
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            if d == today:
                col_x = GUTTER_WIDTH + i * col_w
                tint = QColor(56, 189, 248, 14) if self.is_dark else QColor(37, 99, 235, 12)
                p.fillRect(
                    QRectF(col_x, 0, col_w, (END_HOUR - START_HOUR) * HOUR_HEIGHT),
                    tint
                )

    def _draw_time_grid(
        self,
        p: QPainter,
        grid_pen: QPen,
        sub_grid_pen: QPen
    ) -> None:
        time_font = QFont(self.font())
        time_font.setPointSize(8)
        p.setFont(time_font)
        label_col = QColor(148, 163, 184) if self.is_dark else QColor(100, 116, 139)

        for h in range(START_HOUR, END_HOUR + 1):
            y = (h - START_HOUR) * HOUR_HEIGHT

            p.setPen(grid_pen)
            p.drawLine(int(GUTTER_WIDTH), int(y), self.width(), int(y))

            # 15 dakikalık kılavuz çizgileri
            if h < END_HOUR:
                for minute in (15, 30, 45):
                    sub_y = y + HOUR_HEIGHT * (minute / 60.0)
                    p.setPen(sub_grid_pen)
                    p.drawLine(
                        int(GUTTER_WIDTH),
                        int(sub_y),
                        self.width(),
                        int(sub_y)
                    )

            # 12 saatlik AM / PM gösterimi - çizginin hemen altına (y + 2) hizalandı
            # Böylece üst başlık kaydırma anında saat yazılarını asla ikiye kesmez!
            if h > START_HOUR:
                p.setPen(label_col)
                hour = h % 12
                if hour == 0:
                    hour = 12
                period = "AM" if h < 12 or h == 24 else "PM"
                p.drawText(
                    QRectF(0, y + 2, GUTTER_WIDTH - 8, 16),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                    f"{hour} {period}"
                )

    def _draw_day_columns(
        self,
        p: QPainter,
        col_w: float,
        grid_pen: QPen
    ) -> None:
        h_max = (END_HOUR - START_HOUR) * HOUR_HEIGHT
        for i in range(8):
            x = GUTTER_WIDTH + i * col_w
            p.setPen(grid_pen)
            p.drawLine(int(x), 0, int(x), int(h_max))

    def _draw_availability(
        self,
        p: QPainter,
        col_w: float
    ) -> None:
        tint_map = {
            AvailabilityType.PRIMARY: QColor(34, 197, 94, 35),
            AvailabilityType.RESERVE: QColor(245, 158, 11, 40),
            AvailabilityType.UNAVAILABLE: QColor(148, 163, 184, 45)
        }

        for b in self.blocks:
            day_idx = (b.block_date - self.week_start).days
            if 0 <= day_idx < 7:
                s_min = b.start_time.hour * 60 + b.start_time.minute
                e_min = b.end_time.hour * 60 + b.end_time.minute
                y1 = self._y_for_minute(s_min)
                y2 = self._y_for_minute(e_min)
                x = GUTTER_WIDTH + day_idx * col_w + 1
                p.fillRect(
                    QRectF(x, y1, col_w - 2, max(6.0, y2 - y1)),
                    tint_map[b.block_type]
                )

    def _draw_calendar_items(
        self,
        p: QPainter,
        col_w: float,
        text_color
    ) -> None:
        self._hits = []
        items = self._layout_items()

        for it in items:
            rect = self._item_rect(it, col_w)
            self._hits.append((rect, it))

            if it.lesson is not None:
                self._draw_lesson_card(p, rect, it.lesson, text_color)
            elif it.session is not None:
                self._draw_session_card(p, rect, it.session, text_color)

    def _item_rect(
        self,
        item: _CalendarItem,
        col_w: float
    ) -> QRectF:
        day_x = GUTTER_WIDTH + item.day_idx * col_w
        sub_w = (col_w - 6.0) / item.total_cols
        card_x = day_x + 3.0 + item.col * sub_w
        y1 = self._y_for_minute(item.start_min)
        y2 = self._y_for_minute(item.end_min)
        card_h = max(20.0, y2 - y1 - 2.0)
        card_w = max(18.0, sub_w - 3.0)
        return QRectF(card_x, y1 + 1.0, card_w, card_h)

    def _draw_lesson_card(
        self,
        p: QPainter,
        rect: QRectF,
        lesson: SchoolLesson,
        text_color
    ) -> None:
        # Saydamlık problemi düzeltildi: arkadaki ızgara yazıyı boğmasın diye tok renk kullanılıyor
        base_color = QColor.fromHsv((lesson.subject_id * 53) % 360, 165, 175)
        bg_color = QColor(base_color)
        bg_color.setAlpha(210 if self.is_dark else 225)

        self._draw_card_background(p, rect, bg_color, None)
        p.setBrush(base_color)
        p.drawRoundedRect(QRectF(rect.x(), rect.y(), 4, rect.height()), 2, 2)

        # Kart üzeri metin rengi
        p.setPen(QColor("#FFFFFF") if self.is_dark else QColor("#0F172A"))
        title_font = QFont(self.font())
        title_font.setPointSize(8)
        title_font.setBold(True)
        p.setFont(title_font)

        text_pad = rect.adjusted(7, 2, -3, -2)
        p.drawText(
            text_pad,
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            lesson.subject_name
        )

        if rect.height() > 32:
            self._draw_lesson_time(p, text_pad, lesson)

    def _draw_lesson_time(
        self,
        p: QPainter,
        text_pad: QRectF,
        lesson: SchoolLesson
    ) -> None:
        sub_font = QFont(self.font())
        sub_font.setPointSize(7)
        p.setFont(sub_font)
        p.setPen(QColor(220, 225, 235) if self.is_dark else QColor(71, 85, 105))
        p.drawText(
            QRectF(
                text_pad.x(),
                text_pad.y() + 13,
                text_pad.width(),
                text_pad.height() - 13
            ),
            Qt.AlignmentFlag.AlignTop,
            f"{lesson.start_time:%H:%M} - {lesson.end_time:%H:%M}"
        )

    def _draw_session_card(
        self,
        p: QPainter,
        rect: QRectF,
        sv: SessionView,
        text_color
    ) -> None:
        s = sv.session
        state = sv.display_state(self.now)
        main_color, bg_color = self._session_colors(sv, state)

        self._draw_card_background(
            p,
            rect,
            bg_color,
            QPen(QColor("#EF4444"), 1.5) if state == "overdue" else None
        )

        p.setBrush(main_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(rect.x(), rect.y(), 4, rect.height()), 2, 2)

        p.setPen(QColor("#FFFFFF") if self.is_dark else QColor("#0F172A"))
        title_font = QFont(self.font())
        title_font.setPointSize(8)
        title_font.setBold(True)
        p.setFont(title_font)

        text_pad = rect.adjusted(7, 2, -3, -2)
        mark = "✓ " if state == "completed" else "! " if state == "overdue" else ""
        p.drawText(
            text_pad,
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            f"{mark}{sv.title}"
        )

        if rect.height() > 30:
            self._draw_session_time(p, text_pad, s)

    def _session_colors(
        self,
        sv: SessionView,
        state: str
    ) -> tuple[QColor, QColor]:
        main_color = QColor(CLASS_COLOR[sv.task_class])

        if state == "completed":
            main_color = QColor("#64748B")
            alpha = 185 if self.is_dark else 200
        elif state == "overdue":
            main_color = QColor("#EF4444")
            alpha = 210 if self.is_dark else 225
        else:
            alpha = 205 if self.is_dark else 220

        bg_color = QColor(main_color)
        bg_color.setAlpha(alpha)
        return main_color, bg_color

    def _draw_card_background(
        self,
        p: QPainter,
        rect: QRectF,
        bg_color: QColor,
        border: QPen | None
    ) -> None:
        p.setBrush(bg_color)
        p.setPen(border if border is not None else Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 5, 5)

    def _draw_session_time(
        self,
        p: QPainter,
        text_pad: QRectF,
        session
    ) -> None:
        sub_font = QFont(self.font())
        sub_font.setPointSize(7)
        p.setFont(sub_font)
        p.setPen(QColor(220, 225, 235) if self.is_dark else QColor(71, 85, 105))
        p.drawText(
            QRectF(
                text_pad.x(),
                text_pad.y() + 13,
                text_pad.width(),
                text_pad.height() - 13
            ),
            Qt.AlignmentFlag.AlignTop,
            f"{session.start_time:%H:%M} - {session.end_time:%H:%M} ({session.planned_minutes}m)"
        )

    def _draw_current_time(
        self,
        p: QPainter,
        col_w: float
    ) -> None:
        if not (
            self.week_start
            <= self.now.date()
            <= self.week_start + timedelta(days=6)
        ):
            return

        today_idx = (self.now.date() - self.week_start).days
        now_min = self.now.hour * 60 + self.now.minute
        now_y = self._y_for_minute(now_min)
        line_x = GUTTER_WIDTH + today_idx * col_w

        p.setPen(QPen(QColor("#EF4444"), 2))
        p.drawLine(int(line_x), int(now_y), int(line_x + col_w), int(now_y))

        p.setBrush(QColor("#EF4444"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(line_x, now_y), 4, 4)

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
                f"{CLASS_LABEL[sv.task_class]} — {sv.session.planned_minutes} dk<br>"
                f"<i>{sv.session.explanation or ''}</i>"
            )
        elif it.lesson is not None:
            les = it.lesson
            tip = (
                f"<b>{les.subject_name}</b><br>"
                f"Haftanın {les.subject_lesson_no}. dersi<br>"
            )
            if les.recorded_topic:
                tip += f"Konu: {les.recorded_topic}"
            else:
                tip += "<i>Konuyu kaydetmek için tıklayın</i>"
            self.setToolTip(tip)


class CalendarView(QWidget):
    """Gelişmiş takvim sekmesi."""

    plan_changed = Signal()

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.is_dark = True
        self._initialize_week()
        root = self._create_root_layout()
        self._setup_toolbar(root)
        self._setup_legend(root)
        self._setup_calendar(root)
        self.refresh()
        self._scroll_to_hour(8)

    def set_theme_mode(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self.header.set_theme_mode(is_dark)
        self.grid.set_theme_mode(is_dark)
        self.refresh()

    def _initialize_week(self) -> None:
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())

    def _create_root_layout(self) -> QVBoxLayout:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_TOP,
            TAB_CONTENT_MARGIN_H,
            TAB_CONTENT_MARGIN_BOTTOM
        )
        root.setSpacing(6)
        return root

    def _setup_toolbar(self, root: QVBoxLayout) -> None:
        top_bar = QHBoxLayout()

        today_btn = QPushButton("Bugün")
        prev_btn = QPushButton("◀")
        next_btn = QPushButton("▶")

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 600; font-size: 15px;")

        plan_btn = QPushButton("Planla / Yeniden planla")
        plan_btn.setProperty("primary", True)

        today_btn.clicked.connect(self._go_today)
        prev_btn.clicked.connect(lambda: self._shift(-7))
        next_btn.clicked.connect(lambda: self._shift(7))
        plan_btn.clicked.connect(self.replan)

        top_bar.addWidget(today_btn)
        top_bar.addWidget(prev_btn)
        top_bar.addWidget(next_btn)
        top_bar.addWidget(self.title_label)
        top_bar.addStretch(1)
        top_bar.addWidget(plan_btn)

        root.addLayout(top_bar)

    def _setup_legend(self, root: QVBoxLayout) -> None:
        # Dark mode'da koyu kalmayan, her iki modda da net okunan renkler
        self.legend = QLabel(
            "<span style='color:#5C6BC0; font-weight:bold;'>■</span> Okul dersi &nbsp;&nbsp;"
            "<span style='color:#7E57C2; font-weight:bold;'>■</span> Tekrar &nbsp;&nbsp;"
            "<span style='color:#EF6C00; font-weight:bold;'>■</span> Teslim görevi &nbsp;&nbsp;"
            "<span style='color:#00897B; font-weight:bold;'>■</span> Tekrarlayan &nbsp;&nbsp;"
            "<span style='color:#64748B; font-weight:bold;'>■</span> Tamamlanan &nbsp;&nbsp;"
            "<span style='color:#EF4444; font-weight:bold;'>■</span> Gecikmiş &nbsp;|&nbsp; "
            "<span style='color:#22C55E; font-weight:bold;'>▒</span> PRIMARY &nbsp;&nbsp;"
            "<span style='color:#F59E0B; font-weight:bold;'>▒</span> RESERVE &nbsp;&nbsp;"
            "<span style='color:#94A3B8; font-weight:bold;'>▒</span> UNAVAILABLE"
        )
        self.legend.setObjectName("calendarLegend")
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.legend)

        self.summary = QLabel()
        self.summary.setObjectName("calendarSummary")
        root.addWidget(self.summary)

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
        self._update_title(end)
        self.header.set_week_start(self.week_start)
        sessions, blocks, lessons = self._load_calendar_data(end)
        self.grid.set_data(
            self.week_start,
            sessions,
            blocks,
            lessons
        )

    def _week_end(self) -> date:
        return self.week_start + timedelta(days=6)

    def _update_title(self, end: date) -> None:
        self.title_label.setText(
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
        plan = self._run_replan()
        if plan is None:
            return

        self._show_summary(plan)
        self.refresh()
        self.plan_changed.emit()
        self._show_plan_warnings(plan)

    def _run_replan(self) -> SchedulePlan | None:
        try:
            return self.service.replan()
        except Exception as exc:
            show_error(self, exc)
            return None

    def _show_plan_warnings(self, plan: SchedulePlan) -> None:
        if not (plan.warnings or plan.unscheduled):
            return

        lines = list(plan.warnings)
        lines += [
            f"• {u.title}: {u.minutes} dk yerleştirilemedi ({u.detail})"
            for u in plan.unscheduled[:12]
        ]

        if len(plan.unscheduled) > 12:
            lines.append(f"… ve {len(plan.unscheduled) - 12} kalem daha")

        QMessageBox.information(
            self,
            "Plan uyarıları",
            "\n".join(lines)
        )

    def _show_summary(self, plan: SchedulePlan) -> None:
        total = sum(s.minutes for s in plan.sessions)
        reserve = sum(s.minutes for s in plan.sessions if s.kind.value == "RESERVE")

        self.summary.setText(
            f"Plan: {len(plan.sessions)} oturum, {total} dk "
            f"(RESERVE: {reserve} dk), yerleştirilemeyen: {len(plan.unscheduled)}"
        )

    def _open_session(self, session_id: int) -> None:
        view = self.service.get_session(session_id)
        if view is None:
            return

        if SessionDialog(self.service, view, self).exec() == QDialog.DialogCode.Accepted:
            self._after_session_update()

    def _after_session_update(self) -> None:
        self.refresh()
        self.plan_changed.emit()

        if self._ask_replan():
            self.replan()

    def _ask_replan(self) -> bool:
        return (
            QMessageBox.question(
                self,
                "Yeniden planla",
                "Kalan planı güncel duruma göre yeniden hesaplayayım mı?"
            )
            == QMessageBox.StandardButton.Yes
        )

    def _open_school_lesson(self, lesson: SchoolLesson) -> None:
        if lesson.recorded_topic:
            QMessageBox.information(
                self,
                "Konu zaten kaydedilmiş",
                f"{lesson.subject_name} dersinin konusu "
                f"“{lesson.recorded_topic}” olarak kayıtlı. "
                "Değiştirmek için Dersler sekmesindeki öğrenme geçmişinden kaydı silip yeniden girin."
            )
            return

        if LearningEventDialog(self.service, lesson, self).exec() == QDialog.DialogCode.Accepted:
            self.replan()