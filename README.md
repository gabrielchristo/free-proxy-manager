# Free Proxy Manager

Discovers free HTTP/HTTPS proxies from public lists, checks them, ranks them, and serves the best ones through a simple REST API.

Intended for **local or private network** use. The API has no authentication.

## Run locally

```bash
cp .env.example .env
pip install -r requirements.txt
mkdir -p data
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 9321
```

Open `http://localhost:9321/docs` for the interactive API.

## Run with Docker

```bash
docker compose up -d --build
```

## API

Base URL: `http://localhost:9321`

**Get one healthy proxy**

```bash
curl "http://localhost:9321/proxy"
curl "http://localhost:9321/proxy?protocol=http&country_code=US"
```

**List proxies**

```bash
curl "http://localhost:9321/proxies?limit=10&status=HEALTHY"
```

**Pool stats and health**

```bash
curl "http://localhost:9321/stats"
curl "http://localhost:9321/health"
```
