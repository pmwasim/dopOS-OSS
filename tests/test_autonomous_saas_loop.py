import json, subprocess, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/autonomous_saas_loop.py"
class LoopTests(unittest.TestCase):
    def test_success_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps({"phases":{"inspect":[],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[]}))
            done = subprocess.run(["python3", str(SCRIPT), "--repo", str(root)], text=True, capture_output=True)
            self.assertEqual(done.returncode, 0); self.assertTrue(list((root / "workspace/generated/autonomous-loop").glob("*/report.json")))
    def test_failure_runs_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps({"phases":{"inspect":["false"],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":["true"]},"blocked_capabilities":[]}))
            self.assertNotEqual(subprocess.run(["python3", str(SCRIPT), "--repo", str(root)]).returncode, 0)
    def test_release_is_blocked_without_explicit_enablement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            config={"phases":{"inspect":[],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[],"release":{"enabled":False,"commands":[]}}
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--release"], text=True, capture_output=True)
            self.assertNotEqual(done.returncode, 0)
