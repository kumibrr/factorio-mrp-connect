"""Fresh host-run isolated evidence, passed into the pinned offline assertions."""
import json
import os
from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def smoke_report():
    path = os.environ.get('FACTORIO_SMOKE_REPORT')
    assert path, 'check e2e must execute the live smoke harness and supply its fresh report'
    report = json.loads(Path(path).read_text())
    assert report['context'] == 'isolated-backend-test-lua-receiver'
    assert report['project'] == 'factorio-connect-tests'
    assert report['database'] == 'factorio_tests'
    assert report['passed'], report
    return report
