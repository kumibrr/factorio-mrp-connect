"""Local runtime settings; secrets never enter snapshots or health responses."""
import os
from pathlib import Path
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    odoo_base_url: str = 'http://127.0.0.1:8069'
    database: str = 'factorio_demo'
    api_key: SecretStr
    webhook_token: SecretStr
    pairing_token: SecretStr
    source_id: UUID
    scope_id: str = Field(pattern=r'^company:[1-9][0-9]*/warehouse:[1-9][0-9]*$')
    cache_path: Path = Path('/var/lib/factorio-bridge/cache.sqlite')
    bind_host: Literal['172.28.0.1'] = '172.28.0.1'
    udp_port: int = Field(default=34200, ge=1, le=65535)
    game_udp_port: int = Field(default=34199, ge=1, le=65535)
    bind_port: int = Field(default=8765, ge=1, le=65535)

    @field_validator('api_key', 'webhook_token', 'pairing_token')
    @classmethod
    def valid_secret(cls, value):
        secret = value.get_secret_value()
        if not secret or any(char.isspace() for char in secret) or '/' in secret:
            raise ValueError('Credential must be a nonempty token')
        return value

    @field_validator('odoo_base_url')
    @classmethod
    def valid_url(cls, value):
        from urllib.parse import urlsplit
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Odoo URL must be an HTTP origin without credentials')
        return value.rstrip('/')

    @classmethod
    def from_env(cls):
        return cls.model_validate({name: os.environ['FACTORIO_' + name.upper()] for name in cls.model_fields if 'FACTORIO_' + name.upper() in os.environ})
