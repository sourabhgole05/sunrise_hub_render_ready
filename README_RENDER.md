# Sunrise Hub v11 - Render deployment

This version keeps the original local-PC behavior and adds Render cloud support.

## Local PC

The existing `Start-IPTV.bat` workflow remains valid:

1. `python -m py_compile iptv_dashboard.py`
2. `python iptv_dashboard.py --selftest`
3. `python iptv_dashboard.py`

When run locally, the app still uses ports 8765-8768, opens the browser automatically, detects LAN/Tailscale, and can launch VLC.

## Render

Render sets `RENDER=true` and `PORT`. The app binds to `0.0.0.0:$PORT` and does not try to open a browser on the server.

The public version:

- serves the Sunrise Hub UI over HTTPS through Render
- keeps radio browser playback in the user's browser where supported
- opens HTTP/HTTPS TV stream URLs in a new browser tab
- provides a mobile in-page TV player with browser playback plus an Open in VLC
  handoff when the phone supports VLC intents
- hides phone setup controls when the site is already open on a phone
- disables server-side VLC actions because VLC cannot be launched on the user's PC from the cloud
- hides the local Stop Server and Whole List in VLC controls
- shows a public-URL QR code
- exposes `/healthz` for Render health checks

## Deploy

Repository: `sourabhgole05/sunrise_hub_render_ready`
Branch: `main`

If `render.yaml` is committed at the repository root, create the service from the Blueprint or create a Web Service manually with:

- Build Command: `pip install -r requirements.txt`
- Start Command: `python iptv_dashboard.py`
- Health Check Path: `/healthz`

Do not use Streamlit Cloud for this file. The application is a normal Python `http.server` application, not a Streamlit application.

## Optional integrations

`requirements.txt` includes optional integrations for Internet Archive/Gutendex
books, Yahoo Finance market quotes, RSS parsing, and a FastAPI compatibility
app. The normal Render start command remains `python iptv_dashboard.py`.
To run the compatibility API directly, use `uvicorn iptv_dashboard:fastapi_app`.

HLS transcoding also requires the system `ffmpeg` executable in `PATH`;
`ffmpeg-python` is only the Python command builder. If FFmpeg is unavailable,
the existing direct browser/VLC playback remains available and the HLS route
returns an explicit error instead of silently failing.

The compatibility API exposes:

- `POST /api/stream/start?input_url=...` and
  `GET /api/stream/playlist.m3u8` for temporary HLS playback.
- `GET /api/books/search` and `/api/books/gutenberg` for Internet Archive and
  Gutendex results.
- `GET /api/stock/{ticker}` and `/api/market/news-feed` for market data.

The normal `python iptv_dashboard.py` server also exposes the stream start and
manifest paths as GET-compatible routes, so the existing Render deployment
does not need to be replaced with Uvicorn.

## Important

`custom_playlists.json` is local-file storage. On Render Free, the filesystem is ephemeral, so custom playlists can disappear after a restart/redeploy. A persistent database/storage layer would be needed for durable cloud-created playlists.
