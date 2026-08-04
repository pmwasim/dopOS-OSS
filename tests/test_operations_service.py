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

    def test_journal_projects_ledger_into_readable_entries_and_markdown(self):
        service=OperationsService(); item=service.create_work_item("Journal check", "Show the readable journal")
        plan=service.propose_plan(item["id"], ["status.summary"]); service.approve_plan(plan["id"]); service.execute_plan(plan["id"])
        entries=service.journal()
        self.assertTrue(any(entry["summary"] == "Started: Journal check" for entry in entries))
        self.assertTrue(all(set(entry) == {"id", "kind", "created_at", "summary", "detail"} for entry in entries))
        export=service.journal_markdown()
        self.assertIn("# dopOS Journal", export); self.assertIn("Started: Journal check", export); self.assertNotIn("payload", export)
        service.close()

    def test_recent_work_is_durable_and_includes_latest_plan(self):
        service=OperationsService(); item=service.create_work_item("History", "Show Docker status")
        plan=service.plan_for_request(item["id"])
        recent=service.work_items(); self.assertEqual(recent[0]["id"], item["id"])
        self.assertEqual(recent[0]["plan"]["id"], plan["id"])
        self.assertEqual(service.work_item(item["id"])["plan"]["state"], "awaiting_approval")
        self.assertEqual(service.work_item(item["id"])["state"], "awaiting_approval"); service.close()

    def test_today_projects_pending_decisions_and_recovery_state(self):
        with tempfile.TemporaryDirectory() as directory:
            service=OperationsService(); service.backup_directory=Path(directory)
            item=service.create_work_item("Today", "Show Docker status")
            plan=service.plan_for_request(item["id"])
            service.create_backup()
            today=service.today()
            self.assertEqual(today["needs_decision"][0]["work_item_id"], item["id"])
            self.assertEqual(today["needs_decision"][0]["plan_id"], plan["id"])
            self.assertTrue(today["recovery"]["audit_chain_valid"])
            self.assertEqual(today["recovery"]["backup_count"], 1)
            self.assertFalse(today["recovery"]["retention"]["configured"])
            self.assertIsNone(today["recovery"]["retention"]["policy"])
            self.assertFalse(today["recovery"]["retention"]["prune_enabled"])
            self.assertIn("queue", today)
            self.assertIn("automation", today)
            service.close()

    def test_today_projects_approved_plans_as_ready_to_run(self):
        service=OperationsService(); item=service.create_work_item("Resume", "Show safe status")
        plan=service.propose_plan(item["id"], ["status.summary"])
        service.approve_plan(plan["id"])
        today=service.today()
        self.assertEqual(today["needs_decision"], [])
        self.assertEqual(today["in_motion"][0]["work_item_id"], item["id"])
        self.assertEqual(today["in_motion"][0]["plan_id"], plan["id"])
        service.close()

    def test_today_includes_metadata_only_queue_and_automation_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            evidence = Path(directory) / "loop"
            inbox.mkdir(); evidence.mkdir()
            (inbox / "010-next.md").write_text("# Queue next item\n\nSecret body must stay out of Today.")
            run = evidence / "20260804T120000Z"; run.mkdir()
            (run / "report.json").write_text('{"title":"Cycle A","result":"passed","started_at":"2026-08-04T12:00:00+00:00","completed_at":"2026-08-04T12:01:00+00:00","phases":[{"name":"test","result":"passed"}],"commands":["secret output"]}')
            service=OperationsService(); service.inbox_directory=inbox; service.loop_directory=evidence
            today=service.today()
            self.assertEqual(today["queue"]["count"], 1)
            self.assertEqual(today["queue"]["next_title"], "Queue next item")
            self.assertEqual(today["automation"]["latest_result"], "passed")
            self.assertEqual(today["automation"]["latest_title"], "Cycle A")
            self.assertNotIn("Secret body", str(today))
            self.assertNotIn("secret output", str(today))
            service.close()

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











    def test_request_router_always_appends_diary_preview(self):
        service=OperationsService()
        item=service.create_work_item("Diary", "Show safe operational status")
        plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"][-1], "diary.preview")
        self.assertIn("status.summary", plan["actions"])
        service.close()

    def test_request_router_adds_github_for_repository_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Repository", "Show repository metadata status")
        plan=service.plan_for_request(item["id"])
        self.assertIn("github.status", plan["actions"])
        service.close()

    def test_request_router_adds_ollama_for_ai_runtime_phrase(self):
        service=OperationsService()
        item=service.create_work_item("AI runtime", "Show local AI runtime and model status")
        plan=service.plan_for_request(item["id"])
        self.assertIn("ollama.status", plan["actions"])
        service.close()

    def test_request_router_adds_docker_for_container_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Containers", "Show container status on this host")
        plan=service.plan_for_request(item["id"])
        self.assertIn("docker.status", plan["actions"])
        service.close()

    def test_request_router_adds_quality_for_validate_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Validate", "Please validate the local quality gates")
        plan=service.plan_for_request(item["id"])
        self.assertIn("quality.status", plan["actions"])
        service.close()

    def test_request_router_adds_ci_status_for_pipeline_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Pipeline", "Check the pipeline and GitHub Actions status")
        plan=service.plan_for_request(item["id"])
        self.assertIn("ci.status", plan["actions"])
        service.close()

    def test_request_router_adds_workspace_snapshot(self):
        service=OperationsService()
        item=service.create_work_item("Snapshot route", "Capture workspace snapshot catalog revision")
        plan=service.plan_for_request(item["id"])
        self.assertIn("workspace.snapshot", plan["actions"])
        self.assertIn("workspace.status", plan["actions"])
        service.close()

    def test_request_router_adds_loop_status(self):
        service=OperationsService()
        item=service.create_work_item("Loop route", "Show engineering loop evidence and autonomous loop status")
        plan=service.plan_for_request(item["id"])
        self.assertIn("loop.status", plan["actions"])
        service.close()

    def test_request_router_adds_queue_status(self):
        service=OperationsService()
        item=service.create_work_item("Queue route", "Show autonomous queue status and queued work")
        plan=service.plan_for_request(item["id"])
        self.assertIn("queue.status", plan["actions"])
        service.close()

    def test_request_router_adds_backup_retention_without_create(self):
        service=OperationsService()
        for title, request in (
            ("Retention route", "Show retention policy status"),
            ("Backup retention", "Check backup retention status"),
        ):
            item=service.create_work_item(title, request)
            plan=service.plan_for_request(item["id"])
            self.assertIn("backup.retention", plan["actions"])
            self.assertNotIn("backup.create", plan["actions"])
        service.close()

    def test_safe_actions_include_loop_queue_and_retention_adapters(self):
        from dopos_core.service import SAFE_ACTIONS
        for action in ("loop.status", "queue.status", "backup.retention", "ci.status", "workspace.snapshot"):
            self.assertIn(action, SAFE_ACTIONS)

    def test_rejects_unallowlisted_actions(self):
        service=OperationsService(); item=service.create_work_item("Unsafe", "do not run arbitrary command")
        with self.assertRaisesRegex(ValueError, "unsupported"): service.propose_plan(item["id"], ["shell.rm_rf"])
        service.close()
    def test_audit_is_append_only(self):
        service=OperationsService(); service.create_work_item("Audit", "verify append only")
        with self.assertRaises(sqlite3.DatabaseError): service.db.execute("DELETE FROM audit_events")
        service.close()

    def test_health_status_reports_ledger_and_execution_safety(self):
        service=OperationsService(); service.create_work_item("Health", "verify runtime health")
        health=service.health_status()
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["audit_chain_valid"])
        self.assertFalse(health["execution_paused"])
        self.assertEqual(health["records"]["work_items"], 1)
        self.assertTrue(health["workspace"]["configured"])
        self.assertEqual(health["workspace"]["document_count"], 0)
        self.assertFalse(health["backup_retention"]["configured"])
        self.assertFalse(health["backup_retention"]["prune_enabled"])
        service.close()

    def test_work_item_input_is_bounded_and_text_only(self):
        service=OperationsService()
        with self.assertRaisesRegex(ValueError, "at most 160"): service.create_work_item("x" * 161, "safe request")
        with self.assertRaisesRegex(ValueError, "at most 8000"): service.create_work_item("Safe", "x" * 8001)
        with self.assertRaisesRegex(ValueError, "must be text"): service.create_work_item(None, "safe request")
        self.assertEqual(service.status_summary()["work_items"], 0)
        service.close()

    def test_workspace_inventory_is_read_only_and_router_uses_allowlisted_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root / "Projects").mkdir(); (root / "Projects" / "proposal.md").write_text("private draft")
            (root / "readme.txt").write_text("notes"); (root / "ignore.exe").write_text("not a document")
            service=OperationsService(); service.workspace_directory=root
            status=service.workspace_status()
            self.assertTrue(status["configured"]); self.assertEqual(status["count"], 2)
            self.assertEqual(status["folder_count"], 1)
            self.assertEqual([entry["path"] for entry in status["folders"]], ["Projects"])
            self.assertEqual([entry["path"] for entry in status["documents"]], ["Projects/proposal.md", "readme.txt"])
            found=service.workspace_status("projects/proposal")
            self.assertEqual(found["query"], "projects/proposal")
            self.assertEqual([entry["path"] for entry in found["documents"]], ["Projects/proposal.md"])
            self.assertEqual(found["folders"], [])
            by_folder=service.workspace_status("Projects")
            self.assertEqual([entry["path"] for entry in by_folder["folders"]], ["Projects"])
            self.assertEqual([entry["path"] for entry in by_folder["documents"]], ["Projects/proposal.md"])
            with self.assertRaisesRegex(ValueError, "at most 160"):
                service.workspace_status("x" * 161)
            snapshot = service.workspace_snapshot()
            self.assertEqual(snapshot["document_count"], 2)
            self.assertEqual(snapshot["folder_count"], 1)
            self.assertTrue(snapshot["catalog_revision"])
            item=service.create_work_item("Workspace", "Show document workspace version snapshot")
            plan=service.plan_for_request(item["id"])
            self.assertIn("workspace.status", plan["actions"])
            self.assertIn("workspace.snapshot", plan["actions"])
            service.approve_plan(plan["id"])
            done = service.execute_plan(plan["id"])
            captured = next(entry["result"] for entry in done["results"] if entry["action"] == "workspace.snapshot")
            self.assertEqual(captured["catalog_revision"], snapshot["catalog_revision"])
            service.close()

    def test_default_documents_scaffold_is_configured_without_contents(self):
        service = OperationsService()
        status = service.workspace_status()
        self.assertTrue(status["available"])
        self.assertTrue(status["configured"])
        self.assertEqual(status["count"], 0)
        self.assertEqual(status["folder_count"], 0)
        self.assertEqual(status["documents"], [])
        self.assertEqual(status["folders"], [])
        snapshot = service.workspace_snapshot()
        self.assertEqual(snapshot["document_count"], 0)
        self.assertEqual(snapshot["folder_count"], 0)
        self.assertTrue(snapshot["catalog_revision"])
        service.close()

    def test_autonomous_loop_status_projects_bounded_evidence_without_command_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); run = root / "20260804T220000Z"; run.mkdir()
            (run / "report.json").write_text('{"title":"Local loop","result":"passed","started_at":"2026-08-04T22:00:00Z","completed_at":"2026-08-04T22:01:00Z","work_item":{"title":"Safe enhancement"},"phases":[{"name":"test","result":"passed","commands":[{"stdout":"secret output"}]}]}')
            service = OperationsService(); service.loop_directory = root
            status = service.autonomous_loop_status()
            self.assertTrue(status["configured"]); self.assertEqual(status["count"], 1)
            self.assertEqual(status["cycles"][0]["result"], "passed")
            self.assertNotIn("commands", status["cycles"][0]); self.assertNotIn("secret output", str(status))
            item = service.create_work_item("Loop", "Show autonomous loop status and engineering loop evidence")
            plan = service.plan_for_request(item["id"])
            self.assertIn("loop.status", plan["actions"])
            service.approve_plan(plan["id"])
            done = service.execute_plan(plan["id"])
            captured = next(entry["result"] for entry in done["results"] if entry["action"] == "loop.status")
            self.assertEqual(captured["count"], 1)
            self.assertNotIn("secret output", str(captured))
            service.close()

    def test_autonomous_work_queue_exposes_only_ordered_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "020-second.md").write_text("# Second item\n\nDo not expose this body.")
            (root / "010-first.md").write_text("# First item\n\nDo not expose this body.")
            (root / "ignore.txt").write_text("not a work item")
            service = OperationsService(); service.inbox_directory = root
            queue = service.autonomous_work_queue()
            self.assertEqual(queue["count"], 2)
            self.assertEqual([item["title"] for item in queue["items"]], ["First item", "Second item"])
            self.assertNotIn("Do not expose", str(queue))
            item = service.create_work_item("Queue", "Show autonomous queue status and queued work inbox")
            plan = service.plan_for_request(item["id"])
            self.assertIn("queue.status", plan["actions"])
            service.approve_plan(plan["id"])
            done = service.execute_plan(plan["id"])
            captured = next(entry["result"] for entry in done["results"] if entry["action"] == "queue.status")
            self.assertEqual(captured["count"], 2)
            self.assertNotIn("Do not expose", str(captured))
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

    def test_approved_backup_is_unique_and_inventory_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            service=OperationsService(); service.backup_directory=Path(directory)
            item=service.create_work_item("Backup", "Create a local backup")
            plan=service.plan_for_request(item["id"]); self.assertIn("backup.create", plan["actions"])
            service.approve_plan(plan["id"]); result=service.execute_plan(plan["id"])
            backup=next(entry["result"] for entry in result["results"] if entry["action"] == "backup.create")
            self.assertTrue(Path(backup["path"]).is_file()); self.assertTrue(backup["audit_chain_valid"])
            self.assertEqual(service.backup_inventory()[0]["name"], Path(backup["path"]).name); service.close()

    def test_recovery_health_verifies_backup_integrity_without_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            service=OperationsService(); service.backup_directory=Path(directory)
            service.create_backup()
            verification=service.verify_backups()
            self.assertTrue(verification["ok"])
            self.assertEqual(len(verification["backups"]), 1)
            self.assertTrue(verification["backups"][0]["integrity_ok"])
            self.assertTrue(verification["backups"][0]["audit_chain_valid"])
            self.assertFalse(verification["retention"]["configured"])
            self.assertFalse(verification["retention"]["prune_enabled"])
            item=service.create_work_item("Recovery", "Verify backup health and recovery integrity")
            plan=service.plan_for_request(item["id"])
            self.assertIn("backup.verify", plan["actions"])
            service.close()

    def test_backup_retention_status_is_explicitly_unset(self):
        service=OperationsService()
        status=service.backup_retention_status()
        self.assertFalse(status["configured"])
        self.assertIsNone(status["policy"])
        self.assertFalse(status["prune_enabled"])
        self.assertIn("not implemented", status["message"])
        item=service.create_work_item("Retention", "Show backup retention status and retention policy")
        plan=service.plan_for_request(item["id"])
        self.assertIn("backup.retention", plan["actions"])
        service.approve_plan(plan["id"])
        done=service.execute_plan(plan["id"])
        captured=next(entry["result"] for entry in done["results"] if entry["action"] == "backup.retention")
        self.assertFalse(captured["configured"])
        service.close()

    def test_backups_status_includes_unset_retention_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            service=OperationsService(); service.backup_directory=Path(directory)
            empty=service.backups_status()
            self.assertTrue(empty["available"])
            self.assertEqual(empty["count"], 0)
            self.assertEqual(empty["backups"], [])
            self.assertFalse(empty["retention"]["configured"])
            self.assertIn("retention remains unset", empty["message"])
            service.create_backup()
            status=service.backups_status()
            self.assertEqual(status["count"], 1)
            self.assertEqual(len(status["backups"]), 1)
            self.assertFalse(status["retention"]["prune_enabled"])
            service.close()

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

    def test_ci_adapter_uses_fixed_bounded_github_actions_command(self):
        service=OperationsService()
        with patch("dopos_core.service.shutil.which", return_value="gh"), patch("dopos_core.service.subprocess.run") as run:
            run.return_value=type("Result", (), {"returncode":0,"stdout":"[{\"status\":\"completed\",\"conclusion\":\"success\",\"workflowName\":\"CI\",\"headSha\":\"abcdef123\",\"createdAt\":\"now\",\"updatedAt\":\"now\",\"url\":\"https://example.test/run\"}]","stderr":""})()
            result=service.ci_status()
        self.assertTrue(result["ok"]); self.assertEqual(result["runs"][0]["workflowName"], "CI")
        self.assertEqual(run.call_args.args[0], ["gh", "run", "list", "--limit", "5", "--json", "status,conclusion,workflowName,headSha,createdAt,updatedAt,url"])
        service.close()

    def test_tool_status_includes_read_only_ci_availability(self):
        service=OperationsService()
        with patch.object(service, "ci_status", return_value={"available": True, "ok": True, "runs": []}):
            tools = service.tool_status()
        self.assertEqual(set(tools), {"docker", "github", "ci", "ollama"})
        self.assertTrue(tools["ci"]["available"])
        service.close()

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
        self.assertEqual(plan["actions"], ["status.summary", "ci.status", "quality.status", "diary.preview"]); service.close()

    def test_request_router_adds_read_only_ci_status(self):
        service=OperationsService(); item=service.create_work_item("CI", "Show CI workflow status")
        with patch.object(service, "local_plan_explanation", return_value="Safe CI plan"):
            plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"], ["status.summary", "ci.status", "diary.preview"]); service.close()

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
