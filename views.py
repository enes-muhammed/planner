"""views.py - Tarihli Ünite Kartları, Alt Konu Hafıza Röntgeni ve Görevler sekmesi."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget
)

from dialogs import TaskDialog, UnitDialog
from engine import PlannerService, Task, Unit
from ui_common import (
    CLASS_LABEL, STATUS_LABEL, fmt_date, make_table,
    selected_key, set_row, show_error
)


# ==============================================================================
# 🎨 KART WIDGETLARI (Ders Kaydı, Alt Konu Hafızası & Ünite Kartı)
# ==============================================================================

class LessonEventMiniCard(QFrame):
    """Ünite içindeki tek bir işlenen okul dersi mini kartı."""

    delete_requested = Signal(int)

    def __init__(self, event_id: int, event_date: date, period_no: int | None, topic_name: str, notes: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.event_id = event_id
        self.setFixedWidth(230)
        self.setFixedHeight(95)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QFrame:hover {
                border-color: #CBD5E1;
                background-color: #F8FAFC;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Tarih + Ders Sırası + Silme
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

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
                padding: 1px 4px;
                border: none;
            """)
            top_row.addWidget(lbl_period)

        top_row.addStretch(1)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(16, 16)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("Kaydı Sil")
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #94A3B8;
                font-size: 10px;
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

        # Alt Konu Adı
        lbl_topic = QLabel(topic_name)
        lbl_topic.setWordWrap(True)
        lbl_topic.setStyleSheet("font-size: 12px; font-weight: 600; color: #0F172A; border: none; background: transparent;")
        layout.addWidget(lbl_topic)

        # Not
        if notes and notes.strip():
            lbl_notes = QLabel(f"💬 {notes.strip()}")
            lbl_notes.setStyleSheet("font-size: 10px; color: #64748B; font-style: italic; border: none; background: transparent;")
            layout.addWidget(lbl_notes)
        else:
            layout.addStretch(1)


class TopicMemoryMiniCard(QFrame):
    """Ünite alt konusunun hafıza gücü ve tekrar durumunu gösteren kart."""

    def __init__(self, topic_name: str, phase: str, stability: float, difficulty: float, next_review: date | None, review_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(230)
        self.setFixedHeight(110)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QFrame:hover {
                border-color: #CBD5E1;
                background-color: #F8FAFC;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Konu Adı + Aşama
        top_row = QHBoxLayout()
        lbl_title = QLabel(topic_name)
        lbl_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A; border: none; background: transparent;")
        top_row.addWidget(lbl_title)
        top_row.addStretch(1)

        phase_colors = {
            "LEARNING": ("#EFF6FF", "#1D4ED8", "Öğrenme"),
            "REVIEW": ("#F5F3FF", "#6D28D9", "Tekrar"),
            "CONSOLIDATED": ("#F0FDF4", "#15803D", "Pekiştirme"),
        }
        bg_col, txt_col, phase_label = phase_colors.get(phase.upper(), ("#F1F5F9", "#475569", phase))

        lbl_phase = QLabel(phase_label)
        lbl_phase.setStyleSheet(f"""
            font-size: 9px;
            font-weight: 600;
            color: {txt_col};
            background-color: {bg_col};
            border-radius: 4px;
            padding: 1px 5px;
            border: none;
        """)
        top_row.addWidget(lbl_phase)
        layout.addLayout(top_row)

        # Hafıza Gücü & Zorluk
        lbl_stab = QLabel(f"Hafıza Gücü: <b>{stability:.1f} gün</b> • Zorluk: {difficulty:.1f}")
        lbl_stab.setStyleSheet("font-size: 11px; color: #475569; border: none; background: transparent;")
        layout.addWidget(lbl_stab)

        layout.addStretch(1)

        # Tekrar Rozeti & Sayısı
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
                padding: 1px 5px;
                border: none;
            """)
            bottom_row.addWidget(lbl_rev)
        else:
            bottom_row.addWidget(QLabel("-"))

        bottom_row.addStretch(1)

        lbl_count = QLabel(f"🔄 {review_count}")
        lbl_count.setStyleSheet("font-size: 10px; font-weight: 500; color: #64748B; border: none; background: transparent;")
        bottom_row.addWidget(lbl_count)

        layout.addLayout(bottom_row)


class UnitCardWidget(QFrame):
    """Tarihli ünite ana kartı: Alt konuların hafıza durumları ve okul işlenme geçmişini barındırır."""

    edit_unit_requested = Signal(object)
    delete_unit_requested = Signal(int)
    delete_event_requested = Signal(int)
    add_topic_requested = Signal(int)

    def __init__(
        self,
        unit: Unit | None,
        events: list,
        memory_items: list,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.unit = unit
        self.events = events
        self.memory_items = memory_items

        self.setStyleSheet("""
            UnitCardWidget {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(14)

        # 1. Ünite Başlık Barı (İsim, Tarih Rozeti ve Aksiyonlar)
        self._build_header(card_layout)

        # 2. Alt Konular & Tekrar Durumu (Hafıza Röntgeni)
        self._build_topics_section(card_layout)

        # 3. Okulda İşlenme Geçmişi (Ders Akışı)
        self._build_events_section(card_layout)

    def _build_header(self, layout: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)

        if self.unit:
            # Sıra rozeti
            lbl_order = QLabel(f"{self.unit.order_no}. ÜNİTE")
            lbl_order.setStyleSheet("""
                font-size: 11px;
                font-weight: 800;
                color: #1E293B;
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 3px 8px;
            """)
            head.addWidget(lbl_order)

            # Ünite Adı
            lbl_name = QLabel(self.unit.name)
            lbl_name.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A; border: none; background: transparent;")
            head.addWidget(lbl_name)

            # Tarih Aralığı (Varsa)
            if self.unit.start_date:
                end_str = f" – {fmt_date(self.unit.end_date)}" if self.unit.end_date else "'de Başlandı"
                lbl_dates = QLabel(f"📅 {fmt_date(self.unit.start_date)}{end_str}")
                lbl_dates.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B; border: none; background: transparent;")
                head.addWidget(lbl_dates)

            head.addStretch(1)

            # Özet Metrikler
            lbl_stats = QLabel(f"{len(self.memory_items)} Alt Konu  •  {len(self.events)} Ders Saati")
            lbl_stats.setStyleSheet("font-size: 11px; font-weight: 500; color: #64748B; border: none; background: transparent;")
            head.addWidget(lbl_stats)

            # Düzenle Butonu
            btn_edit = QPushButton("Düzenle")
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setStyleSheet("padding: 4px 10px; font-size: 11px; background-color: #FFFFFF; border: 1px solid #E2E8F0;")
            btn_edit.clicked.connect(lambda: self.edit_unit_requested.emit(self.unit))
            head.addWidget(btn_edit)

            # Sil Butonu
            btn_del = QPushButton("Sil")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: #FEF2F2;
                    color: #DC2626;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #FEE2E2;
                }
            """)
            if self.unit.id is not None:
                btn_del.clicked.connect(lambda: self.delete_unit_requested.emit(self.unit.id))
            head.addWidget(btn_del)
        else:
            # Ünitesiz / Genel Konular
            lbl_name = QLabel("📌 Genel / Henüz Üniteye Atanmamış Konular")
            lbl_name.setStyleSheet("font-size: 15px; font-weight: 700; color: #475569; border: none; background: transparent;")
            head.addWidget(lbl_name)
            head.addStretch(1)

        layout.addLayout(head)

        # Ayırıcı ince çizgi
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(div)

    def _build_topics_section(self, layout: QVBoxLayout) -> None:
        sec_bar = QHBoxLayout()
        lbl_sec = QLabel("🧠 Alt Konular & Hafıza / Tekrar Durumu")
        lbl_sec.setStyleSheet("font-size: 13px; font-weight: 700; color: #334155; border: none; background: transparent;")
        sec_bar.addWidget(lbl_sec)
        sec_bar.addStretch(1)

        if self.unit and self.unit.id is not None:
            btn_add_topic = QPushButton("+ Alt Konu Ekle")
            btn_add_topic.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_add_topic.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #1A73E8;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    text-decoration: underline;
                }
            """)
            btn_add_topic.clicked.connect(lambda: self.add_topic_requested.emit(self.unit.id))
            sec_bar.addWidget(btn_add_topic)

        layout.addLayout(sec_bar)

        if not self.memory_items:
            lbl_empty = QLabel("Bu ünitede henüz kayıtlı alt konu bulunmuyor.")
            lbl_empty.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic; border: none; background: transparent;")
            layout.addWidget(lbl_empty)
            return

        # Alt Konu Kartlarını Yan Yana Diz
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

        cols_per_row = 3
        for idx, m in enumerate(self.memory_items):
            st = m.state
            card = TopicMemoryMiniCard(
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

        layout.addLayout(grid)

    def _build_events_section(self, layout: QVBoxLayout) -> None:
        layout.addSpacing(4)
        lbl_sec = QLabel("🏫 Okulda İşlenme Geçmişi (Ders Akışı)")
        lbl_sec.setStyleSheet("font-size: 13px; font-weight: 700; color: #334155; border: none; background: transparent;")
        layout.addWidget(lbl_sec)

        if not self.events:
            lbl_empty = QLabel("Bu ünite için henüz okul dersi kaydı girilmedi.")
            lbl_empty.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic; border: none; background: transparent;")
            layout.addWidget(lbl_empty)
            return

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

        cols_per_row = 3
        for idx, v in enumerate(self.events):
            card = LessonEventMiniCard(
                event_id=v.event.id,
                event_date=v.event.event_date,
                period_no=v.event.period_start,
                topic_name=v.topic_name,
                notes=v.event.notes or ""
            )
            card.delete_requested.connect(self.delete_event_requested.emit)
            row = idx // cols_per_row
            col = idx % cols_per_row
            grid.addWidget(card, row, col)

        layout.addLayout(grid)


# ==============================================================================
# 🏛️ ANA DERSLER GÖRÜNÜMÜ (SubjectsView)
# ==============================================================================

class SubjectsView(QWidget):
    """Tarihli Ünite Kartları mimarisiyle yeniden inşa edilen Dersler görünümü."""

    subject_changed = Signal()

    def __init__(self, service: PlannerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._current_sid: int | None = None

        # 4 köşenin kesilmesini önlemek için alttan 8px güvenli kenar boşluğu ve şeffaf zemin
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(0)

        # 1. Üst Hero Banner (Köşeleri örtmemesi için şeffaf zemin)
        self.hero_frame = QFrame()
        self.hero_frame.setObjectName("heroFrame")
        self.hero_frame.setStyleSheet("""
            QFrame#heroFrame {
                background-color: transparent;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        hero_layout = QHBoxLayout(self.hero_frame)
        hero_layout.setContentsMargins(20, 14, 20, 14)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        self.title = QLabel("Bir ders seçin")
        self.title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        self.lbl_subtitle = QLabel("Sol menüden bir ders seçerek üniteleri ve öğrenme geçmişini inceleyin")
        self.lbl_subtitle.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748B; border: none; background: transparent;")
        title_col.addWidget(self.title)
        title_col.addWidget(self.lbl_subtitle)
        hero_layout.addLayout(title_col)

        hero_layout.addStretch(1)

        # Butonlar
        btn_add_unit = QPushButton("+ Yeni Ünite Ekle")
        btn_add_unit.setProperty("primary", True)
        btn_add_unit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_unit.clicked.connect(self._add_unit)
        hero_layout.addWidget(btn_add_unit)

        btn_rename = QPushButton("Dersi Düzenle")
        btn_rename.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rename.clicked.connect(self._rename)
        hero_layout.addWidget(btn_rename)

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
        hero_layout.addWidget(btn_delete)

        main_layout.addWidget(self.hero_frame)

        # 2. Kaydırılabilir İçerik Alanı (Şeffaf zemin ile köşe korumalı)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 16, 20, 16)
        self.content_layout.setSpacing(16)

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
        if not subject or subject.id is None:
            return

        units = self.service.list_units(subject.id)
        events = self.service.list_learning_events(subject.id)
        memory_items = self.service.list_memory(subject.id)

        # Header İstatistikleri
        self.title.setText(subject.name)
        self.lbl_subtitle.setText(f"{len(units)} Ünite  •  {len(events)} Ders Saati  •  {len(memory_items)} Takip Edilen Konu")

        if not units and not events and not memory_items:
            empty_box = QFrame()
            empty_box.setStyleSheet("background-color: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 12px; padding: 30px;")
            box_layout = QVBoxLayout(empty_box)
            lbl_empty = QLabel(
                "Bu derse henüz bir ünite veya konu eklenmemiş.\n"
                "Yukarıdaki <b>'+ Yeni Ünite Ekle'</b> butonu ile müfredatınızı planlamaya başlayabilirsiniz."
            )
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_empty.setStyleSheet("font-size: 13px; color: #64748B; border: none; background: transparent;")
            box_layout.addWidget(lbl_empty)
            self.content_layout.addWidget(empty_box)
            return

        # ÜNİTE KARTLARINI SIRALI DİZ
        for u in units:
            u_events = [v for v in events if v.unit_id == u.id]
            u_memory = [m for m in memory_items if m.unit_id == u.id]

            card = UnitCardWidget(unit=u, events=u_events, memory_items=u_memory)
            card.edit_unit_requested.connect(self._edit_unit)
            card.delete_unit_requested.connect(self._delete_unit)
            card.delete_event_requested.connect(self._delete_event)
            card.add_topic_requested.connect(self._add_topic_to_unit)
            self.content_layout.addWidget(card)

        # Henüz bir üniteye atanmamış konular veya ders kayıtları varsa göster
        unassigned_events = [v for v in events if v.unit_id is None]
        unassigned_memory = [m for m in memory_items if m.unit_id is None]
        if unassigned_events or unassigned_memory:
            unassigned_card = UnitCardWidget(unit=None, events=unassigned_events, memory_items=unassigned_memory)
            unassigned_card.delete_event_requested.connect(self._delete_event)
            self.content_layout.addWidget(unassigned_card)

        self.content_layout.addStretch(1)

    def _add_unit(self) -> None:
        if self._current_sid is None:
            return
        dlg = UnitDialog(self.service, self._current_sid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.subject_changed.emit()

    def _edit_unit(self, unit: Unit) -> None:
        if self._current_sid is None:
            return
        dlg = UnitDialog(self.service, self._current_sid, unit=unit, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.subject_changed.emit()

    def _delete_unit(self, unit_id: int) -> None:
        if QMessageBox.question(
            self,
            "Üniteyi Sil",
            "Bu üniteyi silmek istediğinize emin misiniz?\n"
            "Bağlı konular genel konular alanına aktarılacaktır."
        ) == QMessageBox.StandardButton.Yes:
            self.service.delete_unit(unit_id)
            self.refresh()
            self.subject_changed.emit()

    def _delete_event(self, event_id: int) -> None:
        if QMessageBox.question(self, "Kaydı Sil", "Bu ders kaydını silmek istediğinize emin misiniz?") == QMessageBox.StandardButton.Yes:
            self.service.delete_learning_event(event_id)
            self.refresh()

    def _add_topic_to_unit(self, unit_id: int) -> None:
        if self._current_sid is None:
            return
        name, ok = QInputDialog.getText(self, "Yeni Alt Konu", "Alt konu adı:")
        if ok and name.strip():
            self.service.get_or_create_topic(self._current_sid, name.strip(), unit_id=unit_id)
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
        if QMessageBox.question(self, "Dersi Sil", "Ders ve tüm ünite, konu ve kayıtları silinecek. Emin misiniz?") == QMessageBox.StandardButton.Yes:
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