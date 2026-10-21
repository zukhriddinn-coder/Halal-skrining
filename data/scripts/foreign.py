"""
Xorijiy (IFRS) va hisobot ma'lumoti topilmagan kompaniyalar uchun qo'shimcha manba.

- SEC "companyfacts" (har bir kompaniyaning barcha hisobot ko'rsatkichlari): ifrs-full va us-gaap
- Valyuta kurslari: Yahoo Finance (masalan MYRUSD=X)
- ADR'lar uchun aksiyalar soni: Yahoo Finance (ADR'ga teng aksiyalar soni)

Har bir ishga tushishda cheklangan miqdorda yuklanadi va keshlanadi (data/foreign.json),
7 kunda bir marta yangilanadi.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from config import DATA_DIR

FOREIGN_PER_RUN = 700           # bitta ishga tushishda nechta kompaniya
YAHOO_SHARES_PER_RUN = 700
REFRESH_DAYS = 7

# ---------------------------------------------------------------------------
# IFRS ko'rsatkichlari
# ---------------------------------------------------------------------------
IFRS_DEBT_TOTAL = ["Borrowings"]
IFRS_DEBT_CURRENT = ["CurrentBorrowings", "ShorttermBorrowings",
                     "CurrentPortionOfLongtermBorrowings", "CurrentBondsIssued",
                     "CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived"]
IFRS_DEBT_NONCURRENT = ["NoncurrentBorrowings", "LongtermBorrowings",
                        "NoncurrentPortionOfNoncurrentBondsIssued", "NoncurrentLoansReceived",
                        "BondsIssued", "NotesAndDebenturesIssued"]
IFRS_CASH = ["CashAndCashEquivalents"]
IFRS_CASH_EXTRA = ["ShorttermDepositsNotClassifiedAsCashEquivalents", "CurrentInvestments",
                   "OtherCurrentFinancialAssets"]
IFRS_REVENUE = ["Revenue", "RevenueFromContractsWithCustomers"]
IFRS_INTEREST = ["InterestRevenueCalculatedUsingEffectiveInterestMethod", "InterestIncome",
                 "InterestIncomeOnDeposits", "FinanceIncome"]
IFRS_NET_INCOME = ["ProfitLoss", "ProfitLossAttributableToOwnersOfParent"]


def _units(facts, tax, concept):
    return facts.get(tax, {}).get(concept, {}).get("units", {})


def _currency(facts, tax):
    """Balans valyutasi: Assets ko'rsatkichi qaysi valyutada bo'lsa (USD afzal)."""
    u = _units(facts, tax, "Assets")
    if not u:
        return None
    return "USD" if "USD" in u else next(iter(u))


def _latest_instant(facts, tax, concept, cur, end=None):
    rows = [r for r in _units(facts, tax, concept).get(cur, []) if "start" not in r]
    if end:
        rows = [r for r in rows if r.get("end") == end]
    if not rows:
        return None
    r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
    return r["end"], float(r["val"])


def _annual(facts, tax, concept, cur):
    """{yil_oxiri: qiymat} faqat ~1 yillik davrlar uchun."""
    out = {}
    for r in _units(facts, tax, concept).get(cur, []):
        if "start" not in r:
            continue
        try:
            d = (datetime.fromisoformat(r["end"]) - datetime.fromisoformat(r["start"])).days
        except ValueError:
            continue
        if 330 <= d <= 400:
            if r["end"] not in out or r.get("filed", "") > out[r["end"]][1]:
                out[r["end"]] = (float(r["val"]), r.get("filed", ""))
    return {k: v[0] for k, v in out.items()}


def _first_annual(facts, tax, concepts, cur):
    for c in concepts:
        a = _annual(facts, tax, c, cur)
        if a:
            return a
    return {}


def _sum_first(facts, tax, groups, cur, end):
    """Har bir guruhdan birinchi topilgan ko'rsatkichni oladi va qo'shadi."""
    total, found = 0.0, False
    for group in groups:
        for c in group:
            v = _latest_instant(facts, tax, c, cur, end)
            if v is not None:
                total += v[1]
                found = True
                break
    return total if found else None


def extract_ifrs(facts: dict) -> dict | None:
    tax = "ifrs-full"
    cur = _currency(facts, tax)
    if not cur:
        return None
    a = _latest_instant(facts, tax, "Assets", cur)
    if not a:
        return None
    end = a[0]

    debt = _sum_first(facts, tax, [IFRS_DEBT_TOTAL], cur, end)
    if debt is None:
        debt = _sum_first(facts, tax, [IFRS_DEBT_CURRENT, IFRS_DEBT_NONCURRENT], cur, end)
    note = None
    if debt is None:
        debt, note = 0.0, "Hisobotda foizli qarz ko'rsatilmagan, 0 deb olindi"

    cash = _sum_first(facts, tax, [IFRS_CASH], cur, end)
    extra = sum(v[1] for c in IFRS_CASH_EXTRA
                if (v := _latest_instant(facts, tax, c, cur, end)) is not None)
    if cash is not None or extra:
        cash = (cash or 0) + extra

    rev_a = _first_annual(facts, tax, IFRS_REVENUE, cur)
    rev = ii = ni = growth = None
    fy_end = None
    if rev_a:
        fy_end = max(rev_a)
        rev = rev_a[fy_end]
        prev = [k for k in rev_a if k < fy_end]
        if prev and rev_a[max(prev)] > 0:
            growth = rev / rev_a[max(prev)] - 1
        for c in IFRS_INTEREST:
            v = _annual(facts, tax, c, cur).get(fy_end)
            if v is not None:
                ii = v
                break
        for c in IFRS_NET_INCOME:
            v = _annual(facts, tax, c, cur).get(fy_end)
            if v is not None:
                ni = v
                break

    return {"std": "IFRS", "cur": cur, "bs_date": end, "debt": debt, "debt_note": note,
            "cash": cash, "revenue": rev, "interest_income": ii, "net_income": ni,
            "rev_growth": growth, "fy": int(fy_end[:4]) if fy_end else None}


def extract_usgaap(facts: dict, cik: int) -> dict | None:
    """us-gaap kompaniyasi, lekin frames'da topilmagan (masalan, eski yoki noodatiy davr)."""
    from fundamentals import (INSTANT_CONCEPTS, compute_debt, compute_cash)
    tax = "us-gaap"
    if "USD" not in _units(facts, tax, "Assets"):
        return None
    a = _latest_instant(facts, tax, "Assets", "USD")
    end = a[0]
    inst = {}
    for c in INSTANT_CONCEPTS:
        v = _latest_instant(facts, tax, c, "USD", end)
        inst[c] = {cik: v} if v else {}
    debt = compute_debt(inst, cik, end)
    note = None
    if debt is None:
        debt, note = 0.0, "Hisobotda foizli qarz ko'rsatilmagan, 0 deb olindi"
    cash = compute_cash(inst, cik, end)
    rev_a = _first_annual(facts, tax, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                                       "SalesRevenueNet"], "USD")
    rev = ii = ni = growth = None
    fy_end = None
    if rev_a:
        fy_end = max(rev_a)
        rev = rev_a[fy_end]
        prev = [k for k in rev_a if k < fy_end]
        if prev and rev_a[max(prev)] > 0:
            growth = rev / rev_a[max(prev)] - 1
        for c in ["InvestmentIncomeInterest", "InvestmentIncomeInterestAndDividend",
                  "InterestAndDividendIncomeOperating"]:
            v = _annual(facts, tax, c, "USD").get(fy_end)
            if v is not None:
                ii = v
                break
        ni = _annual(facts, tax, "NetIncomeLoss", "USD").get(fy_end)
    return {"std": "US-GAAP", "cur": "USD", "bs_date": end, "debt": debt, "debt_note": note,
            "cash": cash, "revenue": rev, "interest_income": ii, "net_income": ni,
            "rev_growth": growth, "fy": int(fy_end[:4]) if fy_end else None}


def extract(facts: dict, cik: int) -> dict | None:
    if _units(facts, "ifrs-full", "Assets"):
        return extract_ifrs(facts)
    if _units(facts, "us-gaap", "Assets"):
        return extract_usgaap(facts, cik)
    return None


# ---------------------------------------------------------------------------
# Kesh va yuklash
# ---------------------------------------------------------------------------
def _load(name):
    p = DATA_DIR / name
    return json.loads(p.read_text()) if p.exists() else {}


def _save(name, obj):
    (DATA_DIR / name).write_text(json.dumps(obj, separators=(",", ":")))


def _stale(ts):
    if not ts:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(ts) > timedelta(days=REFRESH_DAYS)


def needs_foreign(s: dict) -> bool:
    return s.get("debt") is None and s.get("cash") is None


def update_foreign(stocks: dict):
    from fundamentals import sec_get
    cache = _load("foreign.json")
    ciks = sorted({s["cik"] for s in stocks.values() if needs_foreign(s)})
    todo = [c for c in ciks if _stale(cache.get(str(c), {}).get("at"))]
    print(f"Xorijiy/qo'shimcha hisobotlar: kerak {len(ciks)}, yangilanadi {min(len(todo), FOREIGN_PER_RUN)}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, cik in enumerate(todo[:FOREIGN_PER_RUN]):
        js = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        data = None
        if js:
            try:
                data = extract(js.get("facts", {}), cik)
            except Exception as e:  # noqa: BLE001
                print(f"  ! CIK {cik}: {e}")
        cache[str(cik)] = {"at": now, "d": data}
        if i % 200 == 199:
            _save("foreign.json", cache)
            print(f"  {i + 1} ta olindi")
    _save("foreign.json", cache)
    return cache


def update_fx(currencies: set[str]):
    import yfinance as yf
    fx = _load("fx.json")
    today = datetime.now(timezone.utc).date().isoformat()
    for cur in sorted(currencies - {"USD"}):
        if fx.get(cur, {}).get("day") == today:
            continue
        rate = None
        for sym, inv in ((f"{cur}USD=X", False), (f"USD{cur}=X", True)):
            try:
                h = yf.Ticker(sym).history(period="5d")["Close"].dropna()
                if len(h):
                    v = float(h.iloc[-1])
                    rate = 1 / v if inv else v
                    break
            except Exception:  # noqa: BLE001
                continue
        if rate:
            fx[cur] = {"r": rate, "day": today}
    _save("fx.json", fx)
    print(f"Valyuta kurslari: {len(fx)} ta")
    return fx


def update_yahoo_shares(tickers: list[str]):
    """ADR va boshqa kompaniyalar uchun Yahoo'dagi aksiyalar soni (ADR'ga teng)."""
    import yfinance as yf
    cache = _load("yahoo_shares.json")
    todo = [t for t in tickers if _stale(cache.get(t, {}).get("at"))]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Yahoo aksiyalar soni: kerak {len(tickers)}, yangilanadi {min(len(todo), YAHOO_SHARES_PER_RUN)}")
    for t in todo[:YAHOO_SHARES_PER_RUN]:
        sh = None
        try:
            sh = yf.Ticker(t.replace(".", "-")).fast_info.get("shares")
        except Exception:  # noqa: BLE001
            pass
        cache[t] = {"at": now, "s": float(sh) if sh else None}
    _save("yahoo_shares.json", cache)
    return cache


def merge(t: str, s: dict, foreign: dict, fx: dict, yshares: dict) -> dict:
    """Hisobot ma'lumoti yo'q aksiyani xorijiy/qo'shimcha manba bilan to'ldiradi."""
    if not needs_foreign(s):
        return s
    entry = foreign.get(str(s["cik"]), {}).get("d")
    if not entry:
        return s
    cur = entry["cur"]
    rate = 1.0 if cur == "USD" else (fx.get(cur) or {}).get("r")
    if rate is None:
        return s
    conv = lambda v: None if v is None else v * rate  # noqa: E731
    out = dict(s, bs_date=entry["bs_date"], debt=conv(entry["debt"]), debt_note=entry["debt_note"],
               cash=conv(entry["cash"]), revenue=conv(entry["revenue"]),
               interest_income=conv(entry["interest_income"]), net_income=conv(entry["net_income"]),
               rev_growth=entry["rev_growth"], fy=entry["fy"], std=entry["std"], cur=cur)
    ys = (yshares.get(t) or {}).get("s")
    if entry["std"] == "IFRS":
        # ADR narxi oddiy aksiya narxidan farq qiladi: Yahoo'dagi ADR'ga teng sonni olamiz
        out["shares"] = ys
    elif not out.get("shares"):
        out["shares"] = ys
    return out
