"""Build markets.json for the ZenQuant site from official end-of-day exchange data.

    python fetch_markets.py

Run once a day after both markets close (e.g. 07:00 IST, after the US close).
Sources (end of day, not real time):
  * NIFTY 50 index  - NSE archives, daily index close file (ind_close_all_DDMMYYYY.csv)
  * NIFTY 50 stocks - NSE archives, constituent list + daily bhavcopy (close vs previous close)
  * Nasdaq-100      - Nasdaq (api.nasdaq.com): index history + the 100 member stocks
  * India headlines - Google News RSS (optional; skipped if unavailable)
"""
import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36", "Accept": "*/*"}
IST = timezone(timedelta(hours=5, minutes=30))
SESSIONS = 22  # ~1 month of trading days for the trend line
TOP_N = 5


def get(url, timeout=30, tries=4):
    """Fetch a URL, retrying temporary failures (exchanges sometimes refuse or time out)."""
    import time
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
        time.sleep(5 * (attempt + 1))


def num(s):
    return float(str(s).replace(",", "").replace("$", "").replace("%", "").strip())


def pct(a, b):
    return round((a / b - 1) * 100, 2)


def summary(name, market, currency, rows):
    """rows: oldest -> newest list of dicts with date/open/close (at least 2)."""
    last, prev = rows[-1], rows[-2]
    change = last["close"] - prev["close"]
    return {
        "name": name, "market": market, "currency": currency, "date": last["date"], "status": "closed",
        "open": round(last["open"], 2), "close": round(last["close"], 2), "prevClose": round(prev["close"], 2),
        "change": round(change, 2), "changePct": pct(last["close"], prev["close"]),
        "history": [{"d": r["date"], "c": round(r["close"], 2)} for r in rows[-SESSIONS:]],
        "monthPct": pct(last["close"], rows[-SESSIONS]["close"]) if len(rows) >= SESSIONS else None,
    }


def movers(stocks):
    """stocks: list of {symbol,name,close,changePct}. Returns gainers, losers and breadth."""
    ranked = sorted(stocks, key=lambda s: s["changePct"], reverse=True)
    up = sum(1 for s in stocks if s["changePct"] > 0)
    down = sum(1 for s in stocks if s["changePct"] < 0)
    return {"gainers": ranked[:TOP_N], "losers": ranked[::-1][:TOP_N],
            "breadth": {"up": up, "down": down, "unchanged": len(stocks) - up - down, "total": len(stocks)}}


# ---------------------------------------------------------------- India (NSE)
def nse_index_day(d):
    url = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
    try:
        text = get(url).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:  # no file for that day (weekend / holiday / not yet published)
            return None
        raise  # blocked or server error: let the caller keep yesterday's data
    for row in csv.DictReader(io.StringIO(text)):
        if row["Index Name"].strip().lower() == "nifty 50":
            return {"date": d.isoformat(), "open": num(row["Open Index Value"]), "close": num(row["Closing Index Value"])}
    return None


class MarketOpen(Exception):
    """The exchange is trading right now, so today's numbers are not final yet."""


def trading_now(region, now=None):
    """True while prices for that market can still move (Mon-Fri).
    India: NSE session 09:15-15:30 IST = 03:45-10:00 UTC.
    US: Nasdaq stock prices also move in pre-market (from 04:00 New York) and
    after-hours (to 20:00 New York), i.e. 08:00-01:00 UTC across summer and winter.
    Shifting the clock back 2 hours turns that into 06:00-23:00 on the trading day."""
    now = now or datetime.now(timezone.utc)
    if region == "US":
        now -= timedelta(hours=2)
        start, end = 6 * 60, 23 * 60
    else:
        start, end = 3 * 60 + 45, 10 * 60
    if now.weekday() >= 5:
        return False
    return start <= now.hour * 60 + now.minute < end


def nifty():
    if trading_now("India"):
        raise MarketOpen("NSE is trading; keeping the last close")
    rows, d = [], datetime.now(IST).date()
    for _ in range(50):  # walk back over weekends/holidays until we have ~1 month
        if d.weekday() < 5:
            r = nse_index_day(d)
            if r:
                rows.append(r)
                if len(rows) >= SESSIONS:
                    break
        d -= timedelta(days=1)
    rows.reverse()
    if len(rows) < 2:
        raise RuntimeError(f"NSE returned only {len(rows)} trading day(s)")
    idx = summary("NIFTY 50", "NSE · India", "INR", rows)

    members = {r["Symbol"].strip(): r["Company Name"].strip() for r in csv.DictReader(io.StringIO(
        get("https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv").decode("utf-8", "replace")))}
    day = date.fromisoformat(idx["date"])
    z = zipfile.ZipFile(io.BytesIO(get(
        f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip")))
    stocks = []
    for row in csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "replace"))):
        sym = row["TckrSymb"].strip()
        if sym in members and row["SctySrs"].strip() == "EQ":
            close, prev = num(row["ClsPric"]), num(row["PrvsClsgPric"])
            stocks.append({"symbol": sym, "name": members[sym].replace(" Ltd.", "").replace(" Limited", ""),
                           "close": round(close, 2), "changePct": pct(close, prev)})
    idx.update(movers(stocks))
    return idx


# ------------------------------------------------------------- US (Nasdaq-100)
def nasdaq100():
    if trading_now("US"):
        raise MarketOpen("Nasdaq is trading; keeping the last close")
    end = datetime.now(timezone.utc).date()
    q = urllib.parse.urlencode({"assetclass": "index", "fromdate": (end - timedelta(days=50)).isoformat(),
                                "todate": end.isoformat(), "limit": 60})
    hist = json.loads(get(f"https://api.nasdaq.com/api/quote/NDX/historical?{q}"))["data"]["tradesTable"]["rows"]
    rows = [{"date": datetime.strptime(r["date"], "%m/%d/%Y").date().isoformat(),
             "open": num(r["open"]), "close": num(r["close"])} for r in hist]
    rows.sort(key=lambda r: r["date"])
    idx = summary("Nasdaq-100", "Nasdaq · US", "USD", rows)

    lst = json.loads(get("https://api.nasdaq.com/api/quote/list-type/nasdaq100"))["data"]["data"]["rows"]
    stocks = []
    for r in lst:
        try:
            name = r["companyName"]
            for cut in (" Common Stock", " Class A", " Class C", " American Depositary Shares", " Ordinary Shares"):
                name = name.split(cut)[0]
            stocks.append({"symbol": r["symbol"], "name": name.rstrip(", "), "close": num(r["lastSalePrice"]),
                           "changePct": num(r["percentageChange"])})
        except (ValueError, KeyError):
            continue
    idx.update(movers(stocks))
    return idx


# ------------------------------------------------------------------ headlines
def india_news(limit=6):
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    q = urllib.parse.quote("(Sensex OR Nifty OR NSE) stock market when:2d")
    root = ET.fromstring(get(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"))
    items, seen = [], set()
    for it in root.iter("item"):
        source = (it.findtext("source") or "").strip()
        title = (it.findtext("title") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        items.append({"title": title, "source": source, "url": it.findtext("link"),
                      "time": parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat(timespec="minutes")})
    items.sort(key=lambda x: x["time"], reverse=True)
    return items[:limit]


# ------------------------------------------------------------- latest Short
YT_CHANNEL = "UCiiXsIFONz3DwzDcqgBjQdQ"  # youtube.com/@NeerajPriyadarshi


def youtube_latest_short():
    """Newest upload from the channel's public feed that is a Short (vertical video)."""
    import re
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    root = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={YT_CHANNEL}"))
    for e in root.findall("a:entry", ns):
        vid = e.findtext("yt:videoId", namespaces=ns)
        title = (e.findtext("a:title", namespaces=ns) or "").strip()
        # A Short's /shorts/ URL answers 200; a regular video redirects to /watch
        req = urllib.request.Request(f"https://www.youtube.com/shorts/{vid}", headers=UA, method="HEAD")
        opener = urllib.request.build_opener(type("NoRedirect", (urllib.request.HTTPRedirectHandler,),
                                                  {"redirect_request": lambda *a, **k: None}))
        try:
            if opener.open(req, timeout=20).status != 200:
                continue
        except urllib.error.HTTPError:
            continue
        return {"id": vid, "title": re.sub(r"\s*#shorts\b", "", title, flags=re.I).strip(),
                "published": (e.findtext("a:published", namespaces=ns) or "")[:10]}
    return None


if __name__ == "__main__":
    import sys
    try:  # last good data, used for any market whose source fails today
        with open("markets.json", encoding="utf-8") as f:
            last = json.load(f)
    except (OSError, ValueError):
        last = {}
    previous = {m.get("region"): m for m in last.get("markets", [])}
    markets, failed = [], []
    for region, fetch in (("India", nifty), ("US", nasdaq100)):
        try:
            markets.append(dict(fetch(), region=region))
        except MarketOpen as e:
            print(f"{region}: {e}")
            if region in previous:
                markets.append(previous[region])
            continue
        except Exception as e:
            failed.append(region)
            print(f"::warning::{region} fetch failed ({type(e).__name__}: {e}); keeping last good data")
            if region in previous:
                markets.append(previous[region])
    if len(failed) == 2 or len(markets) < 2:
        sys.exit("Both markets failed today; the site keeps its last data" if len(failed) == 2
                 else "A market is unavailable and there is no previous data for it")
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "source": "NSE and Nasdaq official end-of-day data",
            "markets": markets}
    try:
        data["news"] = {"source": "Google News", "items": india_news()}
    except Exception as e:  # headlines are optional
        print("news skipped:", e)
    try:  # newest YouTube Short for the "From our feed" section (optional)
        data["short"] = youtube_latest_short() or last.get("short")
        print("short:", data["short"])
    except Exception as e:
        print("short skipped:", e)
        if last.get("short"):
            data["short"] = last["short"]  # keep showing the last known Short
    with open("markets.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Same data as a script, so the page also works when opened straight from disk (file://)
    with open("markets.js", "w", encoding="utf-8") as f:
        f.write("window.ZQ_MARKETS = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";\n")
    for m in data["markets"]:
        b = m["breadth"]
        print(f'{m["name"]:<11} {m["date"]} open {m["open"]:>10,.2f} close {m["close"]:>10,.2f} {m["changePct"]:+.2f}%  '
              f'breadth {b["up"]}/{b["total"]} up  top {m["gainers"][0]["symbol"]} {m["gainers"][0]["changePct"]:+.2f}%  '
              f'bottom {m["losers"][0]["symbol"]} {m["losers"][0]["changePct"]:+.2f}%')
