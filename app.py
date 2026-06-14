import os
import time
import signal
import sys
import requests
from bs4 import BeautifulSoup
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.getenv("SCRAPERAPI_KEY")

# Çakışmaları önlemek için threaded=False yapıyoruz, hat yönetimi tek elden akacak
bot = telebot.TeleBot(TOKEN, threaded=False)

BASE_URL = "https://www.amazon.com.tr/Amazon-Depo/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&rh=n%3A44219324031&fs=true"

# Bellek içi çalışma zamanı hafızası
urun_hafizasi = {}
ilk_kurulum_bitti = False


def temizce_kapat(signum, frame):
    """Railway/Docker container'ı durdurduğunda botu düzgünce kapatır.
    Bu sayede Telegram hattı temiz kalır ve yeni instance 409 almaz."""
    print("Kapatma sinyali alındı, bot durduruluyor...")
    try:
        bot.stop_polling()
    except Exception:
        pass
    sys.exit(0)


# SIGTERM: Railway deployment sırasında eski container'a gönderilir
# SIGINT:  Ctrl+C ile manuel durdurmalarda tetiklenir
signal.signal(signal.SIGTERM, temizce_kapat)
signal.signal(signal.SIGINT, temizce_kapat)


# Kredi tasarrufu için maksimum taranacak sayfa sayısı
# 5 sayfa = 120 ürün, yeni eklenenler zaten listenin başında çıkar
MAX_SAYFA = 5

def get_amazon_page(page_number):
    """ScraperAPI üzerinden Amazon sayfasını çeker"""
    page_url = f"{BASE_URL}&page={page_number}"
    try:
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={page_url}&country_code=tr"
        response = requests.get(proxy_url, timeout=60)
        if response.status_code != 200:
            print(f"[Uyarı] Sayfa {page_number} HTTP {response.status_code} döndü")
        return response
    except Exception as e:
        print(f"[Hata] Sayfa {page_number} isteği başarısız: {e}")
        return None


def fiyati_resimden_oku(urun_soup):
    """Ekran görüntüsündeki değişken stoklu depo fiyatlarını hatasız okur"""
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
    except Exception:
        pass

    try:
        fiyat_kutusu = urun_soup.find("span", {"class": "a-price"})
        if fiyat_kutusu:
            gizli_fiyat = fiyat_kutusu.find("span", {"class": "a-offscreen"})
            if gizli_fiyat:
                metin = gizli_fiyat.text.strip()
                fiyat_clean = metin.replace("TL", "").replace("\u20ba", "").replace(".", "").replace(",", ".").strip()
                return metin, float(fiyat_clean), "1"
    except Exception:
        pass
    return None, None, None


def magazayi_bastan_basa_tara(manuel_mod=False, message_object=None):
    """Tüm sayfaları gezerek yeni ve fiyatı düşen ürünleri ayıklar"""
    global urun_hafizasi, ilk_kurulum_bitti
    current_page = 1
    yeni_bulunan_sayisi = 0
    hedef_chat = message_object.chat.id if manuel_mod else CHAT_ID

    if manuel_mod:
        bot.send_message(hedef_chat, "🔍 Amazon Depo taranıyor, lütfen bekleyin...")

    while True:
        response = get_amazon_page(current_page)
        if not response or response.status_code != 200:
            print(f"[Tarama] Sayfa {current_page} DURDU — HTTP: {response.status_code if response else 'Bağlantı hatası'}")
            break

        soup = BeautifulSoup(response.content, "html.parser")
        urunler = soup.find_all("div", {"data-component-type": "s-search-result"})

        if not urunler:
            print(f"[Tarama] Sayfa {current_page} DURDU — Ürün div'i bulunamadı (Amazon bot koruması olabilir)")
            break

        for urun in urunler:
            try:
                isim_etiketi = urun.find("h2")
                if not isim_etiketi:
                    continue
                isim = isim_etiketi.text.strip()

                fiyat_str, fiyat_float, stok_adet = fiyati_resimden_oku(urun)
                if not fiyat_float:
                    continue

                gorsel_etiketi = urun.find("img", {"class": "s-image"})
                gorsel_url = gorsel_etiketi["src"] if gorsel_etiketi else None

                link_etiketi = urun.find("a", {"class": "a-link-normal s-no-outline"})
                link = "https://www.amazon.com.tr" + link_etiketi["href"] if link_etiketi else "#"

                urun_karti = {
                    "isim": isim,
                    "fiyat_str": fiyat_str,
                    "gorsel": gorsel_url,
                    "link": link,
                    "stok_adet": stok_adet,
                }

                if ilk_kurulum_bitti or manuel_mod:
                    if isim not in urun_hafizasi:
                        urun_hafizasi[isim] = fiyat_float
                        telegram_tasarimli_mesaj_gonder(hedef_chat, urun_karti, durum_mesaji="🆕 MAĞAZAYA YENİ EKLENMİŞ!")
                        yeni_bulunan_sayisi += 1
                        time.sleep(1.5)
                    else:
                        eski_fiyat = urun_hafizasi[isim]
                        if fiyat_float < eski_fiyat:
                            indirim_orani = int(((eski_fiyat - fiyat_float) / eski_fiyat) * 100)
                            urun_hafizasi[isim] = fiyat_float
                            durum = f"📉 FİYATI DÜŞTÜ! (%{indirim_orani} İndirim)"
                            telegram_tasarimli_mesaj_gonder(hedef_chat, urun_karti, durum_mesaji=durum)
                            yeni_bulunan_sayisi += 1
                            time.sleep(1.5)
                else:
                    # İlk otomatik çalıştırmada bota yüzlerce mesaj yığılmasın diye sessizce hafızaya alıyoruz
                    urun_hafizasi[isim] = fiyat_float
            except Exception:
                continue

        print(f"[Tarama] Sayfa {current_page} tamamlandi, {len(urunler)} urun islendi.")
        current_page += 1
        time.sleep(2)

        # Manuel modda veya sayfa limitine ulaşıldığında dur
        if manuel_mod or current_page > MAX_SAYFA:
            break

    if not manuel_mod and not ilk_kurulum_bitti:
        ilk_kurulum_bitti = True
        bot.send_message(
            CHAT_ID,
            "✅ Bot başarıyla pusuya yattı! Amazon Depo hafızaya alındı, "
            "anlık indirimler ve yeni ürünler (ilk 120 ürün) 90 dakikada bir otomatik taranacak.",
        )

    if manuel_mod and yeni_bulunan_sayisi == 0:
        bot.send_message(
            hedef_chat,
            "✅ Tarama tamamlandı. Son tura göre yeni eklenen veya fiyatı düşen bir ürün şu an yok.",
        )


def telegram_tasarimli_mesaj_gonder(chat_id, urun_bilgisi, durum_mesaji=""):
    stok_bilgisi = f"📦 <b>Depo Stoğu:</b> {urun_bilgisi['stok_adet']} Adet\n" if urun_bilgisi.get("stok_adet") else ""
    mesaj_metni = (
        f"<b>{durum_mesaji}</b>\n\n"
        f"<b>{urun_bilgisi['isim']}</b>\n\n"
        f"🏷 <b>{urun_bilgisi['fiyat_str']} TL</b>\n"
        f"{stok_bilgisi}"
        f"🛍 <b>Amazon</b>"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="🔗 Aç", url=urun_bilgisi["link"]))
    try:
        if urun_bilgisi["gorsel"]:
            bot.send_photo(chat_id, photo=urun_bilgisi["gorsel"], caption=mesaj_metni, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(chat_id, text=mesaj_metni, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


def otomatik_kontrol_dongusu():
    while True:
        try:
            magazayi_bastan_basa_tara(manuel_mod=False)
        except Exception:
            pass
        time.sleep(5400)  # 90 dakikada bir otomatik çalışır (ScraperAPI kredi tasarrufu)


@bot.message_handler(commands=["kontrol"])
def manuel_kontrol(message):
    Thread(target=magazayi_bastan_basa_tara, args=(True, message)).start()


if __name__ == "__main__":
    print("Kararlı Amazon Botu Aktif Edildi...")

    # ── 1. Adım: Eski webhook kaydını temizle ────────────────────────────────
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    # ── 2. Adım: Telegram kuyruğunu boşalt ──────────────────────────────────
    # offset=-1 ile son update'i "okundu" işaretler; eski instance varsa
    # onun bağlantısını Telegram sunucusu tarafında keser.
    try:
        bot.get_updates(offset=-1)
    except Exception:
        pass

    # ── 3. Adım: Kritik startup gecikmesi ───────────────────────────────────
    # Railway, eski container'a SIGTERM gönderirken yeni container'ı EŞ ZAMANLI başlatır.
    # Eski container Telegram gözünde ~10-15 saniye "hayatta" kalabiliyor.
    # Bu bekleme, polling'i o pencere geçtikten sonra başlatır.
    print("Eski container'ın Telegram bağlantısını kesmesi için 20 saniye bekleniyor...")
    time.sleep(20)

    # ── 4. Adım: Arka plan tarama döngüsünü başlat ──────────────────────────
    t = Thread(target=otomatik_kontrol_dongusu)
    t.daemon = True
    t.start()

    # ── 5. Adım: Ana polling döngüsü ────────────────────────────────────────
    while True:
        try:
            bot.polling(
                non_stop=False,
                timeout=20,
                long_polling_timeout=5,
                allowed_updates=["message", "callback_query"],
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "409" in str(e):
                # 20s startup beklemesine rağmen 409 gelirse (nadir durum),
                # Telegram session'ının düşmesi için ek süre tanıyoruz.
                print("409 Çakışması — 20 saniye bekleniyor...")
                time.sleep(20)
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)
