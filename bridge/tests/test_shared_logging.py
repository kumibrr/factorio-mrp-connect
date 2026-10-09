"""Both deployment hooks must import the same independent stdlib package."""
import importlib.util
import io
import logging
from pathlib import Path


def test_deployment_hooks_share_redactor_and_merge_credentials():
    from factorio_connect_common.redaction import RedactionFilter
    from factorio_bridge.logging import install_redaction
    addon_path = Path(__file__).resolve().parents[2] / 'odoo-addons/factorio_connect/logging.py'
    spec = importlib.util.spec_from_file_location('standalone_addon_logging', addon_path)
    addon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(addon)
    stream = io.StringIO()
    logger = logging.getLogger('shared-deployment-hook-test')
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        install_redaction(['bridge-private'])
        addon.install_redaction(['odoo-private'])
        logger.info('bridge-private odoo-private /odoo/events/url-private')
        assert stream.getvalue() == '[REDACTED] [REDACTED] /odoo/events/[REDACTED]\n'
        assert isinstance(handler.filters[0], RedactionFilter)
        assert len(handler.filters) == 1
    finally:
        logger.removeHandler(handler)
