# Test Client

PyQt5 desktop client for **free-proxy-manager**: integration tests, proxy browser, and pool history charts.

Default probe target: `http://detectportal.firefox.com/success.txt` (same lightweight check as the server).

## Features

| Tab | Description |
|-----|-------------|
| **Integration tests** | `GET /proxy` + ranked `GET /proxies`, probe each proxy against a target URL |
| **Proxy database** | Paginated table of all proxies from `GET /proxies` with full metadata |
| **Pool history** | Matplotlib chart from `GET /stats/history` (healthy, dead, cooldown, etc.) |

## Setup

```bash
cd test-client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Make sure **free-proxy-manager** is running (default: `http://localhost:9321`).

For the **Pool history** tab, enable snapshots on the server:

```env
STATS_SNAPSHOT_INTERVAL=300
```

## Run

```bash
python main.py
```

Set the **Manager URL** at the top (shared across tabs).

### Integration tests tab

Configurable parameters:

- Target URL, timeout, concurrency
- Number of `GET /proxy` calls
- `GET /proxies` filters (protocol, status, anonymous, fetch limit, pick count)
- Optional wait for HEALTHY pool before testing
- Save JSON report

### Proxy database tab

- Filter by protocol, status, country, latency, score, anonymity
- Page through results (100 per page max) or **Load all pages**
- Table columns include score, latency, ISP, source fields, and JSON metadata

### Pool history tab

Defaults (30-day window, aligned with `STATS_SNAPSHOT_INTERVAL=300`):

- **Hours:** 720 (30 days)
- **Max points:** 8640 (one snapshot every 5 minutes for 30 days)
- **Auto refresh:** disabled by default (interval 60 s when enabled)

Toggle series (healthy, dead, in cooldown, total, …) on the chart.

## Dependencies

- **httpx** — API calls and proxy probes
- **PyQt5** — desktop GUI
- **matplotlib** — pool history chart (Qt5 backend)

