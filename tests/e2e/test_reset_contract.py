import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def test_reset_rejects_missing_confirmation_or_unlabelled_target():
    script = ROOT / 'scripts/reset-demo'
    assert script.exists(), 'reset interface missing'
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode != 0
    assert '--confirm factorio-connect-demo' in result.stderr
    from demo_common import verify_labels
    for labels in ({}, {'com.docker.compose.project': 'factorio-connect'}, {'io.factorio-connect.owner': 'factorio-connect-demo', 'com.docker.compose.project': 'other'}):
        with pytest.raises(ValueError, match='ownership'):
            verify_labels(labels, 'factorio-connect')
    verify_labels({'io.factorio-connect.owner': 'factorio-connect-demo', 'com.docker.compose.project': 'factorio-connect'}, 'factorio-connect')


def test_reset_inspects_all_targets_before_deleting(tmp_path, monkeypatch, capsys):
    import json
    import demo_common
    loader = importlib.machinery.SourceFileLoader('reset_cli', str(ROOT / 'scripts/reset-demo'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setenv('FACTORIO_STATE_DIR', str(tmp_path / 'absent'))
    monkeypatch.setattr(sys, 'argv', ['reset-demo','--confirm','factorio-connect-demo'])
    calls = []
    def docker_boundary(args, **kwargs):
        calls.append(args)
        if args[:3] == ['docker','ps','-aq']:
            return 'owned-container'
        if args[:3] == ['docker','container','inspect']:
            return json.dumps([{'Id':'owned-container','Config':{'Labels':{'io.factorio-connect.owner':'factorio-connect-demo','com.docker.compose.project':'factorio-connect'}}}])
        if args[:3] == ['docker','volume','ls']:
            return 'foreign-volume'
        if args[:3] == ['docker','volume','inspect']:
            return json.dumps([{'Name':'foreign-volume','Labels':{'com.docker.compose.project':'factorio-connect'}}])
        raise AssertionError('unexpected mutation or Docker call: '+repr(args))
    monkeypatch.setattr(demo_common,'run',docker_boundary)
    monkeypatch.setattr(module,'run',docker_boundary)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code==2
    assert not any('rm' in command for command in calls)
    assert 'ownership' in capsys.readouterr().err
