"""Minimal local HTTP interface for the dependency-free operations core."""
from __future__ import annotations
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from .service import OperationsService
from .ui import PAGE

MAX_REQUEST_BODY_BYTES = 64 * 1024

class Handler(BaseHTTPRequestHandler):
    service: OperationsService
    def reply(self, code, payload):
        data=json.dumps(payload).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def reply_text(self, code, payload, content_type="text/plain; charset=utf-8"):
        data=payload.encode(); self.send_response(code); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("request body is required")
        if length > MAX_REQUEST_BODY_BYTES:
            raise ValueError("request body exceeds local safety limit")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload
    def do_GET(self):
        if self.path == "/":
            data=PAGE.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if self.path == "/health":
            health = self.service.health_status()
            return self.reply(200 if health["status"] == "ok" else 503, health)
        if self.path == "/today": return self.reply(200, self.service.today())
        if self.path == "/autonomous-loop": return self.reply(200, self.service.autonomous_loop_status())
        if self.path == "/autonomous-loop/queue": return self.reply(200, self.service.autonomous_work_queue())
        if self.path == "/tools/status": return self.reply(200, self.service.tool_status())
        if urlsplit(self.path).path == "/workspace":
            try:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("query", [""])[0]
                return self.reply(200, self.service.workspace_status(query=query))
            except ValueError as exc:
                return self.reply(400, {"error": str(exc)})
        if self.path == "/controls/kill-switch": return self.reply(200, self.service.control_status())
        if self.path == "/backups": return self.reply(200, self.service.backups_status())
        if self.path == "/work-items": return self.reply(200, self.service.work_items())
        if self.path.startswith("/work-items/"):
            try: return self.reply(200, self.service.work_item(int(self.path.split("/")[2])))
            except (IndexError, ValueError) as exc: return self.reply(404, {"error":str(exc)})
        if self.path == "/journal.md": return self.reply_text(200, self.service.journal_markdown(), "text/markdown; charset=utf-8")
        if self.path == "/journal": return self.reply(200, self.service.journal())
        if self.path == "/diary": return self.reply(200, self.service.diary())
        return self.reply(404, {"error":"not found"})
    def do_POST(self):
        try:
            data=self.body()
            if self.path == "/work-items": return self.reply(201, self.service.create_work_item(data["title"], data["request"]))
            if self.path == "/plans": return self.reply(201, self.service.propose_plan(data["work_item_id"], data["actions"]))
            if self.path == "/plans/from-request": return self.reply(201, self.service.plan_for_request(data["work_item_id"]))
            if self.path.startswith("/plans/") and self.path.endswith("/approve"): return self.reply(200, self.service.approve_plan(int(self.path.split("/")[2])))
            if self.path.startswith("/plans/") and self.path.endswith("/reject"): return self.reply(200, self.service.reject_plan(int(self.path.split("/")[2])))
            if self.path.startswith("/plans/") and self.path.endswith("/execute"): return self.reply(200, self.service.execute_plan(int(self.path.split("/")[2])))
            if self.path == "/controls/kill-switch": return self.reply(200, self.service.set_kill_switch(bool(data["enabled"])))
            return self.reply(404, {"error":"not found"})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc: return self.reply(400, {"error":str(exc)})
    def log_message(self, *_): pass

def make_server(host: str, port: int, database: str):
    Handler.service=OperationsService(database)
    return ThreadingHTTPServer((host, port), Handler)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8000); p.add_argument("--database", default="dopos.db"); a=p.parse_args()
    make_server(a.host, a.port, a.database).serve_forever()
if __name__ == "__main__": main()
