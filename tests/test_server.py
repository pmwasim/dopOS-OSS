import json, sys, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from dopos_core.server import make_server

class ServerTests(unittest.TestCase):
    def setUp(self):
        try:
            self.server=make_server("127.0.0.1", 0, ":memory:")
        except PermissionError:
            self.skipTest("loopback socket binding is unavailable in this execution sandbox")
        self.url=f"http://127.0.0.1:{self.server.server_port}"; self.thread=threading.Thread(target=self.server.serve_forever); self.thread.start()
    def tearDown(self): self.server.shutdown(); self.thread.join(); self.server.server_close(); self.server.RequestHandlerClass.service.close()
    def request(self, path, payload=None):
        req=Request(self.url+path, data=json.dumps(payload).encode() if payload is not None else None, headers={"Content-Type":"application/json"}, method="POST" if payload is not None else "GET")
        return json.loads(urlopen(req).read())
    def test_local_ui_and_approval_flow(self):
        health = self.request("/health")
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["audit_chain_valid"])
        self.assertIn("records", health)
        today = self.request("/today")
        self.assertEqual(today["needs_decision"], [])
        self.assertTrue(today["recovery"]["audit_chain_valid"])
        with self.assertRaises(HTTPError) as too_long:
            self.request("/work-items", {"title":"x" * 161, "request":"safe request"})
        self.assertEqual(too_long.exception.code, 400)
        too_long.exception.close()
        page = urlopen(self.url).read().decode()
        self.assertIn("Execute approved plan", page)
        self.assertIn("Ask dopOS anything", page)
        self.assertIn("Live Work", page)
        self.assertIn("Diary", page)
        tools = self.request("/tools/status")
        self.assertEqual(set(tools), {"docker", "github", "ollama"})
        self.assertEqual(self.request("/controls/kill-switch")["kill_switch"], "off")
        self.assertEqual(self.request("/backups"), [])
        item=self.request("/work-items", {"title":"Test","request":"Check Docker status"}); plan=self.request("/plans/from-request", {"work_item_id":item["id"]})
        self.assertEqual(self.request("/work-items")[0]["id"], item["id"])
        self.assertEqual(self.request(f"/work-items/{item['id']}")["plan"]["id"], plan["id"])
        self.request(f"/plans/{plan['id']}/approve", {}); done=self.request(f"/plans/{plan['id']}/execute", {})
        detail = self.request(f"/work-items/{item['id']}")
        self.assertEqual(done["state"], "completed"); self.assertEqual(detail["state"], "completed")
        self.assertEqual(detail["plan"]["results"], done["results"]); self.assertGreaterEqual(len(self.request("/diary")), 4)
        journal = self.request("/journal")
        self.assertTrue(any("Started: Test" == entry["summary"] for entry in journal))
        markdown = urlopen(self.url + "/journal.md").read().decode()
        self.assertIn("# dopOS Journal", markdown)
