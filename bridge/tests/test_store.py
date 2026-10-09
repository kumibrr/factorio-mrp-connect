from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

from factorio_bridge.contracts import Snapshot
from factorio_bridge.store import SnapshotStore

SOURCE = UUID('12345678-1234-5678-1234-567812345679')


def test_atomic_revisions_cache_original_timestamp_and_source_binding(tmp_path, pumpworks_payload):
    snapshot = Snapshot.model_validate(pumpworks_payload)
    path = tmp_path / 'cache.sqlite'
    store = SnapshotStore(path, source_id=SOURCE, scope_id='company:1/warehouse:1')
    with ThreadPoolExecutor(max_workers=4) as pool:
        revisions = list(pool.map(lambda _: store.save(snapshot).revision, range(8)))
    assert sorted(revisions) == list(range(1, 9))
    restarted = SnapshotStore(path, source_id=SOURCE, scope_id='company:1/warehouse:1')
    latest = restarted.load_latest()
    assert latest.revision == 8
    assert latest.snapshot.meta.source_read_at == snapshot.meta.source_read_at
    foreign = SnapshotStore(path, source_id=UUID(int=1), scope_id='company:1/warehouse:1')
    assert foreign.load_latest() is None
    with pytest.raises(ValueError):
        foreign.save(snapshot)
    assert restarted.save(snapshot).revision == 9


def test_wrong_config_cannot_overwrite_another_sources_cache(tmp_path, pumpworks_payload):
    path = tmp_path / 'cache.sqlite'
    correct = SnapshotStore(path, source_id=SOURCE, scope_id='company:1/warehouse:1')
    correct.save(Snapshot.model_validate(pumpworks_payload))
    pumpworks_payload['meta']['source_id'] = str(UUID(int=1))
    other = SnapshotStore(path, source_id=UUID(int=1), scope_id='company:1/warehouse:1')
    with pytest.raises(ValueError):
        other.save(Snapshot.model_validate(pumpworks_payload))
    assert correct.load_latest().revision == 1
