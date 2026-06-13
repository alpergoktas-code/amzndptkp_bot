import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot import types

# Çevre değişkenlerinden bilgileri al (Railway'e gireceğiz)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telebot.TeleBot(TOKEN)

# Amazon Depo Satıcı Linki (Örnek Genel Link - Gerekirse spesifik bir kategori linkiyle değiştirin)
AMAZON_URL = "https://www.amazon.com.tr/s?me=A21V19159D71X&marketplaceID=A33AVAJ2PDY3EV"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

# Veritabanı yerine basit bir hafıza (Fiyat düşüşlerini anlamak için)
urun_hafizasi = {}

def amazon_kontrol():
    global urun_hafizasi
    mesaj_metni = "📦 **Amazon Depo Son Durum:**\n\n"
    guncelleme_var = False
    
    try:
        response = requests.get(AMAZON_URL, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return "Amazon'a erişilemedi (Hata kodu: {})".format(response.status_code)
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            return "Şu anda listelenen ürün bulunamadı veya Amazon engeline takılındı."

        for urun in urunler[:10]: # İlk 10 ürünü kontrol et (Çok uzun mesaj olmaması için)
            isim_etiketi = urun.find("h2")
            isim = isim_etiketi.text.strip() if isim_etiketi else "Bilinmeyen Ürün"
            
            fiyat_tam = urun.find("span", {"class": "a-price-whole"})
            fiyat_krs = urun.find("span", {"class": "a-price-fraction"})
            
            if fiyat_tam:
                fiyat_str = fiyat_tam.text.strip().replace(",", "").replace(".", "")
                fiyat = float(fiyat_str)
                if fiyat_krs:
                    fiyat += float("0." + fiyat_krs.text.strip())
            else:
                fiyat = None

            link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
            link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

            # Fiyat ve Yeni Ürün Kontrolü
            if isim not in urun_hafizasi:
                urun_hafizasi[isim] = fiyat
                mesaj_metni += f"🆕 **YENİ:** {isim}\n💰 Fiyat: {fiyat} TL\n🔗 [Ürüne Git]({link})\n\n"
                guncelleme_var = True
            elif fiyat and urun_hafizasi[isim] and fiyat < urun_hafizasi[isim]:
                eski_fiyat = urun_hafizasi[isim]
                urun_hafizasi[isim] = fiyat
                mesaj_metni += f"📉 **FİYAT DÜŞTÜ:** {isim}\n❌ Eski: {eski_fiyat} TL -> ✅ Yeni: {fiyat} TL\n🔗 [Ürüne Git]({link})\n\n"
                guncelleme_var = True
            else:
                # Fiyat değişmediyse veya ilk defa hafızaya alınıyorsa genel listede göster
                urun_hafizasi[isim] = fiyat

        if guncelleme_var:
            return mesaj_metni
        else:
            return None # Değişiklik yoksa otomatik mesaj tetiklenmesin

    except Exception as e:
        return f"Bir hata oluştu: {str(e)}"

# 30 Dakikada bir çalışan otomatik fonksiyon
def otomatik_kontrol():
    while True:
        sonuc = amazon_kontrol()
        if sonuc: # Eğer yeni ürün veya fiyat düşüşü varsa mesaj at
            try:
                bot.send_message(CHAT_ID, sonuc, parse_mode="Markdown", disable_web_page_preview=True)
            except Exception as e:
                print("Mesaj gönderme hatası:", e)
        time.sleep(1800) # 1800 saniye = 30 dakika

# Telegram Komut Yapısı (/kontrol yazınca çalışır)
@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot.reply_to(message, "🔄 Amazon Depo kontrol ediliyor, lütfen bekleyin...")
    
    # Hafızayı sıfırlamadan o anki ilk 5-10 ürünü direkt raporla
    try:
        response = requests.get(AMAZON_URL, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        rapor = "📊 **Anlık Amazon Depo Listesi:**\n\n"
        for urun in urunler[:5]:
            isim = urun.find("h2").text.strip()
            fiyat_tam = urun.find("span", {"class": "a-price-whole"})
            fiyat = fiyat_tam.text.strip() + " TL" if fiyat_tam else "Fiyat Bulunamadı"
            link = "https://www.amazon.com.tr" + urun.find("a", {"class": "a-link-normal s-no-outline"})["href"]
            rapor += f"• {isim}\n💰 Fiyat: {fiyat}\n🔗 [Ürüne Git]({link})\n\n"
        
        bot.send_message(message.chat.id, rapor, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"Hata: {str(e)}")

if __name__ == "__main__":
    # Otomatik kontrolü arka planda (Thread) başlat
    t = Thread(target=otomatik_kontrol)
    t.daemon = True
    t.start()
    
    # Telegram botu dinlemeye başla
    print("Bot aktif...")
    bot.infinity_polling()