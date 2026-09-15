# Proxy sources

Collection sources live in `sources.json` at the project root. The path can be changed via `.env`:

```env
SOURCES_CONFIG_PATH=./sources.json
```

## Structure

```json
{
  "fetch_timeout": 30,
  "sources": [
    {
      "name": "proxyscrape",
      "type": "proxyscrape",
      "enabled": true,
      "url": "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.json",
      "priority": 100,
      "protocols": ["http", "https"]
    },
    {
      "name": "iplocate-http",
      "type": "text_list",
      "enabled": true,
      "url": "https://github.com/iplocate/free-proxy-list/blob/main/protocols/http.txt",
      "protocol": "http",
      "priority": 90
    }
  ]
}
```

## Global fields

| Field | Description |
|-------|-------------|
| `fetch_timeout` | Default timeout (seconds) for downloading sources |

## Per-source fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique identifier (appears in logs inside `[ ]`) |
| `type` | yes | `proxyscrape`, `text_list`, `geonode`, `proxycompass`, `litport`, `nodemaven`, or `proxydb` |
| `enabled` | no | Default `true`. When `false`, the source is not collected and existing proxies linked only to that source are not checked |
| `url` | yes | Source URL |
| `priority` | yes | Numeric priority (higher = more relevant in logs) |
| `protocols` | proxyscrape, geonode | List of accepted protocols (`http`, `https`, `socks4`, `socks5`) |
| `protocol` | text_list | Single protocol (`http`, `https`, `socks4`, or `socks5`) |
| `page_size` | geonode, litport, nodemaven | Items per API page (defaults: geonode `100`, litport `500`, nodemaven `500`) |
| `max_pages` | geonode, litport, nodemaven, proxydb | Maximum paginated pages (defaults: geonode/litport/nodemaven `10`, proxydb `20`) |
| `download_url` | proxycompass | AJAX endpoint override (default `/wp-admin/admin-ajax.php`) |
| `export_filter` | proxycompass | JSON filter passed to download (default `{}`) |
| `fetch_timeout` | no | Per-source timeout override |

## Types

### `proxyscrape`

Consumes JSON in the ProxyScrape free-proxy-list format. Filters by configured `protocols`.

### `text_list`

Text file with one `host:port` entry per line. Empty lines and comments (`#`) are ignored.

`github.com/.../blob/...` URLs are automatically converted to `raw.githubusercontent.com`.

### `geonode`

Consumes the [Geonode public API](https://proxylist.geonode.com/api/proxy-list) (the page https://geonode.com/free-proxy-list uses this API underneath — no scraping required).

Paginates with `page_size` and `max_pages`, ordered by `lastChecked`. Each item may include multiple protocols; only those listed in `protocols` are kept.

Example:

```json
{
  "name": "geonode",
  "type": "geonode",
  "enabled": true,
  "url": "https://proxylist.geonode.com/api/proxy-list",
  "priority": 85,
  "protocols": ["http", "https"],
  "page_size": 100,
  "max_pages": 25
}
```

### `proxycompass`

Uses the site's **ProxyLister** plugin via WordPress AJAX — **not** HTML table scraping.

Flow:

1. Download the page configured in `url` and extract the `proxylister_ajax` nonce.
2. Call `admin-ajax.php?action=proxylister_download&format=json`.

The public page `https://proxycompass.com/free-proxy/` is behind Cloudflare; the default uses `https://proxycompass.com/?page_id=455912`, which exposes the same widget.

JSON export limitations: usually only `ip_address` and `port` (~500 entries per download). Protocol is inferred (`443` → `https`, otherwise → `http`).

Example:

```json
{
  "name": "proxycompass",
  "type": "proxycompass",
  "enabled": true,
  "url": "https://proxycompass.com/?page_id=455912",
  "priority": 80,
  "protocols": ["http", "https"]
}
```

The paid API `/api/getproxy/` requires a paid package login/password — not applicable to the free list.

### `litport`

Consumes the public API `GET https://litport.net/api/free-proxy` (the page https://litport.net/free-proxy uses this API).

Paginates with `page_size` and `max_pages`. Filters by configured `protocols`. Normalizes `port` with a trailing `\r` and maps `geoCountry`, `responseTimeMs`, `uptimeRating`, and `pingAt`.

Example:

```json
{
  "name": "litport",
  "type": "litport",
  "enabled": true,
  "url": "https://litport.net/api/free-proxy",
  "priority": 70,
  "protocols": ["http", "https"],
  "page_size": 500,
  "max_pages": 5
}
```

### Proxifly (via `proxyscrape`)

The [proxifly/free-proxy-list](https://github.com/proxifly/free-proxy-list) repo uses the same JSON format as ProxyScrape. Prefer per-protocol jsDelivr URLs to control volume:

```json
{
  "name": "proxifly-http",
  "type": "proxyscrape",
  "enabled": true,
  "url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.json",
  "priority": 75,
  "protocols": ["http"]
}
```

Country/city metadata comes from `geolocation.country` / `geolocation.city`.

### `nodemaven`

The page https://nodemaven.com/free-proxy-list/ loads data from a Flask backend at `https://freeproxies.nodemaven.com/proxies`.

Paginates with `page` / `per_page`. Maps `HTTPS`/`SOCKS4`/`SOCKS5` to canonical lowercase protocols.

Example:

```json
{
  "name": "nodemaven",
  "type": "nodemaven",
  "enabled": true,
  "url": "https://freeproxies.nodemaven.com/proxies",
  "priority": 65,
  "protocols": ["http", "https"],
  "page_size": 1000,
  "max_pages": 5
}
```

### `proxydb`

Scrapes the HTML table at https://proxydb.net/ (no official API). Paginates with `offset` (30 rows per page) and passes `protocol=http&protocol=https` filters.

Example:

```json
{
  "name": "proxydb",
  "type": "proxydb",
  "enabled": true,
  "url": "https://proxydb.net/",
  "priority": 60,
  "protocols": ["http", "https"],
  "max_pages": 15
}
```

## Logs

Collector and checker use the source name in brackets:

```text
[iplocate-http] Checking proxy http://1.2.3.4:8080
[iplocate-http] Proxy http://1.2.3.4:8080 check succeeded status=NEW->HEALTHY http=200 latency_ms=183.4 score=72.5
```

If a proxy comes from multiple sources, the log lists all of them by priority:

```text
[proxyscrape, iplocate-http] Checking proxy http://1.2.3.4:8080
```
