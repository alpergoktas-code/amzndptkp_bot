import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

bot = telebot.TeleBot(TOKEN)

# Hedef satıcının arama linki
TARGET_URL = "https://www.amazon.com.tr/s?me=A215JX4S9CANSO&marketplaceID=A33AVAJ2PDY3EV"

urun_hafizasi = {}

def get_amazon_page_via_proxy():
    """ScraperAPI kullanarak Amazon sayfasını çeker"""
    if not SCRAPER_KEY:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        return requests.get(TARGET_URL, headers=headers, timeout=20)
    
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={TARGET_URL}&country_code=tr"
    return requests.get(proxy_url, timeout=60)

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi):
    """Görseli, fiyatı ve butonları olan şık mesaj kartını gönderir"""
    mesaj_metni = (
        f"<b>{urun_bilgisi['isim']}</b>\n\n"
        f"🏷 <b>{urun_bilgisi['fiyat']}</b>\n"
    )
    
    if urun_bilgisi.get('indirim_orani'):
        mesaj_metni += f"💬 <b>Ortalama fiyatın %{urun_bilgisi['indirim_orani']} altında</b>\n"
        
    mesaj_metni += "🛍 <b>Amazon</b>"

    # Görüntüdeki gibi "Aç" butonu oluşturur
    markup = InlineKeyboardMarkup()
    buton = InlineKeyboardButton(text="🔗 Aç", url=urun_bilgisi['link'])
    markup.add(buton)

    try:
        if urun_bilgisi['gorsel'] and urun_bilgisi['gorsel'].startswith("http"):
            bot.send_photo(
                chat_id, 
                photo=urun_bilgisi['gorsel'], 
                caption=mesaj_metni, 
                parse_mode="HTML", 
                reply_markup=markup
            )
        else:
            bot.send_message(
                chat_id, 
                text=mesaj_metni, 
                parse_mode="HTML", 
                reply_markup=markup, 
                disable_web_page_preview=False
            )
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

def fiyati_ayıkla(urun_soup):
    """Amazon'un farklı fiyat etiketlerinden fiyatı bulmaya çalışır"""
    # 1. Yöntem: Gizli ama en kararlı olan 'a-offscreen' sınıfı (Örn: "30,00 TL")
    offscreen = urun_soup.find("span", {"class": "a-offscreen"})
    if offscreen:
        return offscreen.text.strip()
    
    # 2. Yöntem: Standart bütünleşik fiyat alanı
    fiyat_tam = urun_soup.find("span", {"class": "a-price-whole"})
    fiyat_krs = urun_soup.find("span", {"class": "a-price-fraction"})
    if fiyat_tam:
        fiyat_str = fiyat_tam.text.strip()
        if fiyat_krs:
            fiyat_str += "," + fiyat_krs.text.strip()
        return fiyat_str + " TL"
    
    return "Fiyat Bilgisi Yok"

def amazon_kontrol():
    global urun_hafizasi
    try:
        response = get_amazon_page_via_proxy()
        if response.status_code != 200:
            return
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        for urun in urunler[:5]:
            try:
                isim_etiketi = urun.find("h2")
                if not isim_etiketi: continue
                isim = isim_etiketi.text.strip()
                
                fiyat = fiyati_ayıkla(urun)
                gorsel_etiketi = urun.find("img", {"class": "s-image"})
                gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None
                
                link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                if isim not in urun_hafizasi:
                    urun_hafizasi[isim] = fiyat
                    urun_kartı = {
                        "isim": isim,
                        "fiyat": fiyat,
                        "gorsel": gorsel_url,
                        "link": link
                    }
                    telegram_tasarimli_mesaj_gonder(CHAT_ID, urun_kartı)
                    time.sleep(2)
            except Exception:
                continue
    except Exception as e:
        print(f"Hata: {e}")

def otomatik_kontrol():
    while True:
        amazon_kontrol()
        time.sleep(1800)

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot.reply_to(message, "🔄 Güvenli hat üzerinden Amazon kontrol ediliyor, kartlar hazırlanıyor...")
    
    try:
        response = get_amazon_page_via_proxy()
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            bot.send_message(message.chat.id, "⚠️ Aktif ürün bulunamadı.")
            return
            
        # İlk 3 ürünü görsel kart formatında basar
        for urun in urunler[:3]:
            isim = urun.find("h2").text.strip()
            fiyat = fiyati_ayıkla(urun)
            gorsel = urun.find("img", {"class": "s-image"})["src"] if urun.find("img", {"class": "s-image"}) else None
            link = "https://www.amazon.com.tr" + urun.find("a", {"class": "a-link-normal s-no-outline"})["href"]
            
            urun_kartı = {
                "isim": isim,
                "fiyat": fiyat,
                "gorsel": gorsel,
                "link": link
            }
            telegram_tasarimli_mesaj_gonder(message.chat.id, urun_kartı)
            time.sleep(2)
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Hata oluştu: {str(e)}")

if __name__ == "__main__":
    t = Thread(target=otomatik_kontrol)
    t.daemon = True
    t.start()
    bot.infinity_polling()
