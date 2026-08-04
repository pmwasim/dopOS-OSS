import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from dopos_core import OperationsService

class OperationsServiceTests(unittest.TestCase):
    def test_approval_gated_safe_execution_and_diary(self):
        service=OperationsService(); item=service.create_work_item("Check host", "Show safe operational status")
        plan=service.propose_plan(item["id"], ["status.summary"])
        with self.assertRaisesRegex(ValueError, "requires approval"): service.execute_plan(plan["id"])
        service.approve_plan(plan["id"]); done=service.execute_plan(plan["id"])
        self.assertEqual(done["state"], "completed"); self.assertGreaterEqual(len(service.diary()), 4); service.close()
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
        approved=service.propose_plan(item["id"], ["status.summary"]); service.approve_plan(approved["id"]); service.set_kill_switch(True)
        with self.assertRaisesRegex(ValueError, "kill switch"): service.execute_plan(approved["id"])
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

import sqlite3
