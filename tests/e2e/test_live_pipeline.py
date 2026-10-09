"""Real source transactions through HTTP and the production Lua UDP receiver."""


def test_committed_change_reaches_applied_snapshot(smoke_report):
    assert smoke_report['applied_revision'] == smoke_report['published_revision']
    assert smoke_report['commit_delivery_seconds'] <= 5
    assert smoke_report['seed']['posted_pumps'] == 14
    assert smoke_report['seed']['missing_motors'] == 6
    commit = smoke_report['commit']
    assert commit['distinct_transaction_before'] == 'Assembly'
    assert commit['distinct_transaction_after'] == commit['applied_name'] == 'Assembly committed live'
    assert commit['http_202_receipts'] > 0
    assert commit['verified']


def test_rolled_back_change_never_notifies_or_appears(smoke_report):
    assert smoke_report['background_cron_threads'] == 0
    assert smoke_report['automation_rules_active'] == 14
    rollback = smoke_report['rollback']
    assert rollback['distinct_transaction_name'] == 'Assembly committed live'
    assert rollback['applied_name'] == 'Assembly committed live'
    assert rollback['http_202_receipts'] == 0
    assert not rollback['rolled_back_name_seen']


def test_missed_webhook_recovers_within_65_seconds(smoke_report):
    missed = smoke_report['missed_webhook']
    assert missed['http_202_receipts'] == 0
    assert missed['rules_active_during_change'] == 0
    assert missed['applied_name'] == 'Assembly reconciliation live'
    assert missed['delivery_seconds'] <= 65
    assert missed['rules_active'] == 14


def test_real_stock_adjustment_clears_six_motor_warning(smoke_report):
    stock = smoke_report['stock_adjustment']
    assert stock['before_unreserved'] == 6
    assert stock['after_unreserved'] == 0
    assert stock['on_hand'] == stock['reserved'] == 34
    assert stock['posted_pumps'] == 14
    assert stock['delivery_seconds'] <= 5
    assert stock['applied_revision'] == stock['published_revision']
