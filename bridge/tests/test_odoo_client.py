import asyncio
import json

import httpx
import pytest

from factorio_bridge.odoo import OdooClient
from test_webhooks import settings


def test_exact_single_json2_request_and_validation(tmp_path, pumpworks_payload):
    async def scenario():
        calls = []
        def source(request):
            calls.append(request)
            assert str(request.url) == 'http://127.0.0.1:8069/json/2/factorio.factory/get_snapshot'
            assert request.headers['Authorization'] == 'Bearer private-key'
            assert request.headers['X-Odoo-Database'] == 'factorio_demo'
            assert json.loads(request.content) == {}
            return httpx.Response(200, json=pumpworks_payload)
        async with httpx.AsyncClient(transport=httpx.MockTransport(source)) as http:
            client = OdooClient(settings(tmp_path), http)
            snapshot = await client.get_snapshot()
            assert snapshot.meta.scope_id == 'company:1/warehouse:1'
            assert len(calls) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('response', ['error', 'invalid', 'foreign', 'oversize'])
def test_rejected_source_responses(tmp_path, pumpworks_payload, response):
    async def scenario():
        payload = json.loads(json.dumps(pumpworks_payload))
        if response == 'foreign':
            payload['meta']['source_id'] = '00000000-0000-0000-0000-000000000001'
        def source(request):
            if response == 'error':
                return httpx.Response(503, text='secret source body')
            if response == 'invalid':
                return httpx.Response(200, json={'invalid': True})
            if response == 'oversize':
                return httpx.Response(200, content=b'x' * (256 * 1024 + 1))
            return httpx.Response(200, json=payload)
        async with httpx.AsyncClient(transport=httpx.MockTransport(source)) as http:
            with pytest.raises((ValueError, httpx.HTTPError)):
                await OdooClient(settings(tmp_path), http).get_snapshot()
    asyncio.run(scenario())


def test_client_over_real_loopback_http(tmp_path, pumpworks_payload):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    requests = []
    class Source(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, self.headers['Authorization'], self.headers['X-Odoo-Database'], self.rfile.read(int(self.headers['Content-Length']))))
            body = json.dumps(pumpworks_payload).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Source)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    async def scenario():
        configured = settings(tmp_path).model_copy(update={'odoo_base_url': f'http://127.0.0.1:{server.server_port}'})
        async with httpx.AsyncClient(trust_env=False) as http:
            snapshot = await OdooClient(configured, http).get_snapshot()
        assert snapshot.meta.source_read_at.isoformat() == '2026-10-09T12:00:00+00:00'
        assert requests == [('/json/2/factorio.factory/get_snapshot', 'Bearer private-key', 'factorio_demo', b'{}')]
    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
