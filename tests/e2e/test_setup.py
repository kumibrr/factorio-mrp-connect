"""Operator contracts; actual Docker provisioning is recorded separately."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def load_bootstrap():
    path = ROOT / 'scripts/bootstrap-demo'
    assert path.exists(), 'bootstrap interface missing'
    loader = importlib.machinery.SourceFileLoader('bootstrap_demo', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_compose_matches_linux_socket_contract():
    config = json.loads(Path(os.environ['FACTORIO_COMPOSE_CONFIG']).read_text())
    services = config['services']
    assert not services['db'].get('ports')
    assert services['bridge']['network_mode'] == 'host'
    assert services['odoo']['ports'][0]['host_ip'] == '127.0.0.1'
    assert str(services['odoo']['ports'][0]['published']) == '8069'
    assert services['bridge']['environment']['FACTORIO_BIND_HOST'] == '172.28.0.1'
    assert str(services['bridge']['environment']['FACTORIO_UDP_PORT']) == '34200'
    assert str(services['bridge']['environment']['FACTORIO_GAME_UDP_PORT']) == '34199'
    for name in ('db', 'odoo'):
        assert '@sha256:' in services[name]['image']
    assert '@sha256:' in services['bridge']['build']['args']['PYTHON_IMAGE']
    assert config['networks']['default']['ipam']['config'][0] == {'subnet': '172.28.0.0/24', 'gateway': '172.28.0.1'}
    for name in ('db', 'odoo', 'bridge'):
        assert services[name]['labels']['io.factorio-connect.owner'] == 'factorio-connect-demo'


def test_bootstrap_rerun_preserves_seed_and_secrets(tmp_path, monkeypatch):
    module = load_bootstrap()
    state = module.prepare_state(tmp_path / 'outside-git')
    before = {p.name: p.read_bytes() for p in state.iterdir() if p.is_file()}
    # Provisioned metadata and seed IDs represent prior committed operator state.
    metadata = {'source_id': '12345678-1234-5678-1234-567812345678', 'scope_id': 'company:1/warehouse:1', 'key_expires': '2026-11-08', 'seed_ids': [1, 2, 3]}
    (state / 'metadata.json').write_text(json.dumps(metadata))
    module.prepare_state(state)
    assert all((state / name).read_bytes() == data for name, data in before.items())
    assert json.loads((state / 'metadata.json').read_text()) == metadata
    assert all(p.stat().st_mode & 0o077 == 0 for p in state.iterdir() if p.is_file())
    assert (state / 'db-password').read_text().startswith('factorio-')


def test_package_has_expected_root_and_no_secrets(tmp_path):
    script = ROOT / 'scripts/package-mod'
    assert script.exists(), 'packaging interface missing'
    destination = tmp_path / 'dist'
    result = subprocess.run([sys.executable, str(script), '--output-dir', str(destination)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    archive = destination / 'factorio-connect_0.1.0.zip'
    first = archive.read_bytes()
    subprocess.run([sys.executable, str(script), '--output-dir', str(destination)], check=True, capture_output=True)
    assert archive.read_bytes() == first
    with zipfile.ZipFile(archive) as package:
        assert all(name.startswith('factorio-connect_0.1.0/') for name in package.namelist())
        expected = ['info.json', 'control.lua', 'data.lua', 'data-final-fixes.lua', 'settings.lua']
        assert all('factorio-connect_0.1.0/' + name in package.namelist() for name in expected)
        assert all('/tests/' not in name and '.env' not in name and 'token' not in name for name in package.namelist())
        for name in package.namelist():
            source = ROOT / 'factorio-mod' / name.split('/', 1)[1]
            assert source.read_bytes() == package.read(name)


def test_preflight_rejects_remote_and_rootless():
    module = load_bootstrap()
    with pytest.raises(ValueError, match='local'):
        module.validate_daemon('tcp://remote:2375', ['name=seccomp'], 'linux')
    with pytest.raises(ValueError, match='rootful'):
        module.validate_daemon('unix:///run/user/1000/docker.sock', ['name=rootless'], 'linux')
    module.validate_daemon('unix:///var/run/docker.sock', ['name=seccomp'], 'linux')


def test_preflight_accepts_builtin_network_without_ipam(tmp_path, monkeypatch):
    module = load_bootstrap()
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    responses = {
        ('docker', 'context', 'inspect'): json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}]),
        ('docker', 'info', '--format', '{{json .}}'): json.dumps({'SecurityOptions': [], 'OSType': 'linux'}),
        ('docker', 'compose', 'version', '--short'): '5.5.1',
        ('docker', 'network', 'ls', '-q'): 'host-network',
        ('docker', 'network', 'inspect', 'host-network'): json.dumps([{'Labels': {}, 'IPAM': {'Config': None}}]),
    }
    monkeypatch.setattr(module, 'run', lambda args: responses.get(tuple(args), 'already-running' if args[:3] == ['docker', 'ps', '-q'] else ''))
    # Resource enumeration also crosses Docker, so isolate that separate boundary.
    monkeypatch.setattr(module, 'owned_targets', lambda project: [])
    module.preflight({})


def test_seed_cli_uses_official_database_entrypoint(tmp_path, monkeypatch, capsys):
    loader = importlib.machinery.SourceFileLoader('seed_cli', str(ROOT / 'scripts/seed-demo'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setenv('FACTORIO_STATE_DIR', str(tmp_path / 'absent'))
    monkeypatch.setenv('POSTGRES_PASSWORD', 'caller-secret')
    monkeypatch.setattr(sys, 'argv', ['seed-demo', '--verify-baseline'])
    calls = []
    def docker_boundary(args, **kwargs):
        calls.append((args, kwargs))
        return '{"verified": true}'
    monkeypatch.setattr(module, 'run', docker_boundary)
    module.main()
    assert '/entrypoint.sh' in calls[0][0]
    assert 'caller-secret' not in ' '.join(calls[0][0])
    assert 'FACTORIO_SEED_MODE=--verify-baseline' in calls[0][0]
    assert 'SET TRANSACTION READ ONLY' in calls[0][1]['input']
    assert 'caller-secret' not in capsys.readouterr().out


def test_runtime_pins_reject_moving_or_wrong_major_images():
    module = load_bootstrap()
    from demo_common import pins
    expected = pins()
    module.validate_versions(expected)
    for name, image in [('ODOO_IMAGE','odoo:latest'),('POSTGRES_IMAGE','postgres:18@sha256:' + 'a'*64),('PYTHON_IMAGE','python:3.13@sha256:' + 'a'*64)]:
        with pytest.raises(ValueError, match='pin'):
            module.validate_versions(dict(expected, **{name:image}))


def test_docker_failure_diagnostics_use_common_redactor(tmp_path):
    from demo_common import run, private_write
    state = tmp_path / 'state'
    state.mkdir()
    private_write(state / 'api-key', 'private-api')
    environment = dict(os.environ, FACTORIO_STATE_DIR=str(state), POSTGRES_PASSWORD='private-db')
    command = [sys.executable, '-c', "import sys; print('Bearer private-api /odoo/events/private-hook private-db', file=sys.stderr); sys.exit(1)"]
    with pytest.raises(RuntimeError) as error:
        run(command, environment=environment)
    assert '[REDACTED]' in str(error.value)
    assert 'private-api' not in str(error.value)
    assert 'private-hook' not in str(error.value)
    assert 'private-db' not in str(error.value)


def test_backend_adapter_is_explicit_and_test_project_only(tmp_path, monkeypatch):
    module = load_bootstrap()
    state = tmp_path / 'state'
    state.mkdir()
    env = {'FACTORIO_PROJECT': 'factorio-connect-tests', 'FACTORIO_STATE_DIR': str(state), 'BRIDGE_HTTP_PORT': '8875'}
    def docker_boundary(args, **kwargs):
        if args[-3:] == ['ps', '-q', 'odoo']:
            return 'odoo-test-container'
        return json.dumps([{'NetworkSettings': {'Networks': {'factorio-connect-tests_default': {'IPAddress': '172.29.0.3'}}}}])
    monkeypatch.setattr(module, 'run', docker_boundary)
    module.configure_backend(state, env)
    override = json.loads((state / 'backend.compose.yaml').read_text())
    bridge = override['services']['bridge']
    assert bridge['network_mode'] == 'service:odoo'
    assert bridge['environment']['FACTORIO_BIND_HOST'] == '172.29.0.3'
    assert bridge['environment']['FACTORIO_ODOO_BASE_URL'] == 'http://127.0.0.1:8069'
    from demo_common import compose
    assert str(state / 'backend.compose.yaml') in compose(env)
    with pytest.raises(ValueError, match='test'):
        compose(dict(env, FACTORIO_PROJECT='factorio-connect'))


def test_bootstrap_refuses_foreign_state_directory(tmp_path):
    module = load_bootstrap()
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    (foreign / 'important').write_text('preserve')
    with pytest.raises(ValueError, match='state ownership'):
        module.prepare_state(foreign)
    assert (foreign / 'important').read_text() == 'preserve'
    owned = module.prepare_state(tmp_path / 'owned')
    with pytest.raises(ValueError, match='state ownership'):
        module.prepare_state(owned, project='factorio-connect-test-other')


def test_compose_minimum_supports_optional_env_file_and_newer_majors():
    module = load_bootstrap()
    with pytest.raises(ValueError, match='2.24'):
        module.validate_compose_version('2.23.3')
    module.validate_compose_version('2.24.0')
    module.validate_compose_version('5.5.1')


def test_preflight_honors_remote_context_over_local_host_override(monkeypatch):
    module = load_bootstrap()
    monkeypatch.setenv('DOCKER_CONTEXT', 'remote-context')
    monkeypatch.setenv('DOCKER_HOST', 'unix:///var/run/docker.sock')
    def docker_boundary(args):
        if args == ['docker', 'context', 'inspect']:
            return json.dumps([{'Endpoints': {'docker': {'Host': 'ssh://remote'}}}])
        return json.dumps({'SecurityOptions': [], 'OSType': 'linux'})
    monkeypatch.setattr(module, 'run', docker_boundary)
    with pytest.raises(ValueError, match='local'):
        module.preflight({})


def test_normal_bootstrap_rejects_test_override(monkeypatch):
    module = load_bootstrap()
    monkeypatch.delenv('DOCKER_CONTEXT', raising=False)
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    def docker_boundary(args):
        if args == ['docker', 'context', 'inspect']:
            return json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}])
        if args == ['docker','compose','version','--short']:
            return '5.5.1'
        return json.dumps({'SecurityOptions': [], 'OSType': 'linux'})
    monkeypatch.setattr(module, 'run', docker_boundary)
    with pytest.raises(ValueError, match='explicit --backend-test'):
        module.preflight({'FACTORIO_PROJECT':'factorio-connect-tests','FACTORIO_COMPOSE_OVERRIDE':'test-only.yaml'})


def test_preflight_rejects_docker_desktop_socket():
    module = load_bootstrap()
    with pytest.raises(ValueError, match='Desktop'):
        module.validate_daemon('unix:///home/operator/.docker/desktop/docker.sock', [], 'linux')


@pytest.mark.parametrize('business_input', [b'ORM heredoc sentinel\n', b'backup\x00dump\xffbytes\n'])
def test_documented_compose_wrapper_preserves_business_stdin(tmp_path, business_input):
    import re
    guide = (ROOT / 'docs/local-demo.md').read_text()
    wrapper = re.search(r'demo\(\) \{\n.*?\n\}', guide, re.DOTALL).group()
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    # Isolate only Docker and credential loading. The exact documented bash/Python
    # launcher and a real harmless stdin-echo child are executed unchanged.
    (scripts / 'demo_common.py').write_text('''
import os, sys
from pathlib import Path
execute = os.execvpe
os.execvpe = lambda executable, args, env: execute(sys.executable, [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'], env)
def compose(env): return ['docker', 'compose']
def environment(state): return dict(os.environ)
def state_path(): return Path('/nonexistent/harmless-fixture')
''')
    payload = tmp_path / 'business-input'
    payload.write_bytes(business_input)
    with payload.open('rb') as source:
        result = subprocess.run(['bash', '-c', wrapper + '\ndemo exec -T odoo harmless-child'], cwd=tmp_path, stdin=source, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == business_input


def test_database_guard_rejects_production_wrong_database(tmp_path):
    from demo_common import database, private_write
    with pytest.raises(ValueError, match='database'):
        database({'ODOO_DATABASE': 'factorio_tests'})
    with pytest.raises(ValueError, match='isolated'):
        database({'FACTORIO_PROJECT': 'factorio-connect-tests', 'ODOO_DATABASE': 'factorio_tests'})
    state = tmp_path / 'owned'
    state.mkdir()
    private_write(state / 'state-owner.json', json.dumps({'owner': 'factorio-connect-demo', 'project': 'factorio-connect-tests'}))
    explicit = {'FACTORIO_PROJECT': 'factorio-connect-tests', 'ODOO_DATABASE': 'factorio_tests', 'FACTORIO_TEST_CONTEXT': 'factorio-connect-tests', 'FACTORIO_STATE_DIR': str(state)}
    assert database(explicit) == 'factorio_tests'
    assert database({}) == 'factorio_demo'
    cli_env = dict(os.environ, FACTORIO_STATE_DIR=str(tmp_path / 'absent'), FACTORIO_PROJECT='factorio-connect', ODOO_DATABASE='factorio_tests', POSTGRES_PASSWORD='nonsecret-guard-probe')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/seed-demo'), '--verify'], env=cli_env, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'database must be factorio_demo in production' in result.stderr
    with pytest.raises(ValueError, match='database'):
        database(dict(explicit, FACTORIO_PROJECT='factorio-connect'))
    with pytest.raises(ValueError, match='ownership'):
        database(dict(explicit, FACTORIO_STATE_DIR=str(tmp_path / 'foreign')))


def test_isolated_environment_retains_context_and_owned_credentials(tmp_path, monkeypatch):
    from demo_common import environment, private_write
    module = load_bootstrap()
    monkeypatch.delenv('FACTORIO_PROJECT', raising=False)
    state = module.prepare_state(tmp_path / 'isolated', project='factorio-connect-tests')
    private_write(state / 'backend.compose.yaml', '{}')
    env = environment(state, context={'FACTORIO_PROJECT': 'factorio-connect-tests', 'FACTORIO_TEST_CONTEXT': 'factorio-connect-tests', 'ODOO_DATABASE': 'factorio_tests'})
    assert env['FACTORIO_PROJECT'] == env['FACTORIO_TEST_CONTEXT'] == 'factorio-connect-tests'
    assert env['ODOO_DATABASE'] == 'factorio_tests'
    assert env['POSTGRES_PASSWORD'] == (state / 'db-password').read_text().strip()
    assert env['FACTORIO_COMPOSE_OVERRIDE'] == str(state / 'backend.compose.yaml')


def test_webhook_debug_configuration_requires_explicit_isolated_backend_context():
    import configparser
    module = load_bootstrap()
    context = {'FACTORIO_PROJECT': 'factorio-connect-tests', 'FACTORIO_TEST_CONTEXT': 'factorio-connect-tests',
               'FACTORIO_TEST_WEBHOOK_DEBUG': '1'}
    for env, backend in [(context, False), (dict(context, FACTORIO_PROJECT='factorio-connect'), True),
                         (dict(context, FACTORIO_TEST_CONTEXT=''), True),
                         (dict(context, FACTORIO_TEST_WEBHOOK_DEBUG='all'), True)]:
        with pytest.raises(ValueError, match='webhook debug'):
            module.odoo_configuration(env, backend_test=backend)
    config = configparser.ConfigParser()
    config.read_string(module.odoo_configuration(context, backend_test=True))
    assert config['options']['log_handler'] == 'odoo.addons.base.models.ir_actions:DEBUG'
    default = configparser.ConfigParser()
    default.read_string(module.odoo_configuration({}, backend_test=False))
    assert 'log_handler' not in default['options']


@pytest.mark.parametrize('flag,diagnostic', [('FACTORIO_TEST_WEBHOOK_DEBUG','webhook debug'), ('FACTORIO_TEST_DISABLE_CRON','cron control')])
def test_production_bootstrap_refuses_test_configuration_before_docker(tmp_path, flag, diagnostic):
    env = dict(os.environ, FACTORIO_PROJECT='factorio-connect',
               FACTORIO_STATE_DIR=str(tmp_path / 'absent'), DOCKER_HOST='tcp://deliberately-unavailable:1')
    env[flag] = '1'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/bootstrap-demo'), '--check'],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 2 and diagnostic in result.stderr
    assert 'Docker' not in result.stderr and not (tmp_path / 'absent').exists()


def test_isolated_cron_control_preserves_production_defaults_and_requires_backend_context():
    import configparser
    module = load_bootstrap()
    context = {'FACTORIO_PROJECT': 'factorio-connect-tests', 'FACTORIO_TEST_CONTEXT': 'factorio-connect-tests',
               'FACTORIO_TEST_DISABLE_CRON': '1'}
    for env, backend in [(context, False), (dict(context, FACTORIO_PROJECT='factorio-connect'), True),
                         (dict(context, FACTORIO_TEST_CONTEXT=''), True),
                         (dict(context, FACTORIO_TEST_DISABLE_CRON='all'), True)]:
        with pytest.raises(ValueError, match='cron control'):
            module.odoo_configuration(env, backend_test=backend)
    config = configparser.ConfigParser()
    config.read_string(module.odoo_configuration(context, backend_test=True))
    assert config['options']['max_cron_threads'] == '0'
    assert 'log_handler' not in config['options']
    default = configparser.ConfigParser()
    default.read_string(module.odoo_configuration({}, backend_test=False))
    assert 'max_cron_threads' not in default['options']


def test_deployed_smoke_unavailable_endpoint_emits_failed_report():
    env = dict(os.environ, ODOO_GATEWAY='127.0.0.1', BRIDGE_HTTP_PORT='0', NO_PROXY='127.0.0.1')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke-demo')], env=env, capture_output=True, text=True)
    assert result.stdout.strip().startswith('{'), 'outage must emit a structured report'
    report = json.loads(result.stdout)
    assert result.returncode != 0
    assert report['context'] == 'deployed-read-only-health'
    assert report['passed'] is False
    for field in ('source_read_at', 'published_revision', 'applied_revision', 'commit_delivery_seconds', 'seed', 'health'):
        assert report[field] is None
    assert 'ConnectionRefusedError' in report['error']
    assert not result.stderr


@pytest.mark.parametrize('mode,diagnostic', [
    ('http_error', '503'), ('invalid_json', 'JSONDecodeError'),
    ('invalid_utf8', 'UnicodeDecodeError'), ('invalid_shape', 'ValueError'),
    ('missing_fields', 'KeyError'), ('invalid_types', 'ValueError'),
    ('timeout', 'TimeoutError'),
])
def test_deployed_smoke_expected_health_failures_are_bounded_and_nonsecret(mode, diagnostic):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import time
    secret = 'private-response-credential'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if mode == 'timeout':
                time.sleep(3.5)
            self.send_response(503 if mode == 'http_error' else 200, secret)
            self.end_headers()
            payloads = {
                'invalid_json': secret.encode(), 'invalid_utf8': b'\xff',
                'invalid_shape': b'[]', 'missing_fields': json.dumps({'credential': secret}).encode(),
                'invalid_types': json.dumps({'source_ok': 'true', 'latest_revision': 1, 'applied_revision': 1, 'source_read_at': None, 'credential': secret}).encode(),
            }
            try:
                self.wfile.write(payloads.get(mode, secret.encode()))
            except OSError:
                pass  # The real timeout intentionally closes the client socket.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ, ODOO_GATEWAY='127.0.0.1', BRIDGE_HTTP_PORT=str(server.server_port), NO_PROXY='127.0.0.1')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke-demo')], env=env, capture_output=True, text=True)
        assert result.stdout.strip().startswith('{'), 'expected failure must emit a structured report'
        report = json.loads(result.stdout)
        assert result.returncode != 0 and report['passed'] is False
        assert report['context'] == 'deployed-read-only-health'
        for field in ('source_read_at', 'published_revision', 'applied_revision', 'commit_delivery_seconds', 'seed', 'health'):
            assert report[field] is None
        assert diagnostic in report['error'] and len(report['error']) <= 160
        assert secret not in result.stdout + result.stderr
        assert not result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('source_ok,applied,expected_exit', [(True, 4, 0), (True, 3, 1), (False, 4, 1)])
def test_deployed_smoke_preserves_known_health_and_acknowledgments(source_ok, applied, expected_exit):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    health = {'source_ok': source_ok, 'latest_revision': 4, 'applied_revision': applied, 'source_read_at': '2026-10-09T18:00:00Z'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(health).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ, ODOO_GATEWAY='127.0.0.1', BRIDGE_HTTP_PORT=str(server.server_port), NO_PROXY='127.0.0.1')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke-demo')], env=env, capture_output=True, text=True)
        report = json.loads(result.stdout)
        assert result.returncode == expected_exit and not result.stderr
        assert report['passed'] is (expected_exit == 0)
        assert report['source_read_at'] == '2026-10-09T18:00:00Z'
        assert report['published_revision'] == 4 and report['applied_revision'] == applied
        assert report['health'] == health and report['error'] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
