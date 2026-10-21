import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from screening import screen, HALAL, NOT_HALAL, DOUBTFUL, NO_DATA  # noqa: E402

BASE = dict(sic=7372, name="Example Software Inc", price=100.0, shares=1_000_000,
            debt=5_000_000, cash=10_000_000, revenue=50_000_000,
            interest_income=500_000, net_income=4_000_000, rev_growth=0.05)


def s(**kw):
    d = dict(BASE); d.update(kw); return screen(d)


def test_halal_basic():
    r = s()
    assert r["status"] == HALAL
    assert r["mcap"] == 100_000_000
    assert abs(r["checks"]["debt"]["value"] - 0.05) < 1e-9
    assert r["rating"] == 4  # eng yomon nisbat 0.10/0.30 ≈ 0.33... cash; impure 0.01/0.05=0.2


def test_debt_fail():
    assert s(debt=30_000_000)["status"] == NOT_HALAL  # aynan 30% -> o'tmaydi
    assert s(debt=29_000_000)["status"] == HALAL


def test_cash_fail():
    assert s(cash=31_000_000)["status"] == NOT_HALAL


def test_impure_fail():
    assert s(interest_income=2_600_000)["status"] == NOT_HALAL


def test_bank_sic():
    r = s(sic=6021, name="Some National Bank")
    assert r["status"] == NOT_HALAL
    assert "bank" in r["reasons"][0].lower()


def test_name_keyword():
    assert s(name="Lucky Casino Resorts")["status"] == NOT_HALAL


def test_review_sic_doubtful():
    assert s(sic=6798, name="Property Trust")["status"] == DOUBTFUL


def test_no_price():
    assert s(price=None)["status"] == NO_DATA


def test_missing_debt_doubtful():
    assert s(debt=None)["status"] == DOUBTFUL


def test_override():
    r = screen(dict(BASE, sic=6021), {"status": "pass", "reason": "Islomiy bank"})
    assert r["status"] == HALAL


def test_categories():
    assert s(price=2.0)["category"] == "penny"
    assert s(rev_growth=0.3)["category"] == "growth"
    assert s(net_income=10_000_000)["category"] == "value"  # P/E = 10


def test_price_drop_flips_status():
    # Narx tushsa kapitalizatsiya kamayadi va qarz nisbati oshadi
    assert s(debt=25_000_000)["status"] == HALAL
    assert s(debt=25_000_000, price=80.0)["status"] == NOT_HALAL
