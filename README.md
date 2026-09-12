# Sunrise Hub Render Ready V2

Sunrise Hub V2 preserves the existing TV, Radio, News, Podcasts, Markets and Books
pipeline and adds an isolated Movies discovery layer.

## Existing features preserved

- IPTV-org TV playlists
- Radio Browser
- EPG
- News RSS
- Podcasts
- Yahoo Finance market data
- Project Gutenberg / Internet Archive books
- HLS/player support
- Local PC + Render modes
- `/healthz`
- `python iptv_dashboard.py --selftest`

## Movies integration

V2 adds:

- Movies navigation
- Movie/TV search
- Trending discovery
- Basic title metadata/posters
- External provider-page links
- Graceful provider failure

The MovieBox package is loaded lazily/optionally. If it is unavailable or its
upstream provider is unavailable, the rest of Sunrise Hub continues to operate.

This integration deliberately does not proxy, re-host, or expose MovieBox
download/stream endpoints. Use only content you are legally entitled to access.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m py_compile iptv_dashboard.py
python iptv_dashboard.py --selftest
python iptv_dashboard.py
```

Open `http://127.0.0.1:8765/`.

## Render

The included `render.yaml` uses:

```text
Build: pip install -r requirements.txt
Start: python iptv_dashboard.py
Health: /healthz
```

`apt.txt` installs FFmpeg for the existing streaming/transcoding functionality.

## Main dependency

`movie-box-dl` is the Python package published by the MovieBox repository.
The upstream project describes itself as an educational CLI/API and states that
users should only use it where they have the legal right to access or download
content.

## Architecture rule

Existing media code remains in `iptv_dashboard.py`. Movie discovery is isolated
behind:

- `moviebox_search()`
- `moviebox_trending()`
- `/api/movies/search`
- `/api/movies/trending`

A failure in this provider should not take down the existing dashboard.
