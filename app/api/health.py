from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.proxy import HealthResponse
from app.services.pool import PoolService

router = APIRouter(tags=["health"])
pool_service = PoolService()


@router.get("/health", response_model=HealthResponse)
def healthcheck(db: Session = Depends(get_db)) -> HealthResponse:
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    stats = pool_service.get_stats(db)
    pool = stats.pool
    overall = "ok" if db_status == "ok" and pool.healthy > 0 else "degraded"
    if db_status != "ok":
        overall = "error"

    return HealthResponse(status=overall, database=db_status, proxy_pool=pool)
