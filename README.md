# Halol aksiya skrineri — Trading Laboratory

AQSh birjalaridagi (Nasdaq, NYSE, NYSE American, Cboe) barcha oddiy aksiyalarni shariatga muvofiqlik bo'yicha tekshiradigan bepul sayt. Narxlar va halollik statuslari **har soatda**, hisobot ko'rsatkichlari **har kuni** avtomatik yangilanadi. Hammasi bepul GitHub'da ishlaydi: server, hosting yoki API kalit kerak emas.

## Qanday ishlaydi

```
Har soatda (GitHub Actions)
  ├─ SEC EDGAR → qarz, naqd pul, daromad, foizli daromad, aksiyalar soni, soha (SIC)   [kuniga 1 marta]
  ├─ Yahoo Finance → so'nggi narx                                                       [har soatda]
  ├─ scripts/screening.py → har bir aksiya uchun status
  └─ site/ → GitHub Pages'ga chiqariladi
```

### Mezonlar (Islamicly e'lon qilgan, AAOIFI asosidagi)

| Mezon | Chegara |
|---|---|
| Asosiy faoliyat | Alkogol, tamaki, cho'chqa go'shti, qimor, foizli bank/sug'urta, qurol-yarog', kattalar kontenti — chiqariladi |
| Foizli qarz / bozor kapitalizatsiyasi | < 30% |
| Naqd pul + foizli qog'ozlar / bozor kapitalizatsiyasi | < 30% |
| Foizli daromad / jami daromad | < 5% |

**Statuslar:** Halol (1–5 oy bilan ishonch darajasi), Shubhali (qo'lda tekshirish kerak), Halol emas, Ma'lumot yetarli emas.

**Toifalar:** Penny — narxi $5 dan past; Growth — daromad o'sishi ≥15% yoki P/E ≥30; Value — P/E ≤18; qolganlari Aralash.

---

## O'rnatish (taxminan 15 daqiqa)

### 1. GitHub akkaunt va repozitoriy
1. [github.com](https://github.com) da bepul akkaunt oching.
2. Yuqori o'ngdagi **+** → **New repository**. Nomi masalan `halol-skrining`. **Public** ni tanlang (bepul Pages uchun shart). **Create repository**.
3. Ochilgan sahifada **uploading an existing file** havolasini bosing va shu papkadagi barcha fayl va papkalarni (jumladan `.github` papkasini) sudrab tashlang. **Commit changes**.
   - Eslatma: `.github` papkasi yashirin bo'lishi mumkin. Mac'da Finder'da `Cmd+Shift+.`, Windows'da "Yashirin elementlarni ko'rsatish" ni yoqing. Agar yuklanmasa, GitHub'da **Add file → Create new file** bosib, nomiga `.github/workflows/update.yml` yozing va fayl ichidagi matnni nusxalang.

### 2. SEC uchun aloqa ma'lumoti
SEC EDGAR har bir so'rovda kim so'rayotganini bilishni talab qiladi.
1. Repozitoriyda **Settings → Secrets and variables → Actions → Variables** bo'limi → **New repository variable**.
2. Name: `SEC_USER_AGENT`, Value: `TradingLab Screener sizning@email.com` (o'z emailingizni yozing). **Add variable**.

### 3. GitHub Pages'ni yoqish
**Settings → Pages → Build and deployment → Source** ni **GitHub Actions** ga o'zgartiring.

### 4. Birinchi ishga tushirish
1. **Actions** bo'limi → agar so'rasa, **I understand my workflows, go ahead and enable them**.
2. Chapda **Halol skrining — har soatda yangilash** → **Run workflow** → **Run workflow**.
3. Birinchi ishga tushish 20–40 daqiqa davom etadi (barcha kompaniyalar ma'lumoti yuklanadi). Keyingilari 5–10 daqiqa.
4. Tugagach, sayt manzili `https://<foydalanuvchi-nomingiz>.github.io/halol-skrining/` bo'ladi (Settings → Pages'da ko'rinadi).

> Soha (SIC) kodlari birinchi 2–3 soat ichida bosqichma-bosqich yig'iladi. Shu vaqtda ko'p aksiyalar "Shubhali" ko'rinishi normal holat.

### 5. Telegram kanal havolasini qo'yish
`site/config.js` faylini GitHub'da oching (qalam belgisi) va `channelUrl` ga kanalingiz taklif havolasini yozing, masalan `https://t.me/+AbCdEf123`. Commit qiling — keyingi yangilanishda saytda chiqadi.

---

## Boshqarish

- **Qo'lda tuzatish:** `data/overrides.json` da istalgan aksiyaning biznes skrining natijasini o'zgartirish mumkin (`fail`, `pass`, `review`). Masalan, SIC kodi ko'rsatmaydigan kazino yoki pivo kompaniyalari. Moliyaviy nisbatlar baribir tekshiriladi.
- **OTC aksiyalarni qo'shish:** `scripts/config.py` da `EXCHANGES` ga `"OTC"` qo'shing. Bu ro'yxatni ancha kengaytiradi va yangilanishni sekinlashtiradi.
- **Chegaralarni o'zgartirish:** `scripts/screening.py` boshidagi `DEBT_LIMIT`, `CASH_LIMIT`, `IMPURE_REVENUE_LIMIT`.
- **Bitta aksiyaga to'g'ridan-to'g'ri havola:** `.../halol-skrining/#AAPL` — kanalda post yozganda shu havolani bering, sayt aksiya kartasini darhol ochadi.
- **Testlar:** `python -m pytest tests`

## Cheklovlar (bilib qo'ying)

- **Islamicly bilan bog'liq emas.** Ularning ichki algoritmi to'liq ochiq emas: qarzni hisoblash usuli, tahlilchilarning qo'lda tekshiruvi va daromad tarkibi bo'yicha natijalar ba'zan farq qiladi. Saytda Islamicly nomi va logotipini brend sifatida ishlatmang.
- **Harom daromad ulushi taxminiy.** Avtomatik tarzda faqat foizli daromad (hisobotdagi `InvestmentIncomeInterest`) hisoblanadi. Diversifikatsiyalangan kompaniyaning, masalan, alkogol yoki qimordan kelgan kichik daromad ulushini SEC ma'lumotidan avtomatik ajratib bo'lmaydi — bunday holatlar `overrides.json` orqali qo'lda belgilanadi.
- **Xorijiy kompaniyalar (ADR)** IFRS bo'yicha hisobot beradi va ko'pincha "Ma'lumot yetarli emas" bo'lib chiqadi.
- **Ko'p klassli aksiyalar** (masalan, GOOGL/GOOG) uchun kapitalizatsiya taxminiy.
- **Yahoo Finance** rasmiy API emas. Agar u narx bermay qolsa, aksiyalar vaqtincha "Ma'lumot yetarli emas" bo'ladi; bunday holda Finnhub yoki Financial Modeling Prep kabi kalitli manbaga o'tish mumkin.
- **GitHub cron** ba'zan 5–30 daqiqa kechikadi. Repozitoriyda 60 kun hech qanday faollik bo'lmasa, GitHub rejalashtirilgan ishni to'xtatishi mumkin — Actions bo'limida qayta yoqiladi.
- Bu fatvo yoki investitsiya maslahati emas.
