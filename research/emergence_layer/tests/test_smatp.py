import copy
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from smatp import Store, ProtocolError, make_envelope, make_receipt, new_identity


@pytest.fixture()
def setup(tmp_path):
    db_path = tmp_path / "test.db"
    sender, sender_pub = new_identity()
    recipient, recipient_pub = new_identity()
    outsider, outsider_pub = new_identity()
    db = Store(db_path)
    db.register_agent("sender", sender_pub)
    db.register_agent("recipient", recipient_pub)
    db.register_agent("outsider", outsider_pub)
    yield db, sender, recipient, outsider, db_path
    db.close()


def new_message(s):
    return make_envelope("sender", "recipient", "calculate", {"x": 1}, s)


def test_accept_complete_restart_and_verify(setup):
    db, sender, worker, _, path = setup
    env = new_message(sender)
    assert db.submit(env)["status"] == "RECEIVED"
    assert db.submit(env)["duplicate"] is True
    ack = make_receipt(env["message_id"], "recipient", "ACCEPTED", None, worker)
    assert db.append_receipt(ack)["status"] == "ACCEPTED"
    result = make_receipt(env["message_id"], "recipient", "COMPLETED",
                          db.last_receipt_hash(env["message_id"]), worker, result={"value": 1})
    assert db.append_receipt(result)["status"] == "COMPLETED"
    assert db.verify_record(env["message_id"])
    opened = Store(path)
    assert opened.get_record(env["message_id"])["status"] == "COMPLETED"
    assert opened.verify_record(env["message_id"])
    opened.close()


def test_tampering_and_expiration_rejected(setup):
    db, sender, _, _, _ = setup
    env = new_message(sender)
    bad = copy.deepcopy(env)
    bad["payload"]["x"] = 999
    with pytest.raises(ProtocolError, match="Signature"):
        db.submit(bad)
    expired = make_envelope("sender", "recipient", "x", {}, sender, now=int(time.time())-500)
    with pytest.raises(ProtocolError, match="expired"):
        db.submit(expired)


def test_idempotency_collision_and_nonce_replay(setup):
    db, sender, _, _, _ = setup
    env = make_envelope("sender", "recipient", "x", {}, sender, idempotency_key="req-1")
    db.submit(env)
    other = make_envelope("sender", "recipient", "x", {}, sender, idempotency_key="req-1")
    with pytest.raises(ProtocolError, match="Replay"):
        db.submit(other)


def test_wrong_actor_and_illegal_transition(setup):
    db, sender, worker, outsider, _ = setup
    env = new_message(sender)
    db.submit(env)
    unauthorized = make_receipt(env["message_id"], "outsider", "ACCEPTED", None, outsider)
    with pytest.raises(ProtocolError, match="recipient"):
        db.append_receipt(unauthorized)
    bad_transition = make_receipt(env["message_id"], "recipient", "COMPLETED", None, worker,
                                  result={"ok": True})
    with pytest.raises(ProtocolError, match="Illegal"):
        db.append_receipt(bad_transition)


def test_broken_receipt_chain_rejected(setup):
    db, sender, worker, _, _ = setup
    env = new_message(sender)
    db.submit(env)
    ack = make_receipt(env["message_id"], "recipient", "ACCEPTED", None, worker)
    db.append_receipt(ack)
    bad = make_receipt(env["message_id"], "recipient", "FAILED", "0"*64, worker,
                       result={"error": "rejected"})
    with pytest.raises(ProtocolError, match="chain"):
        db.append_receipt(bad)


def test_post_commit_corruption_detected(setup):
    db, sender, _, _, _ = setup
    env = new_message(sender)
    db.submit(env)
    tampered = dict(env)
    tampered["payload"] = {"x": "substituted"}
    db.db.execute("UPDATE messages SET envelope=? WHERE message_id=?",
                  (json.dumps(tampered), env["message_id"]))
    with pytest.raises(ProtocolError, match="digest mismatch"):
        db.verify_record(env["message_id"])


def test_parallel_exact_duplicate(setup):
    db, sender, _, _, path = setup
    env = new_message(sender)
    def submit(_):
        local = Store(path)
        try:
            return local.submit(env)
        finally:
            local.close()
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert sum(not x["duplicate"] for x in responses) == 1
    assert {x["message_id"] for x in responses} == {env["message_id"]}


def test_reject_then_no_complete(setup):
    db, sender, worker, _, _ = setup
    env = new_message(sender)
    db.submit(env)
    rejected = make_receipt(env["message_id"], "recipient", "REJECTED", None, worker,
                            result={"reason": "unsupported"})
    db.append_receipt(rejected)
    completed = make_receipt(env["message_id"], "recipient", "COMPLETED",
                             db.last_receipt_hash(env["message_id"]), worker,
                             result={"ok": True})
    with pytest.raises(ProtocolError, match="Illegal"):
        db.append_receipt(completed)
    assert db.verify_record(env["message_id"])


def test_stored_receipt_digest_corruption_detected(setup):
    db, sender, worker, _, _ = setup
    env = new_message(sender)
    db.submit(env)
    ack = make_receipt(env["message_id"], "recipient", "ACCEPTED", None, worker)
    db.append_receipt(ack)
    db.db.execute("UPDATE receipts SET body_hash=? WHERE message_id=?", ("0"*64, env["message_id"]))
    with pytest.raises(ProtocolError, match="digest"):
        db.verify_record(env["message_id"])


def test_parallel_distinct_messages(setup):
    db, sender, _, _, path = setup
    envelopes = [new_message(sender) for _ in range(12)]
    def submit(env):
        local = Store(path)
        try:
            return local.submit(env)
        finally:
            local.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(submit, envelopes))
    assert len(set(r["message_id"] for r in responses)) == len(envelopes)
    assert all(not r["duplicate"] for r in responses)
