import sys
import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from dopos_core import OperationsService

class OperationsServiceTests(unittest.TestCase):
    def test_approval_gated_safe_execution_and_diary(self):
        service=OperationsService(); item=service.create_work_item("Check host", "Show safe operational status")
        plan=service.propose_plan(item["id"], ["status.summary", "diary.preview"])
        with self.assertRaisesRegex(ValueError, "requires approval"): service.execute_plan(plan["id"])
        service.approve_plan(plan["id"]); done=service.execute_plan(plan["id"])
        self.assertEqual(done["state"], "completed"); self.assertEqual(service.work_item(item["id"])["state"], "completed")
        self.assertEqual(service.work_item(item["id"])["plan"]["results"], done["results"])
        preview = next(row["result"] for row in done["results"] if row["action"] == "diary.preview")
        self.assertTrue(preview); self.assertEqual(set(preview[0]), {"id", "kind", "created_at"})
        self.assertGreaterEqual(len(service.diary()), 4); service.close()

    def test_recent_work_is_durable_and_includes_latest_plan(self):
        service=OperationsService(); item=service.create_work_item("History", "Show Docker status")
        plan=service.plan_for_request(item["id"])
        recent=service.work_items(); self.assertEqual(recent[0]["id"], item["id"])
        self.assertEqual(recent[0]["plan"]["id"], plan["id"])
        self.assertEqual(service.work_item(item["id"])["plan"]["state"], "awaiting_approval")
        self.assertEqual(service.work_item(item["id"])["state"], "awaiting_approval"); service.close()

    def test_recent_work_sanitizes_legacy_terminal_control_codes(self):
        service=OperationsService(); item=service.create_work_item("Legacy", "Show Docker status")
        service.propose_plan(item["id"], ["status.summary"], "Thinking...\x1b[1D\x1b[K ...done thinking. Safe explanation")
        self.assertEqual(service.work_item(item["id"])["plan"]["explanation"], "Safe explanation"); service.close()

    def test_historical_result_projection_does_not_return_nested_diary_payloads(self):
        service=OperationsService(); item=service.create_work_item("Historic", "Show safe status")
        plan=service.propose_plan(item["id"], ["status.summary"]); service.approve_plan(plan["id"])
        service.audit("plan.executed", {"id":plan["id"], "results":[{"action":"diary.preview", "result":[{"id":1,"kind":"plan.executed","created_at":"now","payload":{"deep":"data"}}]}]})
        result=service.work_item(item["id"])["plan"]["results"][0]["result"][0]
        self.assertEqual(result, {"id":1,"kind":"plan.executed","created_at":"now"}); service.close()
    def test_rejects_unallowlisted_actions(self):
        service=OperationsService(); item=service.create_work_item("Unsafe", "do not run arbitrary command")
        with self.assertRaisesRegex(ValueError, "unsupported"): service.propose_plan(item["id"], ["shell.rm_rf"])
        service.close()
    def test_audit_is_append_only(self):
        service=OperationsService(); service.create_work_item("Audit", "verify append only")
        with self.assertRaises(sqlite3.DatabaseError): service.db.execute("DELETE FROM audit_events")
        service.close()

    def test_backup_restores_auditable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            service=OperationsService(); service.create_work_item("Backup", "prove recovery path")
            backup=service.backup_to(Path(directory) / "dopos-backup.db")
            restored=OperationsService(backup["path"])
            self.assertTrue(backup["audit_chain_valid"])
            self.assertTrue(restored.verify_audit_chain())
            self.assertEqual(restored.status_summary()["work_items"], 1)
            restored.close(); service.close()

    def test_reject_and_kill_switch_block_execution(self):
        service=OperationsService(); item=service.create_work_item("Controls", "check stop controls")
        rejected=service.propose_plan(item["id"], ["status.summary"]); self.assertEqual(service.reject_plan(rejected["id"])["state"], "rejected")
        self.assertEqual(service.work_item(item["id"])["state"], "rejected")
        approved=service.propose_plan(item["id"], ["status.summary"]); service.approve_plan(approved["id"]); service.set_kill_switch(True)
        with self.assertRaisesRegex(ValueError, "kill switch"): service.execute_plan(approved["id"])
        self.assertEqual(service.control_status()["kill_switch"], "on")
        service.close()

    def test_docker_adapter_is_allowlisted_and_structured(self):
        service=OperationsService(); item=service.create_work_item("Docker", "read docker status")
        plan=service.propose_plan(item["id"], ["docker.status"]); service.approve_plan(plan["id"])
        result=service.execute_plan(plan["id"])["results"][0]["result"]
        self.assertIn("available", result); service.close()

    def test_github_adapter_is_allowlisted_and_structured(self):
        service=OperationsService(); item=service.create_work_item("GitHub", "read repository metadata")
        plan=service.propose_plan(item["id"], ["github.status"]); service.approve_plan(plan["id"])
        result=service.execute_plan(plan["id"])["results"][0]["result"]
        self.assertIn("available", result); service.close()

    def test_request_router_stays_within_allowlist(self):
        service=OperationsService(); item=service.create_work_item("Route", "Show Docker and GitHub repository status")
        plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"], ["status.summary", "docker.status", "github.status", "diary.preview"])
        service.close()

    def test_quality_adapter_uses_only_fixed_local_ci_commands(self):
        service=OperationsService()
        with patch("dopos_core.service.subprocess.run") as run:
            run.return_value=type("Result", (), {"returncode":0,"stdout":"passed","stderr":""})()
            result=service.quality_status()
        self.assertTrue(result["ok"]); self.assertEqual([check["name"] for check in result["checks"]], ["compile", "tests", "governance"])
        self.assertEqual(run.call_count, 3); self.assertTrue(all(isinstance(call.args[0], list) for call in run.call_args_list)); service.close()

    def test_request_router_adds_quality_check_without_expanding_allowlist(self):
        service=OperationsService(); item=service.create_work_item("Quality", "Run CI tests and validate build")
        with patch.object(service, "local_plan_explanation", return_value="Safe quality plan"):
            plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"], ["status.summary", "quality.status", "diary.preview"]); service.close()

    def test_ollama_adapter_is_allowlisted_and_routed(self):
        service=OperationsService(); item=service.create_work_item("Models", "Show local Ollama model status")
        plan=service.plan_for_request(item["id"]); self.assertIn("ollama.status", plan["actions"])
        service.approve_plan(plan["id"]); result=service.execute_plan(plan["id"])["results"]
        self.assertTrue(any(entry["action"] == "ollama.status" and "available" in entry["result"] for entry in result)); service.close()

    def test_local_explanation_cannot_change_frozen_actions(self):
        service=OperationsService(); item=service.create_work_item("Explain", "Show Docker status")
        with patch("dopos_core.service.shutil.which", return_value="ollama"), patch("dopos_core.service.subprocess.run") as run:
            run.return_value=type("Result", (), {"returncode":0,"stdout":"\u001b[1DThe approved read-only Docker check is ready.","stderr":""})()
            plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"], ["status.summary", "docker.status", "diary.preview"])
        self.assertIn("Docker", plan["explanation"]); self.assertNotIn("\u001b", plan["explanation"])
        self.assertIn("--hidethinking", run.call_args.args[0]); service.close()

import sqlite3
