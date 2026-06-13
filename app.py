import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

bot = telebot.TeleBot(TOKEN, threaded=True)

BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

urun_hafizasi = {}

def get_amazon_page(page_number):
    page_url = f"{BASE_URL}&page={page_number}"
    try:
        if not SCRAPER_KEY:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            return requests.get(page_url, headers=headers, timeout=15)
        
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={page_url}&country_code=tr"
        return requests.get(proxy_url, timeout=30)
    except Exception as e:
        print(f"Bağlantı hatası (Sayfa {page_number}): {e}")
        return None

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi, durum_mesaji="🆕 YENİ ÜRÜN BULDUM!"):
    # Telegram mesajına stok adet bilgisini de ekledik
    stok_bilgisi = f"📦 <b>Depo Stoğu:</b> {urun_bilgisi['stok_adet']} Adet\n" if urun_bilgisi.get('stok_adet') else ""
    
    mesaj_metni = (
        f"<b>{durum_mesaji}</b>\n\n"
        f"<b>{urun_bilgisi['isim']}</b>\n\n"
        f"🏷 <b>{urun_bilgisi['fiyat_str']} TL</b>\n"
        f"{stok_bilgisi}"
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

def fiyati_resimden_oku(urun_soup):
    """
    Değişken stok sayılarını (1, 2, 3 ikinci el ürün) düzenli ifadelerle (Regex)
    yakalar, hem net fiyatı hem de güncel stok adedini döner.
    """
    try:
        fiyat_linkleri = urun_soup.find_all("a", class_="a-link-normal")
        for link in fiyat_linkleri:
            metin = link.text.strip()
            
            # İçinde fiyat ve ikinci el/seçenek ifadesi geçen her şeyi yakala
            if ("TL" in metin or "\u20ba" in metin) and ("ikinci el" in metin.lower() or "seçenekleri" in metin.lower()):
                
                # Regex ile metnin içindeki stok sayısını dinamik olarak bulalım (Örn: '3 ikinci el' içindeki 3'ü alır)
                stok_bul = re.search(r'(\d+)\s+ikinci\s+el', metin.lower())
                stok_adet = stok_bul.group(1) if stok_bul else "1"
                
                # Parantez öncesindeki fiyat kısmını temizce ayıkla
                if "(" in metin:
                    metin = metin.split("(")[0].strip()
                
                # TL ibarelerini temizle ve float'a çevir
                fiyat_clean = metin.replace("TL", "").replace("\u20ba", "").replace(".", "").replace(",", ".").strip()
                return metin, float(fiyat_clean), stok_adet
    except:
        pass
    
    # Yedek Plan
    try:
        fiyat_kutusu = urun_soup.find("span", {"class": "a-price"})
        if fiyat_kutusu:
            gizli_fiyat = fiyat_kutusu.find("span", {"class": "a-offscreen"})
            if gizli_fiyat:
                metin = gizli_fiyat.text.strip()
                fiyat_clean = metin.replace("TL", "").replace("\u20ba", "").replace(".", "").replace(",", ".").strip()
                return metin, float(fiyat_clean), "1"
    except:
        pass

    return None, None, None

def magazayi_bastan_basa_tara(manuel_mod=False, message_object=None):
    global urun_hafizasi
    current_page = 1
    yeni_bulunan_sayisi = 0
    
    if manuel_mod and message_object:
        bot.send_message(message_object.chat.id, "🔍 Tüm sayfalar taranıyor, sadece YENİ eklenen veya FİYATI DÜŞEN varsa buraya dökülecek...")

    while True:
        response = get_amazon_page(current_page)
        if not response or response.status_code != 200:
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
                
                # Güncellenen fonksiyondan stok adet bilgisini de alıyoruz
                fiyat_str, fiyat_float, stok_adet = fiyati_resimden_oku(urun)
                if not fiyat_float: 
                    continue

                gorsel_etiketi = urun.find("img", {"class": "s-image"})
                gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None
                
                link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                urun_kartı = {
                    "isim": str(isim), 
                    "fiyat_str": str(fiyat_str), 
                    "gorsel": gorsel_url, 
                    "link": link,
                    "stok_adet": str(stok_adet)
                }

                if isim not in urun_hafizasi:
                    urun_hafizasi[isim] = fiyat_float
                    if manuel_mod:
                        telegram_tasarimli_mesaj_gonder(message_object.chat.id, urun_kartı, durum_mesaji="🆕 MAĞAZAYA YENİ EKLENMİŞ!")
                        yeni_bulunan_sayisi += 1
                        time.sleep(1.5)
                else:
                    eski_fiyat = urun_hafizasi[isim]
                    if fiyat_float < eski_fiyat:
                        indirim_orani = int(((eski_fiyat - fiyat_float) / eski_fiyat) * 100)
                        urun_hafizasi[isim] = fiyat_float
                        
                        durum = f"📉 FİYATI DÜŞTÜ! (Eski Fiyata Göre %{indirim_orani} İndirim)"
                        hedef_chat = message_object.chat.id if manuel_mod else CHAT_ID
                        telegram_tasarimli_mesaj_gonder(hedef_chat, urun_kartı, durum_mesaji=durum)
                        yeni_bulunan_sayisi += 1
                        time.sleep(1.5)
                    else:
                        urun_hafizasi[isim] = fiyat_float

            except Exception:
                continue
            
        current_page += 1
        time.sleep(2)
        
    if manuel_mod and message_object and yeni_bulunan_sayisi == 0:
        bot.send_message(message_object.chat.id, "✅ Tarama tamamlandı. Son kontrolden bu yana yeni eklenen veya fiyatı düşen bir ürün tespit edilmedi.")

def otomatik_kontrol_dongusu():
    while True:
        try:
            magazayi_bastan_basa_tara(manuel_mod=False)
        except Exception as e:
            print(f"Otomatik döngü hatası: {e}")
        time.sleep(1800)

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    Thread(target=magazayi_bastan_basa_tara, args=(True, message)).start()

if __name__ == "__main__":
    print("Dinamik stok destekli Amazon botu aktif...")
    
    # Arka plandaki otomatik tarama döngüsünü başlatır
    t = Thread(target=otomatik_kontrol_dongusu)
    t.daemon = True
    t.start()
    
    # Botu döngüsel dinleme moduna al (En sade ve hatasız çalışan doğrudan tetikleme)
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
