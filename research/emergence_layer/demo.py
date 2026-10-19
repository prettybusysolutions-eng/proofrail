"""Working signed handoff + durable restart demo; no fake LLM/compute calls."""
import json
import tempfile
from pathlib import Path

from smatp import Store, make_envelope, make_receipt, new_identity


def main():
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "smatp.sqlite3"
        sender_private, sender_pub = new_identity()
        worker_private, worker_pub = new_identity()
        store = Store(db)
        store.register_agent("planner", sender_pub)
        store.register_agent("worker", worker_pub)

        msg = make_envelope("planner", "worker", "calculate", {"a": 7, "b": 8}, sender_private)
        print("SUBMIT", json.dumps(store.submit(msg)))
        accepted = make_receipt(msg["message_id"], "worker", "ACCEPTED", None, worker_private)
        print("ACK", json.dumps(store.append_receipt(accepted)))
        completed = make_receipt(msg["message_id"], "worker", "COMPLETED",
                                 store.last_receipt_hash(msg["message_id"]), worker_private,
                                 result={"sum": 15})
        print("COMPLETE", json.dumps(store.append_receipt(completed)))
        store.close()

        store = Store(db)
        print("RESTART_VERIFY", store.verify_record(msg["message_id"]))
        print("FINAL_STATE", store.get_record(msg["message_id"])["status"])
        store.close()


if __name__ == "__main__":
    main()
