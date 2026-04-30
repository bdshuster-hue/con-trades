"""
Congressional Trades Daily Report
Fetches $250K+ STOCK Act disclosures via Finnhub and emails a formatted HTML report.
"""

import os
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def utcnow():
    return datetime.now(timezone.utc)

RECIPIENT_EMAIL  = os.environ.get("RECIPIENT_EMAIL", "bdshuster@gmail.com")
SENDER_EMAIL     = os.environ.get("SENDER_EMAIL")
GMAIL_APP_PW     = os.environ.get("GMAIL_APP_PASSWORD")
FINNHUB_API_KEY  = os.environ.get("FINNHUB_API_KEY", "")
LOOKBACK_DAYS    = int(os.environ.get("LOOKBACK_DAYS", "1"))
MIN_AMOUNT       = int(os.environ.get("MIN_AMOUNT", "250000"))

AMOUNT_MIDPOINTS = {
    "$1,001 - $15,000": 8000,
    "$15,001 - $50,000": 32500,
    "$50,001 - $100,000": 75000,
    "$100,001 - $250,000": 175000,
    "$250,001 - $500,000": 375000,
    "$500,001 - $1,000,000": 750000,
    "$1,000,001 - $5,000,000": 3000000,
    "$5,000,001 - $25,000,000": 15000000,
    "$25,000,001 - $50,000,000": 37500000,
    "Over $50,000,000": 50000001,
}

AMOUNT_LABELS = {
    "$250,001 - $500,000": "$250K-$500K",
    "$500,001 - $1,000,000": "$500K-$1M",
    "$1,000,001 - $5,000,000": "$1M-$5M",
    "$5,000,001 - $25,000,000": "$5M-$25M",
    "$25,000,001 - $50,000,000": "$25M-$50M",
    "Over $50,000,000": "$50M+",
}

def amount_midpoint(amount_str):
    """Try to parse a dollar midpoint from whatever Finnhub returns."""
    if not amount_str:
        return 0
    # Direct lookup first
    if amount_str in AMOUNT_MIDPOINTS:
        return AMOUNT_MIDPOINTS[amount_str]
    # Finnhub sometimes returns raw numbers as strings
    try:
        return int(float(str(amount_str).replace(",", "").replace("$", "")))
    except Exception:
        return 0

def amount_label(amount_str):
    if amount_str in AMOUNT_LABELS:
        return AMOUNT_LABELS[amount_str]
    try:
        val = int(float(str(amount_str).replace(",", "").replace("$", "")))
        if val >= 50_000_000:   return "$50M+"
        if val >= 25_000_000:   return "$25M-$50M"
        if val >= 5_000_000:    return "$5M-$25M"
        if val >= 1_000_000:    return "$1M-$5M"
        if val >= 500_000:      return "$500K-$1M"
        if val >= 250_000:      return "$250K-$500K"
        return f"${val:,}"
    except Exception:
        return amount_str or "—"

def fetch_finnhub_trades(days):
    trades = []
    if not FINNHUB_API_KEY:
        print("[Finnhub] no API key set")
        return trades

    date_to   = utcnow().strftime("%Y-%m-%d")
    date_from = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    url = "https://finnhub.io/api/v1/stock/congressional-trading"
    params = {"from": date_from, "to": date_to, "token": FINNHUB_API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print(f"[Finnhub] raw response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")

        # Finnhub returns {"data": [...]} or a direct list
        raw = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            print(f"[Finnhub] unexpected format: {str(data)[:200]}")
            return trades

        for t in raw:
            # Normalize amount — Finnhub may use "amount", "transactionAmount", or "amountRange"
            amt_raw = (
                t.get("amountRange") or
                t.get("transactionAmount") or
                t.get("amount") or ""
            )
            mid = amount_midpoint(amt_raw)
            if mid < MIN_AMOUNT:
                continue

            tx_t
