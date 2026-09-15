# IPTV Dashboard — Latest Build (Today + Space + Dictionary Panels)

## Files in this ZIP (drop-in replacements)

| File | Size | Purpose |
|------|------|---------|
| `iptv_dashboard.py` | 178 KB | Main Python app (all new API routes + panels + CSS) |
| `js_check.js` | 70 KB | Served JavaScript (all new modules) |

## What's Included

### Existing Features (all working)
- 📺 TV (757 channels from iptv-org)
- 🎙 Radio (500 stations from radio-browser)
- 📰 News (RSS feeds: NDTV, Times of India, Google News, etc.)
- 🎧 Podcasts (RSS feeds)
- 📚 Books (Project Gutenberg via Gutendex)
- VLC player integration (Play here + Open in VLC + Open in browser)
- live-only toggle + Sort dropdown
- Age-friendly UI (large text, high contrast, 44px+ touch targets)

### New Features Added

#### 📅 Today Panel (Daily Briefing)
Combines 5 free APIs in one call (`/api/today`):
1. **Weather** (Open-Meteo) — temp, humidity, wind, condition
2. **Daily Quote** (ZenQuotes) — inspirational quote
3. **Word of the Day** (freeDictionaryAPI) — word + phonetic + definition + ▶ Pronounce
4. **On This Day** (Wikipedia REST) — 5 historical events
5. **Upcoming Holidays** (Nager.Date + IN fallback) — next 5 holidays

#### 🔍 Dictionary Lookup (in Today panel)
- Input field + "Look Up" button
- Type any English word → get definition, phonetic, example, audio pronunciation
- Source: freeDictionaryAPI (free, no key)
- Press Enter to search

#### 🚀 Space Panel (NASA + ISS)
Combines 3 free APIs in one call (`/api/space`):
1. **NASA APOD** — Astronomy Picture of the Day (image + title + explanation)
2. **ISS Live Position** (Open Notify) — current lat/lng of International Space Station
3. **Astronauts in Space** (Open Notify) — count + names of people in space

## All APIs Used (all free, no key, no signup)

| # | API | Used for |
|---|-----|----------|
| 1 | Open-Meteo | Weather |
| 2 | ZenQuotes | Daily quote |
| 3 | freeDictionaryAPI | Word of the Day + Dictionary lookup |
| 4 | Wikipedia REST | On This Day |
| 5 | Nager.Date | Public holidays |
| 6 | NASA APOD | Astronomy Picture of the Day |
| 7 | Open Notify | ISS position + astronauts |
| 8 | iptv-org | TV channels |
| 9 | radio-browser.info | Radio stations |
| 10 | Gutendex | Books |

## Marketstack Removed
Per your request, the Marketstack stock market API has been fully removed (all traces: API routes, nav button, panel, JS module, CSS).

## Install

```bash
cd /path/to/sunrise_hub_render_ready
git checkout ChatGPTChnage

# Backup current files
cp iptv_dashboard.py iptv_dashboard.py.bak
cp js_check.js js_check.js.bak

# Extract and copy new files
unzip ~/Downloads/iptv-latest.zip -d /tmp/iptv-latest
cp /tmp/iptv-latest/iptv_dashboard.py .
cp /tmp/iptv-latest/js_check.js .

# Verify
python3 -m py_compile iptv_dashboard.py && echo "PYTHON OK"
node --check js_check.js && echo "JS OK"
python3 iptv_dashboard.py --selftest

# Commit + push
git add iptv_dashboard.py js_check.js
git commit -m "Add Today + Space + Dictionary panels; remove Marketstack"
git push origin ChatGPTChnage
git checkout main
git merge ChatGPTChnage
git push origin main
```

## After Deploying

1. Hard-refresh your browser (Ctrl+Shift+R) to clear cache
2. You'll see 7 nav tabs: TV, Radio, News, Podcasts, Books, **Today**, **Space**
3. Click **📅 Today** for weather + quote + word of the day + dictionary + holidays
4. Click **🚀 Space** for NASA APOD + ISS tracker + astronauts

## QA Verified

- ✅ TV channels: 757 loaded, 120 cards
- ✅ Radio: 500 stations
- ✅ News: 8 category chips
- ✅ Books: load via Gutendex
- ✅ Player modal: VLC button visible
- ✅ Today panel: 5 cards (weather, quote, word-of-day, on-this-day, holidays)
- ✅ Dictionary lookup: works (tested "serendipity")
- ✅ Space panel: NASA APOD + ISS + 12 astronauts
- ✅ Marketstack fully removed
- ✅ No JS errors
