# Configuration

All operational settings come from the `.env` file. There are no hardcoded defaults in Python: if a variable is missing, the application fails on startup.

Use `.env.example` as the complete reference.

## Application

| Variable | Description |
|----------|-------------|
| `APP_NAME` | Name shown in OpenAPI |
| `DATABASE_URL` | SQLAlchemy URL |
| `LOG_LEVEL` | Log level |
| `LOG_FORMAT` | Log format |
| `LOG_COLOR_ENABLED` | Colors on stdout (`true`/`false`; works in Docker too) |
| `API_HOST` | Uvicorn host |
| `API_PORT` | Uvicorn port |
| `SOURCES_CONFIG_PATH` | Path to the sources JSON (default `./sources.json`) |

Collection sources live in [`sources.json`](../sources.json). Details in [Sources](sources.md).

## Checker

| Variable | Description |
|----------|-------------|
| `CHECKER_CONCURRENCY` | Concurrent checker workers |
| `CHECKER_QUEUE_MAX_SIZE` | Maximum asyncio queue size for the checker |
| `CHECKER_ENQUEUE_BATCH_SIZE` | Maximum proxies enqueued per refill cycle |
| `CHECKER_REFILL_INTERVAL` | Interval (s) for the loop that refills the checker queue |
| `CHECKER_SELECTION_POOL_SIZE` | Candidate pool size before shuffle (prioritizes oldest `last_checked`) |
| `CHECKER_TRANSPORT_POOL_SIZE` | LRU-cached httpx transports per proxy URL (avoids recreating SSL on every check) |
| `CHECK_TIMEOUT` | Timeout in seconds |
| `CHECK_URL` | Probe URL (prefer small endpoints, e.g. `http://detectportal.firefox.com/success.txt`) |
| `CHECK_ALLOWED_HOSTS` | Allowed hosts (CSV) |
| `CHECK_ALLOWED_SCHEMES` | Allowed schemes (CSV) |
| `CHECK_SUCCESS_STATUS_MIN` | Minimum HTTP status for success |
| `CHECK_SUCCESS_STATUS_MAX` | Maximum HTTP status for success |
| `CHECK_FOLLOW_REDIRECTS` | Follow redirects (`true`/`false`) |

## Jobs (seconds)

| Variable | Description |
|----------|-------------|
| `COLLECT_INTERVAL` | Collection interval |
| `COLLECTOR_RUN_ON_STARTUP` | If `true`, runs a full collection before the API accepts traffic (lifespan); `false` starts fast and collects on the next cycle |
| `COLLECTOR_PERSIST_BATCH_SIZE` | Proxies persisted per commit during collection (frees SQLAlchemy session RAM) |
| `RECHECK_INTERVAL` | Minimum time since `last_checked` before a HEALTHY proxy re-enters the queue |
| `CLEANUP_INTERVAL` | Cleanup interval |
| `SCORE_INTERVAL` | Score recalculation interval |
| `STATS_SNAPSHOT_INTERVAL` | Pool snapshot interval in seconds (`0` disables) |
| `STATS_SNAPSHOT_RETENTION_DAYS` | Days to keep snapshot rows for charts |
| `STATS_HISTORY_MAX_HOURS` | Max lookback for `GET /stats/history` (default 720 = 30 days) |
| `STATS_HISTORY_MAX_LIMIT` | Max snapshots returned by history endpoint (default 8640) |
| `RECHECK_BATCH_SIZE` | Maximum due HEALTHY proxies enqueued per refill cycle (priority tier) |
| `SCORE_BATCH_SIZE` | Proxies processed per batch in the score job |

## Cooldown

| Variable | Description |
|----------|-------------|
| `FAILURE_THRESHOLD` | Consecutive failures before cooldown |
| `COOLDOWN_INITIAL` | Initial cooldown (s) |
| `COOLDOWN_MAX` | Maximum cooldown (s) |
| `COOLDOWN_MAX_LEVEL` | Maximum backoff level |

## Pool and API

| Variable | Description |
|----------|-------------|
| `POOL_MIN_SCORE` | Default minimum score for `/proxy` |
| `POOL_TOP_CANDIDATES` | Candidates considered in weighted selection |
| `POOL_SELECTION_MIN_WEIGHT` | Minimum weight in random selection |
| `API_DEFAULT_LIMIT` | Default `limit` for `/proxies` |
| `API_MAX_LIMIT` | Maximum `limit` for `/proxies` |
| `API_MAX_SCORE` | Maximum score accepted in filters |

## Cleanup

| Variable | Description |
|----------|-------------|
| `CLEANUP_STALE_DAYS` | Days before removing dead proxies with no success history |

## Database

| Variable | Description |
|----------|-------------|
| `DB_POOL_SIZE` | SQLAlchemy pool size |
| `DB_POOL_MAX_OVERFLOW` | Pool overflow |
| `DB_POOL_TIMEOUT` | Timeout when acquiring a connection (s) |
| `DB_SQLITE_TIMEOUT` | SQLite driver timeout (s) |
| `DB_WAL_AUTOCHECKPOINT` | WAL pages before autocheckpoint (~4 KB/page; `25` ≈ 100 KB) |
| `DB_CHECKPOINT_ON_COMMIT` | Checkpoint after each `commit` (disabled avoids a constant ~25 KB WAL) |
| `DB_CHECKPOINT_COMMIT_MODE` | Post-commit checkpoint mode (`PASSIVE`, `FULL`, `RESTART`, `TRUNCATE`) |
| `DB_CHECKPOINT_INTERVAL` | Periodic checkpoint job interval (s) (`0` disables) |
| `DB_CHECKPOINT_INTERVAL_MODE` | Periodic checkpoint mode (recommended `TRUNCATE`) |

Rough tuning: with 4 KB pages, `DB_WAL_AUTOCHECKPOINT=25` allows ~100 KB in the WAL before automatic autocheckpoint. A `TRUNCATE` job every 120 s acts as a safety net without keeping the WAL as small as checkpoint-on-commit (~25 KB) or as large as no checkpoint (~3 MB).

## Scorer

| Variable | Description |
|----------|-------------|
| `SCORER_SUCCESS_WEIGHT` | Success rate weight |
| `SCORER_LATENCY_MAX` | Maximum latency bonus |
| `SCORER_LATENCY_DIVISOR` | Latency divisor |
| `SCORER_RECENCY_MAX` | Maximum recency bonus |
| `SCORER_FAILURE_PENALTY` | Consecutive failure penalty |
| `SCORER_HISTORY_CAP` | History bonus cap |
| `SCORER_SCORE_MAX` | Maximum score |
| `SCORER_HTTPS_BONUS` | Extra bonus for HTTPS proxies |
| `SCORER_HTTPS_PROTOCOL` | `protocol` value that receives the bonus |
| `SCORER_MULTI_SOURCE_BONUS` | Bonus per extra source beyond the first |
| `SCORER_ANONYMITY_BONUS` | Comma-separated `level=bonus` map (e.g. `transparent=0,anonymous=6,elite=12`) |

## Docker Compose

Variables used by `docker-compose.yml`:

| Variable | Description |
|----------|-------------|
| `DOCKER_HEALTHCHECK_INTERVAL` | Healthcheck interval |
| `DOCKER_HEALTHCHECK_TIMEOUT` | Healthcheck timeout |
| `DOCKER_HEALTHCHECK_RETRIES` | Healthcheck retries |
| `DOCKER_HEALTHCHECK_START_PERIOD` | Healthcheck start period |
| `DOCKER_MEMORY_LIMIT` | Container RAM and swap limit (`mem_limit` / `memswap_limit`) |

RAM tuning details: [Memory](memory.md).

Use the same URL locally and in Docker:

```env
DATABASE_URL=sqlite:///./data/proxies.db
```

Mount `./data:/app/data` in Compose to persist the host file `./data/proxies.db`.

## Filters

| Variable | Description |
|----------|-------------|
| `ANONYMOUS_EXCLUDE_VALUE` | Anonymity value excluded when `anonymous=true` |
