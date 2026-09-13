# Test Client

Python client to validate **free-proxy-manager** proxies by fetching an external URL (default: Google).

## What it does

1. **10×** `GET /proxy` — each returned proxy is tested against the target URL.
2. **1×** `GET /proxies` — fetches up to 100 candidates with `protocol=https`, `status=HEALTHY`, `anonymous=true`, ranks by anonymity (`elite` / `high_anonymous` > `anonymous`) and score, picks **10**, and tests each one.

Total: **20 probes** with per-request reporting (OK/FAIL, timing, HTTP status, metadata).

## Setup

```bash
cd test-client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Make sure **free-proxy-manager** is running (e.g. `http://localhost:9321`).

## Usage

```bash
python main.py
```

Useful options:

```bash
python main.py --manager-url http://localhost:9321 --target-url https://www.google.com/
python main.py --json report.json
python main.py --concurrency 3 --timeout 20
```

Environment variables:

| Variable | Default |
|----------|---------|
| `PROXY_MANAGER_URL` | `http://localhost:9321` |
| `TEST_TARGET_URL` | `https://www.google.com/` |
| `TEST_TIMEOUT` | `15` |

## Output

Terminal report with **pool diagnostics** before tests (`/health`, counts by status, how many match the list filter).

If there are no `HEALTHY` proxies, the 10 `/proxies` slots become **one SKIP line** (not 10 duplicates).

### Empty pool / checker still warming up

`/proxy` only returns `HEALTHY` proxies. If the checker has not validated any yet:

```bash
python main.py --wait-seconds 300
```

Waits until at least one `HEALTHY` proxy appears (poll every 5s).

Exit codes: `0` = all executed tests passed; `1` = at least one failed; `2` = no tests executed.
