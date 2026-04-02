import json
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Token
TOKEN = "8665005659:AAEzQJ6Wlpxf0cHScoFDwHfjgnXTjIkrPxE"

# Senin Telegram ID'n
ADMIN_ID = 6424297442  # Örn: 123456789

# Onaylanan kullanıcılar (başlangıçta sadece admin)
onaylı_kullanicilar = set([ADMIN_ID])

# Bekleyen istekler
bekleyen_istekler = {}

# Takım verilerini yükle
with open("takim_verileri.json", "r", encoding="utf-8") as f:
    takimVerileri = json.load(f)

# Poisson hesabı
def poisson(beklenen, hedef):
    return math.exp(-beklenen) * beklenen**hedef / math.factorial(hedef)

# Takım arama
def takim_bul(aranan):
    aranan = aranan.lower().strip()
    
    for takim in takimVerileri:
        if takim.lower() == aranan:
            return [takim]
    
    sonuclar = []
    for takim in takimVerileri:
        if aranan in takim.lower():
            sonuclar.append(takim)
    
    return sonuclar

# Maç tahmini
def mac_tahmini(ev, dep):
    evS = takimVerileri[ev]
    depS = takimVerileri[dep]

    evBeklenen = (evS["ic_gol_atma_ort"] + depS["dis_gol_yeme_ort"]) / 2
    depBeklenen = (depS["dis_gol_atma_ort"] + evS["ic_gol_yeme_ort"]) / 2
    toplam = evBeklenen + depBeklenen

    evIY = (evS["ic_iy_gol_atma_ort"] + depS["dis_iy_gol_yeme_ort"]) / 2
    depIY = (depS["dis_iy_gol_atma_ort"] + evS["ic_iy_gol_yeme_ort"]) / 2
    toplamIY = evIY + depIY

    alt25 = sum([poisson(toplam, i) for i in range(3)])
    ust25 = 1 - alt25

    alt15 = sum([poisson(toplam, i) for i in range(2)])
    ust15 = 1 - alt15

    iyAlt05 = poisson(toplamIY, 0)
    iyUst05 = 1 - iyAlt05

    iyAlt15 = sum([poisson(toplamIY, i) for i in range(2)])
    iyUst15 = 1 - iyAlt15

    mesaj = f"""
⚽ *{ev} vs {dep}*
{'='*35}

🏠 *{ev} (İç Saha)*
▪️ Maç Sayısı: {evS['ic_mac_sayisi']}
▪️ Gol Atma Ort: {evS['ic_gol_atma_ort']}
▪️ Gol Yeme Ort: {evS['ic_gol_yeme_ort']}
▪️ İY Gol Atma: {evS['ic_iy_gol_atma_ort']}
▪️ İY Gol Yeme: {evS['ic_iy_gol_yeme_ort']}

✈️ *{dep} (Deplasman)*
▪️ Maç Sayısı: {depS['dis_mac_sayisi']}
▪️ Gol Atma Ort: {depS['dis_gol_atma_ort']}
▪️ Gol Yeme Ort: {depS['dis_gol_yeme_ort']}
▪️ İY Gol Atma: {depS['dis_iy_gol_atma_ort']}
▪️ İY Gol Yeme: {depS['dis_iy_gol_yeme_ort']}

🎯 *Beklenen Goller*
▪️ {ev}: {evBeklenen:.2f}
▪️ {dep}: {depBeklenen:.2f}
▪️ Toplam: {toplam:.2f}

📈 *Maç Sonu Tahminleri*
⚽ 2.5 ÜST: %{ust25*100:.1f} | ALT: %{alt25*100:.1f}
⚽ 1.5 ÜST: %{ust15*100:.1f} | ALT: %{alt15*100:.1f}

🕐 *İlk Yarı Tahminleri*
⚽ IY 0.5 ÜST: %{iyUst05*100:.1f} | ALT: %{iyAlt05*100:.1f}
⚽ IY 1.5 ÜST: %{iyUst15*100:.1f} | ALT: %{iyAlt15*100:.1f}
"""
    return mesaj

# /start komutu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_id = update.message.from_user.id
    kullanici_ad = update.message.from_user.full_name

    # Admin ise direkt geç
    if kullanici_id == ADMIN_ID:
        await update.message.reply_text("""
👋 Hoş geldin Admin!

📌 *Kullanım:*
`Liverpool - Arsenal`

✅ Takım adını tam yazmana gerek yok!
✅ Büyük küçük harf fark etmez!
""", parse_mode="Markdown")
        return

    # Onaylı kullanıcı ise geç
    if kullanici_id in onaylı_kullanicilar:
        await update.message.reply_text("""
👋 Merhaba! Ben Futbol Analiz Botuyum!

📌 *Kullanım:*
`Liverpool - Arsenal`

✅ Takım adını tam yazmana gerek yok!
✅ Büyük küçük harf fark etmez!
""", parse_mode="Markdown")
        return

    # Zaten bekleyen istek var mı
    if kullanici_id in bekleyen_istekler:
        await update.message.reply_text("⏳ Erişim isteğin zaten gönderildi. Onay bekleniyor...")
        return

    # Yeni istek
    bekleyen_istekler[kullanici_id] = kullanici_ad

    # Admin'e bildirim gönder
    klavye = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Onayla", callback_data=f"onayla_{kullanici_id}"),
            InlineKeyboardButton("❌ Reddet", callback_data=f"reddet_{kullanici_id}")
        ]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 *Yeni Erişim İsteği!*\n\n👤 İsim: {kullanici_ad}\n🆔 ID: {kullanici_id}\n\nOnaylıyor musun?",
        reply_markup=klavye,
        parse_mode="Markdown"
    )

    await update.message.reply_text("⏳ Erişim isteğin gönderildi. Onay bekleniyor...")

# Onay/Red butonu
async def buton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("onayla_"):
        kullanici_id = int(data.split("_")[1])
        onaylı_kullanicilar.add(kullanici_id)
        
        if kullanici_id in bekleyen_istekler:
            del bekleyen_istekler[kullanici_id]

        await query.edit_message_text(f"✅ Kullanıcı {kullanici_id} onaylandı!")

        await context.bot.send_message(
            chat_id=kullanici_id,
            text="✅ Erişim isteğin onaylandı! Artık botu kullanabilirsin!\n\n`Liverpool - Arsenal` formatında maç analizi yapabilirsin.",
            parse_mode="Markdown"
        )

    elif data.startswith("reddet_"):
        kullanici_id = int(data.split("_")[1])
        
        if kullanici_id in bekleyen_istekler:
            del bekleyen_istekler[kullanici_id]

        await query.edit_message_text(f"❌ Kullanıcı {kullanici_id} reddedildi!")

        await context.bot.send_message(
            chat_id=kullanici_id,
            text="❌ Erişim isteğin reddedildi."
        )

# Mesaj gelince analiz yap
async def analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_id = update.message.from_user.id

    if kullanici_id not in onaylı_kullanicilar:
        await update.message.reply_text("⛔ Bu botu kullanma yetkiniz yok!\n\n/start yazarak erişim isteği gönderebilirsin.")
        return

    metin = update.message.text

    if " - " not in metin:
        await update.message.reply_text(
            "⚠️ Lütfen şu formatta yaz:\n`Liverpool - Arsenal`",
            parse_mode="Markdown"
        )
        return

    takimlar = metin.split(" - ")
    if len(takimlar) != 2:
        await update.message.reply_text("⚠️ Hatalı format! Örnek: `Liverpool - Arsenal`")
        return

    ev_aranan = takimlar[0].strip()
    dep_aranan = takimlar[1].strip()

    ev_sonuclar = takim_bul(ev_aranan)
    dep_sonuclar = takim_bul(dep_aranan)

    if len(ev_sonuclar) == 0:
        await update.message.reply_text(f"❌ '{ev_aranan}' bulunamadı!\n\nFarklı bir isim dene.")
        return

    if len(ev_sonuclar) > 1:
        liste = "\n".join([f"▪️ {t}" for t in ev_sonuclar])
        await update.message.reply_text(
            f"🔍 '{ev_aranan}' için birden fazla takım bulundu:\n\n{liste}\n\nDaha spesifik yaz!",
            parse_mode="Markdown"
        )
        return

    if len(dep_sonuclar) == 0:
        await update.message.reply_text(f"❌ '{dep_aranan}' bulunamadı!\n\nFarklı bir isim dene.")
        return

    if len(dep_sonuclar) > 1:
        liste = "\n".join([f"▪️ {t}" for t in dep_sonuclar])
        await update.message.reply_text(
            f"🔍 '{dep_aranan}' için birden fazla takım bulundu:\n\n{liste}\n\nDaha spesifik yaz!",
            parse_mode="Markdown"
        )
        return

    ev = ev_sonuclar[0]
    dep = dep_sonuclar[0]

    await update.message.reply_text("🔍 Analiz yapılıyor...")

    sonuc = mac_tahmini(ev, dep)
    await update.message.reply_text(sonuc, parse_mode="Markdown")

# Botu çalıştır
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buton))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analiz))

print("🤖 Bot çalışıyor...")
app.run_polling()