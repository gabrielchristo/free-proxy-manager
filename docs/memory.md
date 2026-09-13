# Memory usage

Operational target: **~400 MB on average**, with a hard cap of **512 MB** in Docker Compose.

## Where RAM went (~1 GB)

| Source | Why |
|--------|-----|
| **Checker** | New SSL/proxy transport per check × high concurrency (mitigated by `CHECKER_TRANSPORT_POOL_SIZE`) |
| **Checker queue** | Unbounded queue after initial collection (thousands of IDs enqueued at once) |
| **Score job** | Loaded **all** proxies + source links in one SQLAlchemy session |
| **Geonode collection** | Up to 25×100 proxies held in memory before persist |
| **SQLAlchemy pool** | 5 + 25 connections — excessive for single-file SQLite |

## What is already in place

### Code

- **Bounded queue** (`CHECKER_QUEUE_MAX_SIZE`) — asyncio backpressure
- **Continuous refill** (`CHECKER_REFILL_INTERVAL`) — refills the queue; due HEALTHY (`RECHECK_INTERVAL`) go **first**
- **Queue batches** (`CHECKER_ENQUEUE_BATCH_SIZE`) — how many enter per refill cycle
- **HEALTHY recheck** — up to `RECHECK_BATCH_SIZE` due HEALTHY per cycle, before NEW/DEGRADED/DEAD
- **Deprioritized recheck** — among due HEALTHY, `was_dead=false` before `was_dead=true`
- **Transport pool** (`CHECKER_TRANSPORT_POOL_SIZE`) — LRU reuse of httpx proxy transports
- **Batched collection** (`COLLECTOR_PERSIST_BATCH_SIZE`) — periodic commit + `expunge_all` during persist
- **Batched score** (`SCORE_BATCH_SIZE`) — commit + `expunge_all` per batch
- **SQLite in threads** — checker, score, cleanup, and checkpoint do not block the event loop

### `.env` (~400 MB profile)

```env
CHECKER_CONCURRENCY=6
CHECKER_QUEUE_MAX_SIZE=100
CHECKER_ENQUEUE_BATCH_SIZE=100
CHECKER_REFILL_INTERVAL=5
CHECKER_SELECTION_POOL_SIZE=500
CHECKER_TRANSPORT_POOL_SIZE=64
RECHECK_BATCH_SIZE=100
SCORE_BATCH_SIZE=150
COLLECTOR_PERSIST_BATCH_SIZE=250
DB_POOL_SIZE=1
DB_POOL_MAX_OVERFLOW=2
```

### `sources.json`

Geonode reduced to `page_size=50`, `max_pages=10` (~500 proxies/cycle instead of ~2500).

### Docker Compose

```yaml
mem_limit: ${DOCKER_MEMORY_LIMIT}
memswap_limit: ${DOCKER_MEMORY_LIMIT}
environment:
  MALLOC_ARENA_MAX: "2"
```

Set in `.env` (e.g. `DOCKER_MEMORY_LIMIT=512m`). `memswap_limit` equal to `mem_limit` prevents swap inside the container.

## Fine tuning

If you still exceed 400 MB at peak (collection + check overlap):

1. Lower `CHECKER_CONCURRENCY` to **5–6**
2. Lower `CHECKER_ENQUEUE_BATCH_SIZE` / `CHECKER_QUEUE_MAX_SIZE` to **100**
3. Temporarily disable heavy sources in `sources.json` (ProxyScrape loads the full JSON)
4. Increase `COLLECT_INTERVAL` to avoid collection + check overlap
5. Set `COLLECTOR_RUN_ON_STARTUP=false` for fast startup and deferred first collection

If you stay comfortably below 300 MB and want more throughput:

1. Raise `CHECKER_CONCURRENCY` to **10–12**
2. Raise batch sizes to **200**

## Monitoring

```bash
docker stats free-proxy-manager
```

Short spikes above 400 MB during the **first collection** are normal; average should stabilize after the queue drains.

Compare RSS with Python heap when debugging:

```bash
TRACEMALLOC=1 TRACEMALLOC_INTERVAL=300 uvicorn app.main:app --host 0.0.0.0 --port 9321
```

Stable `tracemalloc current` with rising RSS usually means native memory (SQLite cache, OpenSSL) rather than a Python leak.

### Event loop

Jobs that use SQLite synchronously (checker, score, cleanup, checkpoint, collector persistence) run in `asyncio.to_thread` so HTTP timeouts and the API are not blocked.

The cgroup OOM killer (512 MB) terminates the container if the limit is exceeded — reduce concurrency before raising the limit.
