# 📦 Amazon Warehouse (Depo) Tracker Bot

Amazon Türkiye Depo (Warehouse Deals) mağazasındaki açık kutu ve ikinci el ürünleri baştan sona tarayan, **dinamik depo stok adetlerini** ve gizli fiyat bağlantılarını ayıklayarak sadece **yeni eklenen** veya **fiyatı düşen** fırsat ürünlerini Telegram üzerinden anlık olarak bildiren akıllı bir takip botudur.

---

## ✨ Özellikler

* 🎯 **Gizli Fiyat Avcısı:** Amazon'un standart arama sayfalarında gizlediği, sadece *"Seçenekleri Gör"* bağlantılarının altında yer alan depo fiyatlarını cımbızla çeker gibi ayıkla.
* 📦 **Dinamik Stok Takibi:** Regex (Düzenli İfadeler) entegrasyonu sayesinde ürünlerin anlık depo stoğunu (1, 2, 5+ adet ikinci el ürün) tespit eder ve karta ekler.
* 📉 **Akıllı İndirim Hesaplayıcı:** Hafızadaki ürünlerin fiyatı düştüğünde eski fiyata oranla indirim yüzdesini hesaplar ve Telegram'a `📉 FİYATI DÜŞTÜ! (%15 İndirim)` etiketiyle fırlatır.
* 🛡️ **409 Çakışma Zırhı:** Bulut platformlarda (Railway vb.) deployment esnasında oluşan hayalet container kilitlenmelerini (`409 Conflict`) kod seviyesinde otomatik olarak sönümler ve kesintisiz çalışır.
* 💤 **Pusu Modu (Anti-Spam):** İlk açılışta mağazadaki tüm eski ürünleri sessizce hafızaya alır; böylece telefonunuzu ilk dakikada yüzlerce gereksiz bildirimle boğmaz.

---

## 🛠️ Kurulum ve Dağıtım (Railway / VPS)

Bu proje **Railway** veya benzeri Docker/Nixpacks tabanlı platformlarda **Worker (Arka Plan İşçisi)** olarak çalışacak şekilde optimize edilmiştir.

### 1. Gerekli Çevre Değişkenleri (Environment Variables)

Projeyi ayağa kaldırmadan önce platformunuzun **Variables** sekmesinden şu değişkenleri tanımlamanız gerekir:

| Değişken Adı | Açıklama |
| :--- | :--- |
| `TELEGRAM_TOKEN` | @BotFather üzerinden aldığınız botunuzun API anahtarı. |
| `TELEGRAM_CHAT_ID` | Bildirimlerin gönderileceği Telegram sohbet veya kanal ID numaranız. |
| `SCRAPERAPI_KEY` | Amazon'un bot korumasını (Captcha) aşmak için ScraperAPI'den aldığınız 32 haneli anahtar. |

### 2. Kritik Platform Yapılandırması (`railway.json`)

Railway'in güncellemeler sırasında çift bot çalıştırıp Telegram hattını kilitlemesini engellemek için proje kök dizininde yer alan `railway.json` yapılandırması **RECREATE** stratejisini kullanır:

```json
{
  "$schema": "[https://railway.app/railway.schema.json](https://railway.app/railway.schema.json)",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python app.py",
    "restartPolicyType": "ON_FAILURE",
    "strategy": "RECREATE"
  }
}
