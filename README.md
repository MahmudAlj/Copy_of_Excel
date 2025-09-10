# 📊 Copy-of-Excel

Bu proje, Excel/CSV tabanlı verilerle çalışan, **iş yeri / masraf yeri** bazlı maliyet bileşenlerini (AMOR, DIS, EDIS, ENER, GUG) hesaplamaya yarayan masaüstü bir Python uygulamasıdır.  
Uygulama, **PySide6 (Qt GUI)** tabanlı modern bir arayüz sunar ve kullanıcıya iki farklı veri tablosunu (üst / alt) yönetme, karşılaştırma, eşleme ve dışa aktarma imkânı sağlar.

---

## 🚀 Özellikler

- **Modern GUI (PySide6 + Fusion tema)**
  - Koyu/Açık tema desteği
  - Filtreleme, arama, tablo düzenleme
  - Satır / sütun ekleme ve silme
  - Geri al (Undo) desteği
  - Sağ tık menüsü ile kopyalama ve otomatik sütun boyutlandırma

- **Veri Yönetimi**
  - Excel/CSV dosyalarını içe aktarma (üst ve alt tablolar)
  - Manuel veri girişi (İş Yeri, Masraf Yeri vb.)
  - Eşleme uygulama ve sisteme aktarma
  - Dosyaları kaydetme veya farklı kaydetme
  - CSV’ye dışa aktarma

- **Maliyet Hesaplama**
  - AMOR, DIS, EDIS, ENER, GUG bileşenlerini otomatik tanıma
  - İş yeri + masraf yeri filtreleme
  - Varsayılan formüller (`PROCESS_MALIYETI = AMOR + DIS + EDIS + ENER + GUG`)
  - Opsiyonel: Excel’den özel formül okuma (`IS_PLAN_FORMULLER.xlsx`)
  - Satır bazlı detay + özet toplamlar

---

## 📂 Proje Yapısı

.
├── app.py # PySide6 GUI (ana uygulama)
├── core_schema.py # Sütun isimleri için normalize / eşleme şeması
├── cost_components.py # Maliyet bileşenlerini bulma, hesaplama, formüller
├── data_engine.py # veri motoru (bu projeyle birlikte çalışır)
└── IS_PLAN_FORMULLER.xlsx (opsiyonel) # Formül tanımları

yaml
Kodu kopyala

---

## 🛠️ Kurulum

Python 3.10+ önerilir.

```bash
git clone https://github.com/MahmudAlj/Copy-of-Excel.git
cd Copy-of-Excel
pip install -r requirements.txt
requirements.txt
txt
Kodu kopyala
pandas
PySide6
openpyxl
▶️ Çalıştırma
bash
Kodu kopyala
python app.py
Uygulama açıldığında:

Üst Tablo → sistem verileri

Alt Tablo → yeni / staged veriler
olarak gösterilir. "Sisteme Aktar" ile alt tablo üst tabloya işlenebilir.

📘 Kullanım Senaryosu
Dosyaları Yükle

Üst tabloya mevcut sistem verilerini yükle.

Alt tabloya yeni gelen verileri yükle.

Filtrele / Eşle

İş Yeri ve Masraf Yeri kodlarını girerek ilgili kayıtları seç.

"İşyeri+Masraf → Bileşen/Formula" ile maliyetleri hesapla.

Kaydet veya Dışa Aktar

Verileri Excel/CSV’ye kaydet.

Alt tabloyu CSV olarak dışa aktar.

🧩 Örnek Formül Dosyası
IS_PLAN_FORMULLER.xlsx dosyasında şu format olmalı:

name	expr
PROCESS_MALIYETI	AMOR + DIS + EDIS + ENER + GUG
ENER_AMOR_RATIO	ENER / (AMOR + 1)

📜 Lisans
MIT Lisansı altında dağıtılmaktadır.

yaml
Kodu kopyala

---

👉 Bunu **tek seferde kopyalayıp** `README.md` olarak yapıştırabilirsin. İçinde `requirements.txt` bölümü de hazır, onu ayrıca dosya olarak çıkarabilirsin.  

İstiyor musun ki ben sana `requirements.txt` dosyasını da ayrıca tam içerik halinde buraya ekleyeyim, sen hiç uğraşma?



