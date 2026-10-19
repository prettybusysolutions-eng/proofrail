"""Loopback-only SMATP reference HTTP transport. NOT a public production API."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from smatp import ProtocolError, Store

LIMIT = 80 * 1024


def handler_for(db_path: str):
    class Handler(BaseHTTPRequestHandler):
        def response(self, code, obj):
            raw = json.dumps(obj, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if self.path not in ("/v1/messages", "/v1/receipts"):
                self.response(404, {"error": "unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0 or length > LIMIT:
                    raise ProtocolError("Invalid request size")
                obj = json.loads(self.rfile.read(length))
                local = Store(db_path)
                try:
                    result = local.submit(obj) if self.path == "/v1/messages" else local.append_receipt(obj)
                finally:
                    local.close()
                self.response(200 if result.get("duplicate") else 201, result)
            except (ProtocolError, json.JSONDecodeError) as exc:
                self.response(400, {"error": str(exc)})
            except Exception:
                self.response(500, {"error": "internal server error"})

        def do_GET(self):
            if self.path == "/healthz":
                self.response(200, {"ok": True, "version": "smatp/0.1"})
            elif self.path.startswith("/v1/messages/"):
                # Read endpoint is deliberately loopback-only; require auth before remote use.
                try:
                    message_id = unquote(self.path.split("/v1/messages/", 1)[1])
                    local = Store(db_path)
                    try:
                        result = local.get_record(message_id)
                    finally:
                        local.close()
                    self.response(200, result)
                except ProtocolError as exc:
                    self.response(404, {"error": str(exc)})
            else:
                self.response(404, {"error": "unknown endpoint"})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="emergence.sqlite3")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    store = Store(args.db)
    store.close()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(args.db))
    print(f"SMATP reference listening on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
