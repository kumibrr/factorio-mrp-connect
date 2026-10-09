"""Real bridge restart and namespace-preserving native Odoo pause."""


def test_restarts_and_source_outage_preserve_last_truth(smoke_report):
    outage = smoke_report['outages']
    assert outage['method'] == 'docker pause/unpause labelled isolated Odoo container'
    assert outage['source_ok_during_outage'] is False
    assert outage['cached_source_read_at'] == outage['before_source_read_at']
    assert outage['cached_revision'] == outage['before_revision']
    assert outage['receiver_retained_revision'] == outage['before_revision']
    assert outage['verified_during_outage'] is False
    assert outage['verified_after_recovery'] is True
    assert outage['recovered_revision'] > outage['before_revision']
    assert outage['recovered_source_read_at'] > outage['before_source_read_at']
    assert outage['bridge_disconnected_observed'] is True
    assert outage['protocol_logs_tokenless'] is True
    assert outage['revision_timestamps_logged'] is True
