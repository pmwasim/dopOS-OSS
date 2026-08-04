"""Small, dependency-free local core with approval-gated safe actions."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import shutil
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_ACTIONS = {"status.summary", "diary.preview", "docker.status", "github.status", "ollama.status"}

def synchronized(method):
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped

class OperationsService:
    def __init__(self, database: str | Path = ":memory:"):
        self._lock = threading.RLock()
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
        if not title.strip() or not request.strip(): raise ValueError("title and request are required")
        now = self.now(); cursor = self.db.execute("INSERT INTO work_items(title,request,state,created_at) VALUES(?,?,?,?)", (title.strip(), request.strip(), "open", now)); self.db.commit()
        item = {"id": cursor.lastrowid, "title": title.strip(), "request": request.strip(), "state": "open", "created_at": now}; self.audit("work_item.created", item); return item

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
                return payload.get("results", [])
        return None

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
            elif action == "diary.preview": results.append({"action": action, "result": self.diary(limit=5)})
            elif action == "docker.status": results.append({"action": action, "result": self.docker_status()})
            elif action == "github.status": results.append({"action": action, "result": self.github_status()})
            elif action == "ollama.status": results.append({"action": action, "result": self.ollama_status()})
            else: raise ValueError("action is not safe")
        self.db.execute("UPDATE plans SET state=? WHERE id=?", ("completed", plan_id))
        self.db.execute("UPDATE work_items SET state=? WHERE id=?", ("completed", row["work_item_id"])); self.db.commit()
        result={"id":plan_id,"state":"completed","results":results}; self.audit("plan.executed", result); return result

    @synchronized
    def status_summary(self) -> dict[str, int]:
        return {"work_items": self.db.execute("SELECT COUNT(*) FROM work_items").fetchone()[0], "plans": self.db.execute("SELECT COUNT(*) FROM plans").fetchone()[0], "audit_events": self.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]}

    @synchronized
    def tool_status(self) -> dict[str, dict[str, Any]]:
        """Read-only availability snapshot for the local control-room header."""
        return {
            "docker": self.docker_status(),
            "github": self.github_status(),
            "ollama": self.ollama_status(),
        }

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
