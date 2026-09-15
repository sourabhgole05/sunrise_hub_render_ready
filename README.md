# IPTV Dashboard — 3 Defect Fixes

## Files in this ZIP (drop-in replacements)

| File | Purpose |
|------|---------|
| `iptv_dashboard.py` | Main Python app (drop-in replacement) |
| `js_check.js` | Served JavaScript (drop-in replacement) |

## 3 Defects Fixed

### DEFECT 1: VLC button missing in player modal
**Symptom:** When clicking "Watch" on a TV channel, the player modal showed "Play here" and "Open in browser" but NO "Open in VLC" button.

**Root cause:** `openPlayer()` only showed the VLC button when `(isMobile || vlcLink(u) || !IS_CLOUD)`. On desktop cloud (Render), all three conditions are false → VLC button hidden.

**Fix:** Always show VLC button (`display=''`) so users have VLC as a fallback for streams that won't play in-browser (geo-blocked, codec issues, CORS).

**Files changed:** `js_check.js` line 768-772, `iptv_dashboard.py` line 2196-2200

### DEFECT 2: Radio close button broken
**Symptom:** Clicking the X (pbstop) button on the radio player bar didn't close/hide it — the bar stayed visible.

**Root cause:** `pbShow()` set `pbar.style.display='flex'` as an INLINE style. `radioStop()` removed the `playing` class from body but the inline `display:flex` stayed → pbar never hid (inline styles override CSS rules).

**Fix:** `radioStop()` now clears the inline display (`pbar.style.display=''`) so the CSS rule `body.playing #pbar{display:flex}` takes over and the pbar hides when `playing` class is removed.

**Files changed:** `js_check.js` line 419-429, `iptv_dashboard.py` line 1818-1828

### DEFECT 3: Books only 5 dummy showing
**Symptom:** Books page showed only 5 hardcoded dummy books instead of the full Gutendex library.

**Root cause:** 
1. Gutendex API was returning HTTP 403/503 because User-Agent "Mozilla/5.0" was too short (Gutendex blocks it)
2. The `languages` filter parameter is slow/503s on Gutendex's end
3. When gutendex() threw, code fell back to `fallback_books()` which only has 5 hardcoded books

**Fix:**
- Updated `gutendex()` User-Agent to a full Chrome UA string + Accept header, increased timeout from 12s to 25s
- Updated `/api/books` handler to try popular-sort first (no language filter), then retry without language filter if first call fails, then fall back to hardcoded books only as last resort

**Result:** `/api/books` now returns 32 real books (Pride and Prejudice, Moby Dick, Crime and Punishment...) instead of 5 dummy ones.

**Files changed:** `iptv_dashboard.py` line 631-640 (gutendex function), line 3012-3056 (/api/books handler)

## Install

```bash
cd /path/to/sunrise_hub_render_ready
git checkout ChatGPTChnage

# Backup
cp iptv_dashboard.py iptv_dashboard.py.bak
cp js_check.js js_check.js.bak

# Copy new files
unzip ~/Downloads/iptv-fix3.zip -d /tmp/iptv-fix3
cp /tmp/iptv-fix3/iptv_dashboard.py .
cp /tmp/iptv-fix3/js_check.js .

# Verify
python3 -m py_compile iptv_dashboard.py && echo "PYTHON OK"
node --check js_check.js && echo "JS OK"
python3 iptv_dashboard.py --selftest

# Commit + push
git add iptv_dashboard.py js_check.js
git commit -m "Fix 3 defects: VLC button always visible, radio close button, real books"
git push origin ChatGPTChnage
git checkout main
git merge ChatGPTChnage
git push origin main
```

## QA Verification (all passed)

| Test | Before fix | After fix |
|------|-----------|----------|
| VLC button visible | display:'none' (hidden) | display:'' (visible) ✅ |
| Radio pbstop click | pbar stays display:'flex' | pbar hides display:'none' ✅ |
| /api/books items | 5 (fallback) | 32 real books ✅ |
| TV channels | 757 loaded | 757 loaded ✅ |
| Radio stations | 500 loaded | 500 loaded ✅ |
| live-only toggle | works | works ✅ |
| Sort dropdown | works | works ✅ |
| JS console errors | none | none ✅ |
