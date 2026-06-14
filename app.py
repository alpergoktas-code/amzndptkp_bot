import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import logging

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

bot = telebot.TeleBot(TOKEN, threaded=False)
telebot.logger.setLevel(logging.CRITICAL)

BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

# Railway sıfırlansa bile ürünleri unutmaması için basit bir çalışma zamanı hafızası
urun_hafizasi = {}
ilk_kurulum_bitti = False

def get_amazon_page(page_number):
    page_url = f"{BASE_URL}&page={page_number}"
    try:
        if not SCRAPER_KEY:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            return requests.get(page_url, headers=headers, timeout=15), "OK"
        
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={page_url}&country_code=tr"
        response = requests.get(proxy_url, timeout=60)
        return response, f"HTTP {response.status_code}"
    except Exception as e:
        return None, str(e)

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
    return None, None, None

def magazayi_bastan_basa_tara(manuel_mod=False, message_object=None):
    global urun_hafizasi, ilk_kurulum_bitti
    current_page = 1
    yeni_bulunan_sayisi = 0
    hedef_chat = message_object.chat.id if manuel_mod else CHAT_ID
    
    if manuel_mod:
        bot.send_message(hedef_chat, "🔄 Amazon Depo taranıyor, lütfen bekleyin...")

    while True:
        response, durum_mesaji = get_amazon_page(current_page)
        
        if not response:
            if manuel_mod:
                bot.send_message(hedef_chat, f"❌ Bağlantı Hatası: ScraperAPI sunucuya yanıt vermedi. Detay: {durum_mesaji}")
            break
            
        if response.status_code != 200:
            if manuel_mod:
                bot.send_message(hedef_chat, f"❌ Proxy Hatası: {durum_mesaji}. (Muhtemelen ScraperAPI krediniz bitti veya Amazon engelledi.)")
            break
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            if manuel_mod and current_page == 1:
                if "captcha" in response.text.lower():
                    bot.send_message(hedef_chat, "🤖 Amazon robot doğrulamasına (Captcha) yakalandık, proxy IP'si engellenmiş.")
                else:
                    bot.send_message(hedef_chat, "⚠️ Amazon başarılı bağlandı (200) ama sayfada hiçbir ürün listelenmedi. (Amazon bot filtresi)")
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

                urun_kartı = {"isim": isim, "fiyat_str": fiyat_str, "gorsel": gorsel_url, "link": link, "stok_adet": stok_adet}

                # Eğer ilk kurulum bittiyse veya kullanıcı elle kontrol ediyorsa yenileri bas
                if ilk_kurulum_bitti or manuel_mod:
                    if isim not in urun_hafizasi:
                        urun_hafizasi[isim] = fiyat_float
                        # Manuel kontrolde her şeyi dök, otomatik kontrolde sadece yenileri dök
                        telegram_tasarimli_mesaj_gonder(hedef_chat, urun_kartı, durum_mesaji="🆕 MAĞAZAYA YENİ EKLENMİŞ!")
                        yeni_bulunan_sayisi += 1
                        time.sleep(1.5)
                    else:
                        eski_fiyat = urun_hafizasi[isim]
                        if fiyat_float < eski_fiyat:
                            indirim_orani = int(((eski_fiyat - fiyat_float) / eski_fiyat) * 100)
                            urun_hafizasi[isim] = fiyat_float
                            durum = f"📉 FİYATI DÜŞTÜ! (%{indirim_orani} İndirim)"
                            telegram_tasarimli_mesaj_gonder(hedef_chat, urun_kartı, durum_mesaji=durum)
                            yeni_bulunan_sayisi += 1
                            time.sleep(1.5)
                else:
                    # İlk otomatik taramada sadece hafızayı doldur
                    urun_hafizasi[isim] = fiyat_float
            except:
                continue
            
        current_page += 1
        time.sleep(2)
        
        # Manuel modda sadece ilk sayfayı raporlayıp hızlıca bitirelim
        if manuel_mod:
            break
    
    if not manuel_mod and not ilk_kurulum_bitti:
        ilk_kurulum_bitti = True
        bot.send_message(CHAT_ID, "✅ Bot başarıyla pusuya yattı! Mağaza hafızaya alındı, anlık değişiklikler takip ediliyor.")

    if manuel_mod and yeni_bulunan_sayisi == 0:
        bot.send_message(hedef_chat, "✅ Tarama bitti. Sol tura göre yeni eklenen veya fiyatı düşen bir ürün şu an yok.")

def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi, durum_mesaji=""):
    stok_bilgisi = f"📦 <b>Depo Stoğu:</b> {urun_bilgisi['stok_adet']} Adet\n" if urun_bilgisi.get('stok_adet') else ""
    mesaj_metni = f"<b>{durum_mesaji}</b>\n\n<b>{urun_bilgisi['isim']}</b>\n\n🏷 <b>{urun_bilgisi['fiyat_str']} TL</b>\n{stok_bilgisi}🛍 <b>Amazon</b>"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="🔗 Aç", url=urun_bilgisi['link']))
    try:
        if urun_bilgisi['gorsel']:
            bot.send_photo(chat_id, photo=urun_bilgisi['gorsel'], caption=mesaj_metni, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(chat_id, text=mesaj_metni, parse_mode="HTML", reply_markup=markup)
    except:
        pass

def otomatik_kontrol_dongusu():
    while True:
        try:
            magazayi_bastan_basa_tara(manuel_mod=False)
        except:
            pass
        time.sleep(1800)

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    Thread(target=magazayi_bastan_basa_tara, args=(True, message)).start()

if __name__ == "__main__":
    t = Thread(target=otomatik_kontrol_dongusu)
    t.daemon = True
    t.start()
    
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=10)
        except:
            time.sleep(5)
