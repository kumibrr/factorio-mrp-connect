import pytest
from pydantic import ValidationError
from factorio_bridge.settings import Settings
from test_webhooks import settings


def test_environment_configuration_and_secret_repr(monkeypatch, tmp_path):
    for name, value in {'API_KEY': 'private-api', 'WEBHOOK_TOKEN': 'private-hook', 'PAIRING_TOKEN': 'private-pairing', 'SOURCE_ID': '12345678-1234-5678-1234-567812345679', 'SCOPE_ID': 'company:1/warehouse:1', 'CACHE_PATH': str(tmp_path / 'cache.sqlite')}.items():
        monkeypatch.setenv('FACTORIO_' + name, value)
    configured = Settings.from_env()
    assert configured.api_key.get_secret_value() == 'private-api'
    assert configured.bind_host == '172.28.0.1'
    assert configured.bind_port == 8765
    assert 'private-api' not in repr(configured)
    assert 'private-hook' not in repr(configured)


@pytest.mark.parametrize('url', ['http://user:password@host', 'file:///tmp/source', 'http://host/?token=secret'])
def test_rejects_urls_with_credentials_and_wrong_scheme(tmp_path, url):
    values = settings(tmp_path).model_dump()
    values['odoo_base_url'] = url
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_entrypoint_configuration_error_does_not_disclose_credentials(monkeypatch, capsys):
    from factorio_bridge.__main__ import main
    for name in list(__import__('os').environ):
        if name.startswith('FACTORIO_'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('FACTORIO_API_KEY', 'startup-private-api')
    monkeypatch.setenv('FACTORIO_WEBHOOK_TOKEN', 'startup-private-hook')
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert 'Invalid bridge configuration' in output.err
    assert 'startup-private' not in output.err


def test_private_gateway_http_binding_and_pairing_secret(tmp_path):
    values = settings(tmp_path).model_dump()
    values['bind_host'] = '0.0.0.0'
    with pytest.raises(ValidationError):
        Settings.model_validate(values)
    values.pop('bind_host')
    values['pairing_token'] = 'bad / token'
    with pytest.raises(ValidationError):
        Settings.model_validate(values)
