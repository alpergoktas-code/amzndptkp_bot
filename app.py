import os
import time
import random
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telebot.TeleBot(TOKEN)

AMAZON_URL = "https://www.amazon.com.tr/s?me=A215JX4S9CANSO&marketplaceID=A33AVAJ2PDY3EV"

# Amazon'u yanıltmak için farklı tarayıcı kimlikleri listesi
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

urun_hafizasi = {}

def get_amazon_page():
    """Amazon'dan güvenli bir şekilde veri çekmeye çalışan fonksiyon"""
    session = requests.Session()
    
    # Gerçekçi tarayıcı başlıkları (Headers)
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.google.com/"
    }
    
    # İsteği göndermeden önce 1-3 saniye arası rastgele bekle (İnsansı hareket)
    time.sleep(random.uniform(1.0, 3.0))
    
    response = session.get(AMAZON_URL, headers=headers, timeout=20)
    return response

def amazon_kontrol():
    global urun_hafizasi
    mesaj_metni = "📦 **Amazon Depo Son Durum:**\n\n"
    guncelleme_var = False
    
    try:
        response = get_amazon_page()
        
        if response.status_code == 503:
            return "⚠️ Amazon şu an yoğun veya bot korumasına takıldık (Hata: 503). Bir sonraki tur tekrar denenecek."
        elif response.status_code != 200:
            return f"Amazon'a erişilemedi (Hata kodu: {response.status_code})"
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            # Amazon bazen 200 döner ama sayfa içeriğini boş verir (Robot kontrolü sayfası)
            if "api-services-support@amazon.com" in response.text or "captcha" in response.text.lower():
                return "🤖 Amazon doğrulama (Captcha) duvarına denk geldik."
            return "Şu anda listelenen ürün bulunamadı veya sayfa yapısı değişti."

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
                    urun_hafizasi[isim] = fiyat
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
                print("Mesaj gönderme hatası:", e)
        
        # 30 dakika beklerken de küçük bir esneklik payı bırakalım (Tam 1800 saniye olmasın)
        bekleme_suresi = 1800 + random.randint(-60, 60)
        time.sleep(bekleme_suresi)

@bot.message_handler(commands=['kontrol'])
def manuel_kontrol(message):
    bot.reply_to(message, "🔄 Amazon Depo kontrol ediliyor, lütfen bekleyin...")
    
    try:
        response = get_amazon_page()
        if response.status_code == 503:
            bot.send_message(message.chat.id, "❌ Amazon botu engelledi (503). Lütfen birkaç dakika sonra tekrar deneyin.")
            return
            
        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})
        
        if not urunler:
            bot.send_message(message.chat.id, "⚠️ Ürün bulunamadı veya Captcha korumasına takıldı.")
            return
            
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
    print("Bot aktif...")
    t = Thread(target=otomatik_kontrol)
    t.daemon = True
    t.start()
    bot.infinity_polling()
