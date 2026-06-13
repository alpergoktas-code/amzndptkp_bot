import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Çevre değişkenleri
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

bot = telebot.TeleBot(TOKEN)

# Hedef satıcının arama linki
TARGET_URL = "https://www.amazon.com.tr/s?me=A215JX4S9CANSO&marketplaceID=A33AVAJ2PDY3EV"

# Fiyat geçmişini tutmak ve "Ortalama fiyatın %X altında" diyebilmek için hafıza
# Format: {"Ürün Adı": {"en_yuksek": 100.0, "son_fiyat": 100.0}}
urun_hafizasi = {}

def get_amazon_page_via_proxy():
    """ScraperAPI kullanarak Amazon engelini aşan fonksiyon"""
    if not SCRAPER_KEY:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        return requests.get(TARGET_URL, headers=headers, timeout=20)
    
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={TARGET_URL}&country_code=tr"
    return requests.get(proxy_url, timeout=60)

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi):
    """Gelen ürün bilgisini görsel, buton ve emoji mizanpajıyla Telegram'a iletir"""
    # HTML formatında metin tasarımı (Görüntüdeki şablona sadık kalınmıştır)
    mesaj_metni = (
        f"<b>{urun_bilgisi['isim']}</b>\n\n"
        f"🏷 <b>{urun_bilgisi['fiyat']} TL</b>\n"
    )
    
    if urun_bilgisi.get('indirim_orani'):
        mesaj_metni += f"💬 <b>Ortalama fiyatın %{urun_bilgisi['indirim_orani']} altında</b>\n"
        
    mesaj_metni += "🛍 <b>Amazon</b>"

    # "Aç" Butonu tasarımı
    markup = InlineKeyboardMarkup()
    buton = InlineKeyboardButton(text="🔗 Aç", url=urun_bilgisi['link'])
    markup.add(buton)

    try:
        # Eğer ürüne ait görsel linki varsa fotoğraflı mesaj gönderir
        if urun_bilgisi['gorsel'] and urun_bilgisi['gorsel'].startswith("http"):
            bot.send_photo(
                chat_id, 
                photo=urun_bilgisi['gorsel'], 
                caption=mesaj_metni, 
                parse_mode="HTML", 
                reply_markup=markup
            )
        else:
            # Görsel yoksa veya çekilemediyse düz metin ama butonlu gönderir
            bot.send_message(
                chat_id, 
                text=mesaj_metni, 
                parse_mode="HTML", 
                reply_markup=markup, 
                disable_web_page_preview=True
            )
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

def amazon_kontrol():
    global urun_hafizasi
    
    try:
        response = get_amazon_page_via_proxy()
        if response.status_code != 200:
            return
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            return

        for urun in urunler[:5]: # Yoğun istekte Telegram'ı boğmamak için ilk 5 ürüne odaklanıyoruz
            try:
                isim_etiketi = urun.find("h2")
                if not isim_etiketi: continue
                isim = isim_etiketi.text.strip()
                
                # Fiyat Ayıklama
                fiyat_tam = urun.find("span", {"class": "a-price-whole"})
                fiyat_krs = urun.find("span", {"class": "a-price-fraction"})
                if fiyat_tam:
                    fiyat_str = fiyat_tam.text.strip().replace(",", "").replace(".", "")
                    fiyat = float(fiyat_str)
                    if fiyat_krs:
                        fiyat += float("0." + fiyat_krs.text.strip())
                else:
                    continue # Fiyatı olmayan ürünü geç

                # Görsel Linkini Çekme
                gorsel_etiketi = urun.find("img", {"class": "s-image"})
                gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None

                # Ürün Linki
                link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                indirim_orani = None
                bildirim_gonder = False

                # Hafıza ve İndirim Hesaplama Mantığı
                if isim not in urun_hafizasi:
                    urun_hafizasi[isim] = {"en_yuksek": fiyat, "son_fiyat": float(fiyat)}
                    bildirim_gonder = True # Yeni ürün bulundu, bildir
                else:
                    eski_veri = urun_hafizasi[isim]
                    if fiyat < eski_veri["son_fiyat"]:
                        # Fiyat düşmüş! Ortalama (en yüksek) fiyata göre indirim yüzdesini hesapla
                        en_yuksek = eski_veri["en_yuksek"]
                        indirim_orani = int(((en_yuksek - fiyat) / en_yuksek) * 100)
                        urun_hafizasi[isim]["son_fiyat"] = float(fiyat)
                        bildirim_gonder = True
                    else:
                        # Fiyat yükseldiyse tavan fiyatı güncelle ama bildirim atma
                        if fiyat > eski_veri["en_yuksek"]:
                            urun_hafizasi[isim]["en_yuksek"] = float(fiyat)
                        urun_hafizasi[isim]["son_fiyat"] = float(fiyat)

                if bildirim_gonder:
                    urun_kartı = {
                        "isim": isim,
                        "fiyat": fiyat,
                        "gorsel": gorsel_url,
                        "link": link,
                        "indirim_orani": indirim_orani if indirim_orani and indirim_orani > 0 else None
                    }
                    telegram_tasarimli_mesaj_gonder(CHAT_ID, urun_kartı)
                    time.sleep(2) # Telegram limitlerine takılmamak için kısa bekleme

            except Exception:
                continue

    except Exception as e:
        print(f"Sistem Hatası: {str(e)}")

def otomatik_kontrol():
    while True:
        amazon_kontrol()
        time.sleep(1800) # 30 dakika bekle

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot.reply_to(message, "🔄 Amazon listesi taranıyor ve kartlar hazırlanıyor, lütfen bekleyin...")
    
    try:
        response = get_amazon_page_via_proxy()
        if response.status_code != 200:
            bot.send_message(message.chat.id, f"❌ Hata: {response.status_code}")
            return
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            bot.send_message(message.chat.id, "⚠️ Satıcıya ait aktif ürün bulunamadı.")
            return
            
        # Manuel kontrolde o an var olan ilk 3 ürünü kart olarak basar
        for urun in urunler[:3]:
            isim = urun.find("h2").text.strip()
            fiyat_tam = urun.find("span", {"class": "a-price-whole"})
            fiyat = fiyat_tam.text.strip() if fiyat_tam else "Bilinmiyor"
            gorsel = urun.find("img", {"class": "s-image"})["src"] if urun.find("img", {"class": "s-image"}) else None
            link = "https://www.amazon.com.tr" + urun.find("a", {"class": "a-link-normal s-no-outline"})["href"]
            
            urun_kartı = {
                "isim": isim,
                "fiyat": fiyat,
                "gorsel": gorsel,
                "link": link,
                "indirim_orani": None # Manuel kontrolde anlık basıldığı için geçmiş hesabı yapılmaz
            }
            telegram_tasarimli_mesaj_gonder(message.chat.id, urun_kartı)
            time.sleep(1.5)
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Hata oluştu: {str(e)}")

if __name__ == "__main__":
    print("Görsel tasarımlı bot aktif...")
    t = Thread(target=otomatik_kontrol)
    t.daemon = True
    t.start()
    bot.infinity_polling()
