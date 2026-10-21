"""
Yahoo Finance'dan narxlarni olish (yfinance kutubxonasi orqali, API kalit kerak emas).
Savdo vaqtida so'nggi narx, savdo yopiq bo'lsa so'nggi yopilish narxi olinadi.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

from config import DATA_DIR, PRICE_CHUNK


def _yahoo_symbol(t: str) -> str:
    return t.replace(".", "-")


def fetch_prices(tickers: list[str]) -> dict:
    import yfinance as yf  # faqat kerak bo'lganda yuklanadi

    path = DATA_DIR / "prices.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    got = 0
    for i in range(0, len(tickers), PRICE_CHUNK):
        chunk = tickers[i:i + PRICE_CHUNK]
        syms = [_yahoo_symbol(t) for t in chunk]
        for attempt in range(3):
            try:
                df = yf.download(syms, period="5d", interval="1d", group_by="ticker",
                                 auto_adjust=False, progress=False, threads=True)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  ! paket {i}: {e}")
                time.sleep(5 * (attempt + 1))
        else:
            continue
        for t, sym in zip(chunk, syms):
            try:
                closes = df[sym]["Close"] if len(syms) > 1 else df["Close"]
                closes = [float(x) for x in closes.tolist() if x == x and not math.isinf(x)]
            except Exception:  # noqa: BLE001
                continue
            if not closes:
                continue
            last = closes[-1]
            prev = closes[-2] if len(closes) > 1 else None
            old[t] = {"p": round(last, 4),
                      "chg": round((last / prev - 1) * 100, 2) if prev else None,
                      "at": now}
            got += 1
        print(f"  narxlar: {min(i + PRICE_CHUNK, len(tickers))}/{len(tickers)}")
        time.sleep(1)
    path.write_text(json.dumps(old, separators=(",", ":")))
    print(f"Narx yangilandi: {got} ta, jami keshda {len(old)} ta")
    return old


def fill_missing_shares(fund: dict, limit: int = 300):
    """SEC'da aksiyalar soni topilmagan kompaniyalar uchun Yahoo'dan olish (keshlanadi)."""
    import yfinance as yf

    path = DATA_DIR / "shares_fallback.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    missing = [t for t, s in fund.items() if not s.get("shares") and t not in cache]
    for t in missing[:limit]:
        try:
            sh = yf.Ticker(_yahoo_symbol(t)).fast_info.get("shares")
            cache[t] = float(sh) if sh else None
        except Exception:  # noqa: BLE001
            cache[t] = None
    path.write_text(json.dumps(cache))
    return cache
