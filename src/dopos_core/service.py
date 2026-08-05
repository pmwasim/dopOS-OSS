"""Small, dependency-free local core with approval-gated safe actions."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import shutil
import subprocess
import re
import sys
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_ACTIONS = {"status.summary", "diary.preview", "docker.status", "github.status", "ci.status", "ollama.status", "quality.status", "backup.create", "backup.verify", "backup.retention", "workspace.status", "workspace.snapshot", "loop.status", "queue.status", "health.status", "tools.status", "control.status"}
MAX_WORK_ITEM_TITLE = 160
MAX_WORK_ITEM_REQUEST = 8_000
MAX_WORKSPACE_QUERY = 160
MAX_LOOP_REPORT_BYTES = 256_000
MAX_WORK_ITEM_HEADER_BYTES = 4_096

def synchronized(method):
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped

class OperationsService:
    def __init__(self, database: str | Path = ":memory:"):
        self._lock = threading.RLock()
        self.project_root = Path(__file__).resolve().parents[2]
        self.backup_directory = Path(os.environ.get("DOPOS_BACKUP_DIR", self.project_root / "workspace/generated/backups"))
        self.workspace_directory = Path(os.environ.get("DOPOS_WORKSPACE_DIR", self.project_root / "workspace/documents"))
        self.loop_directory = Path(os.environ.get("DOPOS_LOOP_EVIDENCE_DIR", self.project_root / "workspace/generated/autonomous-loop"))
        self.inbox_directory = Path(os.environ.get("DOPOS_INBOX_DIR", self.project_root / "workspace/inbox"))
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS work_items (id INTEGER PRIMARY KEY, title TEXT NOT NULL, request TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, work_item_id INTEGER NOT NULL REFERENCES work_items(id), actions_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT);
        CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS controls (name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
        """)
        if "explanation" not in {row[1] for row in self.db.execute("PRAGMA table_info(plans)")}:
            self.db.execute("ALTER TABLE plans ADD COLUMN explanation TEXT NOT NULL DEFAULT ''")
        if not self.db.execute("SELECT 1 FROM controls WHERE name='kill_switch'").fetchone():
            self.db.execute("INSERT INTO controls(name,value,updated_at) VALUES(?,?,?)", ("kill_switch", "off", self.now())); self.db.commit()

    @synchronized
    def close(self) -> None:
        self.db.close()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def display_text(value: str, limit: int = 1000) -> str:
        """Normalize legacy terminal output before returning it to a browser."""
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        if "...done thinking." in value:
            value = value.split("...done thinking.", 1)[1]
        return " ".join(value.split())[:limit]

    @synchronized
    def audit(self, kind: str, payload: dict[str, Any]) -> int:
        previous = self.db.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        previous_hash = previous[0] if previous else "GENESIS"
        created_at = self.now(); encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        event_hash = hashlib.sha256(f"{previous_hash}|{kind}|{created_at}|{encoded}".encode()).hexdigest()
        cursor = self.db.execute("INSERT INTO audit_events(kind,payload_json,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?)", (kind, encoded, created_at, previous_hash, event_hash))
        self.db.commit(); return cursor.lastrowid

    @synchronized
    def create_work_item(self, title: str, request: str) -> dict[str, Any]:
        if not isinstance(title, str) or not isinstance(request, str):
            raise ValueError("title and request must be text")
        title, request = title.strip(), request.strip()
        if not title or not request:
            raise ValueError("title and request are required")
        if len(title) > MAX_WORK_ITEM_TITLE:
            raise ValueError(f"title must be at most {MAX_WORK_ITEM_TITLE} characters")
        if len(request) > MAX_WORK_ITEM_REQUEST:
            raise ValueError(f"request must be at most {MAX_WORK_ITEM_REQUEST} characters")
        now = self.now(); cursor = self.db.execute("INSERT INTO work_items(title,request,state,created_at) VALUES(?,?,?,?)", (title, request, "open", now)); self.db.commit()
        item = {"id": cursor.lastrowid, "title": title, "request": request, "state": "open", "created_at": now}; self.audit("work_item.created", item); return item

    @synchronized
    def work_items(self, limit: int = 12) -> list[dict[str, Any]]:
        """Recent durable work, with the most recent plan state for each item."""
        rows = self.db.execute("""
            SELECT w.id, w.title, w.request, w.state, w.created_at,
                   p.id AS plan_id, p.actions_json, p.state AS plan_state,
                   p.created_at AS plan_created_at, p.approved_at, p.explanation
            FROM work_items AS w
            LEFT JOIN plans AS p ON p.id = (
                SELECT id FROM plans WHERE work_item_id=w.id ORDER BY id DESC LIMIT 1
            )
            ORDER BY w.id DESC LIMIT ?
        """, (max(1, min(limit, 100)),)).fetchall()
        return [self._work_item_row(row) for row in rows]

    def _work_item_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = {key: row[key] for key in ("id", "title", "request", "state", "created_at")}
        if row["plan_id"] is not None:
            # The newest plan is the source of truth for legacy rows created
            # before work-item lifecycle state was introduced.
            item["state"] = row["plan_state"]
            item["plan"] = {
                "id": row["plan_id"], "actions": json.loads(row["actions_json"]),
                "state": row["plan_state"], "created_at": row["plan_created_at"],
                "approved_at": row["approved_at"],
                "explanation": self.display_text(row["explanation"]),
                "results": self.plan_results(row["plan_id"]),
            }
        else:
            item["plan"] = None
        return item

    def plan_results(self, plan_id: int) -> list[dict[str, Any]] | None:
        """Project the immutable execution event into a read-only task detail."""
        rows = self.db.execute(
            "SELECT payload_json FROM audit_events WHERE kind='plan.executed' ORDER BY id DESC"
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if payload.get("id") == plan_id:
                return self.display_results(payload.get("results", []))
        return None

    @staticmethod
    def display_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep historical result projections bounded even if old diary previews nested audit data."""
        projected = []
        for entry in results:
            copied = dict(entry)
            if copied.get("action") == "diary.preview" and isinstance(copied.get("result"), list):
                copied["result"] = [
                    {key: event.get(key) for key in ("id", "kind", "created_at")}
                    for event in copied["result"] if isinstance(event, dict)
                ]
            projected.append(copied)
        return projected

    @synchronized
    def work_item(self, work_item_id: int) -> dict[str, Any]:
        """Read a durable work item and its latest plan without changing state."""
        rows = self.work_items(limit=100)
        for item in rows:
            if item["id"] == work_item_id:
                return item
        raise ValueError("work item not found")

    @synchronized
    def propose_plan(self, work_item_id: int, actions: list[str], explanation: str = "") -> dict[str, Any]:
        if not actions or any(action not in SAFE_ACTIONS for action in actions): raise ValueError("plan contains unsupported action")
        if not self.db.execute("SELECT 1 FROM work_items WHERE id=?", (work_item_id,)).fetchone(): raise ValueError("work item not found")
        now=self.now(); cursor=self.db.execute("INSERT INTO plans(work_item_id,actions_json,state,created_at,explanation) VALUES(?,?,?,?,?)", (work_item_id, json.dumps(actions), "awaiting_approval", now, explanation[:4000]))
        self.db.execute("UPDATE work_items SET state=? WHERE id=?", ("awaiting_approval", work_item_id)); self.db.commit()
        plan={"id":cursor.lastrowid,"work_item_id":work_item_id,"actions":actions,"explanation":explanation[:4000],"state":"awaiting_approval","created_at":now}; self.audit("plan.proposed", plan); return plan

    @synchronized
    def plan_for_request(self, work_item_id: int) -> dict[str, Any]:
        """Deterministic local planner; it never expands beyond the safe allowlist."""
        row = self.db.execute("SELECT request FROM work_items WHERE id=?", (work_item_id,)).fetchone()
        if not row: raise ValueError("work item not found")
        request = row["request"].lower(); actions=["status.summary"]
        if "docker" in request or "container" in request: actions.append("docker.status")
        if "github" in request or "repository" in request or "repo" in request: actions.append("github.status")
        if re.search(r"\bci\b", request) or any(phrase in request for phrase in ("github actions", "workflow", "pipeline")):
            actions.append("ci.status")
        if "ollama" in request or "model" in request or "ai runtime" in request or "installed models" in request: actions.append("ollama.status")
        if any(word in request for word in ("test", "build", "validate", "quality")): actions.append("quality.status")
        if any(word in request for word in ("workspace", "document", "documents", "folder", "folders", "file", "files")):
            actions.append("workspace.status")
        if any(word in request for word in ("workspace snapshot", "document snapshot", "workspace version", "document version", "catalog revision")):
            actions.append("workspace.snapshot")
        if any(phrase in request for phrase in ("autonomous loop", "loop status", "engineering loop", "loop evidence")):
            actions.append("loop.status")
        if any(phrase in request for phrase in ("work queue", "queue status", "inbox queue", "autonomous queue", "queued work")):
            actions.append("queue.status")
        if any(phrase in request for phrase in ("runtime health", "service health", "system health", "health probe", "health status", "service probe", "monitor health", "local monitor", "runtime probe", "ledger health", "audit chain", "runtime ledger", "health check", "probe runtime", "local health probe", "local runtime health", "host health")):
            actions.append("health.status")
        if any(phrase in request for phrase in ("tool status", "tools status", "local tools", "control room tools", "tools availability", "tool availability", "control room header")):
            actions.append("tools.status")
        if any(phrase in request for phrase in ("kill switch status", "kill switch", "execution safety", "safety control", "control status", "execution paused", "safety ready", "paused execution")):
            actions.append("control.status")
        if any(term in request for term in ("recovery", "integrity", "verify backup", "backup health")):
            actions.append("backup.verify")
        elif any(phrase in request for phrase in ("backup retention", "retention policy", "prune backup", "retention status")):
            actions.append("backup.retention")
        elif "backup" in request:
            actions.append("backup.create")
        actions.append("diary.preview")
        explanation = self.local_plan_explanation(row["request"], actions)
        plan=self.propose_plan(work_item_id, actions, explanation)
        self.audit("plan.routed", {"plan_id":plan["id"],"method":"deterministic-safe-router","actions":actions, "explanation_source":"local-qwen-or-fallback"})
        return plan

    @synchronized
    def local_plan_explanation(self, request: str, actions: list[str]) -> str:
        """Optional local explanation; selected actions remain deterministic and frozen."""
        fallback = "Safe plan prepared from the request. It contains only allowlisted read-only checks and still requires approval."
        executable = shutil.which("ollama")
        if not executable: return fallback
        prompt = ("Explain this already-frozen safe operations plan in at most two short sentences. "
                  "Do not suggest extra tools, commands, actions, permissions, or approvals. "
                  f"Request: {request[:1000]}\nFrozen actions: {', '.join(actions)}")
        try:
            # An explanation enriches a plan but must never delay the safe,
            # deterministic planning path.  The local model is best-effort.
            result=subprocess.run([executable, "run", "--hidethinking", "--think=false", "--nowordwrap", "qwen3:latest", prompt], text=True, capture_output=True, timeout=8, check=False)
        except subprocess.TimeoutExpired: return fallback
        text=self.display_text(result.stdout)
        return text if result.returncode == 0 and text else fallback

    @synchronized
    def approve_plan(self, plan_id: int) -> dict[str, Any]:
        row=self.db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row: raise ValueError("plan not found")
        if row["state"] != "awaiting_approval": raise ValueError("plan is not awaiting approval")
        approved_at=self.now(); self.db.execute("UPDATE plans SET state=?, approved_at=? WHERE id=?", ("approved", approved_at, plan_id))
        self.db.execute("UPDATE work_items SET state=? WHERE id=?", ("approved", row["work_item_id"])); self.db.commit()
        result={"id":plan_id,"state":"approved","approved_at":approved_at}; self.audit("plan.approved", result); return result

    @synchronized
    def reject_plan(self, plan_id: int) -> dict[str, Any]:
        row=self.db.execute("SELECT state,work_item_id FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row: raise ValueError("plan not found")
        if row["state"] != "awaiting_approval": raise ValueError("plan is not awaiting approval")
        self.db.execute("UPDATE plans SET state=? WHERE id=?", ("rejected", plan_id))
        self.db.execute("UPDATE work_items SET state=? WHERE id=?", ("rejected", row["work_item_id"])); self.db.commit()
        result={"id":plan_id,"state":"rejected"}; self.audit("plan.rejected", result); return result

    @synchronized
    def set_kill_switch(self, enabled: bool) -> dict[str, Any]:
        value="on" if enabled else "off"; now=self.now(); self.db.execute("UPDATE controls SET value=?,updated_at=? WHERE name='kill_switch'", (value, now)); self.db.commit()
        result={"kill_switch":value,"updated_at":now}; self.audit("control.kill_switch_changed", result); return result

    @synchronized
    def kill_switch_enabled(self) -> bool:
        return self.db.execute("SELECT value FROM controls WHERE name='kill_switch'").fetchone()[0] == "on"

    @synchronized
    def control_status(self) -> dict[str, Any]:
        row = self.db.execute("SELECT value,updated_at FROM controls WHERE name='kill_switch'").fetchone()
        return {
            "kill_switch": row["value"],
            "execution_paused": row["value"] == "on",
            "updated_at": row["updated_at"],
        }

    @synchronized
    def execute_plan(self, plan_id: int) -> dict[str, Any]:
        row=self.db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row: raise ValueError("plan not found")
        if self.kill_switch_enabled(): raise ValueError("execution blocked by kill switch")
        if row["state"] != "approved": raise ValueError("plan requires approval")
        actions=json.loads(row["actions_json"]); results=[]
        for action in actions:
            if action == "status.summary": results.append({"action": action, "result": self.status_summary()})
            elif action == "diary.preview": results.append({"action": action, "result": self.diary_preview(limit=5)})
            elif action == "docker.status": results.append({"action": action, "result": self.docker_status()})
            elif action == "github.status": results.append({"action": action, "result": self.github_status()})
            elif action == "ci.status": results.append({"action": action, "result": self.ci_status()})
            elif action == "ollama.status": results.append({"action": action, "result": self.ollama_status()})
            elif action == "quality.status": results.append({"action": action, "result": self.quality_status()})
            elif action == "backup.create": results.append({"action": action, "result": self.create_backup()})
            elif action == "backup.verify": results.append({"action": action, "result": self.verify_backups()})
            elif action == "backup.retention": results.append({"action": action, "result": self.backup_retention_status()})
            elif action == "workspace.status": results.append({"action": action, "result": self.workspace_status()})
            elif action == "workspace.snapshot": results.append({"action": action, "result": self.workspace_snapshot()})
            elif action == "loop.status": results.append({"action": action, "result": self.autonomous_loop_status()})
            elif action == "queue.status": results.append({"action": action, "result": self.autonomous_work_queue()})
            elif action == "health.status": results.append({"action": action, "result": self.health_status()})
            elif action == "tools.status": results.append({"action": action, "result": self.tool_status()})
            elif action == "control.status": results.append({"action": action, "result": self.control_status()})
            else: raise ValueError("action is not safe")
        self.db.execute("UPDATE plans SET state=? WHERE id=?", ("completed", plan_id))
        self.db.execute("UPDATE work_items SET state=? WHERE id=?", ("completed", row["work_item_id"])); self.db.commit()
        result={"id":plan_id,"state":"completed","results":results}; self.audit("plan.executed", result); return result

    @synchronized
    def status_summary(self) -> dict[str, int]:
        return {"work_items": self.db.execute("SELECT COUNT(*) FROM work_items").fetchone()[0], "plans": self.db.execute("SELECT COUNT(*) FROM plans").fetchone()[0], "audit_events": self.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]}

    @synchronized
    def health_status(self) -> dict[str, Any]:
        """Read-only runtime health suitable for a local monitor or service probe."""
        summary = self.status_summary()
        audit_chain_valid = self.verify_audit_chain()
        workspace = self.workspace_status(limit=100)
        retention = self.backup_retention_status()
        backup_count = len(self.backup_inventory(limit=100))
        queue = self.autonomous_work_queue(limit=1)
        loop = self.autonomous_loop_status(limit=1)
        latest = loop["cycles"][0] if loop.get("cycles") else None
        return {
            "status": "ok" if audit_chain_valid else "degraded",
            "core": "dopos",
            "audit_chain_valid": audit_chain_valid,
            "execution_paused": self.kill_switch_enabled(),
            "records": summary,
            "workspace": {
                "configured": workspace.get("configured", False),
                "document_count": workspace.get("count", 0),
                "folder_count": workspace.get("folder_count", 0),
                "catalog_revision": workspace.get("catalog_revision"),
            },
            "backup_count": backup_count,
            "backup_retention": {
                "configured": retention["configured"],
                "prune_enabled": retention["prune_enabled"],
            },
            "queue": {
                "configured": queue.get("configured", False),
                "count": queue.get("count", 0),
                "next_title": queue["items"][0]["title"] if queue.get("items") else None,
            },
            "automation": {
                "configured": loop.get("configured", False),
                "latest_result": latest.get("result") if latest else None,
                "latest_title": latest.get("title") if latest else None,
            },
        }

    @synchronized
    def today(self) -> dict[str, Any]:
        """A local-first Home projection made only from durable operational state."""
        rows = self.db.execute("""
            SELECT w.id, w.title, p.id AS plan_id, p.state AS plan_state
            FROM work_items AS w
            LEFT JOIN plans AS p ON p.id = (
                SELECT id FROM plans WHERE work_item_id=w.id ORDER BY id DESC LIMIT 1
            )
            WHERE p.state IN ('awaiting_approval', 'approved')
            ORDER BY w.id DESC LIMIT 12
        """).fetchall()
        entries = [{"work_item_id": row["id"], "title": self.display_text(row["title"], 160), "plan_id": row["plan_id"], "state": row["plan_state"]} for row in rows]
        backups = self.backup_inventory(limit=1)
        queue = self.autonomous_work_queue(limit=1)
        loop = self.autonomous_loop_status(limit=1)
        workspace = self.workspace_status(limit=100)
        latest = loop["cycles"][0] if loop.get("cycles") else None
        return {
            "generated_at": self.now(),
            "needs_decision": [entry for entry in entries if entry["state"] == "awaiting_approval"],
            "in_motion": [entry for entry in entries if entry["state"] == "approved"],
            "recent_activity": self.journal(limit=5),
            "recovery": {
                "audit_chain_valid": self.verify_audit_chain(),
                "backup_count": len(self.backup_inventory(limit=100)),
                "latest_backup": backups[0] if backups else None,
                "retention": self.backup_retention_status(),
            },
            "workspace": {
                "configured": workspace.get("configured", False),
                "document_count": workspace.get("count", 0),
                "folder_count": workspace.get("folder_count", 0),
                "catalog_revision": workspace.get("catalog_revision"),
            },
            "safety": {
                "execution_paused": self.kill_switch_enabled(),
                "kill_switch": self.control_status()["kill_switch"],
            },
            "queue": {
                "configured": queue.get("configured", False),
                "count": queue.get("count", 0),
                "next_title": queue["items"][0]["title"] if queue.get("items") else None,
            },
            "automation": {
                "configured": loop.get("configured", False),
                "latest_result": latest.get("result") if latest else None,
                "latest_title": latest.get("title") if latest else None,
            },
        }

    @synchronized
    def tool_status(self) -> dict[str, dict[str, Any]]:
        """Read-only availability snapshot for the local control-room header."""
        return {
            "docker": self.docker_status(),
            "github": self.github_status(),
            "ci": self.ci_status(),
            "ollama": self.ollama_status(),
        }

    @synchronized
    def autonomous_loop_status(self, limit: int = 8) -> dict[str, Any]:
        """Project bounded summaries of local loop evidence, never command output."""
        root = self.loop_directory
        if not root.is_dir():
            return {"available": True, "configured": False, "cycles": [], "count": 0, "message": "No local autonomous-loop evidence directory has been created yet."}
        cycles = []
        for run in sorted(root.iterdir(), reverse=True):
            if len(cycles) >= max(1, min(limit, 20)):
                break
            report = run / "report.json"
            try:
                if not run.is_dir() or run.is_symlink() or not report.is_file() or report.is_symlink() or report.stat().st_size > MAX_LOOP_REPORT_BYTES:
                    continue
                payload = json.loads(report.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                phases = payload.get("phases", [])
                cycles.append({
                    "id": run.name,
                    "title": self.display_text(str(payload.get("title", "Autonomous SaaS engineering cycle")), 160),
                    "result": payload.get("result") if payload.get("result") in {"passed", "failed", "blocked", "planned"} else "unknown",
                    "started_at": self.display_text(str(payload.get("started_at", "")), 64),
                    "completed_at": self.display_text(str(payload.get("completed_at", "")), 64),
                    "work_item": self.display_text(str((payload.get("work_item") or {}).get("title", "")), 160),
                    "phases": [{"name": self.display_text(str(phase.get("name", "")), 64), "result": phase.get("result") if phase.get("result") in {"passed", "failed", "planned"} else "unknown"} for phase in phases if isinstance(phase, dict)],
                })
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
        return {"available": True, "configured": True, "cycles": cycles, "count": len(cycles), "message": "Autonomous-loop evidence summaries are read-only."}

    @synchronized
    def autonomous_work_queue(self, limit: int = 20) -> dict[str, Any]:
        """List the runner's Markdown candidates without reading work-item bodies."""
        root = self.inbox_directory
        if not root.is_dir():
            return {"available": True, "configured": False, "items": [], "count": 0, "message": "No local autonomous-work inbox has been created yet."}
        items = []
        for path in sorted(root.glob("*.md")):
            if len(items) >= max(1, min(limit, 50)):
                break
            try:
                if path.name == ".gitkeep" or not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_WORK_ITEM_REQUEST:
                    continue
                with path.open("r", encoding="utf-8", errors="replace") as source:
                    header = source.read(MAX_WORK_ITEM_HEADER_BYTES)
                title = next((line[2:].strip() for line in header.splitlines() if line.startswith("# ")), path.stem.replace("-", " "))
                items.append({"path": str(path.relative_to(root)), "title": self.display_text(title, 160), "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
            except (OSError, ValueError):
                continue
        return {"available": True, "configured": True, "items": items, "count": len(items), "message": "Queued work is listed by filename and title only; the oldest name is selected by the runner."}

    @synchronized
    def workspace_status(self, query: str = "", limit: int = 100) -> dict[str, Any]:
        """Find workspace files by filename/path without reading contents or links."""
        if not isinstance(query, str):
            raise ValueError("workspace query must be text")
        if len(query) > MAX_WORKSPACE_QUERY:
            raise ValueError(f"workspace query must be at most {MAX_WORKSPACE_QUERY} characters")
        needle = query.strip().casefold()
        root = self.workspace_directory
        if not root.is_dir():
            return {"available": True, "configured": False, "query": query, "documents": [], "folders": [], "count": 0, "folder_count": 0, "catalog_revision": None, "message": "Local workspace directory has not been created yet."}
        allowed_suffixes = {".md", ".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".ods", ".odt", ".odp"}
        documents = []
        folders = []
        for path in sorted(root.rglob("*")):
            try:
                if path.is_symlink():
                    continue
                relative = path.relative_to(root)
                relative_text = str(relative)
                if needle and needle not in relative_text.casefold():
                    continue
                if path.is_dir():
                    if len(folders) < max(1, min(limit, 100)):
                        folders.append({"path": relative_text, "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
                    continue
                if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
                    continue
                if len(documents) >= max(1, min(limit, 100)):
                    continue
                documents.append({"path": relative_text, "extension": path.suffix.lower(), "size": path.stat().st_size, "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
            except (OSError, ValueError):
                continue
        message = "Local workspace search completed without reading document contents." if needle else "Local workspace inventory completed without reading document contents."
        revision_input = "\n".join(
            [f"folder|{folder['path']}|{folder['modified_at']}" for folder in folders]
            + [f"document|{document['path']}|{document['size']}|{document['modified_at']}" for document in documents]
        )
        return {"available": True, "configured": True, "query": query, "documents": documents, "folders": folders, "count": len(documents), "folder_count": len(folders), "catalog_revision": hashlib.sha256(revision_input.encode()).hexdigest(), "message": message}

    @synchronized
    def workspace_snapshot(self) -> dict[str, Any]:
        """Capture an approved, metadata-only catalog revision in the audit trail."""
        status = self.workspace_status()
        return {"available": status["available"], "configured": status["configured"], "document_count": status["count"], "folder_count": status.get("folder_count", 0), "catalog_revision": status["catalog_revision"], "message": "Metadata-only workspace snapshot captured in the approved plan evidence."}

    @synchronized
    def quality_status(self) -> dict[str, Any]:
        """Run only the repository's fixed local CI gates; no shell interpolation."""
        checks = [
            ("compile", [sys.executable, "scripts/compile_source.py", "--root", "src"]),
            ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
            ("governance", [sys.executable, "scripts/validate_companyos.py", "--repo", "."]),
        ]
        outcomes = []
        for name, command in checks:
            try:
                result = subprocess.run(command, cwd=self.project_root, text=True, capture_output=True, timeout=90, check=False)
                outcomes.append({"name": name, "passed": result.returncode == 0, "output": (result.stdout + result.stderr)[-4000:]})
            except subprocess.TimeoutExpired:
                outcomes.append({"name": name, "passed": False, "output": "timed out after 90 seconds"})
        return {"available": True, "ok": all(check["passed"] for check in outcomes), "checks": outcomes}

    @synchronized
    def docker_status(self) -> dict[str, Any]:
        """Read-only adapter; never interpolates user input into a command."""
        executable = shutil.which("docker")
        if not executable: return {"available": False, "reason": "docker executable not found"}
        try:
            result = subprocess.run([executable, "ps", "--format", "{{.Names}}\t{{.Status}}"], text=True, capture_output=True, timeout=10, check=False)
        except subprocess.TimeoutExpired: return {"available": True, "ok": False, "reason": "docker status timed out"}
        return {"available": True, "ok": result.returncode == 0, "containers": result.stdout[:12000], "error": result.stderr[:2000]}

    @synchronized
    def github_status(self) -> dict[str, Any]:
        """Read-only GitHub metadata for the repository containing this process."""
        executable = shutil.which("gh")
        if not executable: return {"available": False, "reason": "GitHub CLI executable not found"}
        try:
            result = subprocess.run([executable, "repo", "view", "--json", "nameWithOwner,defaultBranchRef,isPrivate,url"], text=True, capture_output=True, timeout=10, check=False)
        except subprocess.TimeoutExpired: return {"available": True, "ok": False, "reason": "GitHub status timed out"}
        if result.returncode != 0: return {"available": True, "ok": False, "error": result.stderr[:2000]}
        try: return {"available": True, "ok": True, "repository": json.loads(result.stdout)}
        except json.JSONDecodeError: return {"available": True, "ok": False, "error": "GitHub CLI returned invalid JSON"}

    @synchronized
    def ci_status(self) -> dict[str, Any]:
        """Read the latest GitHub Actions results with a fixed, bounded query."""
        executable = shutil.which("gh")
        if not executable:
            return {"available": False, "reason": "GitHub CLI executable not found"}
        command = [executable, "run", "list", "--limit", "5", "--json", "status,conclusion,workflowName,headSha,createdAt,updatedAt,url"]
        try:
            result = subprocess.run(command, cwd=self.project_root, text=True, capture_output=True, timeout=15, check=False)
        except subprocess.TimeoutExpired:
            return {"available": True, "ok": False, "reason": "CI status timed out"}
        if result.returncode != 0:
            return {"available": True, "ok": False, "error": result.stderr[:2000]}
        try:
            payload = json.loads(result.stdout)
            if not isinstance(payload, list):
                raise ValueError("expected a list")
            runs = []
            for run in payload[:5]:
                if not isinstance(run, dict):
                    continue
                runs.append({key: self.display_text(str(run.get(key, "")), 240) for key in ("status", "conclusion", "workflowName", "headSha", "createdAt", "updatedAt", "url")})
            return {"available": True, "ok": True, "runs": runs}
        except (json.JSONDecodeError, ValueError, TypeError):
            return {"available": True, "ok": False, "error": "GitHub CLI returned invalid CI status JSON"}

    @synchronized
    def ollama_status(self) -> dict[str, Any]:
        """Read-only inventory of locally available models."""
        executable = shutil.which("ollama")
        if not executable: return {"available": False, "reason": "ollama executable not found"}
        try:
            result = subprocess.run([executable, "list"], text=True, capture_output=True, timeout=10, check=False)
        except subprocess.TimeoutExpired: return {"available": True, "ok": False, "reason": "Ollama status timed out"}
        return {"available": True, "ok": result.returncode == 0, "models": result.stdout[:12000], "error": result.stderr[:2000]}

    @synchronized
    def diary(self, limit: int = 25) -> list[dict[str, Any]]:
        rows=self.db.execute("SELECT id,kind,payload_json,created_at,event_hash FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id":r["id"],"kind":r["kind"],"payload":json.loads(r["payload_json"]),"created_at":r["created_at"],"event_hash":r["event_hash"]} for r in reversed(rows)]

    @synchronized
    def diary_preview(self, limit: int = 5) -> list[dict[str, Any]]:
        """Compact display-safe diary projection; never nests prior audit payloads."""
        rows = self.db.execute(
            "SELECT id,kind,created_at FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"id": row["id"], "kind": row["kind"], "created_at": row["created_at"]} for row in reversed(rows)]

    @classmethod
    def journal_entry(cls, event: dict[str, Any]) -> dict[str, Any]:
        """Create a bounded human-readable view without altering audit evidence."""
        payload = event["payload"]
        kind = event["kind"]
        if kind == "work_item.created":
            summary = f"Started: {cls.display_text(str(payload.get('title', 'new work')), 160)}"
            detail = cls.display_text(str(payload.get("request", "")), 360)
        elif kind == "plan.proposed":
            actions = payload.get("actions", [])
            summary = f"Prepared a safe plan with {len(actions) if isinstance(actions, list) else 0} action(s)."
            detail = ", ".join(cls.display_text(str(action), 100) for action in actions[:6]) if isinstance(actions, list) else ""
        elif kind == "plan.routed":
            summary = "Selected the local safe action route."
            detail = cls.display_text(str(payload.get("method", "")), 180)
        elif kind == "plan.approved":
            summary = f"Approved plan #{payload.get('id', 'unknown')}."
            detail = "The allowed checks can now run locally."
        elif kind == "plan.rejected":
            summary = f"Rejected plan #{payload.get('id', 'unknown')}."
            detail = "No action was run."
        elif kind == "plan.executed":
            results = payload.get("results", [])
            summary = f"Completed plan #{payload.get('id', 'unknown')} with {len(results) if isinstance(results, list) else 0} result(s)."
            detail = "Captured the output of approved local checks."
        elif kind == "control.kill_switch_changed":
            paused = payload.get("kill_switch") == "on"
            summary = "Execution paused." if paused else "Execution resumed."
            detail = "New plan execution is blocked." if paused else "New approved plans can run."
        elif kind == "database.backed_up":
            summary = "Created a verified local recovery backup."
            detail = "The append-only audit chain was checked before recording the backup."
        else:
            summary = cls.display_text(kind.replace("_", " ").replace(".", " · ").capitalize(), 180)
            detail = "Recorded in the immutable local audit ledger."
        return {"id": event["id"], "kind": kind, "created_at": event["created_at"], "summary": summary, "detail": detail}

    @synchronized
    def journal(self, limit: int = 50) -> list[dict[str, Any]]:
        """Readable projection of the immutable audit ledger for people and the UI."""
        return [self.journal_entry(event) for event in self.diary(max(1, min(limit, 100)))]

    @synchronized
    def journal_markdown(self, limit: int = 50) -> str:
        """Export the bounded local journal without exposing raw audit payloads."""
        entries = self.journal(limit)
        lines = ["# dopOS Journal", "", "A local human-readable projection of the append-only audit ledger."]
        if not entries:
            lines += ["", "No journal entries have been recorded yet."]
        for entry in entries:
            lines += ["", f"- **{entry['created_at']}** — {entry['summary']}"]
            if entry["detail"]:
                lines.append(f"  {entry['detail']}")
        return "\n".join(lines) + "\n"

    @synchronized
    def verify_audit_chain(self) -> bool:
        previous = "GENESIS"
        for row in self.db.execute("SELECT kind,payload_json,created_at,previous_hash,event_hash FROM audit_events ORDER BY id"):
            expected = hashlib.sha256(f"{previous}|{row['kind']}|{row['created_at']}|{row['payload_json']}".encode()).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                return False
            previous = row["event_hash"]
        return True

    @synchronized
    def backup_to(self, destination: str | Path) -> dict[str, Any]:
        destination = Path(destination)
        if destination.exists(): raise ValueError("backup destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try: self.db.backup(target)
        finally: target.close()
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        result = {"path": str(destination), "sha256": digest, "audit_chain_valid": self.verify_audit_chain()}
        self.audit("database.backed_up", result)
        return result

    @synchronized
    def create_backup(self) -> dict[str, Any]:
        """Create a unique local SQLite backup in the configured protected state directory."""
        stamp = self.now().replace(":", "").replace("+00:00", "Z")
        path = self.backup_directory / f"dopos-{stamp}-{uuid.uuid4().hex[:8]}.db"
        return self.backup_to(path)

    @synchronized
    def backup_inventory(self, limit: int = 20) -> list[dict[str, Any]]:
        """Read-only local backup inventory; retention and remote copying remain separate controls."""
        if not self.backup_directory.is_dir():
            return []
        files = sorted(self.backup_directory.glob("dopos-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
        return [{"name": path.name, "size": path.stat().st_size, "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()} for path in files[:max(1, min(limit, 100))]]

    @synchronized
    def backups_status(self, limit: int = 20) -> dict[str, Any]:
        """HTTP-facing backup projection with explicit unset retention metadata."""
        backups = self.backup_inventory(limit=limit)
        return {
            "available": True,
            "count": len(backups),
            "backups": backups,
            "retention": self.backup_retention_status(),
            "message": "Local backup inventory is read-only; retention remains unset.",
        }

    @staticmethod
    def _backup_audit_chain(connection: sqlite3.Connection) -> bool:
        previous = "GENESIS"
        try:
            rows = connection.execute("SELECT kind,payload_json,created_at,previous_hash,event_hash FROM audit_events ORDER BY id")
            for row in rows:
                expected = hashlib.sha256(f"{previous}|{row[0]}|{row[2]}|{row[1]}".encode()).hexdigest()
                if row[3] != previous or row[4] != expected:
                    return False
                previous = row[4]
            return True
        except sqlite3.DatabaseError:
            return False

    @synchronized
    def backup_retention_status(self) -> dict[str, Any]:
        """Report that local retention remains unset; never prune or delete backups."""
        return {
            "configured": False,
            "policy": None,
            "prune_enabled": False,
            "message": "Backup retention is not implemented yet; existing local backups are left untouched.",
        }

    @synchronized
    def verify_backups(self, limit: int = 20) -> dict[str, Any]:
        """Read each local backup without modifying it and prove it is structurally usable."""
        if not self.backup_directory.is_dir():
            return {"available": True, "ok": True, "backups": [], "retention": self.backup_retention_status(), "message": "No local backups have been created yet."}
        files = sorted(self.backup_directory.glob("dopos-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)[:max(1, min(limit, 100))]
        checks = []
        for path in files:
            try:
                connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    integrity_ok = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    audit_chain_valid = self._backup_audit_chain(connection)
                finally:
                    connection.close()
                checks.append({"name": path.name, "integrity_ok": integrity_ok, "audit_chain_valid": audit_chain_valid, "ok": integrity_ok and audit_chain_valid})
            except (OSError, sqlite3.DatabaseError) as exc:
                checks.append({"name": path.name, "integrity_ok": False, "audit_chain_valid": False, "ok": False, "error": self.display_text(str(exc), 300)})
        return {"available": True, "ok": all(check["ok"] for check in checks), "backups": checks, "retention": self.backup_retention_status(), "message": "No local backups have been created yet." if not checks else "Backup integrity checks completed locally."}
