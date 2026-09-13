# Development

## Project structure

```text
app/
├── api/           # FastAPI routes
├── jobs/          # Scheduler and periodic jobs
├── models/        # SQLAlchemy ORM
├── schemas/       # Pydantic response models
├── services/      # Business logic
├── sources/       # Source adapters
├── config.py
├── database.py
└── main.py
alembic/           # Migrations
docs/              # Technical documentation
tests/             # pytest tests
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
mkdir -p data
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

For fast startup without blocking on the initial collection:

```env
COLLECTOR_RUN_ON_STARTUP=false
```

## Migrations

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

The initial revision is in `alembic/versions/001_initial_schema.py`.

## Tests

```bash
pytest
```

Tests use in-memory SQLite and disable the lifespan (background jobs).

## Docker

```bash
docker compose up -d --build
docker compose logs -f
```

The entrypoint runs `alembic upgrade head` before starting Uvicorn.

## Adding a new source

1. Create an adapter in `app/sources/` implementing `ProxySourceBase`.
2. Register the new `type` in `app/sources/loader.py`.
3. Add an entry in `sources.json`.

JSON details: [Sources](sources.md).

## Score

The formula lives in `app/services/scorer.py` and considers:

- success rate;
- latency;
- recency of last success;
- success history;
- HTTPS bonus (`SCORER_HTTPS_BONUS`);
- multi-source bonus (`SCORER_MULTI_SOURCE_BONUS` × extra sources);
- anonymity level bonus (`SCORER_ANONYMITY_BONUS`, e.g. `elite` > `anonymous` > `transparent`);
- consecutive failure penalty.

Persisted fields per proxy include location (`city`, `isp`, `asn`, `org`), source-reported metrics (`source_latency_ms`, `source_uptime_percent`, `source_speed`, `source_last_checked`), last check error (`last_error`), extra JSON metadata (`metadata`), and per-source snapshot in `proxy_source_links.source_metadata`.

Ranking tweaks should be made there, without changing the checker.

## Operational notes

- Initial collection + checking thousands of proxies can take several minutes unless `COLLECTOR_RUN_ON_STARTUP=false`.
- Lower `CHECKER_CONCURRENCY` if you notice high CPU/network usage.
- Free proxies have a low success rate; `/stats` helps calibrate expectations.

## Memory profiling

Enable tracemalloc in the app lifespan:

```bash
TRACEMALLOC=1 TRACEMALLOC_INTERVAL=60 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

See [Memory](memory.md) for tuning.
