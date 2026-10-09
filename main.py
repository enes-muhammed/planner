"""main.py - application entry point (no business logic here)."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from database import Database
from engine import AvailabilityType, PlannerService, RecurrenceKind, RecurringRule


def default_db_path() -> Path:
    folder = Path.home() / ".tubitak_study_planner"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "planner.db"


def seed_demo(service: PlannerService) -> None:
    """Optional demo data (only service API calls): Subject -> Topic -> Event -> Review -> Plan."""
    if service.list_subjects():
        return
    today = date.today()
    math = service.add_subject("Matematik")
    service.add_subject("Fizik")
    service.add_subject("Türk Dili ve Edebiyatı")
    for offset, periods, topic in ((6, (1, 2), "Üçgenler"), (4, (3, 4), "Trigonometri"),
                                   (1, (1, 2), "Trigonometri"), (0, (3, 4), "Paralelkenar")):
        service.add_learning_event(math.id, today - timedelta(days=offset), topic, *periods)
    service.add_availability_range(today, today + timedelta(days=20), range(5), time(17, 0), time(21, 30),
                                   AvailabilityType.PRIMARY)
    service.add_availability_range(today, today + timedelta(days=20), range(5, 7), time(10, 0), time(13, 0),
                                   AvailabilityType.PRIMARY)
    service.add_availability_range(today, today + timedelta(days=20), range(7), time(21, 30), time(23, 0),
                                   AvailabilityType.RESERVE)
    service.add_deadline_task(title="Matematik performans ödevi", duration=90, deadline=today + timedelta(days=5),
                              priority=6, splittable=True, minimum_session=30, tags=["#Okul", "#Matematik"])
    service.add_recurring_task(today=today, title="TYT Matematik", duration=45,
                               rule=RecurringRule(RecurrenceKind.DAILY), priority=8, tags=["#TYT"])
    service.add_recurring_task(today=today, title="20 paragraf", duration=20,
                               rule=RecurringRule(RecurrenceKind.DAILY), priority=6, tags=["#TYT", "#Günlük"])
    service.add_recurring_task(today=today, title="Soru çözümü", duration=40,
                               rule=RecurringRule(RecurrenceKind.TIMES_PER_WEEK, times_per_week=3), priority=5)
    service.replan(datetime.now())


def main() -> int:
    parser = argparse.ArgumentParser(description="TÜBİTAK dinamik çalışma planlayıcı")
    parser.add_argument("--db", type=Path, default=None, help="SQLite dosya yolu")
    parser.add_argument("--demo", action="store_true", help="boş veritabanına örnek veri ekle")
    args = parser.parse_args()

    db = Database(args.db or default_db_path())
    service = PlannerService(db)
    if args.demo:
        seed_demo(service)

    from PySide6.QtWidgets import QApplication   # type: ignore # imported late: engine/tests need no Qt
    from ui import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow(service)
    window.show()
    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())

