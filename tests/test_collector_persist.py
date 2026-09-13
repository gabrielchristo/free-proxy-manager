from app.config import get_settings
from app.models import Proxy, ProxySource
from app.services.collector import CollectorService
from app.sources.base import CollectedProxy


def test_persist_collected_commits_in_batches(db_session):
    source = ProxySource(
        name="batch-test",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    db_session.add(source)
    db_session.commit()

    collected = [
        CollectedProxy(host=f"10.0.0.{index}", port=8000 + index, protocol="http")
        for index in range(5)
    ]

    settings = get_settings().model_copy(update={"collector_persist_batch_size": 2})
    service = CollectorService(settings=settings)

    commit_calls = 0
    expunge_calls = 0
    original_commit = db_session.commit
    original_expunge = db_session.expunge_all

    def counting_commit():
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    def counting_expunge():
        nonlocal expunge_calls
        expunge_calls += 1
        original_expunge()

    db_session.commit = counting_commit
    db_session.expunge_all = counting_expunge

    queued_ids = service._persist_collected(db_session, source.id, source.name, collected)

    assert len(queued_ids) == 5
    assert commit_calls == 3
    assert expunge_calls == 3

    db_session.expunge_all()
    assert db_session.query(Proxy).count() == 5
