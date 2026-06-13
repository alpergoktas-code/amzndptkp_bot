import os
import time
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot

# Çevre değişkenleri
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

bot = telebot.TeleBot(TOKEN)

# Hedef satıcının arama linki
TARGET_URL = "https://www.amazon.com.tr/s?me=A215JX4S9CANSO&marketplaceID=A33AVAJ2PDY3EV"

urun_hafizasi = {}

def get_amazon_page_via_proxy():
    """ScraperAPI kullanarak Amazon engelini aşan fonksiyon"""
    # Eğer Railway'e API key girilmediyse düz istek atmayı dener (Yedek plan)
    if not SCRAPER_KEY:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        return requests.get(TARGET_URL, headers=headers, timeout=20)
    
    # ScraperAPI entegrasyonu (country_code=tr ile Türkiye IP'si simüle edilir)
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={TARGET_URL}&country_code=tr"
    
    # ScraperAPI arkada proxy döndürdüğü için süre uzayabilir, timeout'u yüksek tutuyoruz
    response = requests.get(proxy_url, timeout=60)
    return response

def amazon_kontrol():
    global urun_hafizasi
    mesaj_metni = "📦 **Amazon Depo Son Durum:**\n\n"
    guncelleme_var = False
    
    try:
        response = get_amazon_page_via_proxy()
        
        if response.status_code != 200:
            return f"⚠️ Proxy servisi hata döndürdü (Hata kodu: {response.status_code})"
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Amazon arama sonuçlarındaki ürün blokları
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            if "captcha" in response.text.lower() or "robot" in response.text.lower():
                return "🤖 Proxy'ye rağmen Captcha duvarına takılındı. (Nadir durum)"
            return "Şu anda satıcıya ait listelenen aktif ürün bulunamadı."

        for urun in urunler[:10]:
            try:
                isim_etiketi = urun.find("h2")
                if not isim_etiketi: continue
                isim = isim_etiketi.text.strip()
                
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

                if isim not in urun_hafizasi:
                    urun_hafizasi[isim] = fiyat
                    mesaj_metni += f"🆕 **YENİ:** {isim}\n💰 Fiyat: {fiyat if fiyat else 'Bilinmiyor'} TL\n🔗 [Ürüne Git]({link})\n\n"
                    guncelleme_var = True
                elif fiyat and urun_hafizasi[isim] and fiyat < urun_hafizasi[isim]:
                    eski_fiyat = urun_hafizasi[isim]
                    urun_hafizasi[isim] = float(fiyat)
                    mesaj_metni += f"📉 **FİYAT DÜŞTÜ:** {isim}\n❌ Eski: {eski_fiyat} TL -> ✅ Yeni: {fiyat} TL\n🔗 [Ürüne Git]({link})\n\n"
                    guncelleme_var = True
            except Exception:
                continue

        if guncelleme_var:
            return mesaj_metni
        else:
            return None

    except Exception as e:
        return f"Bir hata oluştu: {str(e)}"

def otomatik_kontrol():
    while True:
        sonuc = amazon_kontrol()
        if sonuc:
            try:
                bot.send_message(CHAT_ID, sonuc, parse_mode="Markdown", disable_web_page_preview=True)
            except Exception as e:
                print("Telegram gönderme hatası:", e)
        
        # 30 dakika (1800 saniye) bekle
        time.sleep(1800)

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot.reply_to(message, "🔄 Güvenli hat üzerinden Amazon kontrol ediliyor, bu işlem 10-15 saniye sürebilir...")
    
    try:
        response = get_amazon_page_via_proxy()
        if response.status_code != 200:
            bot.send_message(message.chat.id, f"❌ Sayfa çekilemedi. Proxy hatası: {response.status_code}")
            return
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            bot.send_message(message.chat.id, "⚠️ Aktif ürün bulunamadı veya hâlâ engelleniyor.")
            return
            
        rapor = "📊 **Anlık Satıcı Ürün Listesi:**\n\n"
        for urun in urunler[:5]:
            isim = urun.find("h2").text.strip()
            fiyat_tam = urun.find("span", {"class": "a-price-whole"})
            fiyat = fiyat_tam.text.strip() + " TL" if fiyat_tam else "Fiyat Bulunamadı"
            link = "https://www.amazon.com.tr" + urun.find("a", {"class": "a-link-normal s-no-outline"})["href"]
            rapor += f"• {isim}\n💰 Fiyat: {fiyat}\n🔗 [Ürüne Git]({link})\n\n"
        
        bot.send_message(message.chat.id, rapor, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"Hata oluştu: {str(e)}")

if __name__ == "__main__":
    print("Bot güvenli proxy moduyla başlatıldı...")
    t = Thread(target=otomatik_kontrol)
    t.daemon = True
    t.start()
    bot.infinity_polling()
