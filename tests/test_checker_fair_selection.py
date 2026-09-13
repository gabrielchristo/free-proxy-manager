from datetime import UTC, datetime

from app.jobs.checker_job import CheckerJob


def test_round_robin_proxy_rows_interleaves_providers():
    buckets = {
        1: [(101, None), (102, None), (103, None)],
        2: [(201, None), (202, None)],
        3: [(301, None)],
    }

    selected = CheckerJob._round_robin_proxy_rows(buckets, limit=5)
    ids = [proxy_id for proxy_id, _ in selected]

    assert len(ids) == 5
    assert len(set(ids)) == 5
    assert ids[0] in {101, 102, 103, 201, 202, 301}
    providers_seen = []
    for proxy_id in ids:
        if proxy_id >= 200 and proxy_id < 300:
            providers_seen.append(2)
        elif proxy_id >= 300:
            providers_seen.append(3)
        else:
            providers_seen.append(1)
    assert len(set(providers_seen)) >= 2


def test_round_robin_proxy_rows_deduplicates_multi_source_proxy():
    same = (999, datetime(2026, 9, 13, 12, 0, tzinfo=UTC))
    buckets = {
        1: [same, (101, None)],
        2: [same, (201, None)],
    }

    selected = CheckerJob._round_robin_proxy_rows(buckets, limit=3)
    ids = [proxy_id for proxy_id, _ in selected]

    assert ids.count(999) == 1
    assert len(ids) == 3
