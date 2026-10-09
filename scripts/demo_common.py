"""Shared local demo identity and secret-safe Compose process boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'factorio-connect-demo'
PROJECT = 'factorio-connect'


def pins():
    return dict(line.split('=', 1) for line in (ROOT / 'deploy/versions.env').read_text().splitlines() if line and not line.startswith('#'))


def run(args, *, environment=None, input=None, include_stderr=False):
    result = subprocess.run(args, env=environment, input=input, capture_output=True, text=True)
    if result.returncode:
        sys.path.insert(0, str(ROOT / 'bridge/src'))
        from factorio_connect_common.redaction import RedactionFilter
        credentials = [value for name, value in (environment or {}).items() if any(word in name for word in ('PASSWORD', 'TOKEN', 'API_KEY'))]
        state = Path((environment or {}).get('FACTORIO_STATE_DIR', '/nonexistent'))
        for name in ('db-password','master-password','admin-password','operator-password','webhook-token','pairing-token','api-key'):
            path = state / name
            if path.is_file():
                credentials.append(path.read_text().strip())
        details = RedactionFilter(credentials).redact(result.stderr)[-4000:]
        raise RuntimeError(f'{args[0]} operation failed (exit {result.returncode}): ' + details.strip())
    return result.stdout + result.stderr if include_stderr else result.stdout


def verify_labels(labels, project):
    if labels.get('io.factorio-connect.owner') != OWNER or labels.get('com.docker.compose.project') != project:
        raise ValueError('target ownership labels do not match this demo project')


def state_path():
    return Path(os.environ.get('FACTORIO_STATE_DIR', Path.home() / '.local/share/factorio-connect/demo')).expanduser().resolve()


def verify_state(state, project):
    identity = state / 'state-owner.json'
    if not identity.is_file() or identity.is_symlink() or json.loads(identity.read_text()) != {'owner': OWNER, 'project': project}:
        raise ValueError('state ownership does not match this demo project')


def environment(state):
    env = dict(os.environ, **pins())
    verify_state(state, env.get('FACTORIO_PROJECT', PROJECT))
    env['FACTORIO_STATE_DIR'] = str(state)
    env['POSTGRES_PASSWORD'] = (state / 'db-password').read_text().strip()
    if test_project(env.get('FACTORIO_PROJECT', PROJECT)) and (state / 'backend.compose.yaml').exists():
        env['FACTORIO_COMPOSE_OVERRIDE'] = str(state / 'backend.compose.yaml')
    env['ODOO_MASTER_PASSWORD'] = (state / 'master-password').read_text().strip()
    return env


def test_project(project):
    return project == 'factorio-connect-tests' or project.startswith('factorio-connect-test-')


def compose(env):
    project = env.get('FACTORIO_PROJECT', PROJECT)
    if project != PROJECT and not test_project(project):
        raise ValueError('project must be factorio-connect or an isolated factorio-connect-test-* project')
    command = ['docker', 'compose', '-p', project, '-f', str(ROOT / 'deploy/compose.yaml')]
    override = env.get('FACTORIO_COMPOSE_OVERRIDE')
    if override:
        if not test_project(project):
            raise ValueError('Compose override requires an isolated test project')
        command += ['-f', override]
    return command


def owned_targets(project):
    targets = []
    for kind, noun in [('container', 'ps'), ('volume', 'volume'), ('network', 'network')]:
        command = ['docker', 'ps', '-aq'] if kind == 'container' else ['docker', noun, 'ls', '-q']
        ids = run(command + ['--filter', 'label=com.docker.compose.project=' + project]).split()
        if ids:
            items = json.loads(run(['docker', kind, 'inspect', *ids]))
            for item in items:
                labels = (item.get('Config') or {}).get('Labels') if kind == 'container' else item.get('Labels')
                verify_labels(labels or {}, project)
                targets.append((kind, item.get('Id') or item['Name']))
    return targets


def private_write(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('secret path must not be a symlink')
    temporary = path.with_name(path.name + '.new')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(value)
    temporary.chmod(0o600)
    temporary.replace(path)
