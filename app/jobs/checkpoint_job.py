from app.config import Settings, get_settings
from app.database import checkpoint_database, run_wal_checkpoint


class CheckpointJob:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self) -> tuple[int, int, int]:
        return checkpoint_database(self.settings.db_checkpoint_interval_mode)
