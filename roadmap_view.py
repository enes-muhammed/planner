"""roadmap_view.py - 2026-2027 MEB & Diyanet Yıllık Akademik Yol Haritası ve Müfredat Çizelgesi."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from engine import (
    AcademicCalendarEvent, AcademicEventType, AcademicTerm,
    DayStatus, PlannerService, TermType
)
from ui_common import fmt_date, show_error


class TermSummaryCard(QFrame):
    """4 Periyot / Çeyrek özet kartı."""

    def __init__(self, title: str, dates_str: str, weeks_str: str, badge_text: str, badge_color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none;")
        top.addWidget(lbl_t)
        top.addStretch(1)

        lbl_b = QLabel(badge_text)
        lbl_b.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 700;
            color: {badge_color};
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 1px 6px;
        """)
        top.addWidget(lbl_b)
        layout.addLayout(top)

        lbl_d = QLabel(f"📅 {dates_str}")
        lbl_d.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569; border: none;")
        layout.addWidget(lbl_d)

        lbl_w = QLabel(weeks_str)
        lbl_w.setStyleSheet("font-size: 11px; color: #64748B; border: none;")
        layout.addWidget(lbl_w)


class AcademicEventRow(QFrame):
    """Resmi tatil veya özel gün bilgi satırı."""

    def __init__(self, ev: AcademicCalendarEvent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QFrame:hover {
                background-color: #F8FAFC;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Durum İkonu
        if ev.day_status is DayStatus.CLOSED:
            icon_str, tag_bg, tag_col = "❌", "#FEF2F2", "#DC2626"
            status_desc = "Okul Yok"
        elif ev.day_status is DayStatus.HALF_DAY:
            icon_str, tag_bg, tag_col = "🟡", "#FFFBEB", "#B45309"
            status_desc = "Yarım Gün"
        else:
            icon_str, tag_bg, tag_col = "🏁" if ev.event_type is AcademicEventType.SEMESTER_END else "✅", "#F0FDF4", "#15803D"
            status_desc = "Okul Açık"

        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 14px; border: none; background: transparent;")
        layout.addWidget(lbl_icon)

        # Başlık ve Açıklama
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_title = QLabel(ev.title)
        lbl_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A; border: none;")
        title_box.addWidget(lbl_title)

        if ev.description:
            lbl_desc = QLabel(ev.description)
            lbl_desc.setStyleSheet("font-size: 11px; color: #64748B; border: none;")
            title_box.addWidget(lbl_desc)

        layout.addLayout(title_box)
        layout.addStretch(1)

        # Tarih
        d_str = fmt_date(ev.start_date)
        if ev.start_date != ev.end_date:
            d_str += f" – {fmt_date(ev.end_date)}"

        lbl_date = QLabel(d_str)
        lbl_date.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155; border: none;")
        layout.addWidget(lbl_date)

        # Durum Rozeti
        lbl_st = QLabel(status_desc)
        lbl_st.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 700;
            color: {tag_col};
            background-color: {tag_bg};
            border-radius: 4px;
            padding: 2px 7px;
            border: none;
        """)
        layout.addWidget(lbl_st)


class RoadmapView(QWidget):
    """2026-2027 Akademik Yol Haritası ve Yıllık Müfredat Takip Görünümü."""

    plan_changed = Signal()

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.current_term_filter = "ALL"  # ALL, TERM_1, TERM_2

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(0)

        self._setup_hero(main_layout)
        self._setup_scroll_content(main_layout)
        self.refresh()

    def _setup_hero(self, root: QVBoxLayout) -> None:
        hero = QFrame()
        hero.setObjectName("heroFrame")
        hero.setStyleSheet("""
            QFrame#heroFrame {
                background-color: transparent;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(12)

        # 1. Hafta Rozeti
        badge_frame = QFrame()
        badge_frame.setFixedSize(56, 44)
        badge_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)
        b_layout = QVBoxLayout(badge_frame)
        b_layout.setContentsMargins(0, 4, 0, 4)
        b_layout.setSpacing(0)

        lbl_tag = QLabel("AKADEMİK")
        lbl_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_tag.setStyleSheet("font-size: 8px; font-weight: 800; color: #9CA3AF; border: none;")

        self.lbl_week = QLabel("H.05")
        self.lbl_week.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_week.setStyleSheet("font-size: 13px; font-weight: 800; color: #111827; border: none;")

        b_layout.addWidget(lbl_tag)
        b_layout.addWidget(self.lbl_week)
        layout.addWidget(badge_frame)

        # 2. Başlık
        t_col = QVBoxLayout()
        t_col.setSpacing(2)
        lbl_t = QLabel("2026–2027 Akademik Yol Haritası")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: 800; color: #0F172A; border: none;")
        self.lbl_sub = QLabel("14 Eylül 2026 – 25 Haziran 2027 • 4 Periyot • 2 Dönem • 36 Hafta")
        self.lbl_sub.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748B; border: none;")
        t_col.addWidget(lbl_t)
        t_col.addWidget(self.lbl_sub)
        layout.addLayout(t_col)

        layout.addStretch(1)

        # 3. Filtre Butonları [ Tüm Yıl | 1. Dönem | 2. Dönem ]
        filter_group = QFrame()
        filter_group.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                font-size: 12px;
                color: #475569;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #F8FAFC;
            }
        """)
        f_layout = QHBoxLayout(filter_group)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(0)

        self.btn_all = QPushButton("Tüm Yıl")
        self.btn_t1 = QPushButton("1. Dönem")
        self.btn_t2 = QPushButton("2. Dönem")

        self.btn_all.clicked.connect(lambda: self.set_filter("ALL"))
        self.btn_t1.clicked.connect(lambda: self.set_filter("TERM_1"))
        self.btn_t2.clicked.connect(lambda: self.set_filter("TERM_2"))

        f_layout.addWidget(self.btn_all)
        f_layout.addWidget(self.btn_t1)
        f_layout.addWidget(self.btn_t2)
        layout.addWidget(filter_group)

        root.addWidget(hero)

    def _setup_scroll_content(self, root: QVBoxLayout) -> None:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(20, 16, 20, 20)
        self.content_layout.setSpacing(20)

        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

    def set_filter(self, filter_key: str) -> None:
        self.current_term_filter = filter_key
        # Buton stilleri
        self.btn_all.setStyleSheet("font-weight: 700; color: #0F172A;" if filter_key == "ALL" else "")
        self.btn_t1.setStyleSheet("font-weight: 700; color: #0F172A;" if filter_key == "TERM_1" else "")
        self.btn_t2.setStyleSheet("font-weight: 700; color: #0F172A;" if filter_key == "TERM_2" else "")
        self.refresh()

    def refresh(self) -> None:
        # Eski içeriği temizle
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sub_layout(item.layout())

        # Mevcut hafta hesabı
        today = date.today()
        start_year = date(2026, 9, 14)
        if today < start_year:
            self.lbl_week.setText("Hazırlık")
        elif today > date(2027, 6, 25):
            self.lbl_week.setText("Yaz")
        else:
            diff_weeks = (today - start_year).days // 7 + 1
            self.lbl_week.setText(f"H.{diff_weeks:02d}")

        # 1. BÖLÜM: 4 Çeyrek / Periyot Özet Kartları
        self._build_period_cards()

        # 2. BÖLÜM: Müfredat İlerleme Çizelgesi (Pacing)
        self._build_curriculum_pacing_section()

        # 3. BÖLÜM: MEB & Diyanet Resmi Tatil ve Okul Takvimi
        self._build_holidays_section()

        self.content_layout.addStretch(1)

    def _build_period_cards(self) -> None:
        grid = QGridLayout()
        grid.setSpacing(12)

        periods = [
            ("1. Çeyrek (Güz)", "14 Eyl 2026 – 13 Kas 2026", "9 Hafta Okul", "Ara Tatil: 16-20 Kas", "#2563EB"),
            ("2. Çeyrek (Kış)", "23 Kas 2026 – 22 Oca 2027", "9 Hafta Okul", "Sömestr: 25 Oca-5 Şub", "#1D4ED8"),
            ("3. Çeyrek (Bahar)", "08 Şub 2027 – 05 Mar 2027", "4 Hafta Okul", "Bayram: 8-12 Mar", "#7C3AED"),
            ("4. Çeyrek (Yaz)", "15 Mar 2027 – 25 Haz 2027", "15 Hafta Okul", "Kurban: 17-19 May", "#15803D"),
        ]

        # Filtreye göre periyotları göster
        if self.current_term_filter == "TERM_1":
            active_periods = periods[:2]
        elif self.current_term_filter == "TERM_2":
            active_periods = periods[2:]
        else:
            active_periods = periods

        for idx, (t, d, w, b_txt, b_col) in enumerate(active_periods):
            card = TermSummaryCard(t, d, w, b_txt, b_col)
            grid.addWidget(card, 0, idx)

        self.content_layout.addLayout(grid)

    def _build_curriculum_pacing_section(self) -> None:
        sec_box = QFrame()
        sec_box.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        layout = QVBoxLayout(sec_box)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        head = QHBoxLayout()
        lbl_head = QLabel("📊 Müfredat ve Ünite İlerleme Çizelgesi (Pacing)")
        lbl_head.setStyleSheet("font-size: 14px; font-weight: 800; color: #0F172A; border: none;")
        head.addWidget(lbl_head)
        head.addStretch(1)
        layout.addLayout(head)

        subjects = self.service.list_subjects()
        if not subjects:
            lbl_empty = QLabel("Henüz ders tanımlanmamış.")
            lbl_empty.setStyleSheet("font-size: 12px; color: #94A3B8; font-style: italic; border: none;")
            layout.addWidget(lbl_empty)
            self.content_layout.addWidget(sec_box)
            return

        for subj in subjects:
            if subj.id is None:
                continue

            subj_box = QFrame()
            subj_box.setStyleSheet("""
                QFrame {
                    background-color: #F8FAFC;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                    padding: 8px 12px;
                }
            """)
            s_layout = QVBoxLayout(subj_box)
            s_layout.setSpacing(6)

            # Ders Başlığı
            s_head = QHBoxLayout()
            lbl_sname = QLabel(f"<b>{subj.name}</b>")
            lbl_sname.setStyleSheet("font-size: 13px; color: #1E293B; border: none;")
            s_head.addWidget(lbl_sname)
            s_head.addStretch(1)

            units = self.service.list_units(subj.id)
            lbl_ucount = QLabel(f"{len(units)} Ünite Planlı")
            lbl_ucount.setStyleSheet("font-size: 11px; color: #64748B; border: none;")
            s_head.addWidget(lbl_ucount)
            s_layout.addLayout(s_head)

            # Ünitelerin Yatay İlerleme Barları
            if units:
                units_row = QHBoxLayout()
                units_row.setSpacing(8)
                for u in units:
                    u_card = QFrame()
                    u_card.setStyleSheet("""
                        QFrame {
                            background-color: #FFFFFF;
                            border: 1px solid #CBD5E1;
                            border-radius: 6px;
                            padding: 6px 10px;
                        }
                    """)
                    u_l = QVBoxLayout(u_card)
                    u_l.setContentsMargins(6, 4, 6, 4)
                    u_l.setSpacing(2)

                    lbl_uname = QLabel(f"<b>{u.order_no}. {u.name}</b>")
                    lbl_uname.setStyleSheet("font-size: 11px; color: #0F172A; border: none;")
                    u_l.addWidget(lbl_uname)

                    u_date = f"{fmt_date(u.start_date)}" if u.start_date else "Planlanmadı"
                    if u.end_date:
                        u_date += f" – {fmt_date(u.end_date)}"
                    lbl_udate = QLabel(u_date)
                    lbl_udate.setStyleSheet("font-size: 10px; color: #64748B; border: none;")
                    u_l.addWidget(lbl_udate)

                    units_row.addWidget(u_card)
                units_row.addStretch(1)
                s_layout.addLayout(units_row)
            else:
                lbl_no_u = QLabel("Henüz ünite eklenmemiş. Dersler sekmesinden ekleyebilirsiniz.")
                lbl_no_u.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic; border: none;")
                s_layout.addWidget(lbl_no_u)

            layout.addWidget(subj_box)

        self.content_layout.addWidget(sec_box)

    def _build_holidays_section(self) -> None:
        sec_box = QFrame()
        sec_box.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        layout = QVBoxLayout(sec_box)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        head = QHBoxLayout()
        lbl_head = QLabel("🏖️ 2026–2027 MEB & Diyanet Resmi Okul ve Tatil Takvimi")
        lbl_head.setStyleSheet("font-size: 14px; font-weight: 800; color: #0F172A; border: none;")
        head.addWidget(lbl_head)
        head.addStretch(1)
        layout.addLayout(head)

        # Tarih filtrelemesi
        if self.current_term_filter == "TERM_1":
            s_d, e_d = date(2026, 9, 14), date(2027, 1, 24)
        elif self.current_term_filter == "TERM_2":
            s_d, e_d = date(2027, 2, 8), date(2027, 6, 25)
        else:
            s_d, e_d = date(2026, 9, 14), date(2027, 6, 25)

        events = self.service.list_academic_events(s_d, e_d)
        for ev in events:
            row = AcademicEventRow(ev)
            layout.addWidget(row)

        self.content_layout.addWidget(sec_box)

    def _clear_sub_layout(self, layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sub_layout(item.layout())