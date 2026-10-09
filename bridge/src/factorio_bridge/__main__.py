"""Source coordinator and acknowledged localhost delivery process."""
from contextlib import asynccontextmanager
import logging
import sys

from pydantic import ValidationError

import httpx
import uvicorn

from .app import create_app
from .coordinator import RefreshCoordinator, SystemClock
from .logging import install_redaction
from .odoo import OdooClient
from .settings import Settings
from .store import SnapshotStore
from .udp import UdpDelivery


def main():
    try:
        settings = Settings.from_env()
    except ValidationError:
        print('Invalid bridge configuration; check FACTORIO_ environment settings', file=sys.stderr)
        raise SystemExit(2) from None
    logging.basicConfig(level=logging.INFO)
    install_redaction([settings.api_key.get_secret_value(), settings.webhook_token.get_secret_value(), settings.pairing_token.get_secret_value()])
    http = httpx.AsyncClient(trust_env=False)
    client = OdooClient(settings, http)
    store = SnapshotStore(settings.cache_path, source_id=settings.source_id, scope_id=settings.scope_id)
    clock = SystemClock()
    delivery = UdpDelivery(settings, clock)
    coordinator = RefreshCoordinator(client.get_snapshot, store, delivery.enqueue, clock)
    app = create_app(settings, coordinator, delivery)
    original = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original(app):
                yield
        finally:
            await http.aclose()
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host=settings.bind_host, port=settings.bind_port, timeout_keep_alive=5, limit_concurrency=64)


if __name__ == '__main__':
    main()
