"""One source reader with bounded coalescing, retries, and full reconciliation."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Protocol

from .store import StoredSnapshot

_logger = logging.getLogger(__name__)


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def utcnow(self) -> datetime: ...
    async def sleep(self, seconds: float): ...


class SystemClock:
    def monotonic(self):
        return time.monotonic()

    def utcnow(self):
        return datetime.now(timezone.utc)

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


@dataclass(frozen=True)
class BridgeHealth:
    source_ok: bool
    source_age_seconds: float | None
    last_success_at: datetime | None
    last_error: str | None
    refreshing: bool


class RefreshCoordinator:
    def __init__(self, fetch, store, publish, clock: Clock):
        self.fetch, self.store, self.publish, self.clock = fetch, store, publish, clock
        self.latest: StoredSnapshot | None = None
        self.dirty = False
        self._first = self._last = None
        self._immediate = False
        self._retry_at = None
        self._failures = 0
        self._source_ok = False
        self._success_at = self._error = None
        self._refreshing = False
        self._wake = asyncio.Event()
        self._tasks = []

    @property
    def health(self) -> BridgeHealth:
        age = None if self.latest is None else max(0, (self.clock.utcnow() - self.latest.snapshot.meta.source_read_at).total_seconds())
        return BridgeHealth(self._source_ok, age, self._success_at, self._error, self._refreshing)

    async def start(self):
        if self._tasks:
            return
        self._source_ok = False
        self._success_at = None
        self._error = None
        self._failures = 0
        self._retry_at = None
        self.latest = self.store.load_latest()
        if self.latest is not None:
            await self.publish(self.latest)
        await self.request_initial()
        self._tasks = [asyncio.create_task(self._worker()), asyncio.create_task(self._reconcile())]

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._refreshing = False

    async def notify(self, reason: str):
        now = self.clock.monotonic()
        if not self.dirty:
            self._first = now
        self._last = now
        self.dirty = True
        self._wake.set()

    async def request_initial(self):
        await self.notify('initial')
        self._retry_at = None
        self._immediate = True
        self._wake.set()

    async def _reconcile(self):
        while True:
            await self.clock.sleep(60)
            await self.notify('reconciliation')
            self._immediate = True
            self._wake.set()

    async def _wait_until(self, due):
        delay = max(0, due - self.clock.monotonic())
        if not delay:
            return
        sleeper = asyncio.create_task(self.clock.sleep(delay))
        wake = asyncio.create_task(self._wake.wait())
        try:
            await asyncio.wait((sleeper, wake), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sleeper, wake):
                task.cancel()
            await asyncio.gather(sleeper, wake, return_exceptions=True)

    async def _worker(self):
        while True:
            self._wake.clear()
            if not self.dirty:
                await self._wake.wait()
                continue
            now = self.clock.monotonic()
            if self._retry_at is not None:
                due = self._retry_at
            elif self._immediate:
                due = now
            else:
                due = min(self._last + .25, self._first + 1)
            if due > now:
                await self._wait_until(due)
                continue
            self.dirty = False
            self._first = self._last = None
            self._immediate = False
            self._retry_at = None
            self._refreshing = True
            try:
                snapshot = await self.fetch()
                stored = self.store.save(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._source_ok = False
                # Exception strings and source response bodies can contain credentials.
                self._error = type(error).__name__
                if self._failures == 0 or self.clock.monotonic() - self._last_error_log >= 30:
                    _logger.warning('Source refresh failed (%s)', self._error)
                    self._last_error_log = self.clock.monotonic()
                delay = (1, 2, 4, 8, 16, 30)[min(self._failures, 5)]
                self._failures += 1
                self._retry_at = self.clock.monotonic() + delay
                await self.notify('retry')
            else:
                self.latest = stored
                self._source_ok = True
                self._success_at = self.clock.utcnow()
                self._error = None
                self._failures = 0
                try:
                    await self.publish(stored)
                except Exception as error:
                    _logger.warning('Snapshot publication failed (%s)', type(error).__name__)
            finally:
                self._refreshing = False
