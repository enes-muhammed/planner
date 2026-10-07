# PROJECT_SPEC – Kişiselleştirilmiş Dinamik Akademik Çalışma Planlama Sistemi

Durum: **v0.1 çalışan prototip.** Bu dosya kodla birlikte güncellenir; kod ile çelişirse kod düzeltilir ya da bu dosya.

## 1. Etiketleme kuralı (önemli)
| Etiket | Anlamı |
|---|---|
| **Literature-supported concept** | Genel ilke literatürde araştırılmıştır (retrieval practice, spaced practice). Sayısal değer anlamına gelmez. |
| **Initial experimental parameter** | Prototip için seçilmiş başlangıç değeri; simülasyon/pilotla belirlenecek. |
| **Design decision** | Mühendislik tercihi; bilimsel iddia içermez. |

> **Bu sürümdeki hiçbir sayısal parametre "scientifically validated" değildir.** Aşağıdaki tablolar bunu açıkça ayırır.

## 2. Mimari
```
ui.py ──► PlannerService (engine.py, bölüm E) ──► Database (database.py) ──► SQLite
              │
              ├─ MemoryEngine   (B)  ideal tekrar tarihi
              ├─ TaskEngine     (C)  görev üretimi, occurrence, bölme
              └─ Scheduler      (D)  yerleştirme + açıklama
```
* `engine.py` SQL göndermez; `database.py` domain'i import etmez (satırlar `dict`). Dönüşüm `row_to_model` / `model_to_row`.
* UI SQL, memory formülü ya da scheduler içermez.
* Scheduler saf fonksiyondur: `SchedulerInput → SchedulePlan`. `today`/`now` dışarıdan verilir → deterministik, test edilebilir.

## 3. Veri modeli (özet)
Subject (ders) 1─n Topic (konu) 1─n LearningEvent (tarih + ders saati). Topic 1─1 MemoryState.
Task (REVIEW | DEADLINE_TASK | RECURRING_TASK) n─n Topic (`task_topic_links`). Recurring Task 1─n TaskOccurrence.
Task 1─n StudySession (planlanan / gerçekleşen). AvailabilityBlock (PRIMARY/RESERVE/UNAVAILABLE). Exam n─n Topic.
SchoolTimetable (haftalık program) **ayrı** tutulur; işlenen konu yalnızca LearningEvent'te yaşar.

## 4. Veritabanı tabloları (şema sürümü 1)
`students, subjects, topics, learning_events, memory_states, tasks, task_topic_links, task_occurrences,
availability_blocks, study_sessions, exams, exam_topic_links, school_timetable, settings`
* Tarih `YYYY-MM-DD`, saat `HH:MM`, datetime ISO 8601. Foreign key açık; dosya DB'de WAL.
* `tasks.tags` ve `tasks.recurring_rule` JSON metin (ayrı tag tablosu bilinçli olarak yok).
* Tablo/sütun adları şemaya karşı doğrulanır; değerler parametrelidir. Test: model alanları == tablo sütunları.
* Sütun adları: `availability_blocks(block_date, start_time, end_time, block_type)` (`end` SQL anahtar kelimesi olduğu için); `tasks.task_class`.
* Migration: `MIGRATIONS` listesi + `PRAGMA user_version`; her adım tek transaction.
* Silme: ders silinince konular, öğrenme kayıtları, hafıza durumu ve ilgili review görevleri silinir; görev silinince oturumları da silinir (CASCADE).

## 5. Memory model (Initial experimental parameters)
* Subjective: `(rating-1)/9`. Birleşik skor `Q = 0.75·objective + 0.25·subjective` (ağırlıklar config).
* Performans çarpanı: `Q<0.40→0.50; <0.60→0.80; <0.80→1.20; <0.90→1.60; ≥0.90→2.00`.
* `S_new = clamp(S_old · çarpan · (1.10 − 0.20·D), 1, 180)` gün. Varsayılan: faktörde **eski** D kullanılır (`use_updated_difficulty_for_stability=False`) – spesifikasyon sırayı belirtmediği için bu bir *design decision*.
* `D_new = clamp(D + 0.10·(0.5 − Q), 0, 1)`, `D₀ = 0.5`, `S₀ = 3 gün`.
* Unutma: `R(t) = 2^(−t/S)`; hedef `R = 0.85` ⇒ `t = −S·log2(0.85) ≈ 0.234465·S`; ideal aralık en yakın tam güne yuvarlanır (yarım yukarı), alt sınır 1 gün.
* Başarısızlık: `Q < 0.40` ⇒ `RELEARNING`, `lapse_count++`, sonraki tekrar `relearning_interval_days` (1) gün sonra.
* Review penceresi: ideal ±1 gün; `earliest ≥ son çalışma + min aralık`.
* Aynı konuya yeni LearningEvent: stability korunur, saat yeniden başlar (*design decision*).
* Tekrar süresi: ilk konu 30 dk, ek konu başına +15 dk. Aciliyet: `5 + 3·D (+2 relearning)`.

**Bilinen sonuç:** bu başlangıç değerleriyle aralıklar yavaş uzar (S=4.8 gün ⇒ ~1.1 gün aralık; S=100 ⇒ ~23 gün). Belgedeki "1 → 14 → 36" gibi seyrek diziler bu parametrelerle kendiliğinden çıkmaz; `target_recall`, çarpanlar ve `S₀` simülasyonla yeniden ayarlanmalıdır.

## 6. Scheduler modeli (Initial experimental parameters + design decisions)
**Hard constraints:** UNAVAILABLE zaman, tamamlanmış/geçmiş zaman, deadline ve tekrar pencereleri, minimum oturum (küçük artık yaratılmaz), bölünemeyen görevlerde bitişik slot, günlük review sınırı, slot türü uygunluğu.
**Slot türleri:** PRIMARY (maliyet 0) · BUFFER (günlük PRIMARY kapasitenin %20'si, günün sonundan ayrılır, maliyet 1; yalnızca baskısı ≥0.6 olan ya da gecikmiş deadline görevleri) · RESERVE (maliyet 2; yalnızca deadline ve recurring görevler; review kullanamaz).
**Sıralama skoru (soft):** `1.0·priority/10 + 2.5·deadline_baskısı + 1.5·review_aciliyeti + 1.0·sınav_yakınlığı + 0.8·rutin + 0.5·delay_cost/10`. Eşitlikte pencere genişliği, sonra id.
**Yerleştirme maliyeti (dakika başına):** slot maliyeti + zaman maliyeti + 0.4·günlük yük + 0.3·bölme cezası; en düşük maliyet seçilir.
* Review zaman maliyeti: ideale uzaklık (erken 0.3/gün, geç 0.5/gün) + pencere dışı cezası, aciliyetle ölçeklenir. Pencere başlangıcından en fazla 2 gün önce planlanır.
* Deadline zaman maliyeti: son tarihe yaklaştıkça artan risk; gecikmiş görev en erken uygun yere konur.
* Recurring: pencere sert (günlük = o gün); haftada N gün için pencere hafta, nominal gün ortalama dağıtılır.
* Günlük review sınırı: PRIMARY (buffer hariç) kapasitenin %50'si → birikmiş reviewlar günlere yayılır, deadline'ları aç bırakmaz.
* Sınav: konusu sınava bağlı review'ın ideal tarihi sınavdan 1 gün öncesine çekilir; sınav yaklaştıkça skor artar.
* Sığmayan iş: kısmen yerleştirilir, kalan `UnscheduledItem(reason, minutes)` olarak raporlanır; son tarih riski `warnings`'e yazılır.
* Her oturumun `explanation` alanı: neden bu gün/slot, ideal tarihten sapma, RESERVE/BUFFER kullanım nedeni.
* **Dinamik yeniden planlama** = aynı scheduler'ı güncel durumla yeniden çalıştırmak. Başlamış-tamamlanmamış PLANNED oturumlar `MISSED` olur, gelecekteki PLANNED oturumlar silinip yeniden üretilir; tamamlanan oturumlar gerçek süreleriyle meşgul zaman sayılır. `remaining_duration -= gerçek süre`.

## 7. UI görünümleri
* **CalendarView:** haftalık 7 kolon × saat; müsaitlik arka planı; oturum durumları (planlı / tamamlanan / gecikmiş) ve türleri renk ile ayrılır; oturuma tıklayınca açıklama + sonuç girişi.
* **SubjectsView:** ders listesi (ekle/düzenle/sil), seçili dersin kronolojik öğrenme geçmişi, yeni öğrenme kaydı, konu hafıza durumu.
* **TasksView:** görev havuzu; filtreler all/review/deadline/recurring/overdue/completed; detay paneli; yeni görev (deadline, recurring, manuel review).
* Ek diyaloglar: müsaitlik, okul ders programı, sınavlar.

## 8. Konfigürasyon
`EngineConfig(memory, task, scheduler)` – dondurulmuş dataclass'lar. Testlerde `replace(...)`/`with_overrides(...)` ile değiştirilir;
`PlannerService.update_config({...})` skaler değerleri `settings` tablosuna kaydeder (tuple alanları şimdilik koddan).
Parametre listesi doğrudan `engine.py` bölüm 0'dadır; her biri *initial experimental parameter*'dır.

## 9. Varsayımlar
1. Süreler dakika, planlama dakika çözünürlüğündedir; oturumlar slotun başına yerleşir.
2. Bir review tek bir "oturum"dur (bölünemez); tamamlanması için her konuya objective (0–1) ve subjective (1–10) sonuç girilir. Çok konulu review'da session kaydına ortalama yazılır, hafıza güncellemesi konu bazlıdır.
3. Overdue türetilmiş bir durumdur (veritabanında saklanmaz); kaçırılan oturum `MISSED`, süresi dolan recurring occurrence `MISSED` olur.
4. Tek öğrenci (id=1) kullanılır; şema çok öğrenciye hazırdır.
5. Tag'ler yalnızca filtreleme/etiketleme içindir; scheduler bunlara bağlı değildir.

## 10. Bilinen sınırlamalar
* Scheduler açgözlü sezgiseldir; global optimum garantisi yoktur (sıralama + en düşük maliyetli slot).
* Planlar arası kararlılık yok: yeniden planlamada gereksiz kaydırma olabilir.
* Tek çalışma günü içinde slot başına tek bloğa yerleştirme; saat tercihi (sabah/akşam) yok; geçiş süresi yalnızca buffer ile modellenir.
* Gün içi kısmi ilerleme için "iş birimi" ilerlemesi = gerçek süre varsayılır (30 dk'lık iş 60 dk sürdüyse 60 dk ilerleme sayılır).
* Takvimde sürükle-bırak yok; parametre ayar ekranı yok.
* UI, geliştirme ortamında gerçek PySide6 ile **çalıştırılamadı**; sınıflar sahte (stub) PySide6'ya karşı oluşturularak isim/akış hataları denendi. Gerçek ekran ilk çalıştırmada gözden geçirilmelidir.
* Kapsam dışı: bildirim, çoklu cihaz/senkronizasyon, AI/ML.

## 11. TODO
* [ ] Parametre ayar ekranı ve `settings` üzerinden tuple alanları.
* [ ] Plan karşılaştırma ölçütleri: on-time completion, overdue sayısı, review-window ihlali, deadline ihlali, yeniden planlama sayısı, planlanan/gerçek süre.
* [ ] Simülasyon altyapısı (sentetik öğrenciler, üç sistem karşılaştırması).
* [ ] Okul ders programından LearningEvent için saat önerisi.
* [ ] Plan kararlılığı (önceki plana yakınlık bonusu).
* [ ] Sürükle-bırak ve oturumu elle sabitleme.

## 12. Çözülmemiş araştırma parametreleri
`target_recall`, performans çarpanı bantları, `S₀`, `S_max`, objective/subjective ağırlıkları, difficulty adımı, review pencere genişliği,
başlangıç aralık dizisi (örn. 1→14→36 adayı), review süresi, günlük review payı, buffer oranı, RESERVE/BUFFER maliyetleri,
sıralama skoru ağırlıkları, sınav çekme gün sayısı. Hepsi literatür + simülasyon + pilot sonuçlarına göre belirlenecektir.
