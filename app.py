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

# Gönderdiğin en güncel ve resmi Amazon Depo mağaza linki tabanı
BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

urun_hafizasi = {}

def get_amazon_page(page_number):
    """Belirli bir sayfa numarası için ScraperAPI kullanarak istek atar"""
    page_url = f"{BASE_URL}&page={page_number}"
    
    if not SCRAPER_KEY:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        return requests.get(page_url, headers=headers, timeout=20)
    
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={page_url}&country_code=tr"
    return requests.get(proxy_url, timeout=60)

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi):
    """İstenen görsel şablonla Telegram'a kart gönderir"""
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
            bot.send_message(chat_id, text=mesaj_metni, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

def fiyati_kesin_bul(urun_soup):
    """Amazon'un JSON veri bloklarından veya alternatif sınıflarından fiyatı kesin olarak söker"""
    # 1. En Garanti Yöntem: Amazon'un tarayıcıya gizlediği saf veri katmanını (Arama Verisi) okumak
    try:
        price_span = urun_soup.find("span", {"class": "a-price"})
        if price_span:
            offscreen = price_span.find("span", {"class": "a-offscreen"})
            if offscreen:
                return offscreen.text.strip()
    except:
        pass

    # 2. Alternatif: Grafik yüzeyindeki parçalı fiyat etiketleri
    fiyat_tam = urun_soup.find("span", {"class": "a-price-whole"})
    fiyat_krs = urun_soup.find("span", {"class": "a-price-fraction"})
    if fiyat_tam:
        fiyat_str = fiyat_tam.text.strip().replace(".", "").replace(",", "")
        if fiyat_krs:
            return f"{fiyat_str},{fiyat_krs.text.strip()} TL"
        return f"{fiyat_str} TL"

    return "Fiyat Bilgisi Yok"

def tum_magazayi_tara():
    """Tüm sayfaları gezerek yeni veya fiyatı düşen ürünleri tarar"""
    global urun_hafizasi
    current_page = 1
    
    while current_page <= 5:  # İlk aşamada Amazon Depo'nun ilk 5 sayfasını (Yaklaşık 100 ürün) tarar. İstersen artırabilirsin.
        try:
            response = get_amazon_page(current_page)
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.content, "html.parser")
            urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
            
            # Eğer sayfada hiç ürün yoksa mağaza bitmiştir, döngüden çık
            if not urunler:
                break

            for urun in urunler:
                try:
                    isim_etiketi = urun.find("h2")
                    if not isim_etiketi: continue
                    isim = isim_etiketi.text.strip()
                    
                    fiyat = fiyati_kesin_bul(urun)
                    if fiyat == "Fiyat Bilgisi Yok": 
                        continue  # Fiyatı çekilemeyen hatalı ürünleri listeye alıp bota çööp mesaj attırma
                    
                    gorsel_etiketi = urun.find("img", {"class": "s-image"})
                    gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None
                    
                    link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                    link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                    # Sadece yeni bir ürün eklendiğinde veya mevcut ürünün fiyatı değiştiğinde mesaj gönder
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
                        
                except Exception:
                    continue
            
            current_page += 1
            time.sleep(2) # Sayfa geçişleri arasında ScraperAPI'yi ve Amazon'u yormamak için kısa bekleme
            
        except Exception as e:
            print(f"Sayfa {current_page} taranırken hata: {e}")
            break

def otomatik_kontrol():
    while True:
        tum_magazayi_tara()
        time.sleep(1800) # 30 dakikada bir tüm mağazayı baştan aşağı kontrol eder

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot
