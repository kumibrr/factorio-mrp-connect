"""Atomic SQLite revisions, bound permanently to one database and scope."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from uuid import UUID

from .contracts import Snapshot


@dataclass(frozen=True)
class StoredSnapshot:
    revision: int
    snapshot: Snapshot


class SnapshotStore:
    def __init__(self, path: Path, *, source_id: UUID, scope_id: str):
        self.path = Path(path)
        self.source_id = UUID(str(source_id))
        self.scope_id = scope_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS binding (singleton INTEGER PRIMARY KEY CHECK(singleton=1), source_id TEXT NOT NULL, scope_id TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS snapshots (revision INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _matches(self, snapshot):
        return snapshot.meta.source_id == self.source_id and snapshot.meta.scope_id == self.scope_id

    def save(self, snapshot: Snapshot) -> StoredSnapshot:
        if not self._matches(snapshot):
            raise ValueError('Snapshot source does not match configured binding')
        payload = snapshot.model_dump_json()
        if len(payload.encode()) > 256 * 1024:
            raise ValueError('Snapshot exceeds size limit')
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            binding = connection.execute('SELECT source_id, scope_id FROM binding WHERE singleton=1').fetchone()
            expected = (str(self.source_id), self.scope_id)
            if binding is not None and binding != expected:
                raise ValueError('Cache belongs to another source; use a separate cache path')
            connection.execute('INSERT OR IGNORE INTO binding VALUES (1, ?, ?)', expected)
            cursor = connection.execute('INSERT INTO snapshots(payload) VALUES (?)', (payload,))
            revision = cursor.lastrowid
            connection.execute('DELETE FROM snapshots WHERE revision <> ?', (revision,))
        return StoredSnapshot(revision, snapshot)

    def load_latest(self) -> StoredSnapshot | None:
        with self._connect() as connection:
            binding = connection.execute('SELECT source_id, scope_id FROM binding WHERE singleton=1').fetchone()
            if binding != (str(self.source_id), self.scope_id):
                return None
            row = connection.execute('SELECT revision, payload FROM snapshots ORDER BY revision DESC LIMIT 1').fetchone()
        if row is None:
            return None
        snapshot = Snapshot.model_validate_json(row[1])
        if not self._matches(snapshot):
            return None
        return StoredSnapshot(row[0], snapshot)
