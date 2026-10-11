"""views.py - Modern kart görünümlü Dersler ve Görevler sekmesi."""
from __future__ import annotations

from datetime import date, timedelta
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget
)

from dialogs import TaskDialog
from engine import PlannerService, Task
from ui_common import (
    CLASS_LABEL, STATUS_LABEL, fmt_date, make_table,
    selected_key, set_row, show_error
)


# ==============================================================================
# 🎨 KART WIDGETLARI (Öğrenme Geçmişi & Hafıza Durumu)
# ==============================================================================

class LessonEventCard(QFrame):
    """Tek bir işlenen dersin modern kart görünümü."""

    delete_requested = Signal(int)

    def __init__(self, event_id: int, event_date: date, period_no: int | None, topic_name: str, notes: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.event_id = event_id
        self.setFixedWidth(240)
        self.setFixedHeight(115)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            QFrame:hover {
                border-color: #CBD5E1;
                background-color: #F8FAFC;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 1. Satır: Tarih + Kaçıncı Ders Rozeti + Silme Butonu
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        day_name = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][event_date.weekday()]
        lbl_date = QLabel(f"{day_name}, {event_date.day} {fmt_date(event_date).split()[1] if len(fmt_date(event_date).split()) > 1 else ''}")
        lbl_date.setStyleSheet("font-size: 11px; font-weight: 700; color: #1E293B; border: none; background: transparent;")
        top_row.addWidget(lbl_date)

        if period_no:
            lbl_period = QLabel(f"{period_no}. Ders")
            lbl_period.setStyleSheet("""
                font-size: 10px;
                font-weight: 600;
                color: #475569;
                background-color: #F1F5F9;
                border-radius: 4px;
                padding: 1px 5px;
                border: none;
            """)
            top_row.addWidget(lbl_period)

        top_row.addStretch(1)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(18, 18)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("Kaydı Sil")
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #94A3B8;
                font-size: 11px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #FEE2E2;
                color: #EF4444;
            }
        """)
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self.event_id))
        top_row.addWidget(btn_del)
        layout.addLayout(top_row)

        # 2. Satır: Konu Adı
        lbl_topic = QLabel(topic_name)
        lbl_topic.setWordWrap(True)
        lbl_topic.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A; border: none; background: transparent;")
        layout.addWidget(lbl_topic)

        # 3. Satır: Varsa Not, Yoksa Boşluk
        if notes and notes.strip():
            lbl_notes = QLabel(f"💬 {notes.strip()}")
            lbl_notes.setStyleSheet("font-size: 11px; color: #64748B; font-style: italic; border: none; background: transparent;")
            layout.addWidget(lbl_notes)
        else:
            layout.addStretch(1)


class TopicMemoryCard(QFrame):
    """Konunun hafıza tutma ve tekrar durumunu gösteren kart."""

    def __init__(self, topic_name: str, phase: str, stability: float, difficulty: float, next_review: date | None, review_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setFixedHeight(120)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            QFrame:hover {
                border-color: #CBD5E1;
                background-color: #F8FAFC;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 1. Başlık ve Aşama Rozeti
        top_row = QHBoxLayout()
        lbl_title = QLabel(topic_name)
        lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A; border: none; background: transparent;")
        top_row.addWidget(lbl_title)
        top_row.addStretch(1)

        # Aşama rengi (Pastel tonlar)
        phase_colors = {
            "LEARNING": ("#EFF6FF", "#1D4ED8", "Öğrenme"),
            "REVIEW": ("#F5F3FF", "#6D28D9", "Tekrar"),
            "CONSOLIDATED": ("#F0FDF4", "#15803D", "Pekiştirme"),
        }
        bg_col, txt_col, phase_label = phase_colors.get(phase.upper(), ("#F1F5F9", "#475569", phase))

        lbl_phase = QLabel(phase_label)
        lbl_phase.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 600;
            color: {txt_col};
            background-color: {bg_col};
            border-radius: 4px;
            padding: 2px 6px;
            border: none;
        """)
        top_row.addWidget(lbl_phase)
        layout.addLayout(top_row)

        # 2. Stabilite & Zorluk
        lbl_stab = QLabel(f"Hafıza Gücü: <b>{stability:.1f} gün</b>  •  Zorluk: {difficulty:.1f}")
        lbl_stab.setStyleSheet("font-size: 11px; color: #475569; border: none; background: transparent;")
        layout.addWidget(lbl_stab)

        layout.addStretch(1)

        # 3. İdeal Tekrar Durumu ve Tekrar Sayısı
        bottom_row = QHBoxLayout()
        if next_review:
            is_overdue = next_review <= date.today()
            rev_color = "#DC2626" if is_overdue else "#2563EB"
            rev_bg = "#FEF2F2" if is_overdue else "#EFF6FF"
            rev_prefix = "⚠️ Tekrar: " if is_overdue else "📅 İdeal: "
            lbl_rev = QLabel(f"{rev_prefix}{fmt_date(next_review)}")
            lbl_rev.setStyleSheet(f"""
                font-size: 10px;
                font-weight: 600;
                color: {rev_color};
                background-color: {rev_bg};
                border-radius: 4px;
                padding: 2px 6px;
                border: none;
            """)
            bottom_row.addWidget(lbl_rev)
        else:
            bottom_row.addWidget(QLabel("-"))

        bottom_row.addStretch(1)

        lbl_count = QLabel(f"🔄 {review_count} tekrar")
        lbl_count.setStyleSheet("font-size: 11px; font-weight: 500; color: #64748B; border: none; background: transparent;")
        bottom_row.addWidget(lbl_count)

        layout.addLayout(bottom_row)


# ==============================================================================
# 🏛️ ANA DERSLER GÖRÜNÜMÜ (SubjectsView)
# ==============================================================================

class SubjectsView(QWidget):
    """Modern kart akışı ve analitik paneliyle yeniden tasarlanan Dersler görünümü."""

    subject_changed = Signal()

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._current_sid: int | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Üst Hero Banner (Ders Adı, Metrikler ve Hızlı Butonlar)
        self.hero_frame = QFrame()
        self.hero_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
                padding: 16px 20px;
            }
        """)
        hero_layout = QHBoxLayout(self.hero_frame)
        hero_layout.setContentsMargins(20, 16, 20, 16)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        self.title = QLabel("Bir ders seçin")
        self.title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A; border: none;")
        self.lbl_subtitle = QLabel("Sol menüden bir ders seçerek öğrenme geçmişini inceleyin")
        self.lbl_subtitle.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748B; border: none;")
        title_col.addWidget(self.title)
        title_col.addWidget(self.lbl_subtitle)
        hero_layout.addLayout(title_col)

        hero_layout.addStretch(1)

        # İşlem Butonları
        btn_rename = QPushButton("Dersi Düzenle")
        btn_rename.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rename.clicked.connect(self._rename)

        btn_delete = QPushButton("Dersi Sil")
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #FEF2F2;
                color: #DC2626;
                border: none;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #FEE2E2;
            }
        """)
        btn_delete.clicked.connect(self._delete)

        hero_layout.addWidget(btn_rename)
        hero_layout.addWidget(btn_delete)
        main_layout.addWidget(self.hero_frame)

        # 2. Kaydırılabilir İçerik Alanı (Haftalık Kartlar + Hafıza Durumu)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #FFFFFF; }")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(24, 20, 24, 24)
        self.content_layout.setSpacing(24)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

    @property
    def current_sid(self) -> int | None:
        return self._current_sid

    def select_subject(self, sid: int) -> None:
        self._current_sid = sid
        self.refresh()

    def refresh(self) -> None:
        # Eski içerikleri temizle
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        subjects = self.service.list_subjects()
        if not subjects:
            self.title.setText("Henüz Ders Eklenmemiş")
            self.lbl_subtitle.setText("Sol menüdeki '+ Ders Ekle' butonunu kullanarak ilk dersinizi ekleyin.")
            return

        if self._current_sid is None or not any(s.id == self._current_sid for s in subjects):
            self._current_sid = subjects[0].id

        subject = next((s for s in subjects if s.id == self._current_sid), None)
        if not subject:
            return

        events = self.service.list_learning_events(subject.id)
        memory_items = self.service.list_memory(subject.id)

        # Header Bilgisini Güncelle
        self.title.setText(subject.name)
        self.lbl_subtitle.setText(f"Toplam {len(events)} ders kaydı  •  {len(memory_items)} takip edilen konu")

        # 1. BÖLÜM: Haftalık Gruplu Öğrenme Akışı (Card View)
        self._build_learning_events_section(events)

        # 2. BÖLÜM: Konu Hafıza & Tekrar Durumu (Retention Cards)
        self._build_memory_status_section(memory_items)

        self.content_layout.addStretch(1)

    def _build_learning_events_section(self, events: list) -> None:
        sec_header = QHBoxLayout()
        lbl_sec = QLabel("Öğrenme Geçmişi (Ders Akışı)")
        lbl_sec.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        sec_header.addWidget(lbl_sec)

        badge_count = QLabel(f"{len(events)} Ders")
        badge_count.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #475569;
            background-color: #F1F5F9;
            border-radius: 10px;
            padding: 2px 8px;
        """)
        sec_header.addWidget(badge_count)
        sec_header.addStretch(1)
        self.content_layout.addLayout(sec_header)

        if not events:
            empty_box = QFrame()
            empty_box.setStyleSheet("background-color: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 10px; padding: 20px;")
            box_layout = QVBoxLayout(empty_box)
            lbl_empty = QLabel("Henüz öğrenme kaydı bulunmuyor.\nTakvim üzerinden okul derslerine tıkladığınızda işlenen konular burada haftalık kartlar halinde listelenir.")
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_empty.setStyleSheet("font-size: 12px; color: #64748B; border: none;")
            box_layout.addWidget(lbl_empty)
            self.content_layout.addWidget(empty_box)
            return

        # Haftalara göre grupla (Son haftalar en üstte)
        events_by_week: dict[tuple[date, date], list] = {}
        for v in events:
            e = v.event
            w_start = e.event_date - timedelta(days=e.event_date.weekday())
            w_end = w_start + timedelta(days=6)
            key = (w_start, w_end)
            events_by_week.setdefault(key, []).append(v)

        sorted_weeks = sorted(events_by_week.keys(), key=lambda w: w[0], reverse=True)

        for w_start, w_end in sorted_weeks:
            week_events = events_by_week[(w_start, w_end)]
            week_num = w_start.isocalendar()[1]

            # Hafta Başlığı ve Ayırıcı Çizgi
            week_title_row = QHBoxLayout()
            week_title_row.setSpacing(8)

            lbl_w_tag = QLabel(f"Hafta {week_num}")
            lbl_w_tag.setStyleSheet("""
                font-size: 11px;
                font-weight: 700;
                color: #1E293B;
                background-color: #F1F5F9;
                border-radius: 4px;
                padding: 2px 6px;
            """)
            week_title_row.addWidget(lbl_w_tag)

            lbl_w_range = QLabel(f"{fmt_date(w_start)} – {fmt_date(w_end)}")
            lbl_w_range.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748B;")
            week_title_row.addWidget(lbl_w_range)

            week_title_row.addStretch(1)
            self.content_layout.addLayout(week_title_row)

            # Aynı haftadaki kartları aynı satırda yan yana dizen Grid
            grid = QGridLayout()
            grid.setSpacing(12)
            grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

            cols_per_row = 3  # Her satıra yan yana 3 kart yerleştir
            for idx, v in enumerate(week_events):
                card = LessonEventCard(
                    event_id=v.event.id,
                    event_date=v.event.event_date,
                    period_no=v.event.period_start,
                    topic_name=v.topic_name,
                    notes=v.event.notes or ""
                )
                card.delete_requested.connect(self._delete_event_by_id)
                row = idx // cols_per_row
                col = idx % cols_per_row
                grid.addWidget(card, row, col)

            self.content_layout.addLayout(grid)

    def _build_memory_status_section(self, memory_items: list) -> None:
        self.content_layout.addSpacing(10)

        sec_header = QHBoxLayout()
        lbl_sec = QLabel("Konu Hafıza ve Tekrar Durumu")
        lbl_sec.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        sec_header.addWidget(lbl_sec)

        badge_count = QLabel(f"{len(memory_items)} Konu")
        badge_count.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #475569;
            background-color: #F1F5F9;
            border-radius: 10px;
            padding: 2px 8px;
        """)
        sec_header.addWidget(badge_count)
        sec_header.addStretch(1)
        self.content_layout.addLayout(sec_header)

        if not memory_items:
            lbl_empty = QLabel("Henüz hafıza algoritmasına giren konu bulunmuyor.")
            lbl_empty.setStyleSheet("font-size: 12px; color: #94A3B8; font-style: italic;")
            self.content_layout.addWidget(lbl_empty)
            return

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

        cols_per_row = 3
        for idx, m in enumerate(memory_items):
            st = m.state
            card = TopicMemoryCard(
                topic_name=m.topic_name,
                phase=st.phase.value,
                stability=st.stability_days,
                difficulty=st.difficulty,
                next_review=st.next_review_date,
                review_count=st.review_count
            )
            row = idx // cols_per_row
            col = idx % cols_per_row
            grid.addWidget(card, row, col)

        self.content_layout.addLayout(grid)

    def _delete_event_by_id(self, event_id: int) -> None:
        if QMessageBox.question(self, "Kaydı Sil", "Bu ders kaydını silmek istediğinize emin misiniz?") == QMessageBox.StandardButton.Yes:
            self.service.delete_learning_event(event_id)
            self.refresh()

    def _rename(self) -> None:
        if self._current_sid is None:
            return
        name, ok = QInputDialog.getText(self, "Dersi Düzenle", "Yeni ders adı:", text=self.title.text())
        if ok and name.strip():
            self.service.rename_subject(self._current_sid, name.strip())
            self.refresh()
            self.subject_changed.emit()

    def _delete(self) -> None:
        if self._current_sid is None:
            return
        if QMessageBox.question(self, "Dersi Sil", "Ders ve tüm kayıtları silinecek. Emin misiniz?") == QMessageBox.StandardButton.Yes:
            self.service.delete_subject(self._current_sid)
            self._current_sid = None
            self.refresh()
            self.subject_changed.emit()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())


# ==============================================================================
# 🎯 GÖREVLER GÖRÜNÜMÜ (TasksView)
# ==============================================================================

class TasksView(QWidget):
    """Genişletilmiş sol sidebar ile filtrelenen Görevler sekmesi."""

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._current_filter = "all"
        self._tasks: dict[int, Task] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Üst Araç Çubuğu
        top = QHBoxLayout()
        lbl_head = QLabel("Görev Listesi")
        lbl_head.setStyleSheet("font-size: 20px; font-weight: 800; color: #0F172A;")
        top.addWidget(lbl_head)
        top.addStretch(1)

        btn_new = QPushButton("Yeni Görev +")
        btn_new.setProperty("primary", True)
        menu = QMenu(btn_new)
        menu.addAction("Teslim Görevi…", lambda: self._new("deadline"))
        menu.addAction("Tekrarlayan Görev…", lambda: self._new("recurring"))
        menu.addAction("Manuel Tekrar…", lambda: self._new("review"))
        btn_new.setMenu(menu)
        top.addWidget(btn_new)
        root.addLayout(top)

        # Tablo & Detay Ayrımı
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = make_table(["Başlık", "Tür", "Kalan / Süre", "Son Tarih / İdeal", "Öncelik", "Durum"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.table)

        self._detail = QGroupBox("Görev Detayı")
        form = QVBoxLayout(self._detail)
        self.fields = {k: QLabel("-") for k in ("title", "type", "duration", "remaining", "priority", "deadline", "ideal", "status")}
        for k, lbl in self.fields.items():
            form.addWidget(QLabel(f"<b>{k.capitalize()}:</b>"))
            form.addWidget(lbl)

        btn_cancel = QPushButton("Görevi İptal Et")
        btn_delete = QPushButton("Görevi Sil")
        btn_cancel.clicked.connect(self._cancel)
        btn_delete.clicked.connect(self._delete)
        form.addWidget(btn_cancel)
        form.addWidget(btn_delete)
        form.addStretch(1)

        split.addWidget(self._detail)
        split.setSizes([650, 300])
        root.addWidget(split, 1)

        self.refresh()

    def set_filter(self, filter_key: str) -> None:
        self._current_filter = filter_key
        self.refresh()

    def refresh(self) -> None:
        tasks = self.service.list_tasks(self._current_filter, date.today())
        self._tasks = {t.id: t for t in tasks if t.id is not None}
        self.table.setRowCount(len(tasks))

        for r, t in enumerate(tasks):
            overdue = t.is_overdue(date.today())
            when = fmt_date(t.deadline) if t.deadline else fmt_date(t.ideal_date) if t.ideal_date else "-"
            set_row(
                self.table, r,
                [
                    t.title, CLASS_LABEL[t.task_class],
                    f"{t.remaining_duration}/{t.duration} dk", when,
                    str(t.priority), "Gecikmiş" if overdue else STATUS_LABEL[t.status]
                ],
                t.id
            )
            if overdue:
                for c in range(self.table.columnCount()):
                    self.table.item(r, c).setForeground(QColor("#D32F2F"))

    def _show_detail(self) -> None:
        key = selected_key(self.table)
        t = self._tasks.get(key) if key is not None else None
        if not t:
            for l in self.fields.values():
                l.setText("-")
            return

        self.fields["title"].setText(t.title)
        self.fields["type"].setText(CLASS_LABEL[t.task_class])
        self.fields["duration"].setText(f"{t.duration} dk")
        self.fields["remaining"].setText(f"{t.remaining_duration} dk")
        self.fields["priority"].setText(str(t.priority))
        self.fields["deadline"].setText(fmt_date(t.deadline) if t.deadline else "-")
        self.fields["ideal"].setText(fmt_date(t.ideal_date) if t.ideal_date else "-")
        self.fields["status"].setText("Gecikmiş" if t.is_overdue(date.today()) else STATUS_LABEL[t.status])

    def _new(self, mode: str) -> None:
        if TaskDialog(self.service, mode, self).exec():
            self.refresh()

    def _cancel(self) -> None:
        key = selected_key(self.table)
        if key is not None:
            self.service.cancel_task(key)
            self.refresh()

    def _delete(self) -> None:
        key = selected_key(self.table)
        if key is not None and QMessageBox.question(self, "Sil", "Görev silinsin mi?") == QMessageBox.StandardButton.Yes:
            self.service.delete_task(key)
            self.refresh()