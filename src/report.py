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

            tx_type = (t.get("transactionType") or t.get("type") or "").lower()
            if "purchase" in tx_type or "buy" in tx_type:
                tx_clean = "buy"
            elif "sale" in tx_type or "sell" in tx_type:
                tx_clean = "sell"
            else:
                tx_clean = tx_type or "—"

            trades.append({
                "name":       t.get("name") or t.get("representative") or "Unknown",
                "chamber":    t.get("chamber") or "—",
                "party":      t.get("party") or "—",
                "state":      t.get("state") or "",
                "ticker":     t.get("symbol") or t.get("ticker") or "—",
                "type":       tx_clean,
                "amount":     amount_label(amt_raw),
                "trade_date": t.get("transactionDate") or t.get("tradeDate") or "—",
                "filed_date": t.get("filingDate") or t.get("filedDate") or "—",
            })

        print(f"[Finnhub] {len(trades)} trades >= ${MIN_AMOUNT:,}")

    except Exception as e:
        print(f"[Finnhub] failed: {e}")

    return trades

def get_trades(days):
    trades = fetch_finnhub_trades(days)
    trades.sort(key=lambda x: x.get("trade_date", ""), reverse=True)
    return trades

def party_badge(party):
    p = (party or "").lower()
    if "rep" in p: return '<span class="badge rep">R</span>'
    if "dem" in p: return '<span class="badge dem">D</span>'
    return '<span class="badge ind">I</span>'

def type_badge(tx):
    if "buy" in (tx or "").lower() or "purchase" in (tx or "").lower():
        return '<span class="badge buy">BUY</span>'
    return '<span class="badge sell">SELL</span>'

def build_html(trades, report_date, lookback):
    buys    = sum(1 for t in trades if "buy" in t["type"])
    sells   = len(trades) - buys
    members = len({t["name"] for t in trades})
    period  = "today" if lookback == 1 else f"last {lookback} days"

    if trades:
        rows = ""
        for i, t in enumerate(trades):
            bg = "#fdfcf8" if i % 2 == 0 else "#ffffff"
            rows += f"""<tr style="background:{bg}">
              <td><div class="name">{t['name']}</div><div class="meta">{t['chamber']} · {t['state']}</div></td>
              <td><span class="ticker">{t['ticker']}</span></td>
              <td>{type_badge(t['type'])}</td>
              <td><span class="amount">{t['amount']}</span></td>
              <td>{party_badge(t['party'])}</td>
              <td><span class="date">{t['trade_date']}</span></td>
              <td><span class="date">{t['filed_date']}</span></td>
            </tr>"""
    else:
        rows = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#aaa">No trades above $250K threshold filed in this period</td></tr>'

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{{margin:0;padding:0;background:#f4f4f0;font-family:Arial,sans-serif;color:#1a1a18}}
.wrap{{max-width:680px;margin:28px auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e0dfd8}}
.hdr{{background:#0f1117;padding:26px 34px}}
.hdr h1{{color:#fff;font-size:19px;font-weight:500;margin:0 0 4px}}
.hdr p{{color:#8a8a82;font-size:11px;margin:0;font-family:monospace}}
.hdr-date{{color:#8a8a82;font-size:11px;font-family:monospace;float:right;text-align:right}}
.stats{{display:flex;background:#f8f7f3;border-bottom:1px solid #e8e7e0}}
.stat{{flex:1;padding:14px 18px;text-align:center;border-right:1px solid #e8e7e0}}
.stat:last-child{{border-right:none}}
.stat-num{{font-size:22px;font-weight:500;font-family:monospace}}
.stat-lbl{{font-size:10px;color:#888880;margin-top:2px;text-transform:uppercase}}
.sec{{padding:22px 34px;border-bottom:1px solid #eeeee8}}
.sec-title{{font-size:10px;font-weight:500;color:#888880;text-transform:uppercase;letter-spacing:.08em;margin:0 0 14px;font-family:monospace}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{text-align:left;font-size:10px;text-transform:uppercase;color:#aaa9a0;font-weight:400;padding:0 8px 9px 0;border-bottom:1px solid #eeeee8;font-family:monospace}}
tbody td{{padding:9px 8px 9px 0;border-bottom:1px solid #f4f4f0;vertical-align:middle}}
tbody tr:last-child td{{border-bottom:none}}
.name{{font-weight:500;font-size:13px}}.meta{{font-size:10px;color:#aaa9a0;font-family:monospace;margin-top:2px}}
.ticker{{font-family:monospace;font-weight:500}}.amount{{font-family:monospace;font-size:11px;color:#5a5a54}}
.date{{font-family:monospace;font-size:11px;color:#aaa9a0}}
.badge{{display:inline-block;font-size:10px;padding:2px 6px;border-radius:3px;font-family:monospace;font-weight:500}}
.buy{{background:#eaf3de;color:#3b6d11}}.sell{{background:#fcebeb;color:#a32d2d}}
.rep{{background:#e6f1fb;color:#185fa5}}.dem{{background:#faece7;color:#993c1d}}.ind{{background:#f1efe8;color:#5f5e5a}}
.notice{{background:#fafaf6;border:1px solid #e8e7e0;border-radius:7px;padding:13px 16px;font-size:11px;color:#888880;line-height:1.6}}
.ftr{{background:#f8f7f3;padding:14px 34px;font-size:10px;color:#aaa9a0;font-family:monospace}}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <span class="hdr-date">{report_date}<br>Morning Edition</span>
    <h1>Congressional Trades Report</h1>
    <p>House &amp; Senate · STOCK Act · {period} · threshold $250K+</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-num">{len(trades)}</div><div class="stat-lbl">Trades</div></div>
    <div class="stat"><div class="stat-num" style="color:#3b6d11">{buys}</div><div class="stat-lbl">Buys</div></div>
    <div class="stat"><div class="stat-num" style="color:#a32d2d">{sells}</div><div class="stat-lbl">Sells</div></div>
    <div class="stat"><div class="stat-num">{members}</div><div class="stat-lbl">Members</div></div>
  </div>
  <div class="sec">
    <div class="sec-title">Disclosed Trades — $250K+ · {period}</div>
    <table>
      <thead><tr>
        <th style="width:26%">Member</th><th style="width:10%">Ticker</th>
        <th style="width:9%">Type</th><th style="width:17%">Amount</th>
        <th style="width:8%">Party</th><th style="width:15%">Trade date</th><th style="width:15%">Filed</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div class="sec">
    <div class="notice"><strong>Note:</strong> STOCK Act requires filing within 45 days of the transaction.
    Amounts are reported ranges, not exact figures. Not investment advice.<br>
    <strong>Source:</strong> Finnhub · STOCK Act filings (Senate eFD, House Clerk)</div>
  </div>
  <div class="ftr">Congressional Trades Report · {RECIPIENT_EMAIL} · finnhub.io · capitoltrades.com</div>
</div></body></html>"""

def send_email(subject, html_body):
    if not SENDER_EMAIL or not GMAIL_APP_PW:
        raise EnvironmentError("Missing SENDER_EMAIL or GMAIL_APP_PASSWORD env vars.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_APP_PW)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
    print(f"[email] sent to {RECIPIENT_EMAIL}")

def main():
    today = utcnow().strftime("%B %d, %Y")
    print(f"[start] {today} · lookback={LOOKBACK_DAYS}d · threshold=${MIN_AMOUNT:,}")
    trades = get_trades(LOOKBACK_DAYS)
    print(f"[result] {len(trades)} qualifying trades")
    html = build_html(trades, today, LOOKBACK_DAYS)
    subject = f"Congressional Trades $250K+ | {utcnow().strftime('%b %d, %Y')}"
    send_email(subject, html)
    print("[done]")

if __name__ == "__main__":
    main()
