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

    def test_empty_journal_markdown_export_includes_explicit_empty_note(self):
        service = OperationsService()
        export = service.journal_markdown()
        self.assertIn("# dopOS Journal", export)
        self.assertIn("No journal entries have been recorded yet.", export)
        self.assertNotIn("payload", export)
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
            self.assertIn("quality", today)
            self.assertTrue(today["quality"].get("configured") or today["quality"].get("available"))
            self.assertIn("workspace", today)
            self.assertIn("extension_counts", today["workspace"])
            self.assertIn("supported_extensions", today["workspace"])
            self.assertIn("total_bytes", today["workspace"])
            self.assertIn(".md", today["workspace"]["supported_extensions"])
            self.assertTrue(today["workspace"]["configured"])
            self.assertEqual(today["workspace"]["document_count"], 0)
            self.assertEqual(today["workspace"]["folder_count"], 0)
            self.assertIn("safety", today)
            self.assertFalse(today["safety"]["execution_paused"])
            self.assertEqual(today["safety"]["kill_switch"], "off")
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
            self.assertIn("workspace", today)
            service.close()

    def test_today_safety_line_reflects_kill_switch(self):
        service = OperationsService()
        service.set_kill_switch(True)
        today = service.today()
        self.assertTrue(today["safety"]["execution_paused"])
        self.assertEqual(today["safety"]["kill_switch"], "on")
        service.set_kill_switch(False)
        today = service.today()
        self.assertFalse(today["safety"]["execution_paused"])
        self.assertEqual(today["safety"]["kill_switch"], "off")
        service.close()

    def test_today_workspace_summary_counts_local_documents_and_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Notes").mkdir()
            (root / "Notes" / "idea.md").write_text("private")
            (root / "readme.txt").write_text("notes")
            service = OperationsService()
            service.workspace_directory = root
            today = service.today()
            self.assertTrue(today["workspace"]["configured"])
            self.assertEqual(today["workspace"]["document_count"], 2)
            self.assertEqual(today["workspace"]["folder_count"], 1)
            self.assertTrue(today["workspace"]["catalog_revision"])
            self.assertNotIn("private", str(today["workspace"]))
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













    def test_request_router_adds_backup_create_for_plain_backup(self):
        service=OperationsService()
        item=service.create_work_item("Backup", "Create a local backup")
        plan=service.plan_for_request(item["id"])
        self.assertIn("backup.create", plan["actions"])
        self.assertNotIn("backup.verify", plan["actions"])
        self.assertNotIn("backup.retention", plan["actions"])
        service.close()

    def test_request_router_starts_with_status_summary(self):
        service=OperationsService()
        item=service.create_work_item("Start", "Show Docker and GitHub repository status")
        plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"][0], "status.summary")
        service.close()

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



    def test_request_router_adds_workspace_for_supported_extensions_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Allowed", "List supported extensions and allowed document types")
        with patch.object(service, "local_plan_explanation", return_value="Safe workspace plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("workspace.status", plan["actions"]); service.close()

    def test_request_router_adds_workspace_for_file_types_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Types", "Show document types and extension counts")
        with patch.object(service, "local_plan_explanation", return_value="Safe workspace plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("workspace.status", plan["actions"]); service.close()


    def test_request_router_adds_workspace_for_catalog_size_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Size", "Show catalog size and total bytes for the workspace")
        with patch.object(service, "local_plan_explanation", return_value="Safe workspace plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("workspace.status", plan["actions"]); service.close()


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


    def test_safe_actions_exclude_shell_aliases(self):
        from dopos_core.service import SAFE_ACTIONS
        banned = {"shell", "bash", "sh", "system", "shell.run", "shell.rm_rf"}
        self.assertTrue(SAFE_ACTIONS.isdisjoint(banned))
        self.assertFalse(any(action.startswith("shell.") for action in SAFE_ACTIONS))

    def test_safe_actions_include_loop_queue_and_retention_adapters(self):
        from dopos_core.service import SAFE_ACTIONS
        self.assertGreaterEqual(len(SAFE_ACTIONS), 16)
        for action in ("loop.status", "queue.status", "backup.retention", "ci.status", "workspace.snapshot", "health.status", "tools.status", "control.status"):
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
        self.assertIn("catalog_revision", health["workspace"])
        self.assertIn("extension_counts", health["workspace"])
        self.assertEqual(health["workspace"]["extension_counts"], {})
        self.assertEqual(health["workspace"]["total_bytes"], 0)
        self.assertIn(".md", health["workspace"]["supported_extensions"])
        self.assertEqual(health["backup_count"], 0)
        self.assertFalse(health["backup_retention"]["configured"])
        self.assertFalse(health["backup_retention"]["prune_enabled"])
        self.assertEqual(health["backup_retention"]["message"], "Backup retention is unset; existing local backups are left untouched.")
        self.assertIn("configured", health["queue"])
        self.assertIn("count", health["queue"])
        self.assertIn("next_title", health["queue"])
        self.assertIn("configured", health["automation"])
        self.assertIn("latest_result", health["automation"])
        self.assertIn("latest_title", health["automation"])
        self.assertIn("quality", health)
        self.assertTrue(health["quality"]["available"])
        self.assertTrue(health["quality"].get("configured"))
        service.close()


    def test_health_status_includes_queue_next_title_when_inbox_present(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            evidence = Path(directory) / "evidence"
            inbox.mkdir(); evidence.mkdir()
            (inbox / "010-next.md").write_text("# Queue next item\n\nBody stays private.")
            run = evidence / "cycle-a"; run.mkdir()
            (run / "report.json").write_text('{"title":"Cycle A","result":"passed","started_at":"t","completed_at":"t","phases":[],"work_item":{"title":"x"}}')
            service = OperationsService(); service.inbox_directory = inbox; service.loop_directory = evidence
            health = service.health_status()
            self.assertEqual(health["queue"]["count"], 1)
            self.assertEqual(health["queue"]["next_title"], "Queue next item")
            self.assertEqual(health["automation"]["latest_result"], "passed")
            self.assertEqual(health["automation"]["latest_title"], "Cycle A")
            service.close()

    def test_request_router_adds_health_status_without_backup_create(self):
        service = OperationsService()
        for title, request in (
            ("Runtime health", "Show runtime health probe"),
            ("Service health", "Check service health status"),
            ("System health", "Report system health"),
            ("Service probe", "Run a service probe"),
            ("Monitor health", "Monitor health for local runtime"),
            ("Local monitor", "Run a local monitor check"),
            ("Runtime probe", "Run a runtime probe"),
            ("Ledger health", "Check ledger health"),
            ("Audit chain", "Check audit chain validity"),
            ("Runtime ledger", "Inspect runtime ledger status"),
            ("Health check", "Run a health check"),
            ("Probe runtime", "Probe runtime health now"),
            ("Local health probe", "Run a local health probe"),
            ("Local runtime health", "Show local runtime health"),
            ("Host health", "Show host health"),
        ):
            item = service.create_work_item(title, request)
            plan = service.plan_for_request(item["id"])
            self.assertIn("health.status", plan["actions"])
            self.assertNotIn("backup.create", plan["actions"])
            self.assertNotIn("backup.verify", plan["actions"])
        backup_health = service.create_work_item("Backup health", "Verify backup health and recovery integrity")
        plan = service.plan_for_request(backup_health["id"])
        self.assertIn("backup.verify", plan["actions"])
        self.assertNotIn("health.status", plan["actions"])
        service.close()

    def test_health_status_action_executes_readonly_projection(self):
        service = OperationsService()
        item = service.create_work_item("Health action", "Show runtime health status")
        plan = service.plan_for_request(item["id"])
        self.assertIn("health.status", plan["actions"])
        service.approve_plan(plan["id"])
        done = service.execute_plan(plan["id"])
        captured = next(entry["result"] for entry in done["results"] if entry["action"] == "health.status")
        self.assertEqual(captured["status"], "ok")
        self.assertIn("backup_count", captured)
        self.assertFalse(captured["backup_retention"]["configured"])
        service.close()


    def test_request_router_adds_tools_status_for_quality_configured(self):
        service=OperationsService()
        item=service.create_work_item("Configured", "Are the quality configured gates visible in local tools?")
        with patch.object(service, "local_plan_explanation", return_value="Safe tools plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("tools.status", plan["actions"]); service.close()

    def test_request_router_adds_tools_status_aggregate(self):
        service = OperationsService()
        for title, request in (
            ("Tool status", "Show tool status for the control room"),
            ("Local tools", "Check local tools availability"),
            ("Tools status", "Report tools status"),
        ):
            item = service.create_work_item(title, request)
            plan = service.plan_for_request(item["id"])
            self.assertIn("tools.status", plan["actions"])
        service.close()

    def test_tools_status_action_executes_aggregate_projection(self):
        service = OperationsService()
        item = service.create_work_item("Tools action", "Show tools status")
        plan = service.plan_for_request(item["id"])
        self.assertIn("tools.status", plan["actions"])
        service.approve_plan(plan["id"])
        done = service.execute_plan(plan["id"])
        captured = next(entry["result"] for entry in done["results"] if entry["action"] == "tools.status")
        for name in ("docker", "github", "ci", "ollama", "quality"):
            self.assertIn(name, captured)
            self.assertIn("available", captured[name])
        service.close()

    def test_request_router_adds_control_status_readonly(self):
        service = OperationsService()
        for title, request in (
            ("Kill switch", "Show kill switch status"),
            ("Execution safety", "Check execution safety control"),
            ("Control status", "Report control status"),
        ):
            item = service.create_work_item(title, request)
            plan = service.plan_for_request(item["id"])
            self.assertIn("control.status", plan["actions"])
        service.close()






    def test_request_router_adds_tools_status_for_control_room_header(self):
        service = OperationsService()
        item = service.create_work_item("Tools", "Check control room header tools")
        plan = service.plan_for_request(item["id"])
        self.assertIn("tools.status", plan["actions"])
        service.close()

    def test_request_router_adds_tools_status_for_tool_availability(self):
        service = OperationsService()
        item = service.create_work_item("Tools", "Show tool availability for the control room")
        plan = service.plan_for_request(item["id"])
        self.assertIn("tools.status", plan["actions"])
        service.close()

    def test_request_router_adds_control_status_for_paused_execution(self):
        service = OperationsService()
        item = service.create_work_item("Safety", "Report paused execution state")
        plan = service.plan_for_request(item["id"])
        self.assertIn("control.status", plan["actions"])
        service.close()

    def test_request_router_adds_control_status_for_safety_ready(self):
        service = OperationsService()
        item = service.create_work_item("Safety", "Confirm safety ready state")
        plan = service.plan_for_request(item["id"])
        self.assertIn("control.status", plan["actions"])
        service.close()

    def test_request_router_adds_control_status_for_bare_kill_switch(self):
        service = OperationsService()
        item = service.create_work_item("Safety", "Show kill switch")
        plan = service.plan_for_request(item["id"])
        self.assertIn("control.status", plan["actions"])
        self.assertNotIn("backup.create", plan["actions"])
        service.close()

    def test_control_status_action_does_not_toggle_kill_switch(self):
        service = OperationsService()
        item = service.create_work_item("Control", "Show kill switch status")
        plan = service.plan_for_request(item["id"])
        self.assertIn("control.status", plan["actions"])
        service.approve_plan(plan["id"])
        done = service.execute_plan(plan["id"])
        captured = next(entry["result"] for entry in done["results"] if entry["action"] == "control.status")
        self.assertEqual(captured["kill_switch"], "off")
        self.assertFalse(captured["execution_paused"])
        self.assertIn("updated_at", captured)
        self.assertEqual(service.control_status()["kill_switch"], "off")
        self.assertFalse(service.control_status()["execution_paused"])
        service.close()

    def test_work_item_input_is_bounded_and_text_only(self):
        service=OperationsService()
        with self.assertRaisesRegex(ValueError, "at most 160"): service.create_work_item("x" * 161, "safe request")
        with self.assertRaisesRegex(ValueError, "at most 8000"): service.create_work_item("Safe", "x" * 8001)
        with self.assertRaisesRegex(ValueError, "must be text"): service.create_work_item(None, "safe request")
        self.assertEqual(service.status_summary()["work_items"], 0)
        service.close()




    def test_workspace_snapshot_includes_supported_extensions(self):
        from dopos_core.service import WORKSPACE_SUPPORTED_EXTENSIONS
        service=OperationsService()
        snap=service.workspace_snapshot()
        self.assertEqual(snap["supported_extensions"], list(WORKSPACE_SUPPORTED_EXTENSIONS))
        service.close()


    def test_workspace_snapshot_includes_total_bytes(self):
        service = OperationsService()
        snap = service.workspace_snapshot()
        self.assertIn("total_bytes", snap)
        self.assertEqual(snap["total_bytes"], 0)
        service.close()



    def test_workspace_snapshot_includes_unsupported_skipped(self):
        service = OperationsService()
        snap = service.workspace_snapshot()
        self.assertEqual(snap["unsupported_skipped"], 0)
        service.close()


    def test_workspace_supported_extensions_constant(self):
        from dopos_core.service import WORKSPACE_SUPPORTED_EXTENSIONS
        self.assertEqual(WORKSPACE_SUPPORTED_EXTENSIONS, (".md", ".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".ods", ".odt", ".odp"))
        self.assertEqual(len(WORKSPACE_SUPPORTED_EXTENSIONS), 9)


    def test_workspace_status_ignores_hidden_scaffold_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitkeep").write_text("", encoding="utf-8")
            (root / ".secret.bin").write_text("x", encoding="utf-8")
            (root / "note.md").write_text("# n\n", encoding="utf-8")
            service = OperationsService(); service.workspace_directory = root
            status = service.workspace_status()
            self.assertEqual(status["count"], 1)
            self.assertEqual(status["unsupported_skipped"], 0)
            self.assertEqual([d["path"] for d in status["documents"]], ["note.md"])
            service.close()

    def test_workspace_status_includes_extension_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "documents"
            docs.mkdir()
            (docs / "a.md").write_text("# a\n", encoding="utf-8")
            (docs / "b.txt").write_text("b\n", encoding="utf-8")
            (docs / "c.md").write_text("# c\n", encoding="utf-8")
            import os
            os.environ["DOPOS_WORKSPACE_DIR"] = str(docs)
            try:
                service = OperationsService()
                status = service.workspace_status()
            finally:
                os.environ.pop("DOPOS_WORKSPACE_DIR", None)
                service.close()
            self.assertEqual(status["count"], 3)
            self.assertEqual(status["extension_counts"], {".md": 2, ".txt": 1})
            self.assertEqual(list(status["extension_counts"]), [".md", ".txt"])
            self.assertEqual(status["total_bytes"], (docs / "a.md").stat().st_size + (docs / "b.txt").stat().st_size + (docs / "c.md").stat().st_size)
            self.assertIn(".md", status["supported_extensions"])
            self.assertIn(".pdf", status["supported_extensions"])

    def test_workspace_inventory_is_read_only_and_router_uses_allowlisted_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root / "Projects").mkdir(); (root / "Projects" / "proposal.md").write_text("private draft")
            (root / "readme.txt").write_text("notes"); (root / "ignore.exe").write_text("not a document")
            service=OperationsService(); service.workspace_directory=root
            status=service.workspace_status()
            self.assertTrue(status["configured"]); self.assertEqual(status["count"], 2)
            self.assertEqual(status["unsupported_skipped"], 1)
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


    def test_request_router_adds_backup_verify_for_inventory_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Inventory", "Show the backup inventory and list backups")
        with patch.object(service, "local_plan_explanation", return_value="Safe recovery plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("backup.verify", plan["actions"]); service.close()

    def test_backup_retention_status_is_explicitly_unset(self):
        service=OperationsService()
        status=service.backup_retention_status()
        self.assertFalse(status["configured"])
        self.assertIsNone(status["policy"])
        self.assertFalse(status["prune_enabled"])
        self.assertIn("unset", status["message"])
        self.assertNotIn("not implemented", status["message"])
        item=service.create_work_item("Retention", "Show backup retention status and retention policy")
        plan=service.plan_for_request(item["id"])
        self.assertIn("backup.retention", plan["actions"])
        service.approve_plan(plan["id"])
        done=service.execute_plan(plan["id"])
        captured=next(entry["result"] for entry in done["results"] if entry["action"] == "backup.retention")
        self.assertFalse(captured["configured"])
        service.close()


    def test_backups_status_message_is_unique(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertEqual(text.count('Local backup inventory is read-only; retention remains unset.'), 1)
        service=OperationsService()
        status=service.backups_status()
        self.assertEqual(status["message"], 'Local backup inventory is read-only; retention remains unset.')
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


    def test_docker_status_reports_missing_executable_reason(self):
        import shutil
        service = OperationsService()
        original = shutil.which
        try:
            shutil.which = lambda name: None if name == "docker" else original(name)
            status = service.docker_status()
            self.assertFalse(status["available"])
            self.assertIn("docker executable not found", status["reason"])
        finally:
            shutil.which = original
        service.close()

    def test_docker_adapter_is_allowlisted_and_structured(self):
        service=OperationsService(); item=service.create_work_item("Docker", "read docker status")
        plan=service.propose_plan(item["id"], ["docker.status"]); service.approve_plan(plan["id"])
        result=service.execute_plan(plan["id"])["results"][0]["result"]
        self.assertIn("available", result); service.close()


    def test_github_status_reports_missing_executable_reason(self):
        import shutil
        service = OperationsService()
        original = shutil.which
        try:
            shutil.which = lambda name: None if name == "gh" else original(name)
            status = service.github_status()
            self.assertFalse(status["available"])
            self.assertIn("GitHub CLI executable not found", status["reason"])
        finally:
            shutil.which = original
        service.close()

    def test_github_adapter_is_allowlisted_and_structured(self):
        service=OperationsService(); item=service.create_work_item("GitHub", "read repository metadata")
        plan=service.propose_plan(item["id"], ["github.status"]); service.approve_plan(plan["id"])
        result=service.execute_plan(plan["id"])["results"][0]["result"]
        self.assertIn("available", result); service.close()


    def test_ci_status_reports_missing_executable_reason(self):
        import shutil
        service = OperationsService()
        original = shutil.which
        try:
            shutil.which = lambda name: None if name == "gh" else original(name)
            status = service.ci_status()
            self.assertFalse(status["available"])
            self.assertIn("GitHub CLI executable not found", status["reason"])
        finally:
            shutil.which = original
        service.close()

    def test_ci_adapter_uses_fixed_bounded_github_actions_command(self):
        service=OperationsService()
        with patch("dopos_core.service.shutil.which", return_value="gh"), patch("dopos_core.service.subprocess.run") as run:
            run.return_value=type("Result", (), {"returncode":0,"stdout":"[{\"status\":\"completed\",\"conclusion\":\"success\",\"workflowName\":\"CI\",\"headSha\":\"abcdef123\",\"createdAt\":\"now\",\"updatedAt\":\"now\",\"url\":\"https://example.test/run\"}]","stderr":""})()
            result=service.ci_status()
        self.assertTrue(result["ok"]); self.assertEqual(result["runs"][0]["workflowName"], "CI")
        self.assertEqual(run.call_args.args[0], ["gh", "run", "list", "--limit", "5", "--json", "status,conclusion,workflowName,headSha,createdAt,updatedAt,url"])
        service.close()









    def test_quality_tool_availability_ok_true_in_success(self):
        service=OperationsService()
        result=service.quality_tool_availability()
        self.assertTrue(result["ok"])
        self.assertTrue(result["available"])
        service.close()

    def test_quality_tool_availability_available_true_literal(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertIn('return {"available": True, "ok": True, "configured": True, "message": "Local quality gates are configured"}', text)
        self.assertEqual(text.count('return {"available": True, "ok": True, "configured": True, "message": "Local quality gates are configured"}'), 1)

    def test_quality_tool_availability_configured_true_literal(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertIn('"configured": True', text)
        self.assertGreaterEqual(text.count('"configured": True'), 1)

    def test_quality_tool_availability_message_key_unique(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertIn('"message": "Local quality gates are configured"', text)
        self.assertEqual(text.count('"message": "Local quality gates are configured"'), 1)

    def test_quality_configured_message_is_unique(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("Local quality gates are configured"), 1)

    def test_quality_unavailable_reason_is_unique(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("Local quality gate scripts are not configured"), 1)

    def test_quality_tool_availability_reports_missing_scripts(self):
        service=OperationsService()
        with patch.object(service, "project_root", Path("/tmp/dopos-missing-quality-root")):
            result=service.quality_tool_availability()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "Local quality gate scripts are not configured")
        service.close()

    def test_request_router_adds_quality_for_run_tests_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Tests", "Please run tests for this repository")
        with patch.object(service, "local_plan_explanation", return_value="Safe quality plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("quality.status", plan["actions"]); service.close()

    def test_tool_status_quality_is_availability_only(self):
        service = OperationsService()
        with patch.object(service, "quality_status") as quality_status:
            tools = service.tool_status()
        self.assertIn("quality", tools)
        self.assertTrue(tools["quality"]["available"])
        self.assertTrue(tools["quality"].get("configured"))
        quality_status.assert_not_called()
        service.close()

    def test_tool_status_includes_read_only_ci_availability(self):
        service=OperationsService()
        with patch.object(service, "ci_status", return_value={"available": True, "ok": True, "runs": []}):
            tools = service.tool_status()
        self.assertEqual(set(tools), {"docker", "github", "ci", "ollama", "quality"})
        self.assertTrue(tools["ci"]["available"])
        service.close()

    def test_request_router_stays_within_allowlist(self):
        service=OperationsService(); item=service.create_work_item("Route", "Show Docker and GitHub repository status")
        plan=service.plan_for_request(item["id"])
        self.assertEqual(plan["actions"], ["status.summary", "docker.status", "github.status", "diary.preview"])
        service.close()






    def test_quality_short_circuit_fallback_reason_unique(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("Local quality checks are unavailable."), 1)

    def test_quality_short_circuit_returns_empty_checks_literal(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertIn('"checks": []', text)
        self.assertEqual(text.count('"checks": []'), 1)

    def test_quality_status_short_circuit_guard_unique(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py").read_text(encoding="utf-8")
        self.assertEqual(text.count('if not availability.get("available"):'), 1)

    def test_quality_status_short_circuits_when_scripts_missing(self):
        service=OperationsService()
        with patch.object(service, "quality_tool_availability", return_value={"available": False, "ok": False, "reason": "Local quality gate scripts are not configured"}):
            with patch("dopos_core.service.subprocess.run") as run:
                result=service.quality_status()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "Local quality gate scripts are not configured")
        self.assertEqual(result["checks"], [])
        run.assert_not_called()
        service.close()

    def test_quality_status_timeout_message_is_explicit(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1] / "src" / "dopos_core" / "service.py"
        self.assertIn("timed out after 90 seconds", source.read_text(encoding="utf-8"))

    def test_quality_adapter_uses_only_fixed_local_ci_commands(self):
        service=OperationsService()
        with patch("dopos_core.service.subprocess.run") as run:
            run.return_value=type("Result", (), {"returncode":0,"stdout":"passed","stderr":""})()
            result=service.quality_status()
        self.assertTrue(result["ok"]); self.assertEqual([check["name"] for check in result["checks"]], ["compile", "tests", "governance"])
        self.assertEqual(run.call_count, 3); self.assertTrue(all(isinstance(call.args[0], list) for call in run.call_args_list)); service.close()




    def test_request_router_adds_quality_for_local_quality_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Local quality", "Show local quality status only")
        with patch.object(service, "local_plan_explanation", return_value="Safe quality plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("quality.status", plan["actions"]); service.close()

    def test_request_router_adds_quality_for_quality_gates_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Gates", "Run the quality gates and compile source")
        with patch.object(service, "local_plan_explanation", return_value="Safe quality plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("quality.status", plan["actions"]); service.close()

    def test_request_router_adds_quality_for_lint_phrase(self):
        service=OperationsService()
        item=service.create_work_item("Lint", "Please lint and run unit tests")
        with patch.object(service, "local_plan_explanation", return_value="Safe quality plan"):
            plan=service.plan_for_request(item["id"])
        self.assertIn("quality.status", plan["actions"]); service.close()

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


    def test_request_router_adds_ollama_for_installed_models_phrase(self):
        service = OperationsService()
        item = service.create_work_item("Models", "Show installed models inventory")
        plan = service.plan_for_request(item["id"])
        self.assertIn("ollama.status", plan["actions"])
        service.close()


    def test_ollama_status_reports_missing_executable_reason(self):
        import shutil
        service = OperationsService()
        original = shutil.which
        try:
            shutil.which = lambda name: None if name == "ollama" else original(name)
            status = service.ollama_status()
            self.assertFalse(status["available"])
            self.assertIn("ollama executable not found", status["reason"])
        finally:
            shutil.which = original
        service.close()

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
