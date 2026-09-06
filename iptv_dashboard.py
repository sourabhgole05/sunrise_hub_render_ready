#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  SUNRISE HUB v11  =  Radio + TV + NEWS + MARKETS + BOOKS
#  All free sources: iptv-org / radio-browser / epg.pw /
#  GoogleNews+NDTV+TOI+Hindu+ET+MC RSS / Yahoo Finance /
#  Gutendex (Project Gutenberg)
#  Self-test:  python iptv_dashboard.py --selftest
# ============================================================
import html as H, json, os, re, shutil, socket, subprocess, sys, threading, time
import traceback, base64, io, calendar, gzip
import urllib.request, urllib.error, webbrowser
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION   = "11.0"
CACHE_TTL = 1800
IS_CLOUD  = os.environ.get("RENDER", "").lower() == "true"
SRV, PORT = None, int(os.environ.get("PORT", "8765")) if IS_CLOUD else 8765
LAN_IP, TS_IP = "", ""

BASE_PLAYLISTS = {
    "in":    {"name": "&#x1F1EE;&#x1F1F3; All India",
              "url": "https://iptv-org.github.io/iptv/countries/in.m3u"},
    "hin":   {"name": "&#x1F5E3; Hindi",
              "url": "https://iptv-org.github.io/iptv/languages/hin.m3u"},
    "news":  {"name": "&#x1F4F0; News TV",
              "url": "https://iptv-org.github.io/iptv/categories/news.m3u"},
    "world": {"name": "&#x1F30D; Worldwide",
              "url": "https://iptv-org.github.io/iptv/index.m3u"},
}
PODCAST_FEEDS = [
    ("BBC World Service", "https://podcasts.files.bbci.co.uk/p02nq0gn.rss"),
    ("NPR News Now", "https://feeds.npr.org/500005/podcast.xml"),
    ("The Hindu Podcast", "https://www.thehindu.com/podcast/feeder/default.rss"),
]
PLAYLISTS = {}
RADIO_SOURCES = {
    "rin":  {"name": "&#x1F399; Radio India",
             "path": "/json/stations/search?countrycode=IN&hidebroken=true"
                     "&order=clickcount&reverse=true&limit=500"},
    "rtop": {"name": "&#x1F399; Radio World Top",
             "path": "/json/stations/search?hidebroken=true"
                     "&order=clickcount&reverse=true&limit=500"},
}
RB_MIRRORS = ["de1", "de2", "fi1", "nl1", "at1", "all"]
ALLSRC = {}

CUSTOM_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                           "custom_playlists.json")
CACHE = {}
EXTINF_RE = re.compile(r"^#EXTINF:?-?\d*[^,]*,(.*)$")
ATTR_RE   = re.compile(r'([\w-]+)="([^"]*)"')
SAFE_SCHEMES = ("http", "https", "rtsp", "rtp", "udp", "mms")
NORM_RE     = re.compile(r"[^a-z0-9]+")

def log(m):
    try: print(m)
    except Exception: pass

def norm(s): return NORM_RE.sub("", (s or "").lower())

# ---------------- custom playlists ----------------
def load_custom():
    try:
        with open(CUSTOM_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_custom(d):
    try:
        with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=True, indent=1)
    except Exception as e: log("[!] custom save failed: %s" % e)

def rebuild_sources():
    PLAYLISTS.clear(); PLAYLISTS.update(BASE_PLAYLISTS)
    for k, v in load_custom().items(): PLAYLISTS[k] = v
    ALLSRC.clear(); ALLSRC.update(PLAYLISTS); ALLSRC.update(RADIO_SOURCES)

rebuild_sources()

# ---------------- infra ----------------
def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except Exception: return ""
    finally: s.close()

def get_tailscale_ip():
    cands = [shutil.which("tailscale"),
             r"C:\Program Files\Tailscale\tailscale.exe",
             r"C:\Program Files (x86)\Tailscale\tailscale.exe"]
    for exe in cands:
        if not exe or not os.path.exists(exe): continue
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True,
                                 text=True, timeout=6)
            ips = [l.strip() for l in (out.stdout or "").splitlines()
                   if l.strip()]
            if ips and ips[0].startswith("100."): return ips[0]
        except Exception: pass
    return ""

def find_vlc():
    p = os.environ.get("VLC_PATH")
    if p and os.path.exists(p): return p
    p = shutil.which("vlc")
    if p: return p
    for c in (r"C:\Program Files\VideoLAN\VLC\vlc.exe",
              r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
              "/Applications/VLC.app/Contents/MacOS/VLC", "/usr/bin/vlc"):
        if os.path.exists(c): return c
    return None

VLC = find_vlc()

# ---------------- TV playlists ----------------
def parse_m3u(text):
    chans, pend = [], None
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln: continue
        if ln.startswith("#EXTINF"):
            m = EXTINF_RE.match(ln)
            a = dict(ATTR_RE.findall(ln))
            pend = {"name":  m.group(1).strip() if m else "Unknown",
                    "id":    a.get("tvg-id", ""),
                    "logo":  a.get("tvg-logo", ""),
                    "group": a.get("group-title", ""),
                    "lang":  a.get("tvg-language", "")[:40]}
        elif not ln.startswith("#") and pend:
            pend["url"] = ln; chans.append(pend); pend = None
    return chans

def load_playlist(key):
    c = CACHE.get(key)
    if c and time.time() - c["t"] < CACHE_TTL: return c["chans"]
    req = urllib.request.Request(PLAYLISTS[key]["url"],
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        text = r.read().decode("utf-8", errors="replace")
    chans = parse_m3u(text)
    CACHE[key] = {"t": time.time(), "chans": chans}
    return chans

def load_radio(key):
    c = CACHE.get(key)
    if c and time.time() - c["t"] < CACHE_TTL: return c["chans"]
    src, last = RADIO_SOURCES[key], None
    for mir in RB_MIRRORS:
        try:
            url = "https://%s.api.radio-browser.info%s" % (mir, src["path"])
            req = urllib.request.Request(url,
                    headers={"User-Agent": "SunriseHub/11.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            chans = []
            for st in data:
                tags = [t.strip() for t in (st.get("tags") or "").split(",")
                        if t.strip()]
                u = st.get("url_resolved") or st.get("url") or ""
                if not u: continue
                chans.append({
                    "name":  (st.get("name") or "?").strip(),
                    "id":    "",
                    "logo":  st.get("favicon") or "",
                    "group": tags[0].title()[:22] if tags else "Radio",
                    "lang":  ((st.get("language") or "") + " " +
                              str(st.get("bitrate") or "") + "k").strip()[:24],
                    "url":   u})
            CACHE[key] = {"t": time.time(), "chans": chans}
            return chans
        except Exception as e:
            last = e
    raise RuntimeError("radio api unreachable (%s)" % last)

def get_channels(key):
    if key in PLAYLISTS:     return load_playlist(key)
    if key in RADIO_SOURCES: return load_radio(key)
    raise KeyError(key)

def build_m3u(chans):
    out = ["#EXTM3U"]
    for c in chans:
        logo = str(c.get("logo", "")).replace('"', "'")
        grp  = str(c.get("group", "")).replace('"', "'")
        name = str(c.get("name", "?")).replace('"', "'")
        ex = ""
        if logo or grp:
            ex = ' tvg-logo="%s" group-title="%s"' % (logo, grp)
        out.append("#EXTINF:-1%s,%s" % (ex, name))
        out.append(str(c.get("url", "")))
    return "\n".join(out) + "\n"

# ---------------- EPG (FIXED: gzip decompression) ----------------
EPG_FILES = {"in":  "https://epg.pw/xmltv/epg_IN.xml.gz",
             "hin": "https://epg.pw/xmltv/epg_IN.xml.gz",
             "news":"https://epg.pw/xmltv/epg_IN.xml.gz"}
EPG_LOCK = threading.Lock()
EPG_CACHE, EPG_STATE = {}, {}

def _xmltv_epoch(v):
    m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?"
                 r"(?:\s*([+-])(\d{2})(\d{2}))?", v or "")
    if not m: return 0
    Y, Mo, D, Hh, Mi, S, sign, oh, om = m.groups()
    S = S or "00"
    ep = calendar.timegm((int(Y), int(Mo), int(D), int(Hh), int(Mi), int(S)))
    if sign: ep += (-1 if sign == "+" else 1) * (int(oh)*3600 + int(om)*60)
    return ep

def epg_state(k):
    return EPG_STATE.get(k, "idle") if k in EPG_FILES else "unsupported"

def epg_ensure_async(k):
    if k not in EPG_FILES: return
    with EPG_LOCK:
        if EPG_STATE.get(k, "idle") in ("loading", "ready"): return
        EPG_STATE[k] = "loading"
    threading.Thread(target=_epg_load, args=(k,), daemon=True).start()

def _epg_load(key):
    try:
        raw = None
        urls = [EPG_FILES[key], EPG_FILES[key].replace(".xml.gz", ".xml")]
        last = None
        for url in urls:
            try:
                req = urllib.request.Request(url,
                    headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"})
                with urllib.request.urlopen(req, timeout=45) as r:
                    raw = r.read()
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                if b"<tv" not in raw[:20000]:
                    raise RuntimeError("EPG response was not XML")
                break
            except Exception as e:
                last = e
                raw = None
        if raw is None:
            raise RuntimeError("EPG source unavailable: %s" % last)
        now, horizon = int(time.time()), int(time.time()) + 8*3600
        names, progs = {}, {}
        for ev, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "channel":
                cid = (el.get("id") or "").lower()
                for dn in el.findall("{*}display-name"):
                    n = norm(dn.text or "")
                    if n and cid:
                        names.setdefault(cid, n); names.setdefault(n, n)
                el.clear()
            elif tag == "programme":
                s, e = _xmltv_epoch(el.get("start")), _xmltv_epoch(el.get("stop"))
                if e > now and s < horizon and e > s:
                    t_el = el.find("{*}title")
                    ttl = (t_el.text or "")[:90] if t_el is not None else ""
                    progs.setdefault((el.get("channel") or "").lower(),
                                     []).append({"s": s, "e": e, "t": ttl})
                el.clear()
        data = {}
        for cid, lst in progs.items():
            lst.sort(key=lambda x: x["s"]); rec = {"p": lst}
            data[cid] = rec
            nm = names.get(cid)
            if nm: data[nm] = rec
            base = cid.split(".")[0]
            if "." in cid and base not in data: data[base] = rec
        EPG_CACHE[key] = {"t": time.time(), "data": data}
        with EPG_LOCK: EPG_STATE[key] = "ready"
        log("[i] EPG '%s': %d indexed" % (key, len(data)))
    except Exception as e:
        with EPG_LOCK: EPG_STATE[key] = "error: %s" % str(e)[:70]
        log("[!] EPG failed: %s" % e)

def epg_snapshot(key):
    c = EPG_CACHE.get(key)
    if not c: return {}
    now, out = int(time.time()), {}
    for tok, rec in c["data"].items():
        np_, nx = None, None
        for p in rec["p"]:
            if p["s"] <= now < p["e"]: np_ = p
            elif p["s"] > now: nx = p; break
        if np_ or nx:
            out[tok] = {"n": np_ and {"t": np_["t"], "e": np_["e"]} or None,
                        "x": nx and {"t": nx["t"], "s": nx["s"]} or None}
    return out

# ---------------- NEWS (free public RSS) ----------------
GN = "https://news.google.com/rss"
NEWS_FEEDS = {
    "top":      [("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
                 ("Times of India",
                  "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
                 ("Google News", GN + "?hl=en-IN&gl=IN&ceid=IN:en")],
    "india":    [("NDTV", "https://feeds.feedburner.com/ndtvnews-india-news"),
                 ("The Hindu",
                  "https://www.thehindu.com/news/national/feeder/default.rss"),
                 ("Google News",
                  GN + "/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en")],
    "business": [("Moneycontrol",
                  "https://www.moneycontrol.com/rss/business.xml"),
                 ("The Hindu",
                  "https://www.thehindu.com/business/feeder/default.rss"),
                 ("Google News",
                  GN + "/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en")],
    "markets":  [("ET Markets",
                  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
                 ("Moneycontrol",
                  "https://www.moneycontrol.com/rss/business.xml")],
    "tech":     [("Google News",
                  GN + "/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en"),
                 ("Times of India",
                  "https://timesofindia.indiatimes.com/rssfeeds/66949542.cms")],
    "sports":   [("Google News",
                  GN + "/headlines/section/topic/SPORTS?hl=en-IN&gl=IN&ceid=IN:en"),
                 ("The Hindu",
                  "https://www.thehindu.com/sport/feeder/default.rss")],
    "world":    [("NDTV", "https://feeds.feedburner.com/ndtvnews-world-news"),
                 ("Google News",
                  GN + "/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en")],
    "hindi":    [("BBC Hindi", "https://feeds.bbci.co.uk/hindi/rss.xml"),
                 ("Google News", GN + "?hl=hi&gl=IN&ceid=IN:hi")],
}
NEWS_CACHE, NEWS_LOCK = {}, threading.Lock()

def _parse_pub(*vals):
    for v in vals:
        if not v: continue
        try:
            dt = parsedate_to_datetime(v)
            if dt: return int(dt.timestamp())
        except Exception: pass
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception: continue
    return 0

def _feed_items(src, url, out):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
        root = ET.fromstring(raw)
        for it in root.iter():
            tg = it.tag.rsplit("}", 1)[-1]
            if tg not in ("item", "entry"): continue
            def gt(t):
                x = it.find(t)
                return (x.text or "").strip() if x is not None else ""
            title = gt("title")
            if not title: continue
            link = ""
            le = it.find("link")
            if le is not None:
                link = (le.get("href") or (le.text or "")).strip()
            if not link: link = gt("guid")
            desc = gt("description") or gt("summary") or gt("content")
            img = ""
            audio = ""
            enc = it.find("enclosure")
            if enc is not None:
                if (enc.get("type") or "").startswith("image"):
                    img = enc.get("url") or ""
                elif (enc.get("type") or "").startswith("audio"):
                    audio = enc.get("url") or ""
            if not img:
                m = re.search(r'<img[^>]+src=["\']([^"\']+)', desc or "")
                if m: img = m.group(1)
            snip = H.unescape(re.sub(r"<[^>]+>", " ", desc or ""))
            snip = re.sub(r"\s+", " ", snip).strip()[:200]
            out.append({"t": title[:140], "l": link, "s": src, "d": img,
                        "audio": audio,
                        "b": snip,
                        "pub": _parse_pub(
                            gt("pubDate"),
                            gt("{http://purl.org/dc/elements/1.1/}date"),
                            gt("published"), gt("updated"))})
    except Exception:
        pass

def fetch_news(cat):
    if cat not in NEWS_FEEDS: cat = "top"
    c = NEWS_CACHE.get(cat)
    if c and time.time() - c["t"] < 900: return c["items"]
    with NEWS_LOCK:                              # QA fix #5: race guard
        c = NEWS_CACHE.get(cat)
        if c and time.time() - c["t"] < 900: return c["items"]
        items, ths = [], []
        for src, url in NEWS_FEEDS[cat]:
            t = threading.Thread(target=_feed_items, args=(src, url, items),
                                 daemon=True)
            t.start(); ths.append(t)
        for t in ths: t.join(timeout=10)
        seen, uniq = set(), []
        for it in sorted(items, key=lambda x: x["pub"], reverse=True):
            k = norm(it["t"])[:60]
            if k in seen: continue
            seen.add(k); uniq.append(it)
            if len(uniq) >= 60: break
        NEWS_CACHE[cat] = {"t": time.time(), "items": uniq}
        return uniq

def fetch_podcasts():
    items, threads = [], []
    for src, url in PODCAST_FEEDS:
        t = threading.Thread(target=_feed_items, args=(src, url, items),
                             daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=10)
    seen, out = set(), []
    for item in sorted(items, key=lambda x: x["pub"], reverse=True):
        key = norm(item["t"])[:70]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= 40:
            break
    return out

# ---------------- MARKETS (Yahoo Finance public chart API) ----------------
YF_HOSTS = ("query1", "query2")

def yf_chart(sym, range_="1d", interval="5m"):
    last = None
    for h in YF_HOSTS:
        try:
            u = ("https://%s.finance.yahoo.com/v8/finance/chart/%s"
                 "?range=%s&interval=%s"
                 % (h, quote(sym, safe=""), range_, interval))
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                j = json.loads(r.read().decode("utf-8", errors="replace"))
            res = (j.get("chart") or {}).get("result") or []
            if not res: raise RuntimeError("empty")
            res = res[0]
            meta = res.get("meta") or {}
            q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
            cl = [c for c in (q.get("close") or []) if c is not None]  # QA fix #4
            return {"sym": sym,
                    "name": meta.get("shortName") or meta.get("longName") or sym,
                    "price": meta.get("regularMarketPrice"),
                    "prev": meta.get("previousClose")
                            or meta.get("chartPreviousClose"),
                    "cur": meta.get("currency") or "",
                    "exchangeName": meta.get("exchangeName") or
                                    meta.get("fullExchangeName") or "",
                    "state": meta.get("marketState") or "",
                    "ts": (res.get("timestamp") or [])[-400:],
                    "cl": cl[-400:]}
        except Exception as e:
            last = e
    raise RuntimeError("yahoo failed %s (%s)" % (sym, last))

# ---------------- BOOKS (Project Gutenberg via Gutendex) ----------------
def gutendex(params):
    q = "&".join("%s=%s" % (k, quote(str(v), safe=""))
                 for k, v in params.items())
    req = urllib.request.Request("https://gutendex.com/books?" + q,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))

BOOK_TXT, BOOK_TXT_ORDER = {}, []               # QA fix #6: capped cache

def book_text(bid):
    if bid in BOOK_TXT: return BOOK_TXT[bid]
    j = gutendex({"ids": bid})
    res = j.get("results") or []
    if not res: raise RuntimeError("book not found")
    fmts = res[0].get("formats") or {}
    cand = [k for k in fmts if "text/plain" in k]
    if not cand: raise RuntimeError("no plain-text edition for this book")
    cand.sort(key=lambda k: (0 if "utf-8" in k.lower() else 1))
    req = urllib.request.Request(fmts[cand[0]],
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        txt = r.read().decode("utf-8", errors="replace")
    m1 = re.search(r"\*\*\*\s*START OF (THE )?PROJECT GUTENBERG.*?\*\*\*",
                   txt, re.I)
    m2 = re.search(r"\*\*\*\s*END OF (THE )?PROJECT GUTENBERG", txt, re.I)
    if m1: txt = txt[m1.end():]
    if m2: txt = txt[:m2.start()]
    BOOK_TXT[bid] = txt
    BOOK_TXT_ORDER.append(bid)
    while len(BOOK_TXT_ORDER) > 3:
        BOOK_TXT.pop(BOOK_TXT_ORDER.pop(0), None)
    return txt

# ---------------- misc ----------------
def qr_datauri(url):
    try:
        import qrcode
        buf = io.BytesIO()
        qrcode.make(url).save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

def qr_img_tag(url):
    src = qr_datauri(url)
    if src: return ('<img src="%s" width="170" height="170">' % src, "local")
    return ('<img src="https://api.qrserver.com/v1/create-qr-code/'
            '?size=170x170&amp;data=%s" width="170" height="170">'
            % quote(url, safe=""), "web fallback")

def launch(url):
    if not VLC: return False, "VLC not found on PC."
    try:
        subprocess.Popen([VLC, "--one-instance", "--no-video-title-show", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Launched on PC in VLC"
    except Exception as e:
        return False, "Could not start VLC: %s" % e

def check_stream(url):
    if urlparse(url).scheme not in ("http", "https"):
        return {"ok": None, "code": 0, "ms": 0}
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                               "Range": "bytes=0-0"})
    ms = lambda: int((time.time() - t0) * 1000)
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            code = r.status
        return {"ok": 200 <= code < 400, "code": code, "ms": ms()}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 405, 451):
            return {"ok": None, "code": e.code, "ms": ms()}
        return {"ok": False, "code": e.code, "ms": ms()}
    except Exception:
        return {"ok": False, "code": 0, "ms": ms()}

def esc(s): return H.escape(str(s or ""), quote=True)
def MOBILE_UA(ua): return bool(re.search(r"Android|iPhone|iPad|iPod|Mobile",
                                         ua or ""))

SHELL = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,
 maximum-scale=1,user-scalable=no">
<title>Sunrise Hub</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%93%BA%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#fffdf7;--card:#ffffff;--txt:#1e293b;--mut:#7c8699;
 --acc:#f97316;--acc2:#0ea5e9;--line:#ece5d3;--chip:#ffffff;--hov:#fff3e4;
 --sh:0 2px 10px rgba(120,100,60,.08)}
html[data-theme=dark]{--bg:#0f1220;--card:#181d33;--txt:#e8eaf2;--mut:#8892b0;
 --acc:#e50914;--acc2:#0ea5e9;--line:#262c48;--chip:#232842;--hov:#20263f;
 --sh:0 2px 10px rgba(0,0,0,.35)}
*{box-sizing:border-box;margin:0;-webkit-tap-highlight-color:transparent}
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;color:var(--txt);
 background:linear-gradient(165deg,#fff7ea 0%,#fffdf7 38%,#eef7ff 100%);
 min-height:100vh}
html[data-theme=dark] body{background:#0f1220}
header{position:sticky;top:0;background:var(--card);
 border-bottom:1px solid var(--line);z-index:9;padding:8px 18px 10px}
#mainnav{display:flex;gap:6px;padding:2px 0 8px;border-bottom:1px dashed
 var(--line);margin-bottom:8px;overflow-x:auto}
#mainnav button{border:1px solid var(--line);border-radius:20px;padding:7px 16px;
 background:var(--chip);color:var(--mut);cursor:pointer;font-size:13px;
 font-weight:700;white-space:nowrap}
#mainnav button.on{background:linear-gradient(90deg,#fb923c,#f97316);
 color:#fff;border-color:transparent}
#mainnav button[data-mode=radio].on{background:linear-gradient(90deg,#38bdf8,#0284c7)}
.row1{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
h1{font-size:19px;font-weight:800;background:linear-gradient(90deg,var(--acc),
 var(--acc2));-webkit-background-clip:text;background-clip:text;
 -webkit-text-fill-color:transparent}
.tabs{display:flex;gap:6px;flex-wrap:wrap;flex:1}
.tabs button{border:1px solid var(--line);border-radius:20px;padding:6px 13px;
 background:var(--chip);color:var(--mut);cursor:pointer;font-size:13px}
.tabs button.active{background:linear-gradient(90deg,#fb923c,#f97316);
 color:#fff;border-color:transparent}
.tabs button.radio.active{background:linear-gradient(90deg,#38bdf8,#0284c7)}
.hdrbtn{border:0;background:none;color:var(--mut);cursor:pointer;font-size:17px;
 padding:2px 5px}.hdrbtn:hover{color:var(--acc)}.hdrbtn:disabled{opacity:.3}
.row2{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
#q{flex:1;min-width:160px;padding:8px 13px;border-radius:10px;font-size:14px;
 border:1px solid var(--line);background:var(--card);color:var(--txt)}
.big{cursor:pointer;border:0;border-radius:10px;font-weight:700;
 background:linear-gradient(90deg,#fb923c,#f97316);color:#fff;padding:8px 14px;
 text-decoration:none;display:inline-block;font-size:13px;box-shadow:var(--sh)}
.big.blue{background:linear-gradient(90deg,#38bdf8,#0284c7)}
.big.cy{background:linear-gradient(90deg,#22d3ee,#0891b2)}
.big.grey{background:#64748b}
.big:disabled{opacity:.4;cursor:not-allowed}
.mini{border:1px solid var(--line);background:var(--chip);color:var(--mut);
 border-radius:8px;padding:3px 9px;font-size:11.5px;cursor:pointer;font-weight:700}
.mini:hover{color:var(--acc);border-color:var(--acc)}
label.tog{display:flex;align-items:center;gap:6px;font-size:13px;
 color:var(--mut);cursor:pointer}
#chips{display:flex;gap:6px;overflow-x:auto;padding:8px 0 2px;
 -webkit-overflow-scrolling:touch}
#chips::-webkit-scrollbar{height:5px}
#chips::-webkit-scrollbar-thumb{background:var(--line)}
#chips button{white-space:nowrap;border:1px solid var(--line);
 border-radius:16px;padding:5px 12px;background:var(--chip);color:var(--mut);
 cursor:pointer;font-size:12.5px}
#chips button.active{background:var(--acc);color:#fff;border-color:transparent}
.legend{padding:3px 18px 0;color:var(--mut);font-size:11px}
.note{margin:10px 18px 2px;color:var(--mut);font-size:13px;display:flex;
 justify-content:space-between;flex-wrap:wrap;gap:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
 gap:12px;padding:14px 18px 96px;max-width:1700px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;
 padding:10px;text-align:center;position:relative;display:flex;
 flex-direction:column;gap:5px;box-shadow:var(--sh);transition:.12s}
.card:hover{transform:translateY(-2px);border-color:#fdba74}
.card img{width:50px;height:50px;object-fit:contain;margin:2px auto 0;
 border-radius:8px}
.cname{font-size:12.5px;font-weight:700;line-height:16px;height:32px;overflow:hidden}
.now{font-size:11px;color:#16a34a;height:26px;line-height:13px;overflow:hidden}
.grp{color:var(--mut);font-size:11px;height:13px;overflow:hidden;white-space:nowrap}
.bds{display:flex;gap:4px;justify-content:center;height:16px}
.bd{font-size:10px;padding:1px 7px;border-radius:8px;font-weight:700;color:#fff}
.bhd{background:#0284c7}.bsd{background:#64748b}.blang{background:#16a34a}
.top{position:absolute;top:7px;left:8px;right:8px;display:flex;
 justify-content:space-between}
.dot{border:1px solid var(--line);width:22px;height:22px;border-radius:50%;
 background:var(--chip);color:var(--mut);cursor:pointer;font-size:11px;
 line-height:20px;padding:0}
.dot.checking{color:#f59e0b;animation:spin 1s linear infinite}
.dot.online{color:#16a34a;border-color:#16a34a}
.dot.dead{color:#ef4444;border-color:#ef4444}
.dot.unknown{color:#f59e0b;border-color:#f59e0b}
.dot.nonhttp{color:#0284c7;border-color:#0284c7}
@keyframes spin{to{transform:rotate(360deg)}}
.fav{border:0;background:none;color:#cbd5e1;cursor:pointer;font-size:17px;padding:0}
.fav.on{color:#f59e0b}
.watch{border:1px solid var(--line);border-radius:10px;padding:7px 0;
 background:var(--chip);color:var(--txt);cursor:pointer;font-weight:700;
 width:100%;margin-top:auto}
.watch:hover{background:linear-gradient(90deg,#fb923c,#f97316);color:#fff;
 border-color:transparent}
.altvlc{margin-top:4px;font-size:11px;padding:5px 0;background:transparent;
 border:1px dashed var(--line);border-radius:8px;color:var(--mut);cursor:pointer}
.altvlc:hover{color:var(--acc);border-color:var(--acc)}
.empty{grid-column:1/-1;text-align:center;color:var(--mut);padding:70px 0}
#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%)
 translateY(90px);padding:10px 22px;border-radius:24px;font-size:14px;
 transition:.3s;z-index:99;background:#334155;color:#fff;max-width:86vw}
body.playing #toast{bottom:110px}
#toast.ok{background:#16a34a}#toast.bad{background:#dc2626}
#toast.show{transform:translateX(-50%) translateY(0)}
#loader{position:fixed;inset:0;background:rgba(255,253,247,.85);display:none;
 place-items:center;z-index:50;text-align:center;color:var(--mut)}
.spin{width:44px;height:44px;border:4px solid var(--line);
 border-top-color:var(--acc);border-radius:50%;margin:0 auto 14px;
 animation:spin .8s linear infinite}
.errbox{margin:40px auto;max-width:420px;background:var(--card);
 border:1px solid #ef4444;border-radius:12px;padding:20px;text-align:center}
.modal{display:none;position:fixed;inset:0;background:rgba(51,65,85,.55);
 z-index:80;place-items:center;padding:16px}
.modal.open{display:grid}
.modalcard{background:var(--card);border:1px solid var(--line);
 border-radius:18px;max-width:560px;width:100%;padding:20px;
 max-height:92vh;overflow-y:auto;box-shadow:var(--sh)}
.modalcard h3{margin-bottom:10px}
.modalcard p{font-size:13.5px;color:var(--mut);margin:8px 0;line-height:1.5}
.playercard{max-width:760px}
#tvplayer{display:block;width:100%;max-height:62vh;min-height:180px;
 background:#000;border-radius:12px;margin:12px 0}
.playeractions{display:flex;gap:8px;flex-wrap:wrap}
.playeractions .big{flex:1;min-width:145px;text-align:center}
.lanurl{background:var(--bg);border:1px dashed var(--acc2);border-radius:10px;
 padding:10px;text-align:center;font-size:16px;font-weight:700;margin:10px 0;
 user-select:all}
.qrbox{display:inline-block;margin:8px 12px;text-align:center}
.qrbox .cap{font-size:12px;color:var(--mut);margin-top:4px}
.qrbox img{background:#fff;padding:6px;border-radius:10px}
.mrow{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.closex{float:right;border:0;background:none;color:var(--mut);font-size:20px;
 cursor:pointer}
#gsearch,#seturl,#setname,#nq,#bq{width:100%;padding:8px 12px;border-radius:10px;
 margin-bottom:10px;border:1px solid var(--line);background:var(--bg);
 color:var(--txt)}
.grow{display:flex;gap:10px;padding:8px 6px;border-bottom:1px solid var(--line);
 font-size:13px;align-items:baseline;cursor:pointer;border-radius:8px}
.grow:hover{background:var(--hov)}
.grow b{min-width:130px;max-width:130px;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.grow .np{color:#16a34a;flex:1}
.grow .nx{color:var(--mut);flex:1;font-size:12px}
.grow .tm{color:var(--mut);font-size:11px;white-space:nowrap}
.wb{display:flex;justify-content:space-between;padding:7px 4px;font-size:13.5px;
 border-bottom:1px solid var(--line)}
.wb b.pass{color:#16a34a}.wb b.warn{color:#f59e0b}.wb b.fail{color:#ef4444}
#pbar{position:fixed;left:12px;right:12px;bottom:12px;background:var(--card);
 border:1px solid var(--line);border-radius:16px;
 box-shadow:0 6px 24px rgba(120,100,60,.18);padding:10px 14px;display:none;
 align-items:center;gap:10px;z-index:70}
body.playing #pbar{display:flex}
#pblogo{width:42px;height:42px;object-fit:contain;border-radius:10px;background:#fff}
#pbinfo{flex:1;min-width:0}
#pbname{font-size:14px;font-weight:800;white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis}
#pbtag{font-size:11px;color:var(--mut)}
.eq{display:inline-flex;gap:2px;align-items:flex-end;height:14px;margin-right:6px}
.eq i{width:3px;background:var(--acc2);border-radius:2px;
 animation:eq 1s ease-in-out infinite}
.eq i:nth-child(2){animation-delay:.2s;background:var(--acc)}
.eq i:nth-child(3){animation-delay:.4s}
.eq.off i{animation:none;height:4px}
@keyframes eq{0%,100%{height:4px}50%{height:14px}}
#pbar button{border:1px solid var(--line);border-radius:50%;width:42px;
 height:42px;background:var(--chip);color:var(--txt);font-size:15px;
 cursor:pointer;flex:0 0 auto}
#pbar button:hover{background:var(--acc);color:#fff;border-color:transparent}
#pbar button.vlc{width:auto;border-radius:10px;font-size:11px;padding:0 10px}
#pbvol{width:100px;accent-color:var(--acc)}
#pbslp{background:var(--bg);color:var(--txt);border:1px solid var(--line);
 border-radius:10px;padding:6px;font-size:12px}
/* ===== panels (news/markets/books) ===== */
.panel{display:none;padding:14px 18px 120px;max-width:1200px;margin:0 auto}
body[data-mode=news] #panel-news{display:block}
body[data-mode=markets] #panel-markets{display:block}
body[data-mode=books] #panel-books{display:block}
body[data-mode=podcasts] #panel-podcasts{display:block}
.utilitygrid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.utilitygrid .hdrbtn{border:1px solid var(--line);border-radius:10px;padding:10px}
.charttools{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.charttools button.active{background:var(--acc);color:#fff}
.podlist{display:flex;flex-direction:column;gap:10px}
.podcard{display:flex;gap:12px;align-items:center;background:var(--card);
 border:1px solid var(--line);border-radius:14px;padding:12px}
.podcard img{width:64px;height:64px;object-fit:cover;border-radius:10px}
.podcard .podtext{flex:1;min-width:0}
.pchips{display:flex;gap:6px;overflow-x:auto;padding:4px 0 10px;
 -webkit-overflow-scrolling:touch}
.pchips button{white-space:nowrap;border:1px solid var(--line);border-radius:16px;
 padding:5px 13px;background:var(--chip);color:var(--mut);cursor:pointer;
 font-size:12.5px;font-weight:700}
.pchips button.active{background:var(--acc);color:#fff;border-color:transparent}
.pbar2{display:flex;gap:8px;margin-bottom:10px}
.pbar2 input{flex:1;padding:9px 13px;border-radius:10px;font-size:14px;
 border:1px solid var(--line);background:var(--bg);color:var(--txt)}
.pempty{text-align:center;color:var(--mut);padding:36px 10px;line-height:1.7}
.nlist{display:flex;flex-direction:column;gap:10px}
.ni{display:flex;gap:12px;background:var(--card);border:1px solid var(--line);
 border-radius:14px;padding:12px;cursor:pointer;transition:.12s}
.ni:hover{border-color:#fdba74;background:var(--hov)}
.ni img{width:96px;height:72px;object-fit:cover;border-radius:10px;flex:0 0 auto}
.ni.hero img{width:100%;height:180px;order:-1}
.ni.hero{flex-wrap:wrap}
.ni.hero .nitxt{width:100%}
.nitxt{min-width:0;flex:1}
.nitxt h3{font-size:14.5px;line-height:1.35;margin-bottom:4px}
.ni.hero .nitxt h3{font-size:17px}
.nitxt p{font-size:12.5px;color:var(--mut);line-height:1.5;margin-bottom:6px}
.nimeta{font-size:11px;color:var(--acc);font-weight:700}
.nlist.small .ni{padding:9px}
.nlist.small .ni img{width:64px;height:48px}
.nlist.small .nitxt h3{font-size:13px}
/* markets */
.mksec{margin:16px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--mut)}
.mksec .mini{margin-left:8px}
.mkrow{display:flex;align-items:center;gap:12px;background:var(--card);
 border:1px solid var(--line);border-radius:14px;padding:11px 14px;
 margin-bottom:8px;cursor:pointer;transition:.12s;flex-wrap:wrap}
.mkrow:hover{border-color:#93c5fd;background:var(--hov)}
.mkrow.na{cursor:default;color:var(--mut)}
.mkid{flex:1;min-width:130px;display:flex;align-items:center;gap:8px}
.mkid b{font-size:14px}
.mkst{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:8px}
.mkst.live{background:#dcfce7;color:#16a34a}
.mkst.off{background:#f1f5f9;color:#94a3b8}
.rm{border:0;background:none;color:#cbd5e1;cursor:pointer;font-size:13px;padding:2px}
.rm:hover{color:#ef4444}
.mknum{display:flex;align-items:baseline;gap:10px}
.mkp{font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
.mchg{font-size:12.5px;font-weight:800}
.mchg.up{color:#16a34a}.mchg.down{color:#dc2626}
.mksk{width:120px;height:36px}
.mksk svg{display:block}
.chartbox{background:var(--bg);border:1px solid var(--line);border-radius:12px;
 padding:10px;overflow-x:auto;margin:8px 0}
.chkstats{font-size:13px;color:var(--mut);display:flex;gap:14px;flex-wrap:wrap}
.chkstats b{color:var(--txt);font-size:16px}
/* books */
.contstrip{margin:2px 0 10px;color:var(--mut);font-size:12.5px;
 display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.grid.books{grid-template-columns:repeat(auto-fill,minmax(138px,1fr));
 padding-bottom:20px}
.book .cname{height:32px}
.nocov{width:92px;height:120px;margin:2px auto;border-radius:10px;
 background:linear-gradient(135deg,#fde68a,#fdba74);display:grid;
 place-items:center;font-size:34px}
.bpager{display:flex;gap:14px;align-items:center;justify-content:center;
 padding:8px 0 20px;color:var(--mut);font-size:13px}
/* reader + bookview */
.reader h3{line-height:1.35}
#rvbody{font-size:15px;line-height:1.75;color:var(--txt);white-space:pre-wrap;
 margin:10px 0;min-height:120px}
.rvtools{display:flex;gap:6px;margin-bottom:4px}
#bookview{display:none;position:fixed;inset:0;z-index:95;flex-direction:column;
 background:#fdfaf4;color:#2b2b2b}
#bookview[data-bv=sepia]{background:#f4ecd8;color:#4a3f2a}
#bookview[data-bv=night]{background:#101418;color:#cfd8e3}
.bvtop,.bvbot{display:flex;align-items:center;gap:10px;padding:10px 16px;
 background:rgba(0,0,0,.04)}
#bookview[data-bv=night] .bvtop,#bookview[data-bv=night] .bvbot{
 background:rgba(255,255,255,.05)}
.bvspring{flex:1}
#bvtitle{font-size:14.5px;font-weight:800;white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis}
#bvtext{flex:1;overflow-y:auto;padding:22px 8%;font-family:Georgia,'Times New
 Roman',serif;font-size:18px;line-height:1.85;text-align:justify;
 white-space:pre-wrap}
.bvbot{justify-content:center}
#bvprog{font-size:12px;color:inherit;opacity:.65;min-width:130px;text-align:center}
@media(max-width:760px){
 header{padding:6px 10px 8px}
 h1{font-size:16px;width:100%;order:-1;margin-bottom:2px}
 .row1{gap:8px}
 #mainnav{padding-bottom:6px}
 #mainnav button{padding:6px 12px;font-size:12px}
 .tabs{overflow-x:auto;flex-wrap:nowrap;padding-bottom:4px}
 .tabs button{flex:0 0 auto}
 .hdrbtn{font-size:20px;padding:4px 6px}
 #q{width:100%;min-width:0;order:-1}
 .row2{gap:8px}
 .big{padding:9px 12px;font-size:12.5px}
 .grid{grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;padding:10px 8px 180px}
 .card{padding:8px;border-radius:14px}
 .card img{width:42px;height:42px}
 .cname{font-size:12px;height:30px}
 .legend,.note{padding-left:10px;padding-right:10px;margin-left:0;margin-right:0}
 .panel{padding:12px 10px 130px}
 .ni{padding:10px}
 .ni img{width:74px;height:56px}
 .ni.hero img{height:140px}
 .nitxt h3{font-size:13.5px}
 .mkrow{padding:10px}
 .mksk{width:90px}
 #pbar{left:8px;right:8px;bottom:8px;flex-wrap:wrap;padding:10px;gap:8px;
  margin-bottom:env(safe-area-inset-bottom)}
 #pbinfo{min-width:calc(100% - 116px)}
 #pbar button{width:46px;height:46px}
 #pbplay{order:2}#pbstop{order:3}
 #tvplayer{min-height:150px;max-height:48vh}
 .playeractions{display:grid;grid-template-columns:1fr 1fr}
 .playeractions .big{min-width:0;padding:10px 6px}
 .utilitygrid{grid-template-columns:1fr 1fr}
 #guide,#set,#themebtn,#help{display:none}
 body.playing #toast{bottom:180px}
 body{padding-top:env(safe-area-inset-top)}
 .card:hover{transform:none}
 .ni:hover,.mkrow:hover{transform:none}
}
</style></head><body data-mode="media">
<header>
 <div id="mainnav">
  <button data-mode="tv">&#128250; TV</button>
  <button data-mode="radio">&#127897; Radio</button>
  <button data-mode="news">&#128240; News</button>
  <button data-mode="podcasts">&#127911; Podcasts</button>
  <button data-mode="markets">&#128200; Markets</button>
  <button data-mode="books">&#128218; Books</button>
 </div>
 <div class="row1">
  <button class="hdrbtn" id="home" title="Home">&#x1F3E0;</button>
  <h1>Sunrise Hub</h1>
  <div class="tabs" id="tabs"></div>
  <button class="hdrbtn" id="guide" title="TV Guide">&#128214;</button>
  <button class="hdrbtn" id="mob" title="Phone QR">&#x1F4F1;</button>
  <button class="hdrbtn" id="set" title="Settings">&#9881;</button>
  <button class="hdrbtn" id="themebtn" title="Theme">&#9788;</button>
  <button class="hdrbtn" id="help" title="Help / checks">&#10067;</button>
  <button class="hdrbtn" id="more" title="More">&#8943;</button>
  <button class="hdrbtn" id="quit" title="Stop server">&#x23FB;</button></div>
 <div class="row2">
  <input id="q" placeholder="&#128269; Search channels or stations&hellip;"
   autocomplete="off">
  <button class="big" id="playall">&#9654; Whole list in VLC</button>
  <label class="tog"><input type="checkbox" id="auto" checked> auto-check</label>
  <label class="tog"><input type="checkbox" id="okfirst"> online first</label>
 </div>
 <div id="chips"></div>
</header>
<div class="legend">&#9989; plays &nbsp;&middot;&nbsp; ~ blocked probe (often
 plays) &nbsp;&middot;&nbsp; ? VLC-only &nbsp;&middot;&nbsp; &#10005; dead</div>
<div class="note"><span id="cnt"></span><span id="hint"></span></div>
<div class="grid" id="grid"></div>
<div id="sentinel" style="height:10px"></div>

<div class="panel" id="panel-news">
 <div class="pchips" id="nchips"></div>
 <div class="pbar2"><input id="nq"
  placeholder="Filter headlines&hellip;" autocomplete="off"></div>
 <div id="nlist" class="nlist"><div class="pempty">Pick a topic above</div></div>
</div>

<div class="panel" id="panel-markets">
 <div id="mkwrap"><div class="pempty">Loading quotes&#8230;</div></div>
 <h4 class="mksec">&#128240; MARKET NEWS</h4>
 <div id="mknews" class="nlist small"><div class="pempty">&#8230;</div></div>
</div>

<div class="panel" id="panel-books">
 <div class="pchips" id="bklang"></div>
 <div class="pbar2">
  <input id="bq" placeholder="Search 70,000+ free books&hellip;"
   autocomplete="off">
  <button class="big blue" id="bks">Search</button></div>
 <div id="bkcont" class="contstrip"></div>
 <div id="bkgrid" class="grid books"><div class="pempty">Loading
  popular books&#8230;</div></div>
 <div class="bpager">
  <button class="big grey" id="bkprev">&lsaquo; Prev</button>
  <span id="bkpage"></span>
  <button class="big grey" id="bknext">Next &rsaquo;</button></div>
</div>
<div class="panel" id="panel-podcasts">
 <h3>Latest stories and podcasts</h3>
 <p class="note">Listen to current episodes from public RSS feeds.</p>
 <div id="podlist" class="podlist"><div class="pempty">Loading podcasts...</div></div>
</div>

<div id="loader"><div><div class="spin"></div>Loading&hellip;</div></div>
<div id="toast"></div>

<div id="pbar">
 <img id="pblogo" alt="">
 <div id="pbinfo"><div id="pbname"></div>
  <div id="pbtag"><span class="eq off" id="pbeq"><i></i><i></i><i></i></span><span
   id="pbstate"></span></div></div>
 <button id="pbplay" aria-label="play/pause">&#9654;</button>
 <input id="pbvol" type="range" min="0" max="100" value="85" aria-label="volume">
 <select id="pbslp" aria-label="sleep timer">
  <option value="0">sleep: off</option><option value="15">15 min</option>
  <option value="30">30 min</option><option value="60">60 min</option></select>
 <button id="pbvlc" class="vlc" title="Hand off to VLC (most stable)">VLC</button>
 <button id="pbstop" aria-label="stop">&#10005;</button>
</div>

<div class="modal" id="welcome"><div class="modalcard">
 <h3>&#127749; Welcome to Sunrise Hub</h3>
 <p>TV &#8226; FM Radio &#8226; News &#8226; Stock Markets &#8226; Free Books.
 Quick system check:</p>
 <div id="wbchecks"><p>Checking&#8230;</p></div>
 <p style="margin-top:12px"><b>How to use:</b><br>
 &#128250; Media: pick tab &#8594; Watch (TV opens VLC) / Listen (plays here).<br>
 &#128240; News: tap headline &#8594; clean reader.<br>
 &#128200; Markets: live NIFTY/Sensex/US + watchlist, tap for chart.<br>
 &#128218; Books: free classics English+&#2361;&#2367;&#2344;&#2381;&#2342;&#2368;,
 position auto-saved.<br> Radio keeps playing while you read &#127911;</p>
 <div class="mrow" id="welcome-actions">
  <button class="big blue" id="setupPhone" onclick="showModal('mobpanel',true);wbDone()">
   &#x1F4F1; Set up phone</button>
  <button class="big grey" onclick="wbDone()">Start exploring</button></div>
</div></div>

<div class="modal" id="mobpanel"><div class="modalcard">
 <button class="closex" onclick="showModal('mobpanel',false)">&times;</button>
 <h3>&#x1F4F1; Open on your phone</h3>
 __QRBLOCKS__
 <p><b>Step 1.</b> Same Wi-Fi (home QR) or Tailscale ON (anywhere QR).<br>
 <b>Step 2.</b> Scan / type address into the phone browser.</p>
 <div class="mrow" id="mlinks"></div>
</div></div>

<div class="modal" id="playermodal"><div class="modalcard playercard">
<button class="closex" onclick="closePlayer()">&times;</button>
<h3 id="playertitle">Watch stream</h3>
<video id="tvplayer" controls playsinline preload="metadata"></video>
<p id="playerhint">Choose where you want to play this stream.</p>
<div class="charttools">
 <label class="mini">Screen <select id="playerfit"><option value="contain">Fit</option>
  <option value="cover">Fill</option></select></label>
 <label class="mini">Speed <select id="playerspeed"><option>1</option>
  <option>0.75</option><option>1.25</option><option>1.5</option></select></label>
</div>
<div class="playeractions">
 <button class="big blue" id="playerplay">Play here</button>
 <button class="big cy" id="playervlc">Open in VLC</button>
 <button class="big grey" id="playerexternal">Open in browser</button>
</div>
</div></div>

<div class="modal" id="utilitypanel"><div class="modalcard">
 <button class="closex" onclick="showModal('utilitypanel',false)">&times;</button>
 <h3>More tools</h3>
 <div class="utilitygrid">
  <button class="hdrbtn" id="moreguide">&#128214; TV guide</button>
  <button class="hdrbtn" id="moreset">&#9881; Settings</button>
  <button class="hdrbtn" id="moretheme">&#9788; Theme</button>
  <button class="hdrbtn" id="morehelp">&#10067; System checks</button>
 </div>
</div></div>

<div class="modal" id="guidepanel"><div class="modalcard">
 <button class="closex" onclick="showModal('guidepanel',false)">&times;</button>
 <h3>&#128214; TV Guide - right now
 <span style="font-size:11px">(tap a row to watch)</span></h3>
 <div id="gstat" style="color:var(--mut);font-size:13px"></div>
 <input id="gsearch" placeholder="Filter channels&hellip;">
 <div id="glist" style="max-height:55vh;overflow-y:auto"></div>
</div></div>

<div class="modal" id="setpanel"><div class="modalcard">
 <button class="closex" onclick="showModal('setpanel',false)">&times;</button>
 <h3>&#9881; Settings</h3>
 <p><b>Add your own M3U playlist</b> (becomes a new Media tab):</p>
 <input id="setname" placeholder="Tab name (e.g. My IPTV)">
 <input id="seturl" placeholder="https://example.com/playlist.m3u">
 <button class="big blue" onclick="addCustom()">+ Add playlist</button>
 <p style="margin-top:14px;color:var(--mut)">Stored in custom_playlists.json.
 Sources: iptv-org - radio-browser - epg.pw - public RSS - Yahoo Finance -
 Project Gutenberg. All free.</p>
</div></div>

<div class="modal" id="readerview"><div class="modalcard reader">
 <button class="closex" onclick="showModal('readerview',false)">&times;</button>
 <h3 id="rvtitle"></h3>
 <div id="rvmeta" class="nimeta"></div>
 <div class="rvtools">
  <button class="mini" id="rvfm">A-</button>
  <button class="mini" id="rvfp">A+</button></div>
 <div id="rvbody"></div>
 <a id="rvlink" class="big blue" target="_blank" rel="noopener"
  href="#">&#128279; Read full at source</a>
</div></div>

<div class="modal" id="chartmodal"><div class="modalcard">
 <button class="closex" onclick="showModal('chartmodal',false)">&times;</button>
 <h3 id="chartsym"></h3>
 <div id="chartpills" class="pchips"></div>
 <div class="charttools"><button class="mini active" data-ct="line">Line</button>
  <button class="mini" data-ct="bar">Bars</button></div>
 <div class="chartbox" id="bigchart"></div>
 <div id="chkstats" class="chkstats"></div>
</div></div>

<div id="bookview" data-bv="paper">
 <div class="bvtop">
  <button class="hdrbtn" id="bvclose" title="Close">&#10005;</button>
  <b id="bvtitle"></b><span class="bvspring"></span>
  <button class="hdrbtn" id="bvfa">A-</button>
  <button class="hdrbtn" id="bvfb">A+</button>
  <button class="hdrbtn" id="bvtheme" title="Paper/Sepia/Night">&#9788;</button>
 </div>
 <div id="bvtext"></div>
 <div class="bvbot">
  <button class="big grey" id="bvprev">&lsaquo; Prev</button>
  <span id="bvprog"></span>
  <button class="big grey" id="bvnext">Next &rsaquo;</button></div>
</div>

<script>
var PL=__PL__;
var T_FAV='\\u2605 Favorites',T_REC='\\u23F0 Recent';
var ISMOBILE=/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
 var IS_CLOUD=__CLOUD__;
var CHUNK=ISMOBILE?60:120,CONC=ISMOBILE?3:4,MAXAUTO=ISMOBILE?80:240,
 TTL=20*60*1000;
var S={pl:'in',chans:[],cat:'all',q:'',shown:0,queue:[],busy:0,autoN:0,
 now:{},cache:{}};
S.favs=JSON.parse(localStorage.getItem('iptv-favs')||'[]');
S.hist=JSON.parse(localStorage.getItem('iptv-hist')||'[]');
S.chk=(function(){try{
 var c=JSON.parse(localStorage.getItem('iptv-chk')||'{}');
 var cut=Date.now()-TTL*4,o={};
 for(var k in c)if(c[k].t>cut)o[k]=c[k];return o}catch(e){return{}}})();
function $(i){return document.getElementById(i)}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(m){
 return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]})}
function toast(m,c){var t=$('toast');t.textContent=m;t.className=c||'';
 t.classList.add('show');clearTimeout(t._h);
 t._h=setTimeout(function(){t.classList.remove('show')},2600)}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
function fresh(u){var c=S.chk[u];return(c&&Date.now()-c.t<TTL)?c:null}
function cur(){return S.pl==='recent'?S.hist:S.pl==='favs'?S.favs:S.chans}
function plain(s){return String(s).replace(/&[#\\w]+;/g,'')}
function isTV(pl){return PL[pl]&&PL[pl].t!=='radio'}
function showModal(id,on){$(id).className=on?'modal open':'modal'}
window.showModal=showModal;
function hhmm(ep){if(!ep)return'';
 return new Date(ep*1000).toLocaleTimeString([],
 {hour:'2-digit',minute:'2-digit'})}
function norm(s){return(s||'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
function plTypeOf(pl){
 if(pl==='favs')return S.favs[0]&&S.favs[0].tp;
 if(pl==='recent')return S.hist[0]&&S.hist[0].tp;
 return PL[pl]?PL[pl].t:'tv'}

/* ===== MODE SWITCHER (media pipeline untouched) ===== */
var MODE='tv';
function setMode(m){
 MODE=m;document.body.setAttribute('data-mode',m);
 var nb=document.querySelectorAll('#mainnav button');
 for(var i=0;i<nb.length;i++)
  nb[i].className=(nb[i].dataset.mode===m)?'on':'';
 var med=(m==='media'||m==='tv'||m==='radio');
 $('chips').style.display=med?'flex':'none';
 document.querySelector('.legend').style.display=med?'block':'none';
 document.querySelector('.note').style.display=med?'flex':'none';
 document.querySelector('.row2').style.display=med?'flex':'none';
 document.querySelector('.tabs').style.display=med?'flex':'none';
 $('guide').style.display=(m==='tv'||m==='media')?'':'none';
 $('grid').style.display=med?'grid':'none';
 if(m==='news'&&!NEWS.loaded)nShow(NEWS.cat);
 if(m==='podcasts'&&!POD.loaded)podShow();
 if(m==='markets'){mkPaint();mkStart()}else mkStop();
 if(m==='books'&&!BK.init)bInit();
 if(m==='tv'&&S.pl!=='in')load('in');
 if(m==='radio'&&S.pl!=='rin')load('rin');
}
window.setMode=setMode;

/* ===== THEME ===== */
(function(){var t=localStorage.getItem('iptv-theme');
 if(t==='dark'){document.documentElement.setAttribute('data-theme','dark');
  $('themebtn').innerHTML='\\u263D'}
 $('themebtn').onclick=function(){
  var d=document.documentElement.getAttribute('data-theme')==='dark';
  if(d){document.documentElement.removeAttribute('data-theme');
   this.innerHTML='\\u263C';localStorage.setItem('iptv-theme','light')}
  else{document.documentElement.setAttribute('data-theme','dark');
   this.innerHTML='\\u263D';localStorage.setItem('iptv-theme','dark')}}})();

/* ===== RADIO ENGINE v3 ===== */
var AU=new Audio();AU.preload='auto';AU.playbackRate=1;
AU.volume=parseFloat(localStorage.getItem('iptv-vol')||'0.85');
var PB={on:false,cur:null,tries:0,timer:null,wd:null,bt:null,
        lastT:-1,stall:0,fired:false,vlcTried:false};
function pbSet(txt,live){
 var st=$('pbstate');if(st)st.textContent=txt;
 var eq=$('pbeq');if(eq)eq.className=live?'eq':'eq off'}
function pbShow(it){
 if(it.l){$('pblogo').src=it.l;$('pblogo').style.display=''}
 else{$('pblogo').style.display='none'}
 $('pbname').textContent=plain(esc(it.n)).slice(0,48);
 var st=$('pbstate');if(st)st.textContent='';
 $('pbar').style.display='flex';
 document.body.classList.add('playing');PB.on=true}
function radioStop(msg){
 AU.pause();try{AU.removeAttribute('src');AU.load()}catch(e){}
 clearInterval(PB.wd);clearTimeout(PB.timer);clearInterval(PB.bt);
 document.body.classList.remove('playing');PB.on=false;PB.cur=null;
 if(msg)toast(msg,'bad')}
function radioConnect(it){
 PB.cur=it;PB.fired=false;pbShow(it);
 pbSet('Connecting...',true);
 clearTimeout(PB.timer);clearInterval(PB.wd);clearInterval(PB.bt);
 try{AU.pause();AU.removeAttribute('src');AU.load()}catch(e){}
 AU.src=it.u;
 var t0=Date.now();
 PB.bt=setInterval(function(){
  if(!PB.on||PB.cur!==it||AU.readyState>=3)return;
  var b=AU.buffered,end=b.length?b.end(b.length-1):0;
  var ahead=Math.max(0,end-(AU.currentTime||0));
  pbSet('Buffering '+ahead.toFixed(1)+'s ('+
   Math.round((Date.now()-t0)/1000)+'s)...',true)},300);
 var go=function(){
  if(PB.fired||PB.cur!==it)return;
  var b=AU.buffered,end=b.length?b.end(b.length-1):0;
  var ahead=Math.max(0,end-(AU.currentTime||0));
  if(AU.readyState<3&&ahead<1&&(Date.now()-t0)<7000){
   clearTimeout(PB.timer);PB.timer=setTimeout(go,400);return}
  PB.fired=true;clearInterval(PB.bt);
  var pr=AU.play();
  if(pr&&pr.catch)pr.catch(function(){pbSet('Tap PLAY to start',false)})};
 clearTimeout(PB.timer);PB.timer=setTimeout(go,7200);
 AU.onplaying=function(){PB.tries=0;pbSet('\\u266A LIVE - on air',true)};
 AU.onpause=function(){$('pbplay').innerHTML='\\u25B6'};
 AU.onended=function(){pbRetry('stream ended')};
 AU.onerror=function(){pbRetry('connection dropped')};
 PB.lastT=-1;PB.stall=0;clearInterval(PB.wd);
 PB.wd=setInterval(function(){
  if(!PB.on||PB.cur!==it||AU.paused)return;
  var ct=AU.currentTime||0;
  if(Math.abs(ct-PB.lastT)<0.05){PB.stall++;
   if(PB.stall>=3){PB.stall=0;pbRetry('stalled')}}
  else PB.stall=0;
  PB.lastT=ct},4000)}
function pbRetry(reason){
 if(!PB.cur)return;
 PB.tries++;
 if(PB.tries===2&&!PB.vlcTried){PB.vlcTried=true;
  var u=PB.cur.u,nm=plain(esc(PB.cur.n)).slice(0,28);
  toast('Browser struggling - switching to VLC','bad');
  fetch('/play?url='+encodeURIComponent(u)).then(function(r){return r.json()})
  .then(function(j){if(j.ok)toast(nm+' playing in VLC','ok')});
  radioStop();return}
 if(PB.tries>4){radioStop('Station not responding ('+reason+')');return}
 pbSet('Reconnecting '+PB.tries+'/4...',true);
 var it=PB.cur,delay=Math.min(4000,600*PB.tries);
 setTimeout(function(){if(PB.cur===it)radioConnect(it)},delay)}
function radioPlay(it){
 if(/\\.m3u8/i.test(it.u)){
  toast('HLS station - opening in VLC','bad');
  fetch('/play?url='+encodeURIComponent(it.u)).then(function(r){return r.json()})
  .then(function(j){toast(j.msg,j.ok?'ok':'bad')});
  pushHist(it,'radio');return}
 PB.vlcTried=false;$('pbplay').innerHTML='\\u23F8';
 toast('\\u266B '+plain(esc(it.n)).slice(0,36));
 radioConnect(it);pushHist(it,'radio')}
$('pbplay').onclick=function(){
 if(!PB.cur)return;
 if(AU.paused){var pr=AU.play();if(pr&&pr.catch)pr.catch(function(){});
  this.innerHTML='\\u23F8'}
 else{AU.pause();this.innerHTML='\\u25B6'}};
AU.onplay=function(){$('pbplay').innerHTML='\\u23F8'};
$('pbvol').value=Math.round(AU.volume*100);
$('pbvol').oninput=function(){AU.volume=this.value/100;
 localStorage.setItem('iptv-vol',this.value/100)};
$('pbstop').onclick=function(){radioStop()};
$('pbvlc').onclick=function(){if(!PB.cur)return;
 fetch('/play?url='+encodeURIComponent(PB.cur.u)).then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad')})};
$('pbslp').onchange=function(){clearTimeout(PB.timer);
 var m=parseInt(this.value,10);
 if(m){PB.timer=setTimeout(function(){AU.pause();
  pbSet('Sleep timer done',false);toast('Sleep timer done','ok')},m*60000);
  toast('Sleep in '+m+' min')}};

/* ===== EPG ===== */
function nowFor(it){
 var a=S.now[it.id&&it.id.toLowerCase()];
 if(a)return a;
 return S.now[norm(it.n)]||S.now[norm(it.n).split('.').pop()]}
function paintNow(){
 document.querySelectorAll('.card').forEach(function(c){
  var it=findAny(c.dataset.u);if(!it)return;
  var a=nowFor(it),el=c.querySelector('.now');if(!el)return;
  el.textContent=a&&a.n?(a.n.t+' - till '+hhmm(a.n.e)):
   (a&&a.x?('next: '+a.x.t+' @ '+hhmm(a.x.s)):'')})}
function loadNow(){
 if(!isTV(S.pl)||S.pl==='world'){S.now={};paintNow();return}
 fetch('/api/now?p='+S.pl).then(function(r){return r.json()})
 .then(function(j){
  if(j.status==='ready'){S.now=j.channels||{};paintNow()}
  else if(j.status==='loading')setTimeout(loadNow,4000)})
 .catch(function(){})}

/* ===== TABS/GRID (media - unchanged pipeline) ===== */
function buildTabs(){var h='';
 var mk=function(id,l,rad){return '<button data-pl="'+id+'" class="'+
  (rad?'radio ':'')+(S.pl===id?'active':'')+'">'+l+'</button>'};
 h+=mk('favs',T_FAV+' ('+S.favs.length+')');
 h+=mk('recent',T_REC+' ('+S.hist.length+')');
 for(var k in PL)h+=mk(k,PL[k].n,PL[k].t==='radio');
 $('tabs').innerHTML=h}
function filtered(){var base=cur(),q=S.q.toLowerCase(),out=[];
 for(var i=0;i<base.length;i++){var it=base[i];
  var hay=(it.n+' '+it.g+' '+(it.lg||'')).toLowerCase();
  if(q&&hay.indexOf(q)===-1)continue;
  if(S.cat!=='all'&&it.g!==S.cat)continue;
  out.push(it)}
 if($('okfirst').checked){out=out.slice().sort(function(a,b){
  var ca=fresh(a.u),cb=fresh(b.u);
  var va=!ca?1:(ca.ok===true?0:(ca.ok===false?2:1));
  var vb=!cb?1:(cb.ok===true?0:(cb.ok===false?2:1));
  return va-vb})}
 return out}
function buildChips(){var src=cur(),q=S.q.toLowerCase(),
 counts={},order=[],tot=0;
 for(var i=0;i<src.length;i++){var g=src[i].g||'';
  if(q&&(src[i].n+' '+g).toLowerCase().indexOf(q)===-1)continue;
  if(!(g in counts)){counts[g]=0;order.push(g)}counts[g]++}
 order.sort(function(a,b){return counts[b]-counts[a]||a.localeCompare(b)});
 for(var j=0;j<order.length;j++)tot+=counts[order[j]];
 if(S.cat!=='all'&&order.indexOf(S.cat)===-1)S.cat='all';
 var h='<button data-c="all" class="'+(S.cat==='all'?'active':'')+
  '">All <b>'+tot+'</b></button>';
 for(var k2=0;k2<order.length;k2++){var g2=order[k2];
  h+='<button data-c="'+esc(g2)+'" class="'+(S.cat===g2?'active':'')+'">'+
   esc(g2||'Other')+' <b>'+counts[g2]+'</b></button>'}
 $('chips').innerHTML=h}
function badges(it){var b='',nm=' '+String(it.n).toUpperCase()+' ';
 var lg=(it.lg||'').split(',')[0].trim();
 if(nm.indexOf(' 4K ')>-1||nm.indexOf(' UHD ')>-1)b+='<span class="bd bhd">4K</span>';
 else if(nm.indexOf(' FHD ')>-1||nm.indexOf(' HD ')>-1)b+='<span class="bd bhd">HD</span>';
 else if(nm.indexOf(' SD ')>-1)b+='<span class="bd bsd">SD</span>';
 if(lg&&lg.length<=14)b+='<span class="bd blang">'+esc(lg)+'</span>';
 return '<div class="bds">'+b+'</div>'}
function render(reset){
 if(reset){$('grid').innerHTML='';S.shown=0}
 var view=filtered(),end=Math.min(view.length,S.shown+CHUNK),h='';
 var rad=plTypeOf(S.pl)==='radio';
 if(end===0&&reset){
  h='<div class="empty">'+(S.pl==='favs'
   ?'No favorites yet - tap the star'
   :S.pl==='recent'
   ?'Nothing here yet!'
   :'No channels match your search')+'</div>'}
 for(var i=S.shown;i<end;i++){var it=view[i];
  var cached=fresh(it.u);
  var isHttp=/^https?:/i.test(it.u);
  var dcls=cached?(cached.ok===true?'online':
   (cached.ok===false?'dead':(isHttp?'unknown':'nonhttp'))):'';
  var dtxt=dcls==='online'?'\\u2713':(dcls==='dead'?'\\u2715':
   (dcls==='unknown'?'~':(!isHttp?'?':'\\u00B7')));
  var isFav=S.favs.some(function(f){return f.u===it.u});
  h+='<div class="card" data-u="'+esc(it.u)+'">'+
   '<div class="top"><button class="dot '+dcls+'" data-u="'+esc(it.u)+
    '" title="stream check">'+dtxt+'</button>'+
   '<button class="fav'+(isFav?' on':'')+'" data-u="'+esc(it.u)+
    '" title="Favorite">\\u2605</button></div>'+
   (it.l?'<img src="'+esc(it.l)+'" loading="lazy" onerror="this.remove()">':'')+
   '<div class="cname">'+esc(it.n)+'</div>'+
   '<div class="now"></div>'+badges(it)+
   '<div class="grp">'+esc(it.g)+'</div>'+
   '<button class="watch" data-u="'+esc(it.u)+'">'+
   (rad?'\\u266A Listen':'\\u25B6 Watch')+'</button>'+
   (rad?'<button class="altvlc" data-vlc="'+esc(it.u)+
    '">Open in VLC</button>':'')+'</div>'}
 $('grid').insertAdjacentHTML('beforeend',h);
 S.shown=end;
 var extra=(S.pl==='recent'&&S.hist.length)
   ?' <button class="big grey" style="padding:2px 10px;font-size:11px"'
    +' onclick="clearHist()">Clear history</button>':'';
 $('cnt').textContent='Showing '+Math.min(end,view.length)+' of '+view.length;
 $('cnt').insertAdjacentHTML('beforeend',extra);
 observeDots();paintNow()}

/* ===== HEALTH DOTS ===== */
var dotIO=new IntersectionObserver(function(es){es.forEach(function(e){
 if(e.isIntersecting)schedule(e.target.dataset.u)})},{rootMargin:'200px'});
function observeDots(){if(!$('auto').checked)return;
 document.querySelectorAll('.dot').forEach(function(d){
  if(!d.classList.contains('online')&&!d.classList.contains('dead'))
   dotIO.observe(d)})}
function schedule(u){if(S.autoN>=MAXAUTO)return;
 if(fresh(u))return;if(S.queue.indexOf(u)!==-1)return;
 S.queue.push(u);pump()}
function pump(){while(S.busy<CONC&&S.queue.length){var u=S.queue.shift();
 S.busy++;S.autoN++;test(u,false).then(function(){S.busy--;pump()})}}
function findDot(u){var ds=document.querySelectorAll('.dot');
 for(var i=0;i<ds.length;i++)if(ds[i].dataset.u===u)return ds[i];return null}
function setDot(u,state,txt,title){
 document.querySelectorAll('.dot').forEach(function(d){
  if(d.dataset.u!==u)return;
  d.className='dot '+state;d.textContent=txt;
  if(title)d.title=title;
  try{dotIO.unobserve(d)}catch(e){}})}
function test(u,manual){
 if(!/^https?:/i.test(u)){var e0=findDot(u);
  if(e0)setDot(u,'nonhttp','?','Direct/VLC stream');
  return Promise.resolve()}
 var el=findDot(u);
 if(manual&&el){el.className='dot checking';el.textContent='\\u25CB'}
 var c=fresh(u);if(c&&!manual)return Promise.resolve();
 return fetch('/check?url='+encodeURIComponent(u)).then(function(r){return r.json()})
  .then(function(j){S.chk[u]={ok:j.ok,code:j.code,ms:j.ms,t:Date.now()};
   lsSet('iptv-chk',S.chk);
   setDot(u,j.ok===true?'online':(j.ok===false?'dead':'unknown'),
    j.ok===true?'\\u2713':(j.ok===false?'\\u2715':'~'),
    'HTTP '+j.code+(j.ms?', '+j.ms+' ms':''))})
  .catch(function(){})}

/* ===== ACTIONS ===== */
function pushHist(it,tp){if(!it||!it.u)return;
 S.hist=S.hist.filter(function(x){return x.u!==it.u});
 S.hist.unshift({n:it.n,u:it.u,l:it.l,g:it.g,tp:tp||it.tp||'tv'});
 S.hist=S.hist.slice(0,60);lsSet('iptv-hist',S.hist);buildTabs();
 if(S.pl==='recent'){buildChips();render(true)}}
function findAny(u){var pools=[cur(),S.favs,S.hist,S.chans];
 for(var p=0;p<pools.length;p++)
  for(var i=0;i<pools[p].length;i++)
   if(pools[p][i].u===u)return pools[p][i];
 return null}
var PLAYER={url:'',item:null};
function closePlayer(){
 var v=$('tvplayer');v.pause();v.removeAttribute('src');v.load();
 showModal('playermodal',false);PLAYER.url='';PLAYER.item=null}
window.closePlayer=closePlayer;
function vlcLink(u){
 var p=urlparseForPlayer(u);
 if(/Android/i.test(navigator.userAgent))
  return 'intent://'+p.hostpath+'#Intent;scheme='+p.scheme+
   ';package=org.videolan.vlc;end';
 if(/iPhone|iPad|iPod/i.test(navigator.userAgent))
  return 'vlc-x-callback://x-callback-url/stream?url='+encodeURIComponent(u);
 return '';
}
function urlparseForPlayer(u){
 var p=u.indexOf('://'),m=p>0?[u.slice(0,p),u.slice(p+3)]:null;
 return {scheme:m?m[0]:'http',hostpath:m?m[1]:u};
}
function playerPlay(){
 var v=$('tvplayer');
 if(!PLAYER.url)return;
 if(v.src!==PLAYER.url)v.src=PLAYER.url;
 v.preload='auto';v.play().catch(function(){
  $('playerhint').textContent='Tap the play button if autoplay is blocked by your browser.'
 });
 $('playerhint').textContent='Playing in the phone browser. Source quality is automatic.';
}
function openVlcMobile(){
 if(!PLAYER.url)return;
 var link=vlcLink(PLAYER.url);
 if(link){window.location.href=link;
  $('playerhint').textContent='If VLC is installed, your phone will open it. Otherwise use Play here.';
  return}
 $('playerhint').textContent='Your phone cannot launch VLC from this browser. Use Play here.';
}
function openPlayer(it,u){
 PLAYER.url=u;PLAYER.item=it;
 $('playertitle').textContent='Watch '+plain(it.n||'stream').slice(0,60);
 $('playerhint').textContent=/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
  ?'VLC can be opened when installed; otherwise play in this browser.'
  :'Choose a playback option.';
 $('playervlc').style.display=vlcLink(u)?'':'none';
 $('playerplay').style.display=/^https?:/i.test(u)?'':'none';
 $('playerexternal').style.display=/^https?:/i.test(u)?'':'none';
 showModal('playermodal',true);
 if(/^https?:/i.test(u))playerPlay();
}
$('tvplayer').addEventListener('waiting',function(){
 $('playerhint').textContent='Buffering... keeping the stream ready.';
});
$('tvplayer').addEventListener('canplay',function(){
 $('playerhint').textContent='Playing. Source quality is automatic.';
});
$('tvplayer').addEventListener('error',function(){
 $('playerhint').textContent='Stream paused. Try Play here again or open VLC.';
});
$('playerfit').onchange=function(){$('tvplayer').style.objectFit=this.value};
$('playerspeed').onchange=function(){$('tvplayer').playbackRate=parseFloat(this.value)};
$('playerplay').onclick=playerPlay;
$('playervlc').onclick=openVlcMobile;
$('playerexternal').onclick=function(){
 if(PLAYER.url)window.open(PLAYER.url,'_blank','noopener')};
function route(it,u){
 var tp=it.tp||plTypeOf(S.pl)||'tv';
 if(tp==='radio'){radioPlay(it);return}
 if(ISMOBILE){
  pushHist(it,'tv');openPlayer(it,u);return}
 if(IS_CLOUD){
  if(/^https?:/i.test(u)){toast('Opening stream...');pushHist(it,'tv');window.open(u,'_blank','noopener');}
  else toast('This stream requires VLC on a local PC','bad');
  return}
 toast('Opening '+plain(esc(it.n)).slice(0,40)+'...');
 fetch('/play?url='+encodeURIComponent(u)).then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad');
  if(j.ok)pushHist(it,'tv')})
 .catch(function(){toast('Server not running','bad')})}
function toggleFav(u){var i=-1;
 for(var k=0;k<S.favs.length;k++)if(S.favs[k].u===u){i=k;break}
 if(i>=0){S.favs.splice(i,1);toast('Removed from favorites')}
 else{var src=cur();
  for(var k2=0;k2<src.length;k2++)if(src[k2].u===u){
   var o=src[k2];o.tp=o.tp||plTypeOf(S.pl);
   S.favs.unshift({n:o.n,u:o.u,l:o.l,g:o.g,tp:o.tp});
   toast('\\u2605 Added to favorites');break}}
 lsSet('iptv-favs',S.favs);
 document.querySelectorAll('.fav').forEach(function(b){
  b.classList.toggle('on',S.favs.some(function(f){return f.u===b.dataset.u}))});
 if(S.pl==='favs'){buildChips();render(true)}
 buildTabs()}
window.clearHist=function(){S.hist=[];lsSet('iptv-hist',S.hist);
 buildTabs();buildChips();render(true);toast('History cleared')};
window.wbDone=function(){lsSet('iptv-welcomed',1);showModal('welcome',false)};
window.addCustom=function(){
 var u=$('seturl').value.trim(),n=$('setname').value.trim()||'My IPTV';
 if(u.indexOf('://')<0){toast('Enter a valid http(s) URL','bad');return}
 fetch('/add?url='+encodeURIComponent(u)+'&name='+encodeURIComponent(n))
 .then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad');
  if(j.ok)setTimeout(function(){location.reload()},900)})};

/* ===== GUIDE ===== */
function openGuide(){
 if(!isTV(S.pl)||S.pl==='world'){
  $('glist').innerHTML='<p style="color:var(--mut)">Open a TV tab (not Worldwide).</p>';
  showModal('guidepanel',true);return}
 showModal('guidepanel',true);
 $('gstat').textContent='Loading guide (first time ~10-40s)...';
 $('glist').innerHTML='';
 fetch('/api/now?p='+S.pl).then(function(r){return r.json()})
 .then(function(x){
  if(x.status==='loading'){$('gstat').textContent='Still loading...';
   setTimeout(openGuideRefresh,5000);return}
  if(x.status!=='ready'){$('gstat').innerHTML='Guide unavailable: '+
   esc(x.status)+' <button class="mini" onclick="openGuide()">Retry</button>';return}
  S.now=x.channels||{};$('gstat').textContent='';paintNow();drawGuide()})
 .catch(function(){$('gstat').textContent='Could not reach server.'})}
function openGuideRefresh(){
 if($('guidepanel').className.indexOf('open')<0)return;
 fetch('/api/now?p='+S.pl).then(function(r){return r.json()})
 .then(function(x){
  if(x.status==='ready'){S.now=x.channels||{};
   $('gstat').textContent='';paintNow();drawGuide()}
  else if(x.status==='loading')setTimeout(openGuideRefresh,5000)
  else $('gstat').innerHTML='Guide unavailable: '+esc(x.status)+
   ' <button class="mini" onclick="openGuide()">Retry</button>'})}
function drawGuide(){
 var q=norm($('gsearch').value),rows=[],src=cur();
 for(var i=0;i<src.length;i++){
  var a=nowFor(src[i]);
  if(a&&(a.n||a.x)){
   if(q&&norm(src[i].n).indexOf(q)===-1)continue;
   rows.push({n:src[i].n,u:src[i].u,a:a});if(rows.length>=200)break}}
 var h='';
 for(var r2=0;r2<rows.length;r2++){var rr=rows[r2];
  h+='<div class="grow" data-u="'+esc(rr.u)+'"><b title="'+esc(rr.n)+'">'+
   esc(rr.n)+'</b>'+
   '<span class="np">'+(rr.a.n?('\\u25B6 '+esc(rr.a.n.t)+
    ' <span class=tm>till '+hhmm(rr.a.n.e)+'</span>'):'')+'</span>'+
   '<span class="nx">'+(rr.a.x?('next: '+esc(rr.a.x.t)+
    ' <span class=tm>@ '+hhmm(rr.a.x.s)+'</span>'):'')+'</span></div>'}
 $('glist').innerHTML=h||'<p style="color:var(--mut)">No guide data matched.</p>'}
$('gsearch').addEventListener('input',function(){
 if($('guidepanel').className.indexOf('open')>-1)drawGuide()});
$('glist').onclick=function(e){var r=e.target.closest('.grow');
 if(!r||!r.dataset.u)return;var it=findAny(r.dataset.u);
 if(it)route(it,r.dataset.u)};

/* ================= NEWS PANEL ================= */
var NEWS={cat:'top',items:[],loaded:false};
var NCATS=[['top','Top'],['india','India'],['business','Business'],
 ['markets','Markets'],['tech','Tech'],['sports','Sports'],
 ['world','World'],
 ['hindi','&#2361;&#2367;&#2344;&#2381;&#2342;&#2368;']];
function nChips(){var h='';
 NCATS.forEach(function(c){
  h+='<button data-c="'+c[0]+'" class="'+(NEWS.cat===c[0]?'active':'')+
   '">'+c[1]+'</button>'});
 $('nchips').innerHTML=h}
function nShow(cat){NEWS.cat=cat;nChips();
 $('nlist').innerHTML='<div class="pempty">Loading&#8230;</div>';
 fetch('/api/news?cat='+cat).then(function(r){return r.json()})
 .then(function(j){NEWS.items=j.items||[];NEWS.loaded=true;nPaint()})
 .catch(function(){$('nlist').innerHTML=
  '<div class="pempty">Could not load news.<br><button class="big" '+
  'onclick="nShow(NEWS.cat)">Retry</button></div>'})}
window.nShow=nShow;
function agoT(ep){if(!ep)return'';
 var m=Math.floor((Date.now()-ep*1000)/60000);
 if(m<1)return'now';if(m<60)return m+'m';
 var h=(m/60)|0;if(h<24)return h+'h';return((h/24)|0)+'d'}
function nPaint(){
 var q=$('nq').value.trim().toLowerCase(),idxs=[];
 for(var i=0;i<NEWS.items.length;i++){var it=NEWS.items[i];
  if(q&&(it.t+' '+it.s+' '+(it.b||'')).toLowerCase().indexOf(q)===-1)continue;
  idxs.push(i)}
 if(!idxs.length){$('nlist').innerHTML=
  '<div class="pempty">Nothing matched.</div>';return}
 var h='';
 for(var k=0;k<idxs.length;k++){var i2=idxs[k],a=NEWS.items[i2];
  var thumb=a.d?'<img src="'+esc(a.d)+'" loading="lazy" '+
   'onerror="this.remove()">':'';
  h+='<article class="ni'+(k===0&&!q?' hero':'')+'" data-i="'+i2+'">'+
   thumb+'<div class="nitxt"><h3>'+esc(a.t)+'</h3>'+
   (k===0&&!q&&a.b?'<p>'+esc(a.b)+'</p>':'')+
   '<span class="nimeta">'+esc(a.s)+(a.pub?' &middot; '+agoT(a.pub):'')+
   '</span></div></article>'}
 $('nlist').innerHTML=h}
$('nchips').onclick=function(e){var b=e.target.closest('button');
 if(b)nShow(b.dataset.c)};
$('nq').addEventListener('input',function(){clearTimeout(window._nqt);
 window._nqt=setTimeout(nPaint,180)});
$('nlist').onclick=function(e){var a=e.target.closest('.ni');if(!a)return;
 nOpen(parseInt(a.dataset.i,10))};
function nOpen(i){var a=NEWS.items[i];if(!a)return;
 $('rvtitle').textContent=a.t;
 $('rvmeta').textContent=a.s+(a.pub?(' - '+new Date(a.pub*1000)
  .toLocaleString()):'');
 $('rvbody').textContent=a.b||'Full story at source.';
 $('rvlink').href=/^https?:/.test(a.l)?a.l:'#';
 showModal('readerview',true)}
window.nOpen=nOpen;
(function(){var fs=parseInt(localStorage.getItem('srt-nfs')||'15',10);
 function ap(){$('rvbody').style.fontSize=fs+'px'}ap();
 $('rvfm').onclick=function(){fs=Math.max(12,fs-1);ap();
  localStorage.setItem('srt-nfs',fs)};
 $('rvfp').onclick=function(){fs=Math.min(24,fs+1);ap();
  localStorage.setItem('srt-nfs',fs)}})();

var POD={loaded:false};
function podShow(){
 $('podlist').innerHTML='<div class="pempty">Loading podcasts...</div>';
 fetch('/api/podcasts').then(function(r){return r.json()})
  .then(function(j){
   POD.loaded=true;var h='',items=j.items||[];
   for(var i=0;i<items.length;i++){var a=items[i];
    h+='<article class="podcard">'+(a.d?'<img src="'+esc(a.d)+
     '" loading="lazy" onerror="this.remove()">':'')+
     '<div class="podtext"><b>'+esc(a.t)+'</b><div class="nimeta">'+
     esc(a.s)+(a.pub?' &middot; '+agoT(a.pub):'')+'</div>'+
     (a.b?'<p>'+esc(a.b)+'</p>':'')+'</div>'+
     (a.audio?'<audio controls preload="none" src="'+esc(a.audio)+'"></audio>':'')+
     (a.l?'<a class="big blue" target="_blank" rel="noopener" href="'+
      esc(a.l)+'">Open</a>':'')+'</article>'}
   $('podlist').innerHTML=h||'<div class="pempty">No podcast episodes available.</div>'})
  .catch(function(){$('podlist').innerHTML=
   '<div class="pempty">Could not load podcasts. Try again later.</div>'})}

/* ================= MARKETS PANEL ================= */
var MKT={timer:null,rows:null,watch:[]};
try{MKT.watch=JSON.parse(localStorage.getItem('srt-watch')||'null')||[]}
catch(e){}
if(!MKT.watch.length)MKT.watch=['RELIANCE.NS','TCS.NS','INFY.NS',
 'HDFCBANK.NS','AAPL','MSFT','NVDA'];
var IDX_IN=[['^NSEI','NIFTY 50'],['^BSESN','SENSEX'],
 ['^NSEBANK','BANK NIFTY'],['INR=X','USD/INR']];
var IDX_US=[['^DJI','DOW JONES'],['^GSPC','S&P 500'],['^IXIC','NASDAQ']];
function mkSyms(){return IDX_IN.concat(IDX_US).concat(
 MKT.watch.map(function(s){return[s,s]}))}
function money(n,cur){
 if(n==null||isNaN(n))return'-';
 var s=(Math.abs(n)>=1000)?
  n.toLocaleString('en-IN',{maximumFractionDigits:2}):n.toFixed(2);
 return(cur==='INR'?'\\u20B9':cur==='USD'?'$':'')+s}
function chgHtml(pr,pv){
 if(pr==null||!pv)return'<span class="mchg">-</span>';
 var d=pr-pv,p=d/pv*100,up=d>=0;
 return'<span class="mchg '+(up?'up':'down')+'">'+
  (up?'\\u25B2 ':'\\u25BC ')+Math.abs(p).toFixed(2)+'%</span>'}
function sparkV(vals,w,h){
 if(!vals||vals.length<2)return'';
 var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals);
 var rng=(mx-mn)||1,col=vals[vals.length-1]>=vals[0]?'#16a34a':'#dc2626';
 var pts=[];
 for(var i=0;i<vals.length;i++){
  pts.push(((i/(vals.length-1))*w).toFixed(1)+','+
   (h-3-((vals[i]-mn)/rng)*(h-6)).toFixed(1))}
 return'<svg width="'+w+'" height="'+h+'"><polyline fill="none" stroke="'+
  col+'" stroke-width="2" points="'+pts.join(' ')+'"/></svg>'}
function barV(vals,w,h){
 if(!vals||vals.length<2)return'';
 var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
 var step=w/vals.length,b='';
 for(var i=0;i<vals.length;i++){
  var bh=Math.max(2,((vals[i]-mn)/rng)*(h-8));
  b+='<rect x="'+(i*step).toFixed(1)+'" y="'+(h-bh).toFixed(1)+
  '" width="'+Math.max(1,step-1).toFixed(1)+'" height="'+bh.toFixed(1)+
  '" fill="'+(vals[i]>=vals[0]?'#16a34a':'#dc2626')+'"/>'}
 return'<svg width="'+w+'" height="'+h+'">'+b+'</svg>'}
function mkRow(q,label,canRm){
 var live=q.state==='REGULAR'||q.state==='OPEN';
 return'<div class="mkrow" data-sym="'+esc(q.sym)+'">'+
  '<div class="mkid"><b>'+esc(label||q.name||q.sym)+'</b>'+
  '<span class="mkst '+(live?'live':'off')+'">'+(live?'LIVE':'CLOSED')+
  '</span>'+(canRm?'<button class="rm" data-sym="'+esc(q.sym)+
  '" title="Remove">\\u2715</button>':'')+'</div>'+
  '<div class="mknum"><span class="mkp">'+money(q.price,q.cur)+'</span>'+
  chgHtml(q.price,q.prev)+'</div>'+
  '<div class="mksk">'+sparkV(q.cl40,120,36)+'</div></div>'}
function mkPaint(){
 if(!MKT.rows)$('mkwrap').innerHTML=
  '<div class="pempty">Loading quotes&#8230;</div>';
 else mkRender()}
function mkRender(){
 var by={};(MKT.rows||[]).forEach(function(r){by[r.sym]=r});
 function sec(t,list,rm){
  var h='<h4 class="mksec">'+t+'</h4>';
  list.forEach(function(p){var q=by[p[0]];
   if(!q){h+='<div class="mkrow na"><div class="mkid"><b>'+esc(p[1])+
    '</b></div><span>unavailable</span></div>';return}
   h+=mkRow(q,p[1],rm)});
  return h}
 $('mkwrap').innerHTML=
  sec('&#127470;&#127475; INDIA',IDX_IN,false)+
  sec('&#127482;&#127480; US MARKETS',IDX_US,false)+
  '<h4 class="mksec">&#9733; MY WATCHLIST'+
  '<button class="mini" id="mkadd">+ add symbol</button></h4>'+
  (MKT.watch.length?
   MKT.watch.map(function(s){var q=by[s];
    return q?mkRow(q,null,true):
     '<div class="mkrow na"><div class="mkid"><b>'+esc(s)+
     '</b></div><span>unavailable</span></div>'}).join(''):
   '<div class="pempty">Tap + add to track stocks</div>');
 var ad=$('mkadd');if(ad)ad.onclick=mkAdd}
function saveWatch(){localStorage.setItem('srt-watch',
 JSON.stringify(MKT.watch))}
function mkRefresh(){
 fetch('/api/markets?symbols='+
  encodeURIComponent(mkSyms().map(function(p){return p[0]}).join(',')))
 .then(function(r){return r.json()})
 .then(function(j){MKT.rows=j.quotes||[];mkRender()})
 .catch(function(){$('mkwrap').innerHTML=
  '<div class="pempty">Quotes unavailable right now.<br>'+
  '<button class="big" onclick="mkRefresh()">Retry</button></div>'})}
window.mkRefresh=mkRefresh;
function mkStart(){mkRefresh();clearInterval(MKT.timer);
 MKT.timer=setInterval(function(){if(MODE==='markets')mkRefresh()},60000)}
function mkStop(){clearInterval(MKT.timer)}
function mkAdd(){
 var s=(prompt('Stock symbol:\\nIndia: TATAMOTORS.NS, WIPRO.NS, SBIN.NS\\nUS: GOOG, AMZN, TSLA')||'').trim().toUpperCase();
 if(!s)return;
 if(!/^[A-Z0-9^.=-]{1,15}$/.test(s)){toast('Invalid symbol','bad');return}
 if(MKT.watch.indexOf(s)<0){MKT.watch.push(s);saveWatch();mkRefresh()}}
function mkRemove(sym){
 MKT.watch=MKT.watch.filter(function(x){return x!==sym});
 saveWatch();mkRefresh()}
$('mkwrap').onclick=function(e){
 if(e.target.id==='mkadd')return mkAdd();
 var rm=e.target.closest('.rm');
 if(rm)return mkRemove(rm.dataset.sym);
 var r=e.target.closest('.mkrow');
 if(r&&!r.classList.contains('na'))openChart(r.dataset.sym)};
/* market news sidebar */
function mkNews(){
 fetch('/api/news?cat=markets').then(function(r){return r.json()})
 .then(function(j){
  var it=(j.items||[]).slice(0,6),h='';
  for(var i=0;i<it.length;i++){
   h+='<article class="ni" data-mkl="'+esc(it[i].l)+'"><div class="nitxt">'+
    '<h3>'+esc(it[i].t)+'</h3><span class="nimeta">'+esc(it[i].s)+
    (it[i].pub?' &middot; '+agoT(it[i].pub):'')+'</span></div></article>'}
  $('mknews').innerHTML=h||
   '<div class="pempty">No market news loaded.</div>';
  var as=$('mknews').querySelectorAll('.ni');
  for(var k=0;k<as.length;k++)as[k].onclick=function(){
   var l=this.dataset.mkl;
   if(/^https?:/.test(l))window.open(l,'_blank','noopener')}})
 .catch(function(){$('mknews').innerHTML=
  '<div class="pempty">news unavailable</div>'})}
/* chart modal */
var CR={'1D':['1d','5m'],'5D':['5d','15m'],'1M':['1mo','60m'],
 '6M':['6mo','1d'],'1Y':['1y','1d']};
var CS={sym:null,range:'1M',type:'line'};
function openChart(sym){
 CS.sym=sym;CS.range='1M';
 $('chartsym').textContent=sym;
 showModal('chartmodal',true);loadChart()}
window.openChart=openChart;
function loadChart(){
 var rr=CR[CS.range],ph='';
 for(var k in CR)ph+='<button data-r="'+k+'" class="'+
  (k===CS.range?'active':'')+'">'+k+'</button>';
 $('chartpills').innerHTML=ph;
 var pb=$('chartpills').querySelectorAll('button');
 for(var i=0;i<pb.length;i++)pb[i].onclick=function(){
  CS.range=this.dataset.r;loadChart()};
 document.querySelectorAll('[data-ct]').forEach(function(b){
  b.className='mini '+(b.dataset.ct===CS.type?'active':'');
  b.onclick=function(){CS.type=this.dataset.ct;loadChart()}});
 $('bigchart').innerHTML='<div class="pempty">Loading&#8230;</div>';
 $('chkstats').textContent='';
 fetch('/api/mchart?sym='+encodeURIComponent(CS.sym)+
  '&range='+rr[0]+'&interval='+rr[1])
 .then(function(r){return r.json()})
 .then(function(j){
  var cl=j.cl||[];
  if(cl.length<2){$('bigchart').innerHTML=
   '<div class="pempty">No chart data</div>';return}
  $('bigchart').innerHTML=CS.type==='bar'?barV(cl,560,220):sparkV(cl,560,220);
  var lo=Math.min.apply(null,cl),hi=Math.max.apply(null,cl);
  $('chkstats').innerHTML='<b>'+money(j.price,j.cur)+'</b>'+
   chgHtml(j.price,j.prev)+'<span>low '+money(lo,j.cur)+'</span>'+
   '<span>high '+money(hi,j.cur)+'</span>'+
   (j.state?'<span>'+esc(j.state)+'</span>':'')+
   (j.name?'<span>'+esc(j.name)+'</span>':'')+
   (j.exchangeName?'<span>'+esc(j.exchangeName)+'</span>':'')})
 .catch(function(){$('bigchart').innerHTML=
  '<div class="pempty">Failed to load</div>'})}

/* ================= BOOKS PANEL ================= */
var BK={init:false,q:'',lang:'en,hi',page:1,hasNext:false,hasPrev:false,
 items:[],cur:null,pages:1,pg:0,total:0,
 rfs:parseInt(localStorage.getItem('srt-rfs')||'18',10)};
function bLangBtns(){var h='';
 [['en,hi','All'],['en','English'],
  ['hi','&#2361;&#2367;&#2344;&#2381;&#2342;&#2368;']].forEach(function(p){
  h+='<button data-l="'+p[0]+'" class="'+(BK.lang===p[0]?'active':'')+
   '">'+p[1]+'</button>'});
 $('bklang').innerHTML=h}
function bInit(){
 BK.init=true;
 var sv=localStorage.getItem('srt-blang');
 if(sv)BK.lang=sv;
 bLangBtns();bRestoreStrip();bSearch(true)}
function bSearch(reset){
 if(reset)BK.page=1;
 $('bkgrid').innerHTML='<div class="pempty">Searching&#8230;</div>';
 var u='/api/books?page='+BK.page+'&lang='+encodeURIComponent(BK.lang);
 if(BK.q)u+='&q='+encodeURIComponent(BK.q);
 fetch(u).then(function(r){return r.json()})
 .then(function(j){BK.items=j.items||[];
  BK.hasNext=!!j.next;BK.hasPrev=!!j.prev;bPaint();bPager()})
 .catch(function(){$('bkgrid').innerHTML=
  '<div class="pempty">Could not reach library.<br>'+
  '<button class="big" onclick="bSearch(true)">Retry</button></div>'})}
window.bSearch=bSearch;
function bPager(){$('bkpage').textContent='Page '+BK.page;
 $('bkprev').disabled=!BK.hasPrev;$('bknext').disabled=!BK.hasNext}
function bPaint(){
 if(!BK.items.length){$('bkgrid').innerHTML=
  '<div class="pempty">No books found.</div>';return}
 var h='';
 for(var i=0;i<BK.items.length;i++){var b=BK.items[i];
  var pos=null;
  try{pos=JSON.parse(localStorage.getItem('srt-book-'+b.id)||'null')}
  catch(e){}
  h+='<div class="card book" data-id="'+b.id+'">'+
   (b.cov?'<img src="'+esc(b.cov)+'" loading="lazy" '+
    'onerror="this.replaceWith(document.createElement(\\'div\\'))">':
    '<div class="nocov">&#128214;</div>')+
   '<div class="cname" title="'+esc(b.t)+'">'+esc(b.t)+'</div>'+
   '<div class="grp">'+esc(b.a)+'</div>'+
   '<div class="grp">&#11015; '+(b.d||0).toLocaleString()+
   (pos&&pos.pc?' &middot; '+pos.pc+'%':'')+'</div>'+
   '<button class="watch" data-id="'+b.id+'">&#128214; '+
   (pos?'Continue':'Read')+'</button></div>'}
 $('bkgrid').innerHTML=h}
$('bkgrid').onclick=function(e){
 var c=e.target.closest('.book');if(!c)return;
 var t=c.querySelector('.cname');
 openBook(parseInt(c.dataset.id,10),t?t.textContent:'Book')};
$('bklang').onclick=function(e){var b=e.target.closest('button');if(!b)return;
 BK.lang=b.dataset.l;localStorage.setItem('srt-blang',BK.lang);
 bLangBtns();bSearch(true)};
$('bks').onclick=function(){BK.q=$('bq').value.trim();bSearch(true)};
var BQT=null;
$('bq').addEventListener('input',function(){clearTimeout(BQT);
 BQT=setTimeout(function(){BK.q=$('bq').value.trim();bSearch(true)},450)});
$('bkprev').onclick=function(){if(BK.hasPrev){BK.page--;bSearch(false)}};
$('bknext').onclick=function(){if(BK.hasNext){BK.page++;bSearch(false)}};
function bRestoreStrip(){
 var arr=[];
 try{
  for(var i=0;i<localStorage.length;i++){
   var k=localStorage.key(i);
   if(k&&k.indexOf('srt-book-')===0){
    var v=JSON.parse(localStorage.getItem(k)||'null');
    if(v&&v.pc>0&&v.pc<100&&v.t)
     arr.push({id:k.slice(9),pc:v.pc,t:v.t})}}}
 catch(e){}
 arr.sort(function(a,b){return b.pc-a.pc});
 if(!arr.length){$('bkcont').innerHTML='';return}
 var h='<b>Continue:</b>';
 arr.slice(0,4).forEach(function(p){
  h+='<button class="mini contb" data-id="'+p.id+'" data-t="'+
   esc(p.t)+'">'+esc(p.t.slice(0,22))+' '+p.pc+'%</button>'});
 $('bkcont').innerHTML=h;
 var bs=$('bkcont').querySelectorAll('.contb');
 for(var j=0;j<bs.length;j++)bs[j].onclick=function(){
  openBook(parseInt(this.dataset.id,10),this.dataset.t)}}
/* fullscreen reader */
function openBook(id,title){
 BK.cur={id:id,t:title};
 $('bvtitle').textContent=title;
 $('bookview').setAttribute('data-bv',
  localStorage.getItem('srt-bvtheme')||'paper');
 $('bvtext').style.fontSize=BK.rfs+'px';
 var pos=null;
 try{pos=JSON.parse(localStorage.getItem('srt-book-'+id)||'null')}
 catch(e){}
 loadPage(pos?pos.pg:0);
 $('bookview').style.display='flex';
 document.body.style.overflow='hidden'}
window.openBook=openBook;
function closeBook(){
 if(BK.cur)savePos();
 $('bookview').style.display='none';
 document.body.style.overflow=''}
window.closeBook=closeBook;
function savePos(){
 if(!BK.cur||!BK.total)return;
 var pc=Math.min(100,Math.round(((BK.pg+1)/BK.pages)*100));
 lsSet('srt-book-'+BK.cur.id,{pg:BK.pg,pc:pc,t:BK.cur.t});
 bRestoreStrip()}
function loadPage(pg){
 BK.pg=pg;
 $('bvtext').innerHTML='<div class="pempty">Loading&#8230;</div>';
 fetch('/api/booktext?id='+BK.cur.id+'&page='+pg)
 .then(function(r){return r.json()})
 .then(function(j){
  BK.pages=j.pages;BK.total=j.total;BK.pg=j.page;
  $('bvtext').textContent=j.text;
  $('bvtext').scrollTop=0;
  $('bvprog').textContent=(j.page+1)+' / '+j.pages+' pages';
  savePos()})
 .catch(function(){$('bvtext').innerHTML=
  '<div class="pempty">Failed to load text.</div>'})}
$('bvprev').onclick=function(){if(BK.pg>0)loadPage(BK.pg-1)};
$('bvnext').onclick=function(){if(BK.pg<BK.pages-1)loadPage(BK.pg+1)};
$('bvclose').onclick=closeBook;
$('bvfa').onclick=function(){BK.rfs=Math.max(12,BK.rfs-2);
 $('bvtext').style.fontSize=BK.rfs+'px';
 localStorage.setItem('srt-rfs',BK.rfs)};
$('bvfb').onclick=function(){BK.rfs=Math.min(30,BK.rfs+2);
 $('bvtext').style.fontSize=BK.rfs+'px';
 localStorage.setItem('srt-rfs',BK.rfs)};
$('bvtheme').onclick=function(){
 var T=['paper','sepia','night'];
 var cur=$('bookview').getAttribute('data-bv')||'paper';
 $('bookview').setAttribute('data-bv',
  T[(T.indexOf(cur)+1)%T.length]);
 localStorage.setItem('srt-bvtheme',
  $('bookview').getAttribute('data-bv'))};

/* ===== CHECKS / WELCOME ===== */
function runChecks(){
 fetch('/api/health').then(function(r){return r.json()}).then(function(j){
  var row=function(l,v,t){return '<div class="wb"><span>'+l+
   '</span><b class="'+v+'">'+t+'</b></div>'};
  $('wbchecks').innerHTML=
   row('Internet',j.net?'pass':'fail',j.net?'OK':'offline?')+
   row('VLC on PC',j.vlc?'pass':'warn',
    j.vlc?'found':'not found (TV needs it)')+
   row('Phone access',(j.lan||j.ts)?'pass':'warn',
    j.ts?'Wi-Fi + Anywhere ready':(j.lan?'home Wi-Fi ready':'no network'))+
   row('Firewall rule',j.fw?'pass':'warn',j.fw?'exists':'may need rule')+
   row('TV+Radio DB',j.radio?'pass':'warn',
    j.radio?'reachable':'blocked?')+
   row('News RSS',j.news?'pass':'warn',j.news?'OK':'blocked?')+
   row('Markets API',j.yax?'pass':'warn',j.yax?'OK':'blocked?')+
   row('Books API',j.books?'pass':'warn',j.books?'OK':'blocked?')})
 .catch(function(){$('wbchecks').innerHTML=
  '<p>Could not run checks.</p>'})}
function maybeWelcome(){
 if(!localStorage.getItem('iptv-welcomed')){
  showModal('welcome',true);runChecks()}}
$('help').onclick=function(){runChecks();showModal('welcome',true)};
$('home').onclick=function(){setMode('tv');load('in');
 window.scrollTo(0,0)};

/* ===== LOAD SOURCE (media) ===== */
function load(pl){S.pl=pl;S.cat='all';S.q='';$('q').value='';
 buildTabs();
 $('playall').disabled=(pl==='favs'||pl==='recent');
 document.title=plain(pl==='favs'?T_FAV:pl==='recent'?T_REC:
  (PL[pl]?PL[pl].n:'Sunrise'))+' - Sunrise Hub';
 if(pl==='favs'||pl==='recent'){S.now={};buildChips();render(true);return}
 if(S.cache[pl]){S.chans=S.cache[pl];S.now={};buildChips();render(true);
  if(isTV(pl))loadNow();return}
 $('loader').style.display='grid';
 fetch('/api/channels?p='+pl).then(function(r){if(!r.ok)throw 0;return r.json()})
 .then(function(j){S.chans=j.channels.map(function(c){
   return{n:c.name,u:c.url,l:c.logo,g:c.group,lg:c.lang||'',id:c.id||''}});
  S.cache[pl]=S.chans;
  $('loader').style.display='none';
  if(isTV(pl)){S.now={};loadNow()}
  buildChips();render(true)})
 .catch(function(){$('loader').style.display='none';
  $('grid').innerHTML='<div class="errbox"><h3>Could not load</h3>'+
   '<br>Check your internet connection.<br><br>'+
   '<button class="big" onclick="load(\\''+pl+'\\')">Retry</button></div>'})}

/* ===== EVENTS ===== */
$('mainnav').onclick=function(e){
 var b=e.target.closest('button');if(b)setMode(b.dataset.mode)};
$('tabs').onclick=function(e){if(e.target.dataset.pl)load(e.target.dataset.pl)};
$('chips').onclick=function(e){var b=e.target.closest('button');if(!b)return;
 S.cat=b.dataset.c;buildChips();render(true)};
$('grid').onclick=function(e){
 var v=e.target.closest('.altvlc');
 if(v){fetch('/play?url='+encodeURIComponent(v.dataset.vlc))
  .then(function(r){return r.json()})
  .then(function(j){toast(j.msg,j.ok?'ok':'bad')});return}
 var w=e.target.closest('.watch');
 if(w)return route(findAny(w.dataset.u)||{n:'?',u:w.dataset.u},w.dataset.u);
 var f=e.target.closest('.fav');if(f)return toggleFav(f.dataset.u);
 var d=e.target.closest('.dot');if(d)return test(d.dataset.u,true)};
$('q').addEventListener('input',function(){clearTimeout(window._qt);
 window._qt=setTimeout(function(){
  S.q=$('q').value.trim();
  if(!S.q)S.cat='all';
  buildChips();render(true)},200)});
document.addEventListener('keydown',function(e){
 if($('bookview').style.display==='flex'){
  if(e.key==='ArrowRight'&&BK.pg<BK.pages-1)loadPage(BK.pg+1);
  if(e.key==='ArrowLeft'&&BK.pg>0)loadPage(BK.pg-1);
  if(e.key==='Escape')closeBook();
  return}
 if(e.key==='/'&&!ISMOBILE&&document.activeElement!==$('q')&&
  MODE==='media'){e.preventDefault();$('q').focus()}
 if(e.key==='Escape'){
  ['mobpanel','guidepanel','setpanel','welcome','readerview','chartmodal','playermodal']
   .forEach(function(m){showModal(m,false)});
  if(document.activeElement===$('q')&&MODE==='media'){
   $('q').value='';$('q').dispatchEvent(new Event('input'))}}});
$('okfirst').addEventListener('change',function(){render(true)});
$('mob').onclick=function(){showModal('mobpanel',true)};
$('set').onclick=function(){showModal('setpanel',true)};
$('guide').onclick=openGuide;
$('more').onclick=function(){showModal('utilitypanel',true)};
$('moreguide').onclick=function(){showModal('utilitypanel',false);openGuide()};
$('moreset').onclick=function(){showModal('utilitypanel',false);showModal('setpanel',true)};
$('moretheme').onclick=function(){showModal('utilitypanel',false);$('themebtn').click()};
$('morehelp').onclick=function(){showModal('utilitypanel',false);runChecks();showModal('welcome',true)};
$('playall').onclick=function(){
 if(S.pl==='favs'||S.pl==='recent')return;
 if(ISMOBILE&&!confirm('Play this list on the PC?'))return;
 fetch('/playall?p='+S.pl).then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad')})};
$('quit').onclick=function(){
 if(!confirm('Stop the Sunrise server for ALL devices?'))return;
 fetch('/quit').then(function(){toast('Server stopped','ok')})};
new IntersectionObserver(function(es){es.forEach(function(e){
 if(e.isIntersecting&&S.shown<filtered().length)render(false)})
 }).observe($('sentinel'));

(function(){
 if(ISMOBILE||IS_CLOUD){$('quit').style.display='none'}
 if(ISMOBILE){$('mob').style.display='none';$('setupPhone').style.display='none'}
 if(IS_CLOUD){$('playall').style.display='none';$('pbvlc').style.display='none'}
 var h='';
 for(var k in PL)h+='<a class="big '+(PL[k].t==='radio'?'cy':'blue')+
  '" href="/m3u?p='+k+'">&#11015; '+plain(PL[k].n)+' (.m3u)</a>';
 $('mlinks').innerHTML=h;
})();
window.load=load;load('in');setMode('tv');maybeWelcome();
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        d = body.encode("utf-8", errors="replace") if isinstance(body, str) \
            else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(d)))
        for k, v in (extra or []): self.send_header(k, v)
        self.end_headers()
        try: self.wfile.write(d)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        global SRV
        u  = urlparse(self.path)
        qs = parse_qs(u.query)

        if u.path == "/healthz":
            return self.send(200, "ok", "text/plain; charset=utf-8")

        if u.path == "/":
            pl_json = json.dumps(
                {k: {"n": v["name"],
                     "t": "radio" if k in RADIO_SOURCES else "tv"}
                 for k, v in ALLSRC.items()},
                ensure_ascii=True).replace("</", "<\\/")
            blocks = []
            def add_qr(label, url):
                if not url: return
                tag, how = qr_img_tag(url)
                blocks.append('<div class="qrbox">%s<div class="cap"><b>%s'
                              '</b><br>%s</div></div>' % (tag, label, how))
            if IS_CLOUD:
                host = self.headers.get("Host", "").strip()
                public_url = "https://%s/" % host if host else ""
                add_qr("Public URL", public_url)
            else:
                add_qr("Home Wi-Fi",
                        "http://%s:%d/" % (LAN_IP, PORT) if LAN_IP else "")
                add_qr("Anywhere (Tailscale)",
                        "http://%s:%d/" % (TS_IP, PORT) if TS_IP else "")
            if not blocks:
                blocks.append("<p style='color:#f59e0b'>No network detected.</p>")
            page = (SHELL.replace("__PL__", pl_json)
                         .replace("__QRBLOCKS__", "".join(blocks))
                         .replace("__CLOUD__", "true" if IS_CLOUD else "false"))
            self.send(200, page)

        elif u.path == "/add":
            url = qs.get("url", [""])[0].strip()
            name = re.sub(r'[<>&"\']', "",
                          qs.get("name", ["My IPTV"])[0]).strip()[:40] \
                          or "My IPTV"                       # QA fix #3
            if urlparse(url).scheme not in ("http", "https"):
                return self.send(400,
                    '{"ok":false,"msg":"URL must be http(s)"}',
                    "application/json")
            d = load_custom()
            d["c%d" % int(time.time())] = {"name": name, "url": url}
            save_custom(d); rebuild_sources()
            self.send(200, '{"ok":true,"msg":"Playlist added"}',
                      "application/json")

        elif u.path == "/api/news":
            try:
                items = fetch_news(qs.get("cat", ["top"])[0])
                self.send(200, json.dumps({"count": len(items),
                                           "items": items},
                                          ensure_ascii=True),
                          "application/json")
            except Exception as e:
                self.send(502, json.dumps({"error": str(e)[:80]}),
                          "application/json")

        elif u.path == "/api/podcasts":
            try:
                items = fetch_podcasts()
                self.send(200, json.dumps({"count": len(items), "items": items},
                                          ensure_ascii=True), "application/json")
            except Exception as e:
                self.send(502, json.dumps({"error": str(e)[:80]}),
                          "application/json")

        elif u.path == "/api/markets":
            syms = [s.strip()
                    for s in qs.get("symbols", [""])[0].split(",")
                    if s.strip()][:20]
            if not syms:
                return self.send(400, '{"error":"no symbols"}',
                                 "application/json")
            def one(s):
                try: return yf_chart(s)
                except Exception: return None
            out = []
            with ThreadPoolExecutor(max_workers=6) as ex:
                for r in ex.map(one, syms):
                    if r is None: continue
                    r["cl40"] = r.pop("cl", [])[-40:]
                    r.pop("ts", None)
                    out.append(r)
            self.send(200, json.dumps({"quotes": out},
                                      ensure_ascii=True),
                      "application/json")

        elif u.path == "/api/mchart":
            sym = qs.get("sym", [""])[0][:20]
            rng = qs.get("range", ["1mo"])[0]
            itv = qs.get("interval", ["1d"])[0]
            if (not sym or rng not in ("1d", "5d", "1mo", "6mo", "1y")
                    or itv not in ("5m", "15m", "60m", "1d", "1wk")):
                return self.send(400, '{"error":"bad params"}',
                                 "application/json")
            try:
                self.send(200, json.dumps(yf_chart(sym, rng, itv),
                                          ensure_ascii=True),
                          "application/json")
            except Exception as e:
                self.send(502, json.dumps({"error": str(e)[:80]}),
                          "application/json")

        elif u.path == "/api/books":
            qstr = qs.get("q", [""])[0].strip()[:60]
            lang = qs.get("lang", ["en,hi"])[0]
            if lang not in ("en", "hi", "en,hi"): lang = "en,hi"
            try:
                page = min(50, max(1, int(qs.get("page", ["1"])[0] or 1)))
            except Exception:
                page = 1
            params = {"languages": lang, "page": page}
            if qstr: params["search"] = qstr
            else:    params["sort"] = "popular"
            try:
                j = gutendex(params)
                items = []
                for g in j.get("results", []):
                    au = (g.get("authors") or [{}])[0].get("name", "Unknown")
                    items.append({"id": g.get("id"),
                                  "t": (g.get("title") or "?")[:90],
                                  "a": au,
                                  "cov": (g.get("formats") or {})
                                         .get("image/jpeg", ""),
                                  "d": g.get("download_count", 0)})
                self.send(200, json.dumps(
                    {"total": j.get("count", 0),
                     "next": bool(j.get("next")),
                     "prev": bool(j.get("previous")),
                     "items": items}, ensure_ascii=True),
                    "application/json")
            except Exception as e:
                self.send(502, json.dumps({"error": str(e)[:80]}),
                          "application/json")

        elif u.path == "/api/booktext":
            try:
                bid = int(qs.get("id", ["0"])[0])
            except Exception:
                bid = 0
            if bid <= 0:
                return self.send(400, '{"error":"bad id"}',
                                 "application/json")
            try:
                txt = book_text(bid)
            except Exception as e:
                return self.send(502, json.dumps({"error": str(e)[:90]}),
                                 "application/json")
            size = 8000
            total = len(txt)
            pages = max(1, (total + size - 1) // size)
            try:
                page = min(pages - 1, max(0, int(qs.get("page", ["0"])[0])))
            except Exception:
                page = 0
            self.send(200, json.dumps(
                {"id": bid, "page": page, "pages": pages,
                 "total": total,
                 "text": txt[page*size:(page+1)*size]},
                ensure_ascii=True), "application/json")

        elif u.path == "/api/health":
            def _p(f):
                try: return bool(f())
                except Exception: return False
            self.send(200, json.dumps({
                "vlc": bool(VLC) and not IS_CLOUD, "lan": LAN_IP, "ts": TS_IP,
                "net": _p(net_ok), "fw": True if IS_CLOUD else _fw_ok(), "radio": _p(_radio_ok),
                "news": _p(lambda: len(fetch_news("top")) > 0),
                "yax": _p(lambda: (yf_chart("^NSEI") or {}).get("price")),
                "books": _p(lambda: (gutendex({"languages": "hi"}) or {})
                            .get("count", 0) > 100)},
                ensure_ascii=True), "application/json")

        elif u.path == "/m3u":
            key = qs.get("p", ["in"])[0]
            if key not in ALLSRC: return self.send(404, "unknown source")
            try: chans = get_channels(key)
            except Exception as e: return self.send(502, "source error: %s" % e)
            self.send(200, build_m3u(chans),
                      "audio/x-mpegurl; charset=utf-8",
                      [("Content-Disposition",
                        'attachment; filename="iptv-%s.m3u"' % key)])

        elif u.path == "/api/channels":
            key = qs.get("p", ["in"])[0]
            if key not in ALLSRC:
                return self.send(404, '{"error":"unknown source"}',
                                 "application/json")
            try:
                chans = get_channels(key)
                self.send(200, json.dumps({"total": len(chans),
                                           "channels": chans},
                                          ensure_ascii=True),
                          "application/json")
            except Exception as e:
                self.send(502, json.dumps({"error": str(e)[:120]}),
                          "application/json")

        elif u.path == "/api/now":
            key = qs.get("p", ["in"])[0]
            if key not in EPG_FILES:
                return self.send(200, '{"status":"unsupported"}',
                                 "application/json")
            epg_ensure_async(key)
            payload = {"status": epg_state(key)}
            if payload["status"] == "ready":
                payload["channels"] = epg_snapshot(key)
            self.send(200, json.dumps(payload, ensure_ascii=True),
                      "application/json")

        elif u.path == "/play":
            url = qs.get("url", [""])[0]
            if urlparse(url).scheme not in SAFE_SCHEMES:
                return self.send(400,
                    '{"ok":false,"msg":"Unsupported link"}',
                    "application/json")
            if IS_CLOUD:
                self.send(200, json.dumps({"ok": False,
                                           "msg": "VLC is available only on the local PC. Open the stream from the browser instead."},
                                          ensure_ascii=True),
                          "application/json")
            else:
                ok, msg = launch(url)
                self.send(200, json.dumps({"ok": ok, "msg": msg},
                                          ensure_ascii=True),
                          "application/json")

        elif u.path == "/playall":
            key = qs.get("p", ["in"])[0]
            if key not in ALLSRC:
                return self.send(404, '{"ok":false,"msg":"Unknown source"}',
                                 "application/json")
            if IS_CLOUD:
                self.send(200, '{"ok":false,"msg":"Whole-list VLC playback is disabled on the public cloud version."}',
                          "application/json")
            else:
                target = (("http://127.0.0.1:%d/m3u?p=%s" % (PORT, key))
                          if key in RADIO_SOURCES
                          else PLAYLISTS[key]["url"])
                ok, msg = launch(target)
                self.send(200, json.dumps({"ok": ok, "msg": msg},
                                          ensure_ascii=True),
                          "application/json")

        elif u.path == "/check":
            url = qs.get("url", [""])[0]
            if urlparse(url).scheme not in SAFE_SCHEMES:
                return self.send(200, '{"ok":null,"code":0,"ms":0}',
                                 "application/json")
            self.send(200, json.dumps(check_stream(url)),
                      "application/json")

        elif u.path == "/quit":
            self.send(200, "<h3 style='font-family:sans-serif'>Stopped.</h3>")
            if SRV is not None:
                threading.Timer(0.4, lambda: SRV.shutdown()).start()
        else:
            self.send(404, "<h1>404</h1>")

def net_ok():
    try:
        req = urllib.request.Request(
            "https://iptv-org.github.io/iptv/countries/in.m3u",
            method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 200
    except Exception:
        return False

def _fw_ok():
    if os.name != "nt": return True
    return os.system('netsh advfirewall firewall show rule name='
                     '"IPTV Dashboard" >nul 2>&1') == 0

def _radio_ok():
    try:
        load_radio("rin"); return True
    except Exception:
        return False

def start_server():
    global SRV, PORT
    ports = [PORT] if IS_CLOUD else [8765, 8766, 8767, 8768]
    for p in ports:
        try:
            SRV = ThreadingHTTPServer(("0.0.0.0", p), Handler)
            PORT = p; return True
        except OSError:
            log("[!] Port %d busy, trying next..." % p)
    raise RuntimeError("No free port")

def run():
    global LAN_IP, TS_IP
    LAN_IP = "" if IS_CLOUD else get_lan_ip()
    TS_IP = "" if IS_CLOUD else get_tailscale_ip()
    log("[i] Sunrise Hub v%s" % VERSION)
    log("[i] Mode: %s" % ("Render cloud" if IS_CLOUD else "Local PC"))
    log("[i] VLC: %s" % (VLC or "NOT FOUND"))
    start_server()
    log("")
    if IS_CLOUD:
        log("    Public HTTP : 0.0.0.0:%d" % PORT)
        log("    Render URL  : assigned by Render")
    else:
        log("    PC          :  http://127.0.0.1:%d" % PORT)
        if LAN_IP: log("    Phone(WiFi) :  http://%s:%d" % (LAN_IP, PORT))
        if TS_IP:  log("    Anywhere(TS):  http://%s:%d" % (TS_IP, PORT))
        threading.Timer(0.8, lambda: webbrowser.open(
            "http://127.0.0.1:%d/" % PORT)).start()
    log("")
    try: SRV.serve_forever()
    except KeyboardInterrupt: pass
    log("\nBye!")

def _res(name, ok, info=""):
    log("  [%s] %-26s %s" % ("PASS" if ok else "WARN", name, info))
    return 1 if ok else 0

def selftest():
    log("\nSunrise Hub v%s - SELF TEST\n%s" % (VERSION, "-" * 46))
    sc = 0
    try:
        SHELL.encode("utf-8")
        sc += _res("page template", True, "ascii-clean")
    except Exception as e:
        sc += _res("page template", False, str(e))
    ch = parse_m3u('#EXTM3U\n#EXTINF:-1 tvg-id="X.in" group-title="News",T\n'
                   'http://s/x.m3u8\n')
    sc += _res("m3u parser",
               len(ch) == 1 and ch[0]["id"] == "X.in", "ok")
    sc += _res("epoch parser",
               _xmltv_epoch("20260101120000 +0530") > 0, "ok")
    rb = build_m3u(ch)
    sc += _res("m3u builder",
               rb.count("#EXTINF") == 1 and "http://s/x.m3u8" in rb, "ok")
    global LAN_IP, TS_IP
    LAN_IP = get_lan_ip(); TS_IP = get_tailscale_ip()
    sc += _res("LAN IP", bool(LAN_IP), LAN_IP or "offline?")
    sc += _res("Tailscale", TS_IP != "", TS_IP or "not installed (optional)")
    test_port = PORT if IS_CLOUD else 8765
    s = socket.socket(); free = s.connect_ex(("127.0.0.1", test_port)) != 0
    s.close()
    sc += _res("port %d" % test_port, free, "free" if free else "busy - fallback ready")
    sc += _res("VLC", bool(VLC), VLC or "install VLC!")
    try:
        n = len(load_playlist("in"))
        sc += _res("TV playlist", n > 50, "%d channels" % n)
    except Exception as e:
        _res("TV playlist", False, str(e)[:40])
    ok_r = _radio_ok()
    sc += _res("Radio API", ok_r,
               ("%d stations"
                % len(CACHE.get("rin", {}).get("chans", [])))
               if ok_r else "unreachable")
    try:
        nn = len(fetch_news("top"))
        sc += _res("News RSS", nn >= 5, "%d headlines" % nn)
    except Exception as e:
        _res("News RSS", False, str(e)[:40])
    try:
        p = yf_chart("^NSEI").get("price")
        sc += _res("Markets API", bool(p), "NIFTY %s" % p)
    except Exception as e:
        _res("Markets API", False, str(e)[:40])
    try:
        gc = gutendex({"languages": "hi"}).get("count", 0)
        sc += _res("Books API", gc > 100, "%d hindi books" % gc)
    except Exception as e:
        _res("Books API", False, str(e)[:40])
    sc += _res("Internet", net_ok(), "OK" if net_ok() else "offline")
    log("-" * 46)
    log("RESULT: %s (%d/13 passed)" %
        ("READY TO RUN" if sc >= 9 else "REVIEW WARNINGS ABOVE", sc))
    return 0 if sc >= 9 else 1

def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    try:
        run()
    except Exception:
        err = traceback.format_exc()
        log(err)
        try:
            with open(os.path.join(
                    os.path.dirname(os.path.abspath(sys.argv[0])),
                    "iptv_dashboard.log"), "a", encoding="utf-8") as f:
                f.write("\n[%s]\n%s\n" %
                        (time.strftime("%Y-%m-%d %H:%M"), err))
        except Exception:
            pass
        raise SystemExit(1)

if __name__ == "__main__":
    main()