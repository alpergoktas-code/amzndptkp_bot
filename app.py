import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

bot = telebot.TeleBot(TOKEN, threaded=True)

# Gönderdiğin resmi Amazon Depo mağaza linki
BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

# Ürünlerin fiyat geçmişini takip etmek için hafıza
urun_hafizasi = {}

def get_amazon_page(page_number):
    """ScraperAPI kullanarak ilgili sayfayı çeker"""
    page_url = f"{BASE_URL}&page={page_number}"
    try:
        if not SCRAPER_KEY:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            return requests.get(page_url, headers=headers, timeout=15)
        
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={page_url}&country_code=tr"
        return requests.get(proxy_url, timeout=30)
    except Exception as e:
        print(f"Bağlantı hatası (Sayfa {page_number}): {e}")
        return None

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi, durum_mesaji=""):
    """İstediğin görsel şablonla Telegram'a kart gönderir"""
    prefix = f"<b>{durum_mesaji}</b>\n\n" if durum_mesaji else ""
    
    mesaj_metni = (
        f"{prefix}"
        f"<b>{urun_bilgisi['isim']}</b>\n\n"
        f"🏷 <b>{urun_bilgisi['fiyat']} TL</b>\n"
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

def magazayi_bastan_basa_tara(manuel_mod=False, message_object=None):
    """TÜM SAYFALARI gezerek yeni veya fiyatı düşen ürünleri takip eder"""
    global urun_hafizasi
    current_page = 1
    toplam_bulunan_urun = 0
    
    if manuel_mod and message_object:
        bot.send_message(message_object.chat.id, "🔍 Tüm sayfalar taranıyor, bu işlem mağaza büyüklüğüne göre 1-2 dakika sürebilir...")

    while True:
        response = get_amazon_page(current_page)
        if not response or response.status_code != 200:
            print(f"Tarama bitti veya sayfa çekilemedi. Son sayfa: {current_page - 1}")
            break
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        # Sayfada hiç ürün yoksa tüm mağaza taranmış demektir, döngüden çık
        if not urunler:
            print(f"Boş sayfaya ulaşıldı, tarama sonlandırıldı. Toplam sayfa: {current_page - 1}")
            break

        for urun in urunler:
            try:
                # 1. ADIM: İsmi bul
                isim_etiketi = urun.find("h2")
                if not isim_etiketi: continue
                isim = isim_etiketi.text.strip()
                
                # 2. ADIM: Fiyatı Kesin Bulma (Amazon Veri Katmanından Çekme)
                fiyat_float = None
                fiyat_str = "Fiyat Bilgisi Yok"
                
                # Amazon'un her ürün için sakladığı gizli fiyat paketini yakala
                fiyat_kutusu = urun.find("span", {"class": "a-price"})
                if fiyat_kutusu:
                    gizli_fiyat = fiyat_kutusu.find("span", {"class": "a-offscreen"})
                    if gizli_fiyat:
                        fiyat_str = gizli_fiyat.text.strip().replace("TL", "").replace("₺", "").strip()
                        # Matematiksel karşılaştırma için float'a çevir (Örn: "1.250,50" -> 1250.50)
                        try:
                            fiyat_clean = fiyat_str.replace(".", "").replace(",", ".")
                            fiyat_float = float(fiyat_clean)
                        except:
                            fiyat_float = None

                # Fiyatı hiçbir şekilde okunamayan hatalı veya stoksuz ürünleri listeye alma
                if not fiyat_float:
                    continue 

                # 3. ADIM: Görsel ve Link Al
                gorsel_etiketi = urun.find("img", {"class": "s-image"})
                gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None
                
                link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                urun_kartı = {"isim": isim, "fiyat": fiyat_str, "gorsel": gorsel_url, "link": link}

                # 4. ADIM: Hafıza Mantığı (Yeni Ürün / Fiyat Düşüşü Kontrolü)
                if isim not in urun_hafizasi:
                    # İlk taramada (Bot ilk açıldığında) her şeyi bota atıp boğmasın diye hafızaya alır.
                    # Eğer /kontrol komutuyla elle tetiklediysen anlık durumu görmen için kartı basar.
                    urun_hafizasi[isim] = fiyat_float
                    if manuel_mod:
                        telegram_tasarimli_mesaj_gonder(message_object.chat.id, urun_kartı)
                        toplam_bulunan_urun += 1
                        time.sleep(1.5)
                else:
                    # Ürün zaten hafızada var, fiyatı düşmüş mü kontrol et
                    eski_fiyat = urun_hafizasi[isim]
                    if fiyat_float < eski_fiyat:
                        indirim_orani = int(((eski_fiyat - fiyat_float) / eski_fiyat) * 100)
                        urun_hafizasi[isim] = fiyat_float # Hafızayı güncelle
                        
                        durum = f"📉 FİYAT DÜŞTÜ! (Ortalama fiyatın %{indirim_orani} altında)"
                        # Hem otomatik döngüde hem manuel modda fiyat düşüşünü bildir
                        hedef_chat = message_object.chat.id if manuel_mod else CHAT_ID
                        telegram_tasarimli_mesaj_gonder(hedef_chat, urun_kartı, durum_mesaji=durum)
                        time.sleep(1.5)
                    else:
                        # Fiyat yükseldiyse veya değişmediyse hafızayı sadece güncelle, bildirim atma
                        urun_hafizasi[isim] = fiyat_float

            except Exception as e:
                continue
        
        # Manuel modda ilk sayfayı basıp bitirelim ki kullanıcı saatlerce beklemesin, 
        # ancak otomatik kontrol (arka plan) TÜM sayfaları gezmeye devam etsin.
        if manuel_mod and current_page >= 1 and toplam_bulunan_urun > 0:
            break
            
        current_page += 1
        time.sleep(2) # Proxy limitlerine takılmamak için sayfa arası bekleme

def otomatik_kontrol_dongusu():
    while True:
        try:
            print("🔄 30 dakikalık tam mağaza taraması başlatıldı...")
            magazayi_bastan_basa_tara(manuel_mod=False)
        except Exception as e:
            print(f"Otomatik döngü hatası: {e}")
        time.sleep(1800) # 30 dakika bekle

# /kontrol komutu yazıldığında çalışacak alan
@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    # Komutun botu dondurmaması için işi thread'e veriyoruz
    Thread(target=magazayi_bastan_basa_tara, args=(True, message)).start()

if __name__ == "__main__":
    print("Nihai Amazon Botu Çalışıyor...")
    # Arka planda tüm sayfaları tarayan döngüyü başlat
    t = Thread(target=otomatik_kontrol_dongusu)
    t.daemon = True
    t.start()
    
    # Telegram'ı dinlemeye başla
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
