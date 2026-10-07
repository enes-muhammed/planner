# TÜBİTAK 2204-A – Kişiselleştirilmiş Dinamik Akademik Çalışma Planlayıcı

Lise öğrencileri için, **bireysel hatırlama performansına göre belirlenen tekrar gereksinimlerini**
diğer akademik görevlerle ve öğrencinin **gerçek çalışma zamanlarıyla** birlikte planlayan masaüstü uygulaması.
Bu bir takvim uygulaması değildir; takvim, planlama algoritmasının çıktısıdır.

```
Topic → LearningEvent → MemoryState → Review Task → Task Pool → Availability
      → Dynamic Scheduler → StudySession → Actual Result
```

İlk sürümde AI, makine öğrenmesi, ORM, ağ bağlantısı yoktur. Scheduler deterministiktir ve kararlarını açıklar.

## Kurulum
Python 3.12+ gerekir.
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                          # yalnızca PySide6
```

## Çalıştırma
```bash
python main.py            # veritabanı: ~/.tubitak_study_planner/planner.db
python main.py --demo     # boş veritabanına örnek ders/konu/görev/müsaitlik ekler ve planlar
python main.py --db my.db # farklı veritabanı dosyası
```
İlk kullanım akışı: **Dersler** → ders ekle → "Yeni öğrenme kaydı" → **Planlama ▸ Çalışma zamanları** ile
PRIMARY/RESERVE/UNAVAILABLE blokları ekle → **Takvim ▸ Planla**. Takvimde bir bloğa tıklayınca
planlayıcının açıklaması görünür ve gerçek süre / hatırlama sonucu girilebilir.

## Testler
Testler yalnızca standart kütüphane kullanır (PySide6 gerekmez):
```bash
python -m unittest -v      # ya da: pytest
```

## Dosya yapısı
| Dosya | Sorumluluk |
|---|---|
| `main.py` | Başlatma (DB, QApplication, MainWindow). İş mantığı yok. |
| `database.py` | sqlite3, şema + sürümlü migration, transaction, tüm SQL. |
| `engine.py` | Domain modelleri, memory engine, task engine, scheduler, `PlannerService`. SQL içermez. |
| `ui.py` | Yalnızca arayüz: CalendarView, SubjectsView, TasksView + diyaloglar. |
| `test_engine.py` | Memory/task/scheduler/DB/servis testleri (edge-case dahil). |
| `PROJECT_SPEC.md` | Yaşayan teknik sözleşme (mimari, parametreler, varsayımlar, sınırlar). |

## Temel mimari
* **Memory engine** yalnızca "bu konu *ne zaman* tekrar edilmeli?" sorusunu yanıtlar (ideal tarih + pencere).
* **Scheduler** "bu görev öğrencinin gerçek hayatında *ne zaman* yapılmalı?" sorusunu yanıtlar.
  Review tarihi hard deadline değildir; maliyet fonksiyonuna girer.
* **PlannerService** UI'nin tek giriş noktasıdır; `Database` üzerinden okur/yazar.
* Tüm sayısal parametreler `EngineConfig` altındadır ve **başlangıç deneysel parametreleridir**
  (bilimsel olarak doğrulanmış/optimal olduğu iddia edilmez).

## Mevcut özellikler
* Ders / konu / öğrenme kaydı (ders ≠ konu ≠ öğrenme olayı), kronolojik geçmiş, okul ders programı.
* Objective + subjective recall → birleşik skor → stability/difficulty güncellemesi → ideal tekrar tarihi, relearning.
* Otomatik ve manuel (çok konulu) review; deadline task; tekrarlayan task (günlük / seçili günler / haftada N gün).
* PRIMARY / RESERVE / UNAVAILABLE, günlük buffer, günlük review sınırı, sınav yaklaşımı, bölme (splitting).
* Dinamik yeniden planlama (gerçek süre, kaçırılan oturum, yeni görev), açıklanabilir kararlar.
* Haftalık takvim, görev havuzu ve filtreler.

## Gelecek çalışmalar
Sürükle-bırak, ayarlar ekranı (parametreler), simülasyon/deney altyapısı, öğrenci bazlı parametre kalibrasyonu,
plan kararlılığı (gereksiz kaydırmayı azaltma), CSV/rapor dışa aktarma. Ayrıntı: `PROJECT_SPEC.md`.
