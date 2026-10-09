"""Install the generated wheel outside the source path and exercise redaction."""
import shutil
import subprocess
import sys
from pathlib import Path


def test_bridge_wheel_includes_shared_standalone_redactor(tmp_path):
    project = tmp_path / 'bridge'
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / 'src', project / 'src')
    shutil.copy(source / 'pyproject.toml', project / 'pyproject.toml')
    shutil.copy(source / 'requirements.in', project / 'requirements.in')
    wheels = tmp_path / 'wheels'
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-build-isolation', '--no-deps', '--wheel-dir', str(wheels), str(project)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    installed = tmp_path / 'installed'
    wheel, = wheels.glob('*.whl')
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--target', str(installed), str(wheel)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    execution = subprocess.run([sys.executable, '-I', '-c', '''import sys,io,logging
sys.path.insert(0, sys.argv[1])
from factorio_connect_common.redaction import install_redaction
from factorio_bridge.logging import RedactionFilter
stream=io.StringIO(); handler=logging.StreamHandler(stream)
logger=logging.getLogger('packaged'); logger.addHandler(handler); logger.setLevel(logging.INFO)
install_redaction(['wheel-private'])
logger.info('wheel-private /odoo/events/path-private')
assert stream.getvalue() == '[REDACTED] /odoo/events/[REDACTED]\\n'
assert isinstance(handler.filters[0], RedactionFilter)
print('Installed bridge wheel contains standalone shared redactor')
''', str(installed)], capture_output=True, text=True)
    assert execution.returncode == 0, execution.stderr
