"""Execute the harness with only entropy and Docker process boundaries stubbed."""
import os
from pathlib import Path
import subprocess
import shlex
import sys


def test_generated_database_password_is_safe_for_native_cli(tmp_path):
    capture = tmp_path / 'password'
    environment = dict(os.environ, TASK4_PASSWORD_CAPTURE=str(capture))
    # Export shell functions because the pinned runner deliberately mounts /tmp noexec.
    environment['BASH_FUNC_python3%%'] = "() { " + shlex.quote(sys.executable) + " -c 'import secrets,sys; secrets.token_urlsafe=lambda _: \"-pathological-random-token\"; exec(sys.argv[1])' \"$2\"; }"
    environment['BASH_FUNC_docker%%'] = '() { printf "%s" "$POSTGRES_PASSWORD" > "$TASK4_PASSWORD_CAPTURE"; return 1; }'
    environment.pop('FACTORIO_TEST_DB_PASSWORD', None)
    result = subprocess.run(['/bin/bash', str(Path(__file__).resolve().parents[2] / 'scripts/check'), 'odoo', '--tags', '/factorio_connect'], env=environment, capture_output=True)
    assert result.returncode == 1  # Deliberately stop before contacting any Docker daemon.
    assert capture.read_text() == 'factorio--pathological-random-token'
