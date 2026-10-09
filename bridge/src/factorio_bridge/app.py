"""Metadata-only notification endpoint; response never waits for source IO."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import secrets
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .logging import install_redaction


class Notification(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    model: Literal['mrp.workcenter', 'mrp.production', 'mrp.workorder', 'mrp.workcenter.productivity', 'mrp.workcenter.productivity.loss', 'mrp.bom', 'mrp.bom.line', 'mrp.routing.workcenter', 'product.product', 'product.template', 'uom.uom', 'stock.move', 'stock.move.line', 'stock.quant'] = Field(alias='_model')
    record_id: int = Field(alias='_id', gt=0)
    action: str = Field(alias='_action', min_length=1, max_length=512)


def create_app(settings, coordinator, delivery=None) -> FastAPI:
    def redact():
        install_redaction([settings.api_key.get_secret_value(), settings.webhook_token.get_secret_value(), settings.pairing_token.get_secret_value()])
    redact()
    if delivery is not None:
        delivery.on_reconnect = coordinator.request_initial
        delivery.health_provider = lambda: coordinator.health

    @asynccontextmanager
    async def lifespan(app):
        redact()
        try:
            if delivery is not None:
                await delivery.start()
            await coordinator.start()
            yield
        finally:
            await coordinator.stop()
            if delivery is not None:
                await delivery.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.post('/odoo/events/{token}')
    async def event(token: str, request: Request):
        if not secrets.compare_digest(token.encode(), settings.webhook_token.get_secret_value().encode()):
            raise HTTPException(404, 'Not found')
        try:
            body = bytearray()
            async with asyncio.timeout(.2):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 4096:
                        raise HTTPException(413, 'Payload too large')
                    body.extend(chunk)
            Notification.model_validate_json(body)
        except TimeoutError:
            raise HTTPException(408, 'Request body timeout') from None
        except (ValidationError, ValueError):
            raise HTTPException(422, 'Invalid notification') from None
        await coordinator.notify('webhook')
        return Response(status_code=202)

    @app.get('/healthz')
    async def health():
        return {**asdict(coordinator.health), 'dirty': coordinator.dirty,
                'latest_revision': None if coordinator.latest is None else coordinator.latest.revision,
                'applied_revision': None if delivery is None else delivery.applied_revision}

    return app
