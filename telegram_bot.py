import json
import math
import os
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN   = os.environ.get("TOKEN") or "8665005659:AAEzQJ6Wlpxf0cHScoFDwHfjgnXTjIkrPxE"
ADMIN_ID = 6424297442

onaylı_kullanicilar = set([ADMIN_ID])
bekleyen_istekler   = {}

with open("takim_verileri.json", "r", encoding="utf-8") as f:
    takimVerileri = json.load(f)

def poisson(beklenen, hedef):
    return math.exp(-beklenen) * beklenen**hedef / math.factorial(hedef)

def takim_bul(aranan):
    aranan = aranan.lower().strip()
    for takim in takimVerileri:
        if takim.lower() == aranan:
            return [takim]
    return [t for t in takimVerileri if aranan in t.lower()]

def dinamik_katsayi(takim, mod="ev"):
    veri = takimVerileri.get(takim, {})
    if mod == "ev":
        sonuclar = veri.get("ic_son10_sonuclar", [])
        if not sonuclar:
            return 1.0
        son5  = sonuclar[-5:]
        son10 = sonuclar
        oran5  = son5.count("G")  / len(son5)
        oran10 = son10.count("G") / len(son10)
        agirlikli = (oran5 * 0.6) + (oran10 * 0.4)
        return round(0.85 + (agirlikli * 0.45), 3)
    elif mod == "dep":
        sonuclar = veri.get("dis_son10_sonuclar", [])
        if not sonuclar:
            return 1.0
        son5  = sonuclar[-5:]
        son10 = sonuclar
        yenilgi5  = son5.count("M")  / len(son5)
        yenilgi10 = son10.count("M") / len(son10)
        agirlikli = (yenilgi5 * 0.6) + (yenilgi10 * 0.4)
        return round(1.00 - (agirlikli * 0.28), 3)
    return 1.0

def mac_sonucu_tahmini(ev_lambda, dep_lambda, max_gol=6):
    ev_kazan = beraberlik = dep_kazan = 0.0
    for ev in range(max_gol + 1):
        for dep in range(max_gol + 1):
            p = poisson(ev_lambda, ev) * poisson(dep_lambda, dep)
            if   ev > dep:  ev_kazan   += p
            elif ev == dep: beraberlik += p
            else:           dep_kazan  += p
    return ev_kazan, beraberlik, dep_kazan

def iy_ms_tahmini(ev_iy_lambda, dep_iy_lambda, ev_ms_lambda, dep_ms_lambda, max_gol=6):
    sonuclar = {"1/1": 0, "1/X": 0, "1/2": 0,
                "X/1": 0, "X/X": 0, "X/2": 0,
                "2/1": 0, "2/X": 0, "2/2": 0}
    for ev_iy in range(max_gol + 1):
        for dep_iy in range(max_gol + 1):
            p_iy = poisson(ev_iy_lambda, ev_iy) * poisson(dep_iy_lambda, dep_iy)
            if ev_iy > dep_iy:    iy_sonuc = "1"
            elif ev_iy == dep_iy: iy_sonuc = "X"
            else:                 iy_sonuc = "2"
            for ev_iy2 in range(max_gol + 1):
                for dep_iy2 in range(max_gol + 1):
                    ev_iy2_l  = max(ev_ms_lambda  - ev_iy_lambda,  0.01)
                    dep_iy2_l = max(dep_ms_lambda - dep_iy_lambda, 0.01)
                    p_iy2 = poisson(ev_iy2_l, ev_iy2) * poisson(dep_iy2_l, dep_iy2)
                    ev_ms  = ev_iy  + ev_iy2
                    dep_ms = dep_iy + dep_iy2
                    if ev_ms > dep_ms:    ms_sonuc = "1"
                    elif ev_ms == dep_ms: ms_sonuc = "X"
                    else:                 ms_sonuc = "2"
                    sonuclar[f"{iy_sonuc}/{ms_sonuc}"] += p_iy * p_iy2
    return sonuclar

def kg_tahmini(ev_iy_lambda, dep_iy_lambda, ev_iy2_lambda, dep_iy2_lambda):
    iy_kg_evet   = (1 - poisson(ev_iy_lambda,  0)) * (1 - poisson(dep_iy_lambda,  0))
    iy_kg_hayir  = 1 - iy_kg_evet
    iy2_kg_evet  = (1 - poisson(ev_iy2_lambda, 0)) * (1 - poisson(dep_iy2_lambda, 0))
    iy2_kg_hayir = 1 - iy2_kg_evet
    return {
        "Evet/Evet":   iy_kg_evet  * iy2_kg_evet,
        "Evet/Hayır":  iy_kg_evet  * iy2_kg_hayir,
        "Hayır/Evet":  iy_kg_hayir * iy2_kg_evet,
        "Hayır/Hayır": iy_kg_hayir * iy2_kg_hayir,
    }

def form_str(sonuclar):
    if not sonuclar:
        return "Veri yok"
    emojiler = {"G": "✅", "B": "🟡", "M": "❌"}
    return " ".join(emojiler.get(s, "?") for s in sonuclar[-5:])

def yorum_uret(ev, dep, evS, depS, ev_katsayi, dep_katsayi,
               ev_kazan, beraberlik, dep_kazan, toplam_beklenen):
    satirlar = []
    ic_son5  = evS.get("ic_son10_sonuclar", [])[-5:]
    ic_son10 = evS.get("ic_son10_sonuclar", [])
    ic_gal5  = ic_son5.count("G")
    ic_gal10 = ic_son10.count("G")
    if ic_gal5 >= 4:
        satirlar.append(f"🔥 {ev} iç sahada son 5 maçın {ic_gal5}'ini kazandı, form zirvede.")
    elif ic_gal5 <= 1:
        satirlar.append(f"⚠️ {ev} iç sahada son 5 maçın yalnızca {ic_gal5}'ini kazandı, ev avantajı zayıf.")
    else:
        satirlar.append(f"📊 {ev} iç sahada son 5 maçın {ic_gal5}'ini, son 10 maçın {ic_gal10}'ini kazandı.")
    dis_son5  = depS.get("dis_son10_sonuclar", [])[-5:]
    dis_son10 = depS.get("dis_son10_sonuclar", [])
    dis_gal5  = dis_son5.count("G")
    dis_gal10 = dis_son10.count("G")
    if dis_gal5 >= 4:
        satirlar.append(f"✈️ {dep} deplasmanda son 5 maçın {dis_gal5}'ini kazandı, güçlü deplasman takımı.")
    elif dis_gal5 <= 1:
        satirlar.append(f"📉 {dep} deplasmanda son 5 maçın yalnızca {dis_gal5}'ini kazandı, dezavantaj belirgin.")
    else:
        satirlar.append(f"📊 {dep} deplasmanda son 5 maçın {dis_gal5}'ini, son 10 maçın {dis_gal10}'ini kazandı.")
    if toplam_beklenen > 3.0:
        satirlar.append(f"⚽ Beklenen toplam gol yüksek ({toplam_beklenen:.1f}), gollü maç ihtimali güçlü.")
    elif toplam_beklenen < 2.0:
        satirlar.append(f"🔒 Beklenen toplam gol düşük ({toplam_beklenen:.1f}), düşük skorlu maç bekleniyor.")
    if ev_kazan > 0.50:
        satirlar.append(f"🏆 Ev sahibi favorisi net görünüyor (%{ev_kazan*100:.0f}).")
    elif dep_kazan > 0.40:
        satirlar.append(f"🏆 Deplasman takımı sürpriz yapabilir (%{dep_kazan*100:.0f}).")
    elif beraberlik > 0.28:
        satirlar.append(f"🤝 Beraberlik göz ardı edilmemeli (%{beraberlik*100:.0f}).")
    return "\n".join(satirlar)

def yaklasan_maclari_cek():
    API_KEY = "3fb43b538ea9469a973c2d565e4f3051"
    headers = {"X-Auth-Token": API_KEY}
    LIGLER  = ["PL", "BL1", "SA", "PD", "FL1", "DED", "PPL", "ELC"]
    bugun   = datetime.now().strftime("%Y-%m-%d")
    bitis   = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    maclar  = []
    for lig in LIGLER:
        try:
            url    = f"https://api.football-data.org/v4/competitions/{lig}/matches"
            params = {"status": "SCHEDULED", "dateFrom": bugun, "dateTo": bitis}
            r      = requests.get(url, headers=headers, params=params, timeout=10)
            data   = r.json()
            for mac in data.get("matches", []):
                maclar.append({
                    "ev":    mac["homeTeam"]["name"],
                    "dep":   mac["awayTeam"]["name"],
                    "tarih": mac["utcDate"][:10],
                    "lig":   lig
                })
        except:
            continue
    return maclar

def mac_tahmini(ev, dep):
    evS  = takimVerileri[ev]
    depS = takimVerileri[dep]
    ev_lig_ort  = evS.get("lig_ev_ort",  1.4)
    dep_lig_ort = depS.get("lig_dep_ort", 1.2)
    ev_att  = evS["ic_gol_atma_ort"]  / ev_lig_ort  if ev_lig_ort  > 0 else 1
    ev_def  = evS["ic_gol_yeme_ort"]  / dep_lig_ort if dep_lig_ort > 0 else 1
    dep_att = depS["dis_gol_atma_ort"] / dep_lig_ort if dep_lig_ort > 0 else 1
    dep_def = depS["dis_gol_yeme_ort"] / ev_lig_ort  if ev_lig_ort  > 0 else 1
    ev_katsayi  = dinamik_katsayi(ev,  mod="ev")
    dep_katsayi = dinamik_katsayi(dep, mod="dep")
    evBeklenen  = ev_att  * dep_def * ev_lig_ort  * ev_katsayi
    depBeklenen = dep_att * ev_def  * dep_lig_ort * dep_katsayi
    toplam      = evBeklenen + depBeklenen
    ev_iy_lambda  = (evS["ic_iy_gol_atma_ort"]  + depS["dis_iy_gol_yeme_ort"]) / 2
    dep_iy_lambda = (depS["dis_iy_gol_atma_ort"] + evS["ic_iy_gol_yeme_ort"])  / 2
    toplam_iy     = ev_iy_lambda + dep_iy_lambda
    ev_iy2_lambda  = (evS.get("ic_iy2_gol_atma_ort", 0)  + depS.get("dis_iy2_gol_yeme_ort", 0)) / 2
    dep_iy2_lambda = (depS.get("dis_iy2_gol_atma_ort", 0) + evS.get("ic_iy2_gol_yeme_ort", 0))  / 2
    alt25    = sum(poisson(toplam, i)    for i in range(3))
    ust25    = 1 - alt25
    alt15    = sum(poisson(toplam, i)    for i in range(2))
    ust15    = 1 - alt15
    iy_alt05 = poisson(toplam_iy, 0)
    iy_ust05 = 1 - iy_alt05
    iy_alt15 = sum(poisson(toplam_iy, i) for i in range(2))
    iy_ust15 = 1 - iy_alt15
    ev_kazan, beraberlik, dep_kazan = mac_sonucu_tahmini(evBeklenen, depBeklenen)
    iyms = iy_ms_tahmini(ev_iy_lambda, dep_iy_lambda, evBeklenen, depBeklenen)
    kg   = kg_tahmini(ev_iy_lambda, dep_iy_lambda, ev_iy2_lambda, dep_iy2_lambda)
    yorum = yorum_uret(ev, dep, evS, depS, ev_katsayi, dep_katsayi,
                       ev_kazan, beraberlik, dep_kazan, toplam)
    mesaj = f"""
⚽ *{ev} vs {dep}*
{'='*35}

🏠 *{ev} — İç Saha Formu*
{form_str(evS.get('ic_son10_sonuclar', []))}
▪️ Maç: {evS['ic_mac_sayisi']} | Gol Atma: {evS['ic_gol_atma_ort']} | Yeme: {evS['ic_gol_yeme_ort']}
▪️ Ev Katsayısı: x{ev_katsayi}

✈️ *{dep} — Deplasman Formu*
{form_str(depS.get('dis_son10_sonuclar', []))}
▪️ Maç: {depS['dis_mac_sayisi']} | Gol Atma: {depS['dis_gol_atma_ort']} | Yeme: {depS['dis_gol_yeme_ort']}
▪️ Deplasman Katsayısı: x{dep_katsayi}

🎯 *Beklenen Goller*
▪️ {ev}: {evBeklenen:.2f} | {dep}: {depBeklenen:.2f} | Toplam: {toplam:.2f}

🏆 *Maç Sonucu (1X2)*
1️⃣ {ev} Kazanır: %{ev_kazan*100:.1f}
➖ Beraberlik: %{beraberlik*100:.1f}
2️⃣ {dep} Kazanır: %{dep_kazan*100:.1f}

📈 *Maç Sonu — Üst/Alt*
⚽ 2.5 ÜST: %{ust25*100:.1f} | ALT: %{alt25*100:.1f}
⚽ 1.5 ÜST: %{ust15*100:.1f} | ALT: %{alt15*100:.1f}

🕐 *İlk Yarı — Üst/Alt*
⚽ İY 0.5 ÜST: %{iy_ust05*100:.1f} | ALT: %{iy_alt05*100:.1f}
⚽ İY 1.5 ÜST: %{iy_ust15*100:.1f} | ALT: %{iy_alt15*100:.1f}

🔀 *İlk Yarı / Maç Sonu*
⚽ 1/1: %{iyms['1/1']*100:.1f} | 1/X: %{iyms['1/X']*100:.1f} | 1/2: %{iyms['1/2']*100:.1f}
⚽ X/1: %{iyms['X/1']*100:.1f} | X/X: %{iyms['X/X']*100:.1f} | X/2: %{iyms['X/2']*100:.1f}
⚽ 2/1: %{iyms['2/1']*100:.1f} | 2/X: %{iyms['2/X']*100:.1f} | 2/2: %{iyms['2/2']*100:.1f}

🤝 *Karşılıklı Gol (IY / IY2)*
✅ Evet/Evet: %{kg['Evet/Evet']*100:.1f}
↕️ Evet/Hayır: %{kg['Evet/Hayır']*100:.1f}
↕️ Hayır/Evet: %{kg['Hayır/Evet']*100:.1f}
❌ Hayır/Hayır: %{kg['Hayır/Hayır']*100:.1f}

💬 *Yorum*
{yorum}
"""
    return mesaj

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_id = update.message.from_user.id
    kullanici_ad = update.message.from_user.full_name
    if kullanici_id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Hoş geldin Admin!\n\n📌 *Kullanım:*\n`Liverpool - Arsenal`",
            parse_mode="Markdown")
        return
    if kullanici_id in onaylı_kullanicilar:
        await update.message.reply_text(
            "👋 Merhaba!\n\n📌 *Kullanım:*\n`Liverpool - Arsenal`",
            parse_mode="Markdown")
        return
    if kullanici_id in bekleyen_istekler:
        await update.message.reply_text("⏳ İsteğin zaten gönderildi, onay bekleniyor...")
        return
    bekleyen_istekler[kullanici_id] = kullanici_ad
    klavye = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Onayla", callback_data=f"onayla_{kullanici_id}"),
        InlineKeyboardButton("❌ Reddet", callback_data=f"reddet_{kullanici_id}")
    ]])
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 *Yeni Erişim İsteği!*\n\n👤 {kullanici_ad}\n🆔 {kullanici_id}",
        reply_markup=klavye, parse_mode="Markdown")
    await update.message.reply_text("⏳ İsteğin gönderildi, onay bekleniyor...")

async def buton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    if data.startswith("onayla_"):
        uid = int(data.split("_")[1])
        onaylı_kullanicilar.add(uid)
        bekleyen_istekler.pop(uid, None)
        await query.edit_message_text(f"✅ {uid} onaylandı!")
        await context.bot.send_message(
            chat_id=uid,
            text="✅ Erişimin onaylandı! `Liverpool - Arsenal` formatında yazabilirsin.",
            parse_mode="Markdown")
    elif data.startswith("reddet_"):
        uid = int(data.split("_")[1])
        bekleyen_istekler.pop(uid, None)
        await query.edit_message_text(f"❌ {uid} reddedildi!")
        await context.bot.send_message(chat_id=uid, text="❌ Erişim isteğin reddedildi.")

async def analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_id = update.message.from_user.id
    if kullanici_id not in onaylı_kullanicilar:
        await update.message.reply_text(
            "⛔ Yetkin yok!\n\n/start yazarak erişim isteği gönderebilirsin.")
        return
    metin = update.message.text
    if " - " not in metin:
        await update.message.reply_text(
            "⚠️ Format: `Liverpool - Arsenal`", parse_mode="Markdown")
        return
    parcalar = metin.split(" - ")
    if len(parcalar) != 2:
        await update.message.reply_text("⚠️ Hatalı format! Örnek: `Liverpool - Arsenal`")
        return
    ev_sonuclar  = takim_bul(parcalar[0].strip())
    dep_sonuclar = takim_bul(parcalar[1].strip())
    for sonuclar, taraf in [(ev_sonuclar, parcalar[0]), (dep_sonuclar, parcalar[1])]:
        if len(sonuclar) == 0:
            await update.message.reply_text(f"❌ '{taraf}' bulunamadı!")
            return
        if len(sonuclar) > 1:
            liste = "\n".join(f"▪️ {t}" for t in sonuclar)
            await update.message.reply_text(
                f"🔍 Birden fazla sonuç:\n\n{liste}\n\nDaha spesifik yaz!")
            return
    await update.message.reply_text("🔍 Analiz yapılıyor...")
    sonuc = mac_tahmini(ev_sonuclar[0], dep_sonuclar[0])
    await update.message.reply_text(sonuc, parse_mode="Markdown")

async def tarama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_id = update.message.from_user.id
    if kullanici_id not in onaylı_kullanicilar:
        await update.message.reply_text("⛔ Yetkin yok.")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "📌 *Kullanım:*\n"
            "`/tarama evet/evet 7` — Evet/Evet %7 üstü\n"
            "`/tarama 1/2 5` — 1/2 %5 üstü\n"
            "`/tarama 2/1 5` — 2/1 %5 üstü\n\n"
            "Kriterler: `evet/evet`, `evet/hayir`, `hayir/evet`, `hayir/hayir`,\n"
            "`1/1`, `1/x`, `1/2`, `x/1`, `x/x`, `x/2`, `2/1`, `2/x`, `2/2`",
            parse_mode="Markdown")
        return
    kriter = args[0].lower()
    esik   = float(args[1]) if len(args) > 1 else 5.0
    await update.message.reply_text(f"🔍 Maçlar taranıyor... ({kriter.upper()} > %{esik})")
    maclar = yaklasan_maclari_cek()
    if not maclar:
        await update.message.reply_text("❌ Maç verisi çekilemedi.")
        return
    bulunanlar = []
    for mac in maclar:
        ev  = mac["ev"]
        dep = mac["dep"]
        ev_sonuc  = takim_bul(ev)
        dep_sonuc = takim_bul(dep)
        if len(ev_sonuc) != 1 or len(dep_sonuc) != 1:
            continue
        try:
            evS  = takimVerileri[ev_sonuc[0]]
            depS = takimVerileri[dep_sonuc[0]]
            ev_lig_ort  = evS.get("lig_ev_ort",  1.4)
            dep_lig_ort = depS.get("lig_dep_ort", 1.2)
            ev_att  = evS["ic_gol_atma_ort"]  / ev_lig_ort  if ev_lig_ort  > 0 else 1
            ev_def  = evS["ic_gol_yeme_ort"]  / dep_lig_ort if dep_lig_ort > 0 else 1
            dep_att = depS["dis_gol_atma_ort"] / dep_lig_ort if dep_lig_ort > 0 else 1
            dep_def = depS["dis_gol_yeme_ort"] / ev_lig_ort  if ev_lig_ort  > 0 else 1
            ev_katsayi  = dinamik_katsayi(ev_sonuc[0],  mod="ev")
            dep_katsayi = dinamik_katsayi(dep_sonuc[0], mod="dep")
            evBeklenen  = ev_att  * dep_def * ev_lig_ort  * ev_katsayi
            depBeklenen = dep_att * ev_def  * dep_lig_ort * dep_katsayi
            ev_iy_lambda  = (evS["ic_iy_gol_atma_ort"]  + depS["dis_iy_gol_yeme_ort"]) / 2
            dep_iy_lambda = (depS["dis_iy_gol_atma_ort"] + evS["ic_iy_gol_yeme_ort"])  / 2
            ev_iy2_lambda  = (evS.get("ic_iy2_gol_atma_ort", 0)  + depS.get("dis_iy2_gol_yeme_ort", 0)) / 2
            dep_iy2_lambda = (depS.get("dis_iy2_gol_atma_ort", 0) + evS.get("ic_iy2_gol_yeme_ort", 0))  / 2
            iyms = iy_ms_tahmini(ev_iy_lambda, dep_iy_lambda, evBeklenen, depBeklenen)
            kg   = kg_tahmini(ev_iy_lambda, dep_iy_lambda, ev_iy2_lambda, dep_iy2_lambda)
            kriter_map = {
                "evet/evet":   kg["Evet/Evet"]   * 100,
                "evet/hayir":  kg["Evet/Hayır"]  * 100,
                "hayir/evet":  kg["Hayır/Evet"]  * 100,
                "hayir/hayir": kg["Hayır/Hayır"] * 100,
                "1/1": iyms["1/1"]*100, "1/x": iyms["1/X"]*100, "1/2": iyms["1/2"]*100,
                "x/1": iyms["X/1"]*100, "x/x": iyms["X/X"]*100, "x/2": iyms["X/2"]*100,
                "2/1": iyms["2/1"]*100, "2/x": iyms["2/X"]*100, "2/2": iyms["2/2"]*100,
            }
            deger = kriter_map.get(kriter)
            if deger is not None and deger >= esik:
                bulunanlar.append({
                    "ev":    ev_sonuc[0],
                    "dep":   dep_sonuc[0],
                    "tarih": mac["tarih"],
                    "deger": deger
                })
        except:
            continue
    if not bulunanlar:
        await update.message.reply_text(f"❌ {kriter.upper()} > %{esik} olan maç bulunamadı.")
        return
    bulunanlar.sort(key=lambda x: x["deger"], reverse=True)
    mesaj = f"🎯 *{kriter.upper()} > %{esik} olan maçlar:*\n{'='*30}\n"
    for b in bulunanlar:
        mesaj += f"\n⚽ {b['ev']} vs {b['dep']}\n"
        mesaj += f"   📅 {b['tarih']} | %{b['deger']:.1f}\n"
    if len(mesaj) > 4096:
        mesaj = mesaj[:4090] + "..."
    await update.message.reply_text(mesaj, parse_mode="Markdown")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start",   start))
app.add_handler(CallbackQueryHandler(buton))
app.add_handler(CommandHandler("tarama",  tarama))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analiz))

print("🤖 Bot çalışıyor...")
app.run_polling()
