import io
import logging

from factorio_bridge.logging import install_redaction


def test_handler_redacts_url_bearer_and_exception_traceback():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger('factorio-test-redaction')
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    install_redaction(['raw-api-key', 'raw-token'])
    try:
        logger.info('Webhook call to %s - succeeded', 'http://host/odoo/events/raw-token')
        try:
            raise RuntimeError('http://host/odoo/events/unknown-token Bearer other-api-key raw-api-key')
        except RuntimeError:
            logger.exception('native failure')
        output = stream.getvalue()
        for secret in ['raw-api-key', 'raw-token', 'unknown-token', 'other-api-key']:
            assert secret not in output
        assert 'RuntimeError' in output
        assert 'succeeded' in output
    finally:
        logger.removeHandler(handler)


def test_redaction_preserves_uvicorn_structured_access_arguments(capsys):
    from uvicorn.logging import AccessFormatter
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False))
    logger = logging.getLogger('factorio-test-uvicorn-access')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    install_redaction(['access-token'])
    try:
        logger.info('%s - "%s %s HTTP/%s" %d', '127.0.0.1:1234', 'POST', '/odoo/events/access-token', '1.1', 202)
        assert capsys.readouterr().err == ''
        assert 'access-token' not in stream.getvalue()
        assert 'POST /odoo/events/[REDACTED] HTTP/1.1' in stream.getvalue()
        assert '202 Accepted' in stream.getvalue()
    finally:
        logger.removeHandler(handler)
