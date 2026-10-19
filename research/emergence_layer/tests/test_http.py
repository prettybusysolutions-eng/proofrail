import json
import threading
import urllib.error
import urllib.request

from http.server import ThreadingHTTPServer

from server import handler_for
from smatp import Store, make_envelope, make_receipt, new_identity


def test_real_loopback_http_roundtrip(tmp_path):
    path = str(tmp_path / "api.sqlite")
    sender, sender_pub = new_identity()
    recipient, recipient_pub = new_identity()
    store = Store(path)
    store.register_agent("alice", sender_pub)
    store.register_agent("bob", recipient_pub)
    store.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(path))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(route, body):
        request = urllib.request.Request(base + route, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as reply:
            return json.load(reply)

    try:
        message = make_envelope("alice", "bob", "calculate", {"x": 2, "y": 4}, sender)
        received = post("/v1/messages", message)
        assert received["status"] == "RECEIVED"
        accepted = make_receipt(message["message_id"], "bob", "ACCEPTED", None, recipient)
        assert post("/v1/receipts", accepted)["status"] == "ACCEPTED"
        store = Store(path)
        prior_hash = store.last_receipt_hash(message["message_id"])
        store.close()
        completed = make_receipt(message["message_id"], "bob", "COMPLETED", prior_hash,
                                 recipient, result={"sum": 6})
        assert post("/v1/receipts", completed)["status"] == "COMPLETED"
        with urllib.request.urlopen(base + "/v1/messages/" + message["message_id"], timeout=5) as reply:
            record = json.load(reply)
        assert record["status"] == "COMPLETED"
        store = Store(path)
        assert store.verify_record(message["message_id"])
        store.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
