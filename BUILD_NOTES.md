# Build Notes

Source baseline:
- User-provided `iptv_dashboard.py`
- User-provided `requirements.txt`

Added:
- `movie-box-dl>=2.0.2,<2.1`
- MovieBox discovery adapter
- Movies navigation/page
- `/api/movies/search`
- `/api/movies/trending`
- Render deployment config
- FFmpeg apt dependency
- README and rollback copy

Validation performed:
- Python `py_compile`: PASS
- Inline browser JavaScript syntax check with Node: PASS

Network/API integration was not executed in this environment because outbound
network access is unavailable to the local execution environment.
