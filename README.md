# IPTV Dashboard — Optimized + Cleaned + Age-Friendly UI

## What changed (5 tasks completed)

### Task 1: Performance optimization
- Added gzip compression to the Python server's `send()` method
- Text responses (HTML/JS/CSS/JSON) > 1KB are now gzip-compressed
- Result: Page payload 35KB → 9.3KB (73% reduction), js_check.js 73KB → 19KB (74% reduction), /api/channels 196KB → 33KB (83% reduction)

### Task 2: Removed broker API (yfinance/markets)
**Removed from `iptv_dashboard.py`:**
- `import yfinance` (lines 30-33)
- `yf_chart()`, `yf_fundamentals()`, `yf_quote_snapshot()` functions (was lines 645-728)
- `fetch_market_news_feed()` function
- All `/api/market/*`, `/api/markets`, `/api/mchart`, `/api/fundamentals`, `/api/market/news`, `/api/market/quote` routes
- `register_market_routes()` FastAPI function
- Markets panel HTML (`<div id="panel-markets">`)
- Markets nav button (`<button data-mode="markets">`)
- Markets CSS (`.mkrow`, `.mksec`, `.mksk`, `.mkid`, `.mknum`, `.mkst`, `.mkp`, `.chartbox`)
- Markets selftest check
- "Markets API" row from welcome checks
- "Market snapshot" spa-card from home dashboard
- "Stock Markets" from welcome modal description
- Markets section from inline JS (`var MKT`, `mkRefresh`, `mkPaint`, `mkStart`, `mkStop`, `mkRow`, `mkRender`, `mkSyms`, `mkAdd`, `openChart`)

**Removed from `js_check.js`:**
- Same markets JS section (lines 1074-1264)
- Markets route in ROUTES object
- Markets from `cats` arrays
- Markets from `setMode()` call
- "Markets API" row from welcome checks
- "Market snapshot" spa-card from home dashboard

**Removed from `requirements.txt`:**
- `yfinance>=0.2.40` line

**Renamed (NOT removed — these are RSS news feeds, not broker API):**
- News category "markets" → "finance" (ET Markets + Moneycontrol RSS feeds still available under News > Finance chip)

### Task 3: Removed mobile phone QR scan + telephony logic
**Removed from `iptv_dashboard.py`:**
- `qr_datauri()` and `qr_img_tag()` functions
- `<button id="mob">` (Phone QR) header button
- `<div id="mobpanel">` modal (Open on your phone)
- `<button id="setupPhone">` (Set up phone) from welcome modal
- `__QRBLOCKS__` placeholder + `add_qr()` function in page render
- `$('mob').onclick` event handler
- `$('setupPhone')` hide logic
- `mobpanel` from modals list
- `.qrbox` CSS rules
- "Phone QR" title attribute

**Removed from `js_check.js`:**
- Same `mobpanel`, `setupPhone`, `mob` references

### Task 4: UI/UX redesigned for 35-65 age group
**Larger text:**
- Base font: 13px → 17px (`--fs-base`)
- Small text: 12px → 15px (`--fs-sm`)
- Title h1: 19px → 24px
- Channel names: 12.5px → 15px
- Nav buttons: 13px → 17px
- Search input: 14px → 17px

**Higher contrast:**
- Text color: `#1e293b` → `#1a2332` (darker)
- Muted color: `#7c8699` → `#5b6778` (darker)
- Border color: `#ece5d3` → `#d8cfb8` (darker)
- Border width: 1px → 2px (all interactive elements)
- Focus outline: 2px → 3px

**Larger touch targets:**
- All buttons: min-height 44-48px (was 28-32px)
- Nav buttons: padding 7px 16px → 10px 18px
- Header buttons: font 17px → 22px, min 44×44px
- Favorite star: 17px → 22px, min 32×32px
- Checkboxes: 20×20px with accent-color
- Cards: padding 10px → 12px, logos 50px → 60px

**Simpler controls:**
- All toggles now have explicit `font-weight:600`
- Sort dropdown has 2px border, larger padding
- Live-only toggle has 2px border, larger dot (10px)
- Modal cards: padding 20px → 24px, max-width 560px → 600px

**Mobile viewport:**
- Base font on mobile: 12px → 14px
- Nav buttons on mobile: 12px → 14px, min-height 44px
- Search input on mobile: 14px → 16px, min-height 48px
- Cards on mobile: padding 8px → 10px, logos 42px → 52px
- Channel names on mobile: 12px → 14px
- All touch targets on mobile: min 40-44px

**Viewport meta:**
- Changed from `maximum-scale=1,user-scalable=no` to `maximum-scale=5,user-scalable=yes` (allows pinch-to-zoom for accessibility)

### Task 5: Functionality preserved — all channels work

**Verified via agent-browser:**
- ✅ TV channels load: 757 channels in "All India", 352 in Hindi, 990 in News TV, 11039 in Worldwide
- ✅ Radio stations load: 500 stations in Radio India, 500 in Radio World Top
- ✅ Channel cards render with logos, names, Watch/Listen buttons
- ✅ Category chips work (All 757, News, Entertainment, Religious, etc.)
- ✅ live-only toggle works (red pulse activates, filters to live channels)
- ✅ All 6 sort modes work (default/live/name/name-desc/group/language)
- ✅ Player modal opens with "Play here" + "Open in VLC" + "Open in browser"
- ✅ Favorites work (star click adds to favorites, persists in localStorage)
- ✅ Theme toggle works (dark/light via data-theme attribute)
- ✅ All 5 nav modes work (TV/Radio/News/Podcasts/Books) — Markets removed
- ✅ News > Finance chip replaces Markets chip
- ✅ No JS errors, no 404s in console
- ✅ Gzip compression active (73-83% size reduction)

## Files in this ZIP (drop-in replacements)

| File | Size | Purpose |
|------|------|---------|
| `iptv_dashboard.py` | ~180 KB | Main Python app (HTML + CSS + inline JS backup) |
| `js_check.js` | ~64 KB | The actually-served JavaScript |
| `requirements.txt` | ~300 B | Python dependencies (yfinance removed) |

## Install

```bash
cd /path/to/sunrise_hub_render_ready
git checkout ChatGPTChnage  # or main

# Backup current files
cp iptv_dashboard.py iptv_dashboard.py.bak
cp js_check.js js_check.js.bak
cp requirements.txt requirements.txt.bak

# Copy new files
unzip iptv-optimized.zip -d /tmp/iptv-new
cp /tmp/iptv-new/iptv_dashboard.py .
cp /tmp/iptv-new/js_check.js .
cp /tmp/iptv-new/requirements.txt .

# Verify
python3 -m py_compile iptv_dashboard.py && echo "PYTHON OK"
node --check js_check.js && echo "JS OK"
python3 iptv_dashboard.py --selftest

# Commit + push
git add iptv_dashboard.py js_check.js requirements.txt
git commit -m "Optimize: gzip compression, remove broker API + QR/telephony, age-friendly UI"
git push origin ChatGPTChnage
git checkout main
git merge ChatGPTChnage
git push origin main
```

Render auto-deploys on push.
