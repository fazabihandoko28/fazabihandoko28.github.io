import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
OUT = Path("docs/dashboard/swing/news-catalyst.json")

INTERESTING_STATES = {
    "EARLY_CONFIRMED_BUY", "SWING_BUY", "RADAR_ARMED", "RADAR_PRE_ALERT",
    "RADAR_WATCH", "SETUP_READY", "PRE_ALERT", "EARLY_WATCH",
    "SWING_CONFIRMING", "SWING_WATCH"
}

POSITIVE_CAUSAL = (
    "naik karena", "melonjak karena", "menguat karena", "melesat karena",
    "naik usai", "melonjak usai", "menguat usai", "melesat usai",
    "naik setelah", "melonjak setelah", "menguat setelah", "rally setelah",
    "soars after", "rises after", "jumps after", "gains after", "surges after"
)
NEGATIVE_CAUSAL = (
    "turun karena", "anjlok karena", "melemah karena", "tertekan karena",
    "turun usai", "anjlok usai", "melemah usai", "tertekan usai",
    "turun setelah", "anjlok setelah", "melemah setelah",
    "falls after", "drops after", "slumps after", "slides after", "tumbles after"
)
MATERIAL = (
    "kontrak", "dividen", "laba", "rugi", "akuisisi", "merger", "rights issue",
    "buyback", "tender", "regulasi", "izin", "ekspor", "impor", "tarif",
    "produksi", "penjualan", "guidance", "suspensi", "default", "restrukturisasi",
    "earnings", "profit", "loss", "contract", "acquisition", "merger", "dividend",
    "regulation", "license", "export", "import", "sanction", "rate cut", "rate hike",
    "fed", "bi rate", "rupiah", "oil", "coal", "nickel", "gold"
)


def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def risk_object(row):
    raw = row.get("risk_validation")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def canonical_score(row):
    try:
        return float(risk_object(row).get("canonical_rank_score") or 0)
    except Exception:
        return 0.0


def selected_candidates():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase secrets missing")
    url = f"{SUPABASE_URL}/rest/v1/hanz_swing_signal_monitor?select=*&limit=250"
    r = requests.get(url, headers=headers(), timeout=25)
    r.raise_for_status()
    rows = [x for x in r.json() if str(x.get("state") or "").upper() in INTERESTING_STATES]
    rows.sort(key=lambda x: (-canonical_score(x), str(x.get("ticker") or "")))
    return rows[:5]


def google_news(query):
    url = (
        "https://news.google.com/rss/search?q=" + quote_plus(query) +
        "&hl=id&gl=ID&ceid=ID:id"
    )
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 HANZ-News-Catalyst/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for item in root.findall(".//item")[:20]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
        out.append({"title": title, "url": link, "source": source, "published_at": dt})
    return out


def direction(title):
    low = title.lower()
    if any(k in low for k in POSITIVE_CAUSAL):
        return "POSITIVE"
    if any(k in low for k in NEGATIVE_CAUSAL):
        return "NEGATIVE"
    return None


def confidence_score(title, ticker=None, aliases=None, ihsg=False, published_at=None):
    low = title.lower()
    score = 0
    if ihsg:
        if "ihsg" in low or "jakarta composite" in low:
            score += 3
    else:
        if ticker and re.search(rf"\b{re.escape(ticker.lower())}\b", low):
            score += 4
        aliases = [a for a in (aliases or []) if a]
        if any(str(a).lower() in low for a in aliases if len(str(a)) >= 4):
            score += 3
    if direction(title):
        score += 3
    if any(k in low for k in MATERIAL):
        score += 2
    if published_at:
        age = datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)
        if age <= timedelta(hours=18):
            score += 2
        elif age <= timedelta(hours=36):
            score += 1
    return score


def best_stock_news(row):
    ticker = str(row.get("ticker") or "").upper().replace(".JK", "")
    aliases = [row.get("company_name"), row.get("issuer_name"), row.get("name")]
    query = f'"{ticker}" saham Indonesia OR "{ticker}" emiten when:2d'
    items = google_news(query)
    scored = []
    for item in items:
        d = direction(item["title"])
        if not d:
            continue
        s = confidence_score(item["title"], ticker=ticker, aliases=aliases, published_at=item["published_at"])
        if s >= 8:
            scored.append((s, item, d))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]["published_at"] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    s, item, d = scored[0]
    return {
        "scope": "STOCK",
        "ticker": ticker,
        "direction": d,
        "confidence": "HIGH",
        "score": s,
        "headline": item["title"],
        "source": item["source"],
        "url": item["url"],
        "published_at": item["published_at"].isoformat() if item["published_at"] else None,
        "note": "Likely news-driven: causal wording + direct ticker/company relevance + material-event filter. This is an evidence layer, not a BUY/SELL trigger."
    }


def best_ihsg_news():
    queries = [
        'IHSG naik karena OR IHSG menguat karena OR IHSG melonjak karena when:2d',
        'IHSG turun karena OR IHSG melemah karena OR IHSG anjlok karena when:2d',
        'IHSG naik usai OR IHSG turun usai OR IHSG menguat setelah OR IHSG melemah setelah when:2d'
    ]
    items = []
    for q in queries:
        try:
            items.extend(google_news(q))
        except Exception:
            pass
    seen = set()
    scored = []
    for item in items:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        d = direction(item["title"])
        if not d:
            continue
        s = confidence_score(item["title"], ihsg=True, published_at=item["published_at"])
        if s >= 7:
            scored.append((s, item, d))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]["published_at"] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    s, item, d = scored[0]
    return {
        "scope": "IHSG",
        "direction": d,
        "confidence": "HIGH",
        "score": s,
        "headline": item["title"],
        "source": item["source"],
        "url": item["url"],
        "published_at": item["published_at"].isoformat() if item["published_at"] else None,
        "note": "Likely index news catalyst based on explicit causal headline language. Hidden when causal evidence is weak."
    }


def main():
    candidates = selected_candidates()
    catalysts = []
    for row in candidates:
        try:
            hit = best_stock_news(row)
            if hit:
                catalysts.append(hit)
        except Exception as exc:
            print("stock news error", row.get("ticker"), type(exc).__name__, exc)

    try:
        ihsg = best_ihsg_news()
        if ihsg:
            catalysts.append(ihsg)
    except Exception as exc:
        print("IHSG news error", type(exc).__name__, exc)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": "HIGH_CONFIDENCE_CAUSAL_ONLY",
        "selected_tickers": [str(r.get("ticker") or "") for r in candidates],
        "catalysts": catalysts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected": len(candidates), "shown": len(catalysts)}))


if __name__ == "__main__":
    main()
