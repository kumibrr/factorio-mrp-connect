"""Run public test entry points; replace only external process/entropy boundaries."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Loaded by the child interpreter, including Bash's Docker adapter below. This
# avoids executable test files on the pinned runner's noexec temporary mount.
BOUNDARY = r'''
import json, os, secrets, subprocess, time
from pathlib import Path
secrets.token_urlsafe=lambda _: '-pathological-random-token'
original_run=subprocess.run
capture=Path(os.environ['CHECK_CAPTURE'])
scenario=os.environ['CHECK_SCENARIO']
state=Path(os.environ['CHECK_STATE'])
def boundary(args, **kwargs):
    args=list(map(str,args))
    if args[0]!='docker' and not (args[0].endswith('/scripts/check') or args[0].endswith('/scripts/bootstrap-demo')):
        return original_run(args, **kwargs)
    env=kwargs.get('env') or os.environ
    with capture.open('a') as stream:
        stream.write(json.dumps({'args':args,'password':env.get('POSTGRES_PASSWORD')})+'\n')
    output='';code=0;error=''
    kind=None
    if args[:3]==['docker','ps','-aq']: kind='container'
    elif args[:3]==['docker','volume','ls']: kind='volume'
    elif args[:3]==['docker','network','ls']: kind='network'
    if kind:
        if scenario=='existing_owned' and kind=='container': output='existing-container'
        elif scenario=='wrong_owner' and kind=='volume': output='foreign-volume'
        elif state.exists() and kind=='container': output='current-container'
        elif state.exists() and kind=='volume' and scenario=='cleanup_mismatch_volume': output='changed-volume'
    elif len(args)>2 and args[0]=='docker' and args[2]=='inspect' and args[1] in ('container','volume','network'):
        labels={'com.docker.compose.project':'factorio-connect-tests','io.factorio-connect.owner':'factorio-connect-demo'}
        if scenario=='wrong_owner': labels.pop('io.factorio-connect.owner')
        if state.exists(): labels['io.factorio-connect.test-run']=state.read_text()
        if scenario=='cleanup_mismatch' or (scenario=='cleanup_mismatch_volume' and args[1]=='volume'): labels['io.factorio-connect.test-run']='other-run'
        item={'Id':args[-1],'Name':args[-1],'Labels':labels,'Config':{'Labels':labels}}
        output=json.dumps([item])
    elif 'up' in args or args[0].endswith('/scripts/bootstrap-demo'):
        if 'up' in args or scenario=='diagnostic_cleanup_failure': state.write_text(env.get('FACTORIO_TEST_RUN','unguarded'))
        if scenario=='hold':
            Path(os.environ['CHECK_READY']).touch()
            while not Path(os.environ['CHECK_RELEASE']).exists(): time.sleep(.02)
        code=1;error='deliberate native-start failure'
    elif 'logs' in args and scenario=='diagnostic_cleanup_failure': code=1;error='deliberate diagnostic log failure'
    elif args[:3]==['docker','rm','-f']: state.unlink(missing_ok=True)
    elif 'run' in args: code=1;error='unexpected native test reached'
    return subprocess.CompletedProcess(args,code,output,error)
subprocess.run=boundary
'''


def child_environment(tmp_path, scenario):
    boundary_path = tmp_path / 'boundary'
    boundary_path.mkdir(exist_ok=True)
    (boundary_path / 'sitecustomize.py').write_text(BOUNDARY)
    env = dict(os.environ, PYTHONPATH=str(boundary_path), CHECK_SCENARIO=scenario,
               CHECK_CAPTURE=str(tmp_path / 'commands.jsonl'), CHECK_STATE=str(tmp_path / 'created'),
               CHECK_READY=str(tmp_path / 'ready'), CHECK_RELEASE=str(tmp_path / 'release'))
    env['BASH_FUNC_docker%%'] = '() { ' + shlex.quote(sys.executable) + " -c 'import subprocess,sys; r=subprocess.run([\"docker\",*sys.argv[1:]]); print(r.stdout,end=\"\"); print(r.stderr,end=\"\",file=sys.stderr); sys.exit(r.returncode)' \"$@\"; }"
    env.pop('FACTORIO_TEST_DB_PASSWORD', None)
    env.pop('FACTORIO_COMPOSE_OVERRIDE', None)
    return env


def calls(env):
    path = Path(env['CHECK_CAPTURE'])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def check(env):
    return subprocess.run(['/bin/bash', str(ROOT / 'scripts/check'), 'odoo', '--tags', '/factorio_connect'], env=env, capture_output=True, text=True)


@pytest.mark.parametrize('scenario,diagnostic', [('existing_owned','already exists'), ('wrong_owner','ownership')])
def test_odoo_check_refuses_existing_targets_before_any_mutation(tmp_path, scenario, diagnostic):
    env = child_environment(tmp_path, scenario)
    result = check(env)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    commands = [row['args'] for row in calls(env)]
    assert commands, 'ownership inspection never ran'
    assert not any('up' in cmd or 'run' in cmd or 'down' in cmd or 'rm' in cmd for cmd in commands)


def test_generated_database_password_is_safe_for_native_cli_and_failed_run_cleans_its_owned_targets(tmp_path):
    env = child_environment(tmp_path, 'new_owned')
    result = check(env)
    assert result.returncode != 0
    commands = calls(env)
    assert any('up' in row['args'] for row in commands)
    assert any(row['args'][:3] == ['docker','rm','-f'] for row in commands)
    assert next(row['password'] for row in commands if 'up' in row['args']) == 'factorio--pathological-random-token'
    assert not Path(env['CHECK_STATE']).exists()


@pytest.mark.parametrize('scenario', ['cleanup_mismatch','cleanup_mismatch_volume'])
def test_odoo_check_refuses_cleanup_if_current_run_ownership_changed(tmp_path, scenario):
    env = child_environment(tmp_path, scenario)
    result = check(env)
    assert result.returncode != 0 and 'current test run' in result.stderr
    assert not any('down' in row['args'] or 'rm' in row['args'] for row in calls(env))
    assert Path(env['CHECK_STATE']).exists()


@pytest.mark.parametrize('first', ['check','smoke'])
def test_native_check_and_smoke_cannot_enter_same_project_concurrently(tmp_path, first):
    env = child_environment(tmp_path, 'hold')
    native = ['/bin/bash', str(ROOT / 'scripts/check'), 'odoo']
    smoke = [sys.executable, str(ROOT / 'scripts/smoke-demo'), '--isolated-test', '--output', str(tmp_path / 'smoke.json')]
    command, contender = (native, smoke) if first == 'check' else (smoke, native)
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not Path(env['CHECK_READY']).exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert Path(env['CHECK_READY']).exists(), process.communicate(timeout=1)
        before = len(calls(env))
        result = subprocess.run(contender, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and 'active test run' in result.stderr
        assert len(calls(env)) == before, 'contender crossed Docker boundary despite exclusive project lock'
    finally:
        Path(env['CHECK_RELEASE']).touch()
        process.communicate(timeout=10)


def test_smoke_diagnostic_log_failure_still_cleans_verified_current_run_resources(tmp_path):
    env = child_environment(tmp_path, 'diagnostic_cleanup_failure')
    env['FACTORIO_TEST_WEBHOOK_DEBUG'] = '1'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke-demo'), '--isolated-test',
                             '--output', str(tmp_path / 'smoke.json')], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'deliberate diagnostic log failure' in result.stderr
    assert any(row['args'][:3] == ['docker','rm','-f'] for row in calls(env))
    assert not Path(env['CHECK_STATE']).exists()
