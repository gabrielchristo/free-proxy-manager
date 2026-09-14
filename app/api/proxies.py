from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.proxy import (
    PoolSnapshotHistoryResponse,
    ProxyListResponse,
    ProxyResponse,
    StatsResponse,
)
from app.services.pool import PoolService

router = APIRouter(tags=["proxies"])
settings = get_settings()
pool_service = PoolService(settings)


@router.get("/proxy", response_model=ProxyResponse)
def get_proxy(
    protocol: str | None = Query(default=None),
    country: str | None = Query(default=None),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    max_latency: float | None = Query(default=None, ge=0),
    anonymous: bool | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=settings.api_max_score),
    db: Session = Depends(get_db),
) -> ProxyResponse:
    proxy = pool_service.get_best_proxy(
        db,
        protocol=protocol,
        country=country,
        country_code=country_code,
        max_latency=max_latency,
        anonymous=anonymous,
        min_score=min_score,
    )
    if proxy is None:
        raise HTTPException(status_code=404, detail="No proxy available for the given filters")
    return pool_service.to_response(proxy)


@router.get("/proxies", response_model=ProxyListResponse)
def list_proxies(
    limit: int = Query(
        default=settings.api_default_limit,
        ge=1,
        le=settings.api_max_limit,
    ),
    offset: int = Query(default=0, ge=0),
    protocol: str | None = Query(default=None),
    country: str | None = Query(default=None),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    status: str | None = Query(default=None),
    max_latency: float | None = Query(default=None, ge=0),
    anonymous: bool | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=settings.api_max_score),
    db: Session = Depends(get_db),
) -> ProxyListResponse:
    total, items = pool_service.list_proxies(
        db,
        limit=limit,
        offset=offset,
        protocol=protocol,
        country=country,
        country_code=country_code,
        status=status,
        max_latency=max_latency,
        anonymous=anonymous,
        min_score=min_score,
    )
    return ProxyListResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    return pool_service.get_stats(db)


@router.get("/stats/history", response_model=PoolSnapshotHistoryResponse)
def get_stats_history(
    hours: int = Query(default=720, ge=1),
    limit: int = Query(default=8640, ge=1),
    db: Session = Depends(get_db),
) -> PoolSnapshotHistoryResponse:
    if hours > settings.stats_history_max_hours:
        raise HTTPException(
            status_code=422,
            detail=f"hours must be <= {settings.stats_history_max_hours}",
        )
    if limit > settings.stats_history_max_limit:
        raise HTTPException(
            status_code=422,
            detail=f"limit must be <= {settings.stats_history_max_limit}",
        )
    return pool_service.get_snapshot_history(db, hours=hours, limit=limit)
