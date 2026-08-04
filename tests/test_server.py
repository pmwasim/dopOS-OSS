import json, sys, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
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
        self.assertIn("local operations", urlopen(self.url).read().decode())
        item=self.request("/work-items", {"title":"Test","request":"Check status"}); plan=self.request("/plans", {"work_item_id":item["id"],"actions":["status.summary"]})
        self.request(f"/plans/{plan['id']}/approve", {}); done=self.request(f"/plans/{plan['id']}/execute", {})
        self.assertEqual(done["state"], "completed"); self.assertGreaterEqual(len(self.request("/diary")), 4)
