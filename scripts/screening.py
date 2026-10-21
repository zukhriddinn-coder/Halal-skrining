"""
Shariat skrining algoritmi.

Islamicly o'z blogida e'lon qilgan, AAOIFI standartiga asoslangan mezonlar:
  1. Biznes skrining: asosiy faoliyati harom bo'lgan kompaniyalar chiqariladi.
  2. Harom (foizli) daromad / jami daromad < 5%
  3. Foizli qarz / bozor kapitalizatsiyasi < 30%
  4. Naqd pul + foizli qimmatli qog'ozlar / bozor kapitalizatsiyasi < 30%

Eslatma: Islamicly ichki algoritmining barcha tafsilotlarini ochiq e'lon qilmagan,
shuning uchun natijalar ular ko'rsatgan natijadan ba'zan farq qilishi mumkin.
"""

from __future__ import annotations

# ---- Chegaralar ------------------------------------------------------------
DEBT_LIMIT = 0.30          # foizli qarz / bozor kapitalizatsiyasi
CASH_LIMIT = 0.30          # naqd + foizli qog'ozlar / bozor kapitalizatsiyasi
IMPURE_REVENUE_LIMIT = 0.05  # foizli/harom daromad / jami daromad
NEAR_RATIO = 0.85          # chegaraning 85% idan oshsa "chegaraga yaqin" ogohlantirish

# ---- Statuslar -------------------------------------------------------------
HALAL = "halal"            # Halol
NOT_HALAL = "not_halal"    # Halol emas
DOUBTFUL = "doubtful"      # Shubhali: qo'lda tekshiruv kerak
NO_DATA = "no_data"        # Ma'lumot yetarli emas

# ---- Biznes skrining: SIC kodlari -----------------------------------------
# Har bir yozuv: (boshlanish, tugash, sabab)
HARAM_SIC = [
    (2082, 2085, "Alkogolli ichimliklar ishlab chiqarish"),
    (2100, 2199, "Tamaki mahsulotlari"),
    (3480, 3489, "Qurol-yarog' va o'q-dorilar"),
    (5180, 5182, "Alkogolli ichimliklar ulgurji savdosi"),
    (5813, 5813, "Ichimlik joylari (bar)"),
    (5921, 5921, "Alkogol do'konlari"),
    (6000, 6099, "Foizli bank faoliyati"),
    (6111, 6199, "Foizli kredit tashkilotlari"),
    (6300, 6399, "An'anaviy sug'urta"),
    (6411, 6411, "Sug'urta agentlari va brokerlari"),
    (6770, 6770, "SPAC (mablag'i foizli g'aznachilik qog'ozlarida)"),
]

REVIEW_SIC = [
    (2011, 2015, "Go'sht mahsulotlari: cho'chqa go'shti ulushini tekshirish kerak"),
    (6798, 6798, "REIT: ipoteka REIT'mi yoki ko'chmas mulk REIT'mi, tekshirish kerak"),
    (6200, 6299, "Brokerlik va investitsiya xizmatlari: foizli daromad ulushini tekshirish kerak"),
    (7011, 7011, "Mehmonxonalar: kazino ulushini tekshirish kerak"),
    (7990, 7999, "Ko'ngilochar xizmatlar: qimor ulushini tekshirish kerak"),
    (3720, 3729, "Aviatsiya: harbiy daromad ulushini tekshirish kerak"),
    (3760, 3769, "Raketa va kosmik texnika: harbiy daromad ulushini tekshirish kerak"),
]

HARAM_NAME_KEYWORDS = {
    "casino": "Kazino / qimor",
    "gaming & leisure": "Kazino / qimor",
    "lottery": "Lotereya",
    "brewing": "Pivo ishlab chiqarish",
    "brewery": "Pivo ishlab chiqarish",
    "distiller": "Spirtli ichimliklar",
    "winery": "Vino ishlab chiqarish",
    "tobacco": "Tamaki",
    "cannabis": "Kannabis",
    "bancorp": "Foizli bank faoliyati",
    "bancshares": "Foizli bank faoliyati",
}


def _sic_match(sic: int | None, table):
    if sic is None:
        return None
    for lo, hi, reason in table:
        if lo <= sic <= hi:
            return reason
    return None


def business_screen(sic: int | None, name: str, override: dict | None = None):
    """Biznes skrining. Natija: (status, sabab). status: pass / fail / review."""
    if override:
        st = override.get("status")
        if st in ("pass", "fail", "review"):
            return st, override.get("reason", "Qo'lda belgilangan")
    reason = _sic_match(sic, HARAM_SIC)
    if reason:
        return "fail", reason
    lname = (name or "").lower()
    for kw, why in HARAM_NAME_KEYWORDS.items():
        if kw in lname:
            return "fail", why
    reason = _sic_match(sic, REVIEW_SIC)
    if reason:
        return "review", reason
    if sic is None:
        return "review", "Faoliyat sohasi (SIC) aniqlanmadi"
    return "pass", "Asosiy faoliyat ruxsat etilgan sohada"


def _ratio(num, den):
    if num is None or den is None or den <= 0:
        return None
    return max(num, 0.0) / den


def classify(price, pe, rev_growth):
    """Value / Growth / Penny / Blend toifasi."""
    if price is not None and price < 5:
        return "penny"
    if rev_growth is not None and rev_growth >= 0.15:
        return "growth"
    if pe is not None and pe >= 30:
        return "growth"
    if pe is not None and 0 < pe <= 18:
        return "value"
    return "blend"


def screen(stock: dict, override: dict | None = None) -> dict:
    """
    stock maydonlari (None bo'lishi mumkin):
      sic, name, price, shares, debt, cash, revenue, interest_income,
      net_income, rev_growth
    """
    price = stock.get("price")
    shares = stock.get("shares")
    mcap = price * shares if price and shares else None

    biz_status, biz_reason = business_screen(stock.get("sic"), stock.get("name", ""), override)

    debt_r = _ratio(stock.get("debt"), mcap)
    cash_r = _ratio(stock.get("cash"), mcap)
    rev = stock.get("revenue")
    ii = stock.get("interest_income")
    impure_r = _ratio(ii, rev) if rev and rev > 0 else None
    # Daromadi yo'q, lekin foizli daromadi bor kompaniya: harom daromad ulushi 100%
    if impure_r is None and ii and ii > 0 and (rev is None or rev <= 0):
        impure_r = 1.0

    checks = {
        "business": {"status": biz_status, "reason": biz_reason},
        "debt": {"value": debt_r, "limit": DEBT_LIMIT},
        "cash": {"value": cash_r, "limit": CASH_LIMIT},
        "impure": {"value": impure_r, "limit": IMPURE_REVENUE_LIMIT},
    }
    for key in ("debt", "cash", "impure"):
        c = checks[key]
        v = c["value"]
        if v is None:
            c["status"] = "unknown"
        elif v >= c["limit"]:
            c["status"] = "fail"
        elif v >= c["limit"] * NEAR_RATIO:
            c["status"] = "near"
        else:
            c["status"] = "pass"

    reasons = []
    if biz_status == "fail":
        status = NOT_HALAL
        reasons.append(biz_reason)
    else:
        fails = [k for k in ("debt", "cash", "impure") if checks[k]["status"] == "fail"]
        if fails:
            status = NOT_HALAL
            labels = {
                "debt": "Foizli qarz chegaradan oshgan",
                "cash": "Naqd pul va foizli qog'ozlar chegaradan oshgan",
                "impure": "Foizli daromad ulushi 5% dan oshgan",
            }
            reasons += [labels[k] for k in fails]
        elif mcap is None or checks["debt"]["status"] == "unknown" and checks["cash"]["status"] == "unknown":
            status = NO_DATA
            reasons.append("Bozor kapitalizatsiyasi yoki hisobot ma'lumoti topilmadi")
        elif biz_status == "review":
            status = DOUBTFUL
            reasons.append(biz_reason)
        elif any(checks[k]["status"] == "unknown" for k in ("debt", "cash")):
            status = DOUBTFUL
            reasons.append("Ba'zi moliyaviy ko'rsatkichlar hisobotda topilmadi")
        else:
            status = HALAL

    # 1-5 ishonch reytingi: chegaradan qanchalik uzoq
    rating = None
    if status == HALAL:
        worst = max(
            (checks[k]["value"] / checks[k]["limit"])
            for k in ("debt", "cash", "impure")
            if checks[k]["value"] is not None
        ) if any(checks[k]["value"] is not None for k in ("debt", "cash", "impure")) else 1.0
        if worst < 0.2:
            rating = 5
        elif worst < 0.4:
            rating = 4
        elif worst < 0.6:
            rating = 3
        elif worst < NEAR_RATIO:
            rating = 2
        else:
            rating = 1

    pe = None
    ni = stock.get("net_income")
    if mcap and ni and ni > 0:
        pe = mcap / ni

    return {
        "status": status,
        "rating": rating,
        "reasons": reasons,
        "mcap": mcap,
        "pe": pe,
        "category": classify(price, pe, stock.get("rev_growth")),
        "checks": checks,
        # Dividendni tozalash foizi: foizli daromad ulushi
        "purification": impure_r if impure_r is not None and impure_r < 1 else None,
    }
