import logging
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

CHECKPOINT_MODES = frozenset({"PASSIVE", "FULL", "RESTART", "TRUNCATE"})


class Base(DeclarativeBase):
    pass


def normalize_checkpoint_mode(mode: str) -> str:
    normalized = mode.strip().upper()
    if normalized not in CHECKPOINT_MODES:
        raise ValueError(f"Unsupported checkpoint mode: {mode}")
    return normalized


def run_wal_checkpoint(engine: Engine, mode: str) -> tuple[int, int, int]:
    normalized_mode = normalize_checkpoint_mode(mode)
    with engine.connect() as connection:
        result = connection.execute(
            text(f"PRAGMA wal_checkpoint({normalized_mode})")
        ).fetchone()

    if result is None:
        return (0, 0, 0)

    busy, log_pages, checkpointed = int(result[0]), int(result[1]), int(result[2])
    if checkpointed > 0 or normalized_mode == "TRUNCATE":
        logger.info(
            "WAL checkpoint mode=%s busy=%s log_pages=%s checkpointed=%s",
            normalized_mode,
            busy,
            log_pages,
            checkpointed,
        )
    return busy, log_pages, checkpointed


def _configure_sqlite(engine: Engine, settings: Settings) -> None:
    if engine.dialect.name != "sqlite":
        return

    busy_timeout_ms = settings.db_sqlite_timeout * 1000

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cursor.execute(f"PRAGMA wal_autocheckpoint={settings.db_wal_autocheckpoint}")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    if settings.db_checkpoint_on_commit:

        @event.listens_for(Session, "after_commit")
        def checkpoint_after_commit(session: Session) -> None:
            try:
                bind = session.get_bind()
                if isinstance(bind, Engine):
                    run_wal_checkpoint(bind, settings.db_checkpoint_commit_mode)
            except Exception:
                logger.exception("WAL checkpoint after commit failed")


settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": settings.db_sqlite_timeout},
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_max_overflow,
    pool_timeout=settings.db_pool_timeout,
)
_configure_sqlite(engine, settings)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def checkpoint_database(mode: str | None = None) -> tuple[int, int, int]:
    settings = get_settings()
    checkpoint_mode = mode or settings.db_checkpoint_interval_mode
    return run_wal_checkpoint(engine, checkpoint_mode)
