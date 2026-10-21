"""
Asosiy ishga tushiruvchi.

  python scripts/run.py                # hisobotlar eskirgan bo'lsa yangilaydi, narxlarni oladi, saytni quradi
  python scripts/run.py --no-prices    # narxsiz (faqat mavjud keshdan) qurish
  python scripts/run.py --force-fundamentals
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA_DIR, SITE_DATA_DIR, FUNDAMENTALS_MAX_AGE_HOURS  # noqa: E402
from screening import screen  # noqa: E402

FIELDS = ["t", "n", "ex", "st", "rt", "cat", "p", "chg", "mc", "dr", "cr", "ir", "pe",
          "biz", "bizr", "why", "sic", "bs", "fy", "debt", "cash", "rev", "ii", "note", "pat", "std"]


def _r(x, nd=4):
    return None if x is None else round(x, nd)


def fundamentals_stale() -> bool:
    p = DATA_DIR / "fundamentals.json"
    if not p.exists():
        return True
    ts = json.loads(p.read_text()).get("updated_at")
    if not ts:
        return True
    age = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
    return age > timedelta(hours=FUNDAMENTALS_MAX_AGE_HOURS)


def load_sic() -> dict:
    p = DATA_DIR / "sic.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _load(name):
    p = DATA_DIR / name
    return json.loads(p.read_text()) if p.exists() else {}


def build(fund: dict, prices: dict, shares_fb: dict):
    from foreign import merge
    foreign, fx, yshares = _load("foreign.json"), _load("fx.json"), _load("yahoo_shares.json")
    overrides_p = DATA_DIR / "overrides.json"
    overrides = json.loads(overrides_p.read_text()) if overrides_p.exists() else {}
    overrides = {k.upper(): v for k, v in overrides.items() if not k.startswith("_")}
    sic_cache = load_sic()
    sic_complete = all(str(s["cik"]) in sic_cache for s in fund["stocks"].values())

    rows, statuses = [], {}
    counts = {"halal": 0, "not_halal": 0, "doubtful": 0, "no_data": 0}
    for t, s in fund["stocks"].items():
        pr = prices.get(t) or {}
        s = merge(t, s, foreign, fx, yshares)
        shares = s.get("shares") or shares_fb.get(t)
        sc = sic_cache.get(str(s["cik"]))
        if sc:
            s = dict(s, sic=sc[0], sic_desc=sc[1])
        stock = dict(s, price=pr.get("p"), shares=shares)
        r = screen(stock, overrides.get(t))
        if r["status"] == "no_data":
            r["mcap"] = r["pe"] = None
        c = r["checks"]
        statuses[t] = r["status"]
        counts[r["status"]] += 1
        rows.append([
            t, s["name"], s["exchange"], r["status"], r["rating"], r["category"],
            pr.get("p"), pr.get("chg"), _r(r["mcap"], 0), _r(c["debt"]["value"]),
            _r(c["cash"]["value"]), _r(c["impure"]["value"]), _r(r["pe"], 1),
            c["business"]["status"], c["business"]["reason"], r["reasons"],
            s.get("sic_desc") or "", s.get("bs_date"), s.get("fy"),
            s.get("debt"), s.get("cash"), s.get("revenue"), s.get("interest_income"),
            s.get("debt_note"), pr.get("at"),
            (s.get("std", "US-GAAP") + (" · " + s["cur"] if s.get("cur") and s["cur"] != "USD" else "")),
        ])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Status o'zgarishlari tarixi
    prev_p = DATA_DIR / "statuses.json"
    prev = json.loads(prev_p.read_text()) if prev_p.exists() else {}
    changes_p = DATA_DIR / "changes.json"
    changes = json.loads(changes_p.read_text()) if changes_p.exists() else []
    # Birinchi ishga tushishda va SIC kodlari hali to'liq yig'ilmagan paytda o'zgarish yozilmaydi
    if prev and sic_complete:
        names = {t: s["name"] for t, s in fund["stocks"].items()}
        for t, st in statuses.items():
            old = prev.get(t)
            if old and old != st and "no_data" not in (old, st):
                changes.insert(0, {"t": t, "n": names.get(t, ""), "from": old, "to": st, "at": now})
    changes = changes[:500]
    prev_p.write_text(json.dumps(statuses, separators=(",", ":")))
    changes_p.write_text(json.dumps(changes, separators=(",", ":"), ensure_ascii=False))

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now,
        "fundamentals_at": fund.get("updated_at"),
        "counts": counts,
        "fields": FIELDS,
        "rows": rows,
    }
    (SITE_DATA_DIR / "stocks.json").write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    (SITE_DATA_DIR / "changes.json").write_text(
        json.dumps(changes[:200], separators=(",", ":"), ensure_ascii=False))
    print(f"Sayt ma'lumoti: {len(rows)} ta aksiya, {counts}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-prices", action="store_true")
    ap.add_argument("--force-fundamentals", action="store_true")
    a = ap.parse_args()

    if a.force_fundamentals or fundamentals_stale():
        from fundamentals import update_fundamentals
        fund = update_fundamentals()
    else:
        fund = json.loads((DATA_DIR / "fundamentals.json").read_text())
        print(f"Hisobotlar keshdan: {len(fund['stocks'])} ta ({fund['updated_at']})")

    sic_cache = load_sic()
    missing = [s["cik"] for s in fund["stocks"].values() if str(s["cik"]) not in sic_cache]
    if missing and not a.no_prices:
        from fundamentals import update_sic_cache
        update_sic_cache(sorted(set(missing)))

    prices_p = DATA_DIR / "prices.json"
    shares_fb = {}
    if a.no_prices:
        prices = json.loads(prices_p.read_text()) if prices_p.exists() else {}
    else:
        from prices import fetch_prices, fill_missing_shares
        prices = fetch_prices(sorted(fund["stocks"].keys()))
        shares_fb = fill_missing_shares(fund["stocks"])
        from foreign import update_foreign, update_fx, update_yahoo_shares, needs_foreign
        foreign = update_foreign(fund["stocks"])
        update_fx({(v.get("d") or {}).get("cur") for v in foreign.values()} - {None})
        ifrs_ciks = {int(k) for k, v in foreign.items() if (v.get("d") or {}).get("std") == "IFRS"}
        update_yahoo_shares(sorted(t for t, s in fund["stocks"].items()
                                   if needs_foreign(s) and s["cik"] in ifrs_ciks))
    fb_p = DATA_DIR / "shares_fallback.json"
    if not shares_fb and fb_p.exists():
        shares_fb = json.loads(fb_p.read_text())
    build(fund, prices, shares_fb)


if __name__ == "__main__":
    main()
