"""Shared local demo identity and secret-safe Compose process boundary."""
import json
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import stat
import uuid

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


def verify_labels(labels, project, run_id=None):
    if labels.get('io.factorio-connect.owner') != OWNER or labels.get('com.docker.compose.project') != project:
        raise ValueError('target ownership labels do not match this demo project')
    if run_id is not None and labels.get('io.factorio-connect.test-run') != run_id:
        raise ValueError('target ownership does not match the current test run')


def state_path():
    return Path(os.environ.get('FACTORIO_STATE_DIR', Path.home() / '.local/share/factorio-connect/demo')).expanduser().resolve()


def verify_state(state, project):
    identity = state / 'state-owner.json'
    if not identity.is_file() or identity.is_symlink() or json.loads(identity.read_text()) != {'owner': OWNER, 'project': project}:
        raise ValueError('state ownership does not match this demo project')


def environment(state, *, context=None):
    env = dict(os.environ) | (context or {}) | pins()
    verify_state(state, env.get('FACTORIO_PROJECT', PROJECT))
    env['FACTORIO_STATE_DIR'] = str(state)
    env['POSTGRES_PASSWORD'] = (state / 'db-password').read_text().strip()
    if test_project(env.get('FACTORIO_PROJECT', PROJECT)) and (state / 'backend.compose.yaml').exists():
        env['FACTORIO_COMPOSE_OVERRIDE'] = str(state / 'backend.compose.yaml')
    env['ODOO_MASTER_PASSWORD'] = (state / 'master-password').read_text().strip()
    return env


def test_project(project):
    return project == 'factorio-connect-tests' or project.startswith('factorio-connect-test-')


def database(env):
    value = env.get('ODOO_DATABASE', 'factorio_demo')
    if value == 'factorio_demo':
        return value
    if value != 'factorio_tests' or env.get('FACTORIO_PROJECT') != 'factorio-connect-tests':
        raise ValueError('database must be factorio_demo in production')
    if env.get('FACTORIO_TEST_CONTEXT') != 'factorio-connect-tests':
        raise ValueError('factorio_tests requires explicit isolated test context')
    verify_state(Path(env.get('FACTORIO_STATE_DIR', '/nonexistent')), 'factorio-connect-tests')
    return value


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


def owned_targets(project, run_id=None):
    targets = []
    for kind, noun in [('container', 'ps'), ('volume', 'volume'), ('network', 'network')]:
        command = ['docker', 'ps', '-aq'] if kind == 'container' else ['docker', noun, 'ls', '-q']
        ids = run(command + ['--filter', 'label=com.docker.compose.project=' + project]).split()
        if ids:
            items = json.loads(run(['docker', kind, 'inspect', *ids]))
            for item in items:
                labels = (item.get('Config') or {}).get('Labels') if kind == 'container' else item.get('Labels')
                verify_labels(labels or {}, project, run_id)
                targets.append((kind, item.get('Id') or item['Name']))
    return targets


@contextmanager
def exclusive_test_project(project):
    """Hold one local-user project lock from empty-project inspection to cleanup."""
    if not test_project(project):
        raise ValueError('exclusive test lifecycle requires an isolated test project')
    directory = Path('/tmp') / ('factorio-connect-test-locks-' + str(os.getuid()))
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('test lock directory ownership or permissions mismatch')
    descriptor = os.open(directory / (project + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('test lock file ownership or permissions mismatch')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('isolated project has an active test run; refusing concurrent entry') from None
        if owned_targets(project):
            raise RuntimeError('isolated test project already exists; refusing to reuse or discard existing resources')
        yield str(uuid.uuid4())
    finally:
        os.close(descriptor)
    # Keep the lock inode: unlinking it would allow two locks on the same name.


def cleanup_test_project(env):
    """Inspect every target first, then delete only this run's enumerated IDs."""
    project, run_id = env.get('FACTORIO_PROJECT'), env.get('FACTORIO_TEST_RUN')
    if not project or not test_project(project) or not run_id:
        raise ValueError('cleanup requires an isolated project and current test run identity')
    targets = owned_targets(project, run_id=run_id)
    for kind, target in targets:
        command = ['docker', 'rm', '-f', target] if kind == 'container' else ['docker', kind, 'rm', target]
        run(command, environment=env)


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
