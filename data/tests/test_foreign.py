import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from foreign import extract, merge  # noqa: E402
from screening import screen, HALAL, NOT_HALAL  # noqa: E402


def inst(end, val, filed="2026-04-01"):
    return {"end": end, "val": val, "filed": filed, "form": "20-F"}


def dur(start, end, val, filed="2026-04-01"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": "20-F"}


IFRS_FACTS = {"ifrs-full": {
    "Assets": {"units": {"MYR": [inst("2024-12-31", 900), inst("2025-12-31", 1000)]}},
    "CurrentBorrowings": {"units": {"MYR": [inst("2025-12-31", 40), inst("2024-12-31", 999)]}},
    "NoncurrentBorrowings": {"units": {"MYR": [inst("2025-12-31", 60)]}},
    "CashAndCashEquivalents": {"units": {"MYR": [inst("2025-12-31", 150)]}},
    "Revenue": {"units": {"MYR": [dur("2025-01-01", "2025-12-31", 500),
                                  dur("2024-01-01", "2024-12-31", 400),
                                  dur("2025-07-01", "2025-12-31", 260)]}},
    "FinanceIncome": {"units": {"MYR": [dur("2025-01-01", "2025-12-31", 10)]}},
    "ProfitLoss": {"units": {"MYR": [dur("2025-01-01", "2025-12-31", 50)]}},
}}


def test_extract_ifrs():
    d = extract(IFRS_FACTS, 1)
    assert d["std"] == "IFRS" and d["cur"] == "MYR" and d["bs_date"] == "2025-12-31"
    assert d["debt"] == 100          # 40 + 60, eski 999 olinmaydi
    assert d["cash"] == 150
    assert d["revenue"] == 500       # yarim yillik 260 olinmaydi
    assert abs(d["rev_growth"] - 0.25) < 1e-9
    assert d["interest_income"] == 10 and d["net_income"] == 50 and d["fy"] == 2025


def test_merge_converts_currency_and_uses_adr_shares():
    s = {"cik": 1, "name": "VCI Global", "debt": None, "cash": None, "shares": 9e9}
    foreign = {"1": {"d": extract(IFRS_FACTS, 1)}}
    fx = {"MYR": {"r": 0.25}}
    ys = {"VCIG": {"s": 4.0}}
    m = merge("VCIG", s, foreign, fx, ys)
    assert m["debt"] == 25 and m["cash"] == 37.5 and m["shares"] == 4.0
    r = screen(dict(m, price=100.0, sic=7372))   # mcap = 400 USD
    assert r["status"] == HALAL                   # qarz 6.25%, naqd 9.4%, foizli daromad 2%


def test_merge_without_fx_leaves_no_data():
    s = {"cik": 1, "debt": None, "cash": None}
    m = merge("X", s, {"1": {"d": extract(IFRS_FACTS, 1)}}, {}, {})
    assert m["debt"] is None


def test_merge_skips_domestic_with_data():
    s = {"cik": 1, "debt": 5.0, "cash": 1.0}
    assert merge("X", s, {"1": {"d": {"cur": "USD"}}}, {}, {}) is s


def test_extract_usgaap_fallback():
    facts = {"us-gaap": {
        "Assets": {"units": {"USD": [inst("2023-09-30", 100)]}},
        "LongTermDebt": {"units": {"USD": [inst("2023-09-30", 70)]}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [inst("2023-09-30", 5)]}},
        "Revenues": {"units": {"USD": [dur("2022-10-01", "2023-09-30", 80)]}},
    }}
    d = extract(facts, 7)
    assert d["std"] == "US-GAAP" and d["debt"] == 70 and d["cash"] == 5 and d["revenue"] == 80
    r = screen(dict(d, cik=7, name="Old Co", price=1.0, shares=100.0, sic=7372))
    assert r["status"] == NOT_HALAL   # qarz 70%
