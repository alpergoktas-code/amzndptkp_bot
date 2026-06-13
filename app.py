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

# Çakışmaları en aza indirmek için threaded=False yapıyoruz.
# Arka plan işlemlerini zaten kendimiz Thread ile yönettiğimiz için bu çok daha güvenlidir.
bot = telebot.TeleBot(TOKEN, threaded=False)

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
    try:
        fiyat_linkleri = urun_soup.find_all("a", class_="a-link-normal")
        for link in fiyat_linkleri:
            metin = link.text.strip()
            if ("TL" in metin or "\u20ba" in metin) and ("ikinci el" in metin.lower() or "seçenekleri" in metin.lower()):
                stok_bul = re.search(r'(\d+)\s+ikinci\s+el', metin.lower())
                stok_adet = stok_bul.group(1) if stok_bul else "1"
                if "(" in metin:
                    metin = metin.split("(")[0].strip()
                fiyat_clean = metin.replace("TL", "").replace("\u20ba", "").replace(".", "").replace(",", ".").strip()
                return metin, float(fiyat_clean), stok_adet
    except:
        pass
    
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
                
                fiyat_str, fiyat_float, stok_adet = fiyati_resimden_oku(urun)
                if not fiyat_float: continue

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

                if os.path.exists("hafiza_ilk_kurulum.txt") == False and manuel_mod == False:
                    # Bot ilk kez ayağa kalktığında yüzlerce eski ürünü Telegram'a yığmasın diye hafızaya sessizce alır
                    urun_hafizasi[isim] = fiyat_float
                    continue

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
            except:
                continue
            
        current_page += 1
        time.sleep(2)
    
    # İlk sessiz kurulum bittiğinde bir işaret dosyası koyalım
    if manuel_mod == False and os.path.exists("hafiza_ilk_kurulum.txt") == False:
        with open("hafiza_ilk_kurulum.txt", "w") as f:
            f.write("ok")

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
    print("Zırhlandırılmış kararlı Amazon botu aktif...")
    
    # Arka plandaki otomatik tarama döngüsünü başlatır
    t = Thread(target=otomatik_kontrol_dongusu)
    t.daemon = True
    t.start()
    
    # Çakışmaları (409) kod seviyesinde zorla düşüren akıllı döngü
    while True:
        try:
            print("🚀 Telegram API bağlantısı kuruluyor...")
            # allowed_updates=[] ve long_polling_timeout=1: Hayalet bağlantıları anında düşürür!
            bot.polling(
                non_stop=True, 
                timeout=10, 
                long_polling_timeout=1, 
                allowed_updates=[]
            )
        except Exception as e:
            # Eğer Railway eski container'ı kapatırken bir anlık çakışma yaşatırsa,
            # bot çökmek yerine loglara bilgi yazar, 3 saniye bekler ve tekrar dener.
            print(f"⚠️ Bağlantı kesintisi algılandı, otomatik olarak yeniden bağlanılıyor: {e}")
            time.sleep(3)
