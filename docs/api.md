# API

Local base URL: `http://localhost:9321`

Interactive OpenAPI: `http://localhost:9321/docs`

Authentication: **none** (local use).

## GET /proxy

Returns one **HEALTHY** proxy with the best score, using weighted random selection among top candidates.

Only `HEALTHY` status (outside cooldown). `DEGRADED` proxies are not returned from this endpoint.

### Query params

| Param | Type | Description |
|-------|------|-------------|
| `protocol` | string | `http` or `https` |
| `country` | string | Partial filter by country name |
| `country_code` | string | ISO-3166 alpha-2 code (e.g. `BR`) |
| `max_latency` | float | Maximum latency in ms |
| `anonymous` | bool | Excludes `transparent` proxies |
| `min_score` | float | Minimum score (default: `POOL_MIN_SCORE`) |

### Example

```http
GET /proxy?protocol=http&country_code=BR&max_latency=500
```

### 200 response

```json
{
  "proxy": "http://185.123.45.67:8080",
  "protocol": "http",
  "host": "185.123.45.67",
  "port": 8080,
  "latency_ms": 183.42,
  "score": 91.5,
  "country": "Brazil",
  "country_code": "BR",
  "city": "Sao Paulo",
  "anonymity": "elite",
  "isp": "Example ISP",
  "asn": "AS12345",
  "org": "Example Org",
  "ssl": true,
  "source_latency_ms": 120.5,
  "source_uptime_percent": 98.2,
  "source_speed": 4500,
  "source_last_checked": "2026-03-22T12:00:00Z",
  "last_error": null,
  "metadata": {
    "google": false,
    "responseTime": 2500
  },
  "status": "HEALTHY"
}
```

### Errors

- `404`: no proxy available for the filters.

---

## GET /proxies

Lists proxies with pagination.

### Query params

All params from `/proxy`, plus:

| Param | Default | Description |
|-------|---------|-------------|
| `limit` | 20 | Maximum 100 |
| `offset` | 0 | Pagination |
| `status` | — | Filter by status (`HEALTHY`, `DEAD`, etc.) |

---

## GET /stats

Aggregated pool, protocol, latency, country, and source statistics.

---

## GET /stats/history

Time series of pool status counts recorded by the background snapshot job.

Use this endpoint to chart `healthy`, `dead`, `in_cooldown`, etc. over time.

### Query params

| Param | Default | Description |
|-------|---------|-------------|
| `hours` | 24 | Look back window (1–168) |
| `limit` | 500 | Maximum snapshots returned (1–5000) |

### Example

```http
GET /stats/history?hours=48&limit=200
```

### 200 response

```json
{
  "hours": 48,
  "count": 2,
  "items": [
    {
      "recorded_at": "2026-09-13T12:00:00Z",
      "total_proxies": 18310,
      "pool": {
        "healthy": 71,
        "degraded": 0,
        "dead": 17777,
        "new": 0,
        "checking": 5,
        "disabled": 457,
        "in_cooldown": 3816
      }
    }
  ]
}
```

Configure snapshot frequency with `STATS_SNAPSHOT_INTERVAL` (seconds, `0` disables). Old rows are pruned after `STATS_SNAPSHOT_RETENTION_DAYS`.

---

## GET /health

Healthcheck for Docker and monitoring.

```json
{
  "status": "ok",
  "database": "ok",
  "proxy_pool": {
    "healthy": 42,
    "degraded": 5,
    "dead": 120,
    "new": 30,
    "checking": 2,
    "disabled": 1,
    "in_cooldown": 8
  }
}
```

- `status=ok`: database reachable and at least one `HEALTHY` proxy.
- `status=degraded`: database ok, but no healthy proxies in the pool.
- `status=error`: database failure.
