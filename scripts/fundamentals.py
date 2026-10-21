"""
SEC EDGAR'dan hisobot ma'lumotlarini yig'ish (bepul, API kalit kerak emas).

- Tikerlar ro'yxati: company_tickers_exchange.json
- Balans va daromad ko'rsatkichlari: XBRL "frames" API (bitta so'rovda barcha kompaniyalar)
- Faoliyat sohasi (SIC kodi): har bir kompaniyaning submissions sahifasi (keshlanadi)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import requests

from config import (DATA_DIR, EXCHANGES, SEC_USER_AGENT, SEC_REQUESTS_PER_SECOND,
                    SIC_FETCH_PER_RUN)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"})
_last_call = [0.0]


def sec_get(url: str, retries: int = 4):
    for attempt in range(retries):
        wait = 1.0 / SEC_REQUESTS_PER_SECOND - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            r = SESSION.get(url, timeout=60)
        except requests.RequestException as e:
            print(f"  ! {url}: {e}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 200:
            return r.json()
        print(f"  ! {url}: HTTP {r.status_code}")
        time.sleep(2 ** attempt * 2)
    return None


# ---------------------------------------------------------------------------
# Tikerlar
# ---------------------------------------------------------------------------
_NON_COMMON = re.compile(r"(-W|-WT|-U|-UN|-R|-RT|-P[A-Z]?)$|\.")


def load_tickers():
    js = sec_get("https://www.sec.gov/files/company_tickers_exchange.json")
    if not js:
        raise RuntimeError("SEC tikerlar ro'yxatini yuklab bo'lmadi")
    fields = js["fields"]
    out = {}
    for row in js["data"]:
        rec = dict(zip(fields, row))
        t, ex = rec["ticker"], rec["exchange"]
        if not t or ex not in EXCHANGES:
            continue
        if _NON_COMMON.search(t):
            continue
        # Nasdaq: 5 harfli tikerning oxiri W/U/R bo'lsa - varrant, birlik, huquq
        if ex == "Nasdaq" and len(t) == 5 and t[-1] in "WUR":
            continue
        out[t] = {"cik": int(rec["cik"]), "name": rec["name"], "exchange": ex}
    return out


# ---------------------------------------------------------------------------
# XBRL frames
# ---------------------------------------------------------------------------
INSTANT_CONCEPTS = {
    # Qarz
    "LongTermDebt": "us-gaap", "LongTermDebtNoncurrent": "us-gaap",
    "LongTermDebtCurrent": "us-gaap", "DebtCurrent": "us-gaap",
    "ShortTermBorrowings": "us-gaap", "CommercialPaper": "us-gaap",
    "LongTermDebtAndCapitalLeaseObligations": "us-gaap",
    "ConvertibleNotesPayable": "us-gaap", "ConvertibleNotesPayableCurrent": "us-gaap",
    "NotesPayable": "us-gaap", "NotesPayableCurrent": "us-gaap",
    "LinesOfCreditCurrent": "us-gaap", "LongTermLineOfCredit": "us-gaap",
    # Naqd pul va foizli qog'ozlar
    "CashAndCashEquivalentsAtCarryingValue": "us-gaap",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "us-gaap",
    "Cash": "us-gaap",
    "ShortTermInvestments": "us-gaap", "MarketableSecuritiesCurrent": "us-gaap",
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent": "us-gaap",
    "MarketableSecuritiesNoncurrent": "us-gaap",
    "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent": "us-gaap",
    # Balans mavjudligini tekshirish uchun
    "Assets": "us-gaap",
}
SHARE_CONCEPTS = {
    "EntityCommonStockSharesOutstanding": "dei",
    "CommonStockSharesOutstanding": "us-gaap",
}
ANNUAL_CONCEPTS = {
    "Revenues": "us-gaap",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "us-gaap",
    "SalesRevenueNet": "us-gaap",
    "InvestmentIncomeInterest": "us-gaap",
    "InvestmentIncomeInterestAndDividend": "us-gaap",
    "InterestAndDividendIncomeOperating": "us-gaap",
    "NetIncomeLoss": "us-gaap",
}


def _recent_quarters(n=5):
    now = datetime.now(timezone.utc)
    y, q = now.year, (now.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        out.append(f"CY{y}Q{q}I")
    # joriy chorak ham (erta topshirganlar uchun)
    cy, cq = now.year, (now.month - 1) // 3 + 1
    return [f"CY{cy}Q{cq}I"] + out


def _frame(taxonomy, concept, unit, period):
    url = f"https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json"
    js = sec_get(url)
    return js.get("data", []) if js else []


def collect_instants(concepts, unit, periods):
    """Har bir kompaniya uchun eng so'nggi qiymat: {concept: {cik: (end, val)}}"""
    res = {}
    for concept, tax in concepts.items():
        latest = {}
        for p in periods:
            for d in _frame(tax, concept, unit, p):
                cik, end, val = d["cik"], d["end"], d["val"]
                if cik not in latest or end > latest[cik][0]:
                    latest[cik] = (end, val)
        res[concept] = latest
        print(f"  {concept}: {len(latest)} kompaniya")
    return res


def collect_annual(concepts, years):
    """{concept: {cik: {year: val}}}"""
    res = {}
    for concept, tax in concepts.items():
        per = {}
        for y in years:
            for d in _frame(tax, concept, "USD", f"CY{y}"):
                per.setdefault(d["cik"], {})[y] = d["val"]
        res[concept] = per
        print(f"  {concept}: {len(per)} kompaniya")
    return res


def _v(table, concept, cik, end=None, tolerance_days=200):
    """Qiymatni olish. end berilsa, sana unga yaqin bo'lishi kerak (eski balansni aralashtirmaslik)."""
    hit = table.get(concept, {}).get(cik)
    if not hit:
        return None
    if end is not None:
        d1 = datetime.fromisoformat(hit[0]); d2 = datetime.fromisoformat(end)
        if abs((d1 - d2).days) > tolerance_days:
            return None
    return float(hit[1])


def compute_debt(inst, cik, end):
    g = lambda c: _v(inst, c, cik, end)  # noqa: E731
    ltd_cur = g("LongTermDebtCurrent")
    if g("DebtCurrent") is not None:
        current = g("DebtCurrent")
    else:
        parts = [ltd_cur, g("ShortTermBorrowings"), g("CommercialPaper"),
                 g("NotesPayableCurrent"), g("ConvertibleNotesPayableCurrent"),
                 g("LinesOfCreditCurrent")]
        current = sum(p for p in parts if p) if any(p is not None for p in parts) else None

    if g("LongTermDebtNoncurrent") is not None:
        noncurrent = g("LongTermDebtNoncurrent")
    elif g("LongTermDebtAndCapitalLeaseObligations") is not None:
        noncurrent = g("LongTermDebtAndCapitalLeaseObligations")
    elif g("LongTermDebt") is not None:
        noncurrent = max(g("LongTermDebt") - (ltd_cur or 0), 0)
    else:
        parts = [g("ConvertibleNotesPayable"), g("NotesPayable"), g("LongTermLineOfCredit")]
        noncurrent = sum(p for p in parts if p) if any(p is not None for p in parts) else None

    if current is None and noncurrent is None:
        return None
    return (current or 0) + (noncurrent or 0)


def compute_cash(inst, cik, end):
    g = lambda c: _v(inst, c, cik, end)  # noqa: E731
    cash = g("CashAndCashEquivalentsAtCarryingValue")
    if cash is None:
        cash = g("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
    if cash is None:
        cash = g("Cash")
    st = g("ShortTermInvestments")
    if st is None:
        st = g("MarketableSecuritiesCurrent")
    if st is None:
        st = g("AvailableForSaleSecuritiesDebtSecuritiesCurrent")
    lt = g("MarketableSecuritiesNoncurrent")
    if lt is None:
        lt = g("AvailableForSaleSecuritiesDebtSecuritiesNoncurrent")
    if cash is None and st is None and lt is None:
        return None
    return (cash or 0) + (st or 0) + (lt or 0)


def _first(annual, concepts, cik, year):
    for c in concepts:
        v = annual.get(c, {}).get(cik, {}).get(year)
        if v is not None:
            return float(v)
    return None


# ---------------------------------------------------------------------------
# SIC kodlari
# ---------------------------------------------------------------------------
def update_sic_cache(ciks):
    path = DATA_DIR / "sic.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    missing = [c for c in ciks if str(c) not in cache]
    print(f"SIC: keshda {len(cache)}, yetishmaydi {len(missing)}, bu safar {min(len(missing), SIC_FETCH_PER_RUN)}")
    for i, cik in enumerate(missing[:SIC_FETCH_PER_RUN]):
        js = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if js is None:
            cache[str(cik)] = [None, ""]
        else:
            sic = js.get("sic")
            cache[str(cik)] = [int(sic) if sic and str(sic).isdigit() else None,
                               js.get("sicDescription") or ""]
        if i % 250 == 249:
            path.write_text(json.dumps(cache))
            print(f"  {i + 1} ta olindi")
    path.write_text(json.dumps(cache))
    return cache


# ---------------------------------------------------------------------------
# Asosiy
# ---------------------------------------------------------------------------
def update_fundamentals():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Tikerlar yuklanmoqda...")
    tickers = load_tickers()
    print(f"  {len(tickers)} ta aksiya")
    ciks = sorted({v["cik"] for v in tickers.values()})

    quarters = _recent_quarters(5)
    print("Balans ko'rsatkichlari:", quarters)
    inst = collect_instants(INSTANT_CONCEPTS, "USD", quarters)
    shares_t = collect_instants(SHARE_CONCEPTS, "shares", quarters)

    this_year = datetime.now(timezone.utc).year
    years = [this_year - 1, this_year - 2, this_year - 3]
    print("Yillik ko'rsatkichlar:", years)
    annual = collect_annual(ANNUAL_CONCEPTS, years)

    sic = update_sic_cache(ciks)

    revenue_c = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
    interest_c = ["InvestmentIncomeInterest", "InvestmentIncomeInterestAndDividend",
                  "InterestAndDividendIncomeOperating"]

    out = {}
    for t, info in tickers.items():
        cik = info["cik"]
        bs = inst.get("Assets", {}).get(cik)
        end = bs[0] if bs else None
        if end is None:
            # Assets yo'q bo'lsa, istalgan qarz/naqd ko'rsatkichining eng so'nggi sanasi
            dates = [inst[c][cik][0] for c in inst if cik in inst[c]]
            end = max(dates) if dates else None

        debt = compute_debt(inst, cik, end) if end else None
        debt_note = None
        if debt is None and bs is not None:
            debt, debt_note = 0.0, "Hisobotda foizli qarz ko'rsatilmagan, 0 deb olindi"
        cash = compute_cash(inst, cik, end) if end else None

        sh = shares_t["EntityCommonStockSharesOutstanding"].get(cik) or \
            shares_t["CommonStockSharesOutstanding"].get(cik)

        # Eng so'nggi yil bo'yicha daromad
        rev = ii = ni = growth = None
        fy = None
        for y in years:
            rev = _first(annual, revenue_c, cik, y)
            if rev is not None:
                fy = y
                break
        if fy is not None:
            ii = _first(annual, interest_c, cik, fy)
            ni = _first(annual, ["NetIncomeLoss"], cik, fy)
            prev = _first(annual, revenue_c, cik, fy - 1)
            if prev and prev > 0 and rev is not None:
                growth = rev / prev - 1
        else:
            ni = next((_first(annual, ["NetIncomeLoss"], cik, y) for y in years
                       if _first(annual, ["NetIncomeLoss"], cik, y) is not None), None)

        s = sic.get(str(cik), [None, ""])
        out[t] = {
            "cik": cik, "name": info["name"], "exchange": info["exchange"],
            "sic": s[0], "sic_desc": s[1],
            "bs_date": end, "debt": debt, "debt_note": debt_note, "cash": cash,
            "shares": float(sh[1]) if sh else None,
            "fy": fy, "revenue": rev, "interest_income": ii, "net_income": ni,
            "rev_growth": growth,
        }

    payload = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "stocks": out}
    (DATA_DIR / "fundamentals.json").write_text(json.dumps(payload, separators=(",", ":")))
    print(f"fundamentals.json yozildi: {len(out)} ta aksiya")
    return payload
