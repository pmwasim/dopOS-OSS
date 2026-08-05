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
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps({"phases":{"inspect":[["false"]],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[["true"]]},"blocked_capabilities":[]}))
            self.assertNotEqual(subprocess.run(["python3", str(SCRIPT), "--repo", str(root)]).returncode, 0)
            repair=next((root / "workspace/generated/autonomous-loop").glob("*/repair-work-item.md"))
            self.assertIn("Repair the failed inspect phase", repair.read_text())
    def test_release_is_blocked_without_explicit_enablement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            config={"phases":{"inspect":[],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[],"release":{"enabled":False,"commands":[]}}
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--release"], text=True, capture_output=True)
            self.assertNotEqual(done.returncode, 0)

    def test_selects_markdown_work_item_and_records_schema_v2_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/inbox").mkdir(parents=True); (root / "workspace/generated").mkdir(parents=True)
            (root / "workspace/inbox/001-health-check.md").write_text("# Health check\n\nConfirm the service is healthy.\n")
            config={"phases":{"inspect":[],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[]}
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root)], text=True, capture_output=True)
            self.assertEqual(done.returncode, 0)
            report_path=next((root / "workspace/generated/autonomous-loop").glob("*/report.json"))
            report=json.loads(report_path.read_text())
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["work_item"]["path"], "workspace/inbox/001-health-check.md")

    def test_dry_run_does_not_execute_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            config={"phases":{"inspect":[["false"]],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[]}
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--dry-run"], text=True, capture_output=True)
            self.assertEqual(done.returncode, 0)

    def test_rejects_shell_string_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            config={"phases":{"inspect":["echo unsafe"],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[]}
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root)], text=True, capture_output=True)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("shell strings are not supported", done.stderr)

    def test_rejects_shell_string_release_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
            config={"phases":{"inspect":[],"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[],"release":{"enabled":False,"commands":["echo unsafe"]}}
            (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root)], text=True, capture_output=True)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("shell strings are not supported", done.stderr)

    @staticmethod
    def _queued_repo(root: Path, failing: bool = False):
        (root / ".companyos").mkdir(); (root / "workspace/generated").mkdir(parents=True)
        (root / "workspace/inbox").mkdir(parents=True)
        inspect = [["python3", "-c", "raise SystemExit(1)"]] if failing else []
        config={"phases":{"inspect":inspect,"plan":[],"implement":[],"build":[],"test":[],"verify":[],"package":[],"recover":[]},"blocked_capabilities":[]}
        (root / ".companyos/autonomous-loop.json").write_text(json.dumps(config))
        (root / "workspace/inbox/001-first.md").write_text("# First queued item\n\nDo the first thing.\n", encoding="utf-8")
        (root / "workspace/inbox/002-second.md").write_text("# Second queued item\n\nDo the second thing.\n", encoding="utf-8")

    @staticmethod
    def _latest_report(root: Path):
        runs = sorted((root / "workspace/generated/autonomous-loop").iterdir())
        return json.loads((runs[-1] / "report.json").read_text(encoding="utf-8")), runs[-1]

    def test_selected_work_item_is_retained_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._queued_repo(root)
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root)], text=True, capture_output=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            report, _ = self._latest_report(root)
            self.assertEqual(report["work_item_disposition"], "retained")
            self.assertTrue((root / "workspace/inbox/001-first.md").is_file())

    def test_completing_a_passed_cycle_archives_the_item_and_advances_the_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._queued_repo(root)
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--complete-work-item"], text=True, capture_output=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            report, evidence = self._latest_report(root)
            self.assertEqual(report["work_item_disposition"], "completed")
            self.assertEqual(report["work_item"]["path"], "workspace/inbox/001-first.md")
            # Evidence is written before the inbox copy is removed.
            self.assertIn("Do the first thing.", (evidence / "work-item.md").read_text(encoding="utf-8"))
            self.assertFalse((root / "workspace/inbox/001-first.md").exists())
            # The queue advances: the next cycle picks the following item.
            subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--complete-work-item"], text=True, capture_output=True)
            second, _ = self._latest_report(root)
            self.assertEqual(second["work_item"]["title"], "Second queued item")

    def test_failed_cycle_never_clears_the_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._queued_repo(root, failing=True)
            done=subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--complete-work-item"], text=True, capture_output=True)
            self.assertNotEqual(done.returncode, 0)
            report, _ = self._latest_report(root)
            self.assertEqual(report["result"], "failed")
            self.assertEqual(report["work_item_disposition"], "retained")
            self.assertTrue((root / "workspace/inbox/001-first.md").is_file())

    def test_dry_run_never_clears_the_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._queued_repo(root)
            subprocess.run(["python3", str(SCRIPT), "--repo", str(root), "--complete-work-item", "--dry-run"], text=True, capture_output=True)
            report, _ = self._latest_report(root)
            self.assertEqual(report["work_item_disposition"], "retained")
            self.assertTrue((root / "workspace/inbox/001-first.md").is_file())
