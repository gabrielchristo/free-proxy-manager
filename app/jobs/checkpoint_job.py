from app.config import Settings, get_settings
from app.database import checkpoint_database


class CheckpointJob:
    """Triggers SQLite WAL checkpoint according to configured mode."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self) -> tuple[int, int, int]:
        """Run checkpoint; returns (busy, log, checkpointed) page counts."""
        return checkpoint_database(self.settings.db_checkpoint_interval_mode)
