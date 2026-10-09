"""One bounded JSON-2 transaction for a complete authoritative snapshot."""
import asyncio

import httpx

from .contracts import Snapshot
from .settings import Settings


class OdooClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http

    async def get_snapshot(self) -> Snapshot:
        async with asyncio.timeout(15):
            async with self.http.stream('POST', self.settings.odoo_base_url + '/json/2/factorio.factory/get_snapshot', json={}, headers={
                'Authorization': 'Bearer ' + self.settings.api_key.get_secret_value(),
                'X-Odoo-Database': self.settings.database,
            }, timeout=httpx.Timeout(10, connect=3, pool=3), follow_redirects=False) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 256 * 1024:
                        raise ValueError('Source snapshot exceeds size limit')
                    body.extend(chunk)
        snapshot = Snapshot.model_validate_json(body)
        if snapshot.meta.source_id != self.settings.source_id or snapshot.meta.scope_id != self.settings.scope_id:
            raise ValueError('Source snapshot does not match configured binding')
        return snapshot
