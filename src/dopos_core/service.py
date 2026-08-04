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

SAFE_ACTIONS = {"status.summary", "diary.preview", "docker.status", "github.status", "ollama.status", "quality.status", "backup.create", "backup.verify"}
MAX_WORK_ITEM_TITLE = 160
MAX_WORK_ITEM_REQUEST = 8_000

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
        if "ollama" in request or "model" in request or "ai runtime" in request: actions.append("ollama.status")
        if any(word in request for word in ("test", "build", "ci", "validate", "quality")): actions.append("quality.status")
        if any(term in request for term in ("recovery", "integrity", "verify backup", "backup health")):
            actions.append("backup.verify")
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
        return {"kill_switch": row["value"], "updated_at": row["updated_at"]}

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
            elif action == "ollama.status": results.append({"action": action, "result": self.ollama_status()})
            elif action == "quality.status": results.append({"action": action, "result": self.quality_status()})
            elif action == "backup.create": results.append({"action": action, "result": self.create_backup()})
            elif action == "backup.verify": results.append({"action": action, "result": self.verify_backups()})
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
        return {
            "status": "ok" if audit_chain_valid else "degraded",
            "core": "dopos",
            "audit_chain_valid": audit_chain_valid,
            "execution_paused": self.kill_switch_enabled(),
            "records": summary,
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
        return {
            "generated_at": self.now(),
            "needs_decision": [entry for entry in entries if entry["state"] == "awaiting_approval"],
            "in_motion": [entry for entry in entries if entry["state"] == "approved"],
            "recent_activity": self.journal(limit=5),
            "recovery": {
                "audit_chain_valid": self.verify_audit_chain(),
                "backup_count": len(self.backup_inventory(limit=100)),
                "latest_backup": backups[0] if backups else None,
            },
        }

    @synchronized
    def tool_status(self) -> dict[str, dict[str, Any]]:
        """Read-only availability snapshot for the local control-room header."""
        return {
            "docker": self.docker_status(),
            "github": self.github_status(),
            "ollama": self.ollama_status(),
        }

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
    def verify_backups(self, limit: int = 20) -> dict[str, Any]:
        """Read each local backup without modifying it and prove it is structurally usable."""
        if not self.backup_directory.is_dir():
            return {"available": True, "ok": True, "backups": [], "message": "No local backups have been created yet."}
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
        return {"available": True, "ok": all(check["ok"] for check in checks), "backups": checks, "message": "No local backups have been created yet." if not checks else "Backup integrity checks completed locally."}
