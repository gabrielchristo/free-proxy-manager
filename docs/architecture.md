# Architecture

## Overview

The service runs in a single Python process with FastAPI, internal async jobs, and SQLite.

```text
Consumer applications
          │
          │ GET
          ▼
┌──────────────────────────────┐
│      free-proxy-manager      │
│                              │
│  Collector → Checker →       │
│  Scorer → Proxy Pool → API   │
│                              │
│  SQLite                      │
│  Internal jobs               │
└──────────────────────────────┘
```

## Components

| Module | Responsibility |
|--------|----------------|
| `app/sources/` | Public source adapters |
| `app/services/collector.py` | Orchestrates collection, deduplication, and persistence |
| `app/services/checker.py` | Validates proxies against an allowlisted URL |
| `app/services/scorer.py` | Computes quality score |
| `app/services/pool.py` | Selects usable proxies |
| `app/jobs/` | Periodic collection, checker refill, cleanup, and score loops |
| `app/api/` | Read-only HTTP endpoints |

## Data flow

1. **Collector job** fetches proxies from sources defined in `sources.json`.
2. HTTP/HTTPS entries are normalized and deduplicated by **`host + port`** (canonical IP / lowercase hostname). When the same endpoint appears as both HTTP and HTTPS, one row is kept (HTTPS preferred).
3. New or eligible proxies enter the checker queue; due HEALTHY rechecks get **priority** on refill.
4. **Checker workers** test connectivity through the proxy against `http://detectportal.firefox.com/success.txt`. A background task probes the same URL **directly** every `CONNECTIVITY_CHECK_INTERVAL` seconds (default 30). When direct internet is down, checks are skipped or failures discarded so HEALTHY proxies are not demoted by a local outage.
5. Results update status, metrics, cooldown, and score.
6. The API serves proxies with status `HEALTHY` or `DEGRADED`, outside cooldown.

### Checker queue priority (each refill)

1. `HEALTHY` with `last_checked` ≥ `RECHECK_INTERVAL` ago (`was_dead=false` before `was_dead=true`)
2. `NEW`
3. `DEGRADED`
4. `DEAD` (outside cooldown)

Random selection within each tier via `CHECKER_SELECTION_POOL_SIZE`, with **round-robin across providers** (enabled sources in `proxy_sources`) to avoid batches dominated by a single source.

## Proxy states

```text
NEW → CHECKING → HEALTHY
                 ↓
              DEGRADED / DEAD / DISABLED
```

- `DISABLED`: proxy requires authentication (HTTP 407).
- `DEAD`: consecutive failures above threshold; enters cooldown with backoff.
- `HEALTHY`: last check succeeded.

## Database

SQLite at `./data/proxies.db`, relative to the project root (`/app` in the container).

Local and Docker both use `DATABASE_URL=sqlite:///./data/proxies.db`; Compose mounts `./data:/app/data`.

Tables:

- `proxies`
- `proxy_sources`
- `proxy_source_links`

Migrations managed by Alembic (`alembic/versions/`).

## Checker security

Public lists are treated as untrusted input. The checker:

- only allows destinations on the allowlist (`detectportal.firefox.com`, configurable via `CHECK_ALLOWED_HOSTS`);
- uses timeouts and concurrency limits;
- does not execute source content;
- disables proxies that require authentication.

## Jobs

All run in the application lifecycle (`app/jobs/scheduler.py`):

| Job | Default interval | Function |
|-----|------------------|----------|
| Collector | 900s | Collect sources |
| Recheck | 300s | Re-enqueue eligible proxies |
| Cleanup | 3600s | Remove old dead proxies |
| Score | 300s | Recalculate scores in batches |

The checker uses continuous async workers fed by `asyncio.Queue`.

On startup, the lifespan optionally runs a full collection (`COLLECTOR_RUN_ON_STARTUP`) before accepting traffic, then primes the checker queue.
