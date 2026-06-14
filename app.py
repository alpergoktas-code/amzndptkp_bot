import os
import requests
from bs4 import BeautifulSoup
import telebot

# Şifreleri çek
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

print(f"--- SİSTEM KONTROLÜ ---")
print(f"TELEGRAM_TOKEN mevcut mu?: {bool(TOKEN)}")
print(f"TELEGRAM_CHAT_ID mevcut mu?: {bool(CHAT_ID)}")
print(f"SCRAPERAPI_KEY mevcut mu?: {bool(SCRAPER_KEY)}")
print(f"-----------------------")

# Botu en çıplak haliyle başlat (Hata varsa gizleme, çöksün!)
bot = telebot.TeleBot(TOKEN, threaded=False)

BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

print("🚀 Bot Amazon'a ilk test isteğini gönderiyor...")

# ScraperAPI ile ilk sayfayı çekmeyi dene
if SCRAPER_KEY:
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={BASE_URL}&country_code=tr"
    response = requests.get(proxy_url, timeout=30)
else:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(BASE_URL, headers=headers, timeout=15)

print(f"📡 Amazon Yanıt Kodu: {response.status_code}")

soup = BeautifulSoup(response.content, "html.parser")
urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
print(f"📦 İlk sayfada bulunan ürün sayısı: {len(urunler)}")

print("💌 Telegram'a test mesajı gönderiliyor...")
bot.send_message(CHAT_ID, "🚀 Teşhis Modu Aktif: Bot başarıyla çalıştı ve Amazon'a bağlandı!")
print("✅ Test mesajı gönderildi! Şimdi döngü başlatılıyor...")

# Botu normal dinleme moduna al
bot.infinity_polling()
