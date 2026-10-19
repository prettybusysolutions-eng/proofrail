from counterfactual_lab import experiment


def test_crash_after_effect_requires_destination_idempotency():
    baseline = experiment('durable', 'after_effect')
    protected = experiment('verified', 'after_effect')
    assert baseline['worker_exit_codes'] == [73, 0]
    assert baseline['effect_count'] == 2
    assert protected['worker_exit_codes'] == [73, 0]
    assert protected['effect_count'] == 1
    assert protected['protocol_status'] == 'COMPLETED'


def test_valid_signature_does_not_prove_effect():
    baseline = experiment('idempotent', 'false_ack')
    protected = experiment('verified', 'false_ack')
    assert baseline['receipt_chain_valid']
    assert baseline['false_completion']
    assert protected['effect_count'] == 0
    assert protected['status'] == 'UNCONFIRMED'
    assert protected['protocol_status'] == 'ACCEPTED'
    assert not protected['false_completion']


def test_restart_after_checkpoint_does_not_repeat_effect():
    result = experiment('verified', 'after_checkpoint')
    assert result['worker_exit_codes'] == [73, 0]
    assert result['effect_count'] == 1
    assert result['receipt_chain_valid']


def test_restart_before_effect_eventually_completes():
    result = experiment('verified', 'before_effect')
    assert result['worker_exit_codes'] == [73, 0]
    assert result['correct_effect']
    assert result['protocol_status'] == 'COMPLETED'


def test_wrong_result_is_not_mistaken_for_success():
    baseline = experiment('idempotent', 'wrong_effect')
    protected = experiment('verified', 'wrong_effect')
    assert baseline['receipt_chain_valid'] and baseline['false_completion']
    assert protected['effect_count'] == 1
    assert not protected['correct_effect']
    assert protected['status'] == 'UNCONFIRMED'
    assert protected['protocol_status'] == 'ACCEPTED'
