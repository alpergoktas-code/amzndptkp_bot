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

# Bot bağlantı koptuğunda otomatik yeniden bağlansın (threaded=True çok önemlidir)
bot = telebot.TeleBot(TOKEN, threaded=True)

BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

urun_hafizasi = {}

def get_amazon_page(page_number):
    """ScraperAPI kullanarak sayfayı çeker, timeout limitini sıkı tutar"""
    page_url = f"{BASE_URL}&page={page_number}"
    try:
        if not SCRAPER_KEY:
            headers = {"User-Agent": "Mozilla/5.0"}
            return requests.get(page_url, headers=headers, timeout=15)
        
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={page_url}&country_code=tr"
        # 30 saniye içinde cevap gelmezse sistemi kilitlememek için hata fırlatır
        return requests.get(proxy_url, timeout=30)
    except Exception as e:
        print(f"Bağlantı zaman aşımına uğradı veya hata oluştu: {e}")
        return None

def fiyati_kesin_bul(urun_soup):
    """Fiyatı Amazon yapısından güvenli şekilde söker"""
    try:
        price_span = urun_soup.find("span", {"class": "a-price"})
        if price_span:
            offscreen = price_span.find("span", {"class": "a-offscreen"})
            if offscreen:
                return offscreen.text.strip()
    except:
        pass

    fiyat_tam = urun_soup.find("span", {"class": "a-price-whole"})
    fiyat_krs = urun_soup.find("span", {"class": "a-price-fraction"})
    if fiyat_tam:
        fiyat_str = fiyat_tam.text.strip().replace(".", "").replace(",", "")
        if fiyat_krs:
            return f"{fiyat_str},{fiyat_krs.text.strip()} TL"
        return f"{fiyat_str} TL"

    return "Fiyat Bilgisi Yok"

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi):
    """Görsel kart mesajını iletir"""
    mesaj_metni = (
        f"<b>{urun_bilgisi['isim']}</b>\n\n"
        f"🏷 <b>{urun_bilgisi['fiyat']}</b>\n"
        f"🛍 <b>Amazon</b>"
    )

    markup = InlineKeyboardMarkup()
    buton = InlineKeyboardButton(text="🔗 Aç", url=urun_bilgisi['link'])
    markup.add(buton)

    try:
        if urun_bilgisi['gorsel'] and urun_bilgisi['gorsel'].startswith("http"):
            bot.send_photo(chat_id, photo=urun_bilgisi['gorsel'], caption=mesaj_metni, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(chat_id, text=mesaj_metni, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

def tum_magazayi_tara():
    """Arka planda sessizce çalışan ana tarayıcı döngü"""
    global urun_hafizasi
    print("🔄 Otomatik tarama döngüsü başladı...")
    current_page = 1
    
    while current_page <= 3: # İlk etapta sistemi yormamak için 3 sayfa tarasın
        response = get_amazon_page(current_page)
        if not response or response.status_code != 200:
            print(f"❌ Sayfa {current_page} çekilemedi, döngü kırıldı.")
            break
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            break

        for urun in urunler:
            try:
                isim_etiketi = urun.find("h2")
                if not isim_etiketi: continue
                isim = isim_etiketi.text.strip()
                
                fiyat = fiyati_kesin_bul(urun)
                if fiyat == "Fiyat Bilgisi Yok": continue
                
                gorsel_etiketi = urun.find("img", {"class": "s-image"})
                gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None
                
                link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                if isim not in urun_hafizasi:
                    urun_hafizasi[isim] = fiyat
                    urun_kartı = {"isim": isim, "fiyat": fiyat, "gorsel": gorsel_url, "link": link}
                    telegram_tasarimli_mesaj_gonder(CHAT_ID, urun_kartı)
                    time.sleep(1.5)
                elif urun_hafizasi[isim] != fiyat:
                    urun_hafizasi[isim] = fiyat
                    urun_kartı = {"isim": f"🔄 FİYAT GÜNCELLENDİ:\n{isim}", "fiyat": fiyat, "gorsel": gorsel_url, "link": link}
                    telegram_tasarimli_mesaj_gonder(CHAT_ID, urun_kartı)
                    time.sleep(1.5)
            except:
                continue
        
        current_page += 1
        time.sleep(3)

def otomatik_kontrol_dongusu():
    while True:
        try:
            tum_magazayi_tara()
        except Exception as e:
            print(f"Otomatik taramada genel hata: {e}")
        time.sleep(1800) # 30 dakika bekle

# TELEGRAM KOMUTU (Her zaman çalışmaya hazır)
@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot.reply_to(message, "🔍 Amazon Depo güncel durumu sorgulanıyor, lütfen bekleyin...")
    
    # Komut geldiğinde botun donmaması için bu işlemi de ayrı bir alt iş parçacığında (Thread) yapıyoruz
    def islem():
        try:
            response = get_amazon_page(1)
            if not response or response.status_code != 200:
                bot.send_message(message.chat.id, "❌ Amazon sayfasına şu an ulaşılamıyor. Lütfen az sonra tekrar deneyin.")
                return
                
            soup = BeautifulSoup(response.content, "html.parser")
            urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
            
            if not urunler:
                bot.send_message(message.chat.id, "⚠️ Şu an listelenecek ürün bulunamadı.")
                return
                
            for urun in urunler[:3]:
                isim = urun.find("h2").text.strip()
                fiyat = fiyati_kesin_bul(urun)
                gorsel = urun.find("img", {"class": "s-image"})["src"] if urun.find("img", {"class": "s-image"}) else None
                link = "https://www.amazon.com.tr" + urun.find("a", {"class": "a-link-normal s-no-outline"})["href"]
                
                urun_kartı = {"isim": isim, "fiyat": fiyat, "gorsel": gorsel, "link": link}
                telegram_tasarimli_mesaj_gonder(message.chat.id, urun_kartı)
                time.sleep(1.5)
        except Exception as e:
            bot.send_message(message.chat.id, f"Hata oluştu: {str(e)}")
            
    Thread(target=islem).start()

if __name__ == "__main__":
    print("Donmaz Amazon botu başlatılıyor...")
    # Arka plan döngüsünü başlat
    t = Thread(target=otomatik_kontrol_dongusu)
    t.daemon = True
    t.start()
    
    # Telegram botunu sonsuz döngüde dinle (Hatalarda durmaması için non_stop=True)
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
