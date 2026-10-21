"""Loyiha sozlamalari."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"          # doimiy kesh (git'da saqlanadi)
SITE_DIR = ROOT / "site"          # GitHub Pages'ga chiqadigan sayt
SITE_DATA_DIR = SITE_DIR / "data"

# SEC EDGAR har bir so'rovda aloqa ma'lumoti bo'lgan User-Agent talab qiladi.
# GitHub'da "Settings -> Secrets and variables -> Actions -> Variables" bo'limida
# SEC_USER_AGENT o'zgaruvchisini yarating, masalan: "TradingLab Screener sizning@email.com"
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "TradingLab Halal Screener admin@example.com")

# Qaysi birjalar qamrab olinadi (SEC ro'yxatidagi nomlar).
# OTC (birjadan tashqari) aksiyalarni ham qo'shish uchun "OTC" ni qo'shing.
EXCHANGES = {"Nasdaq", "NYSE", "CBOE"}

# Hisobot ma'lumotlari necha soatdan keyin eskirgan hisoblanadi
FUNDAMENTALS_MAX_AGE_HOURS = 24

# Bitta ishga tushishda SEC'dan nechta kompaniyaning soha (SIC) kodi olinadi.
# Birinchi ishga tushishda hammasi bir necha soatlik ishga bo'linadi.
SIC_FETCH_PER_RUN = 2500

# SEC: sekundiga 10 so'rovdan oshmaslik kerak
SEC_REQUESTS_PER_SECOND = 8

# Yahoo Finance'dan narx olishda bir paketdagi tikerlar soni
PRICE_CHUNK = 300
