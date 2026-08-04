"""Small, dependency-free local core with approval-gated safe actions."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_ACTIONS = {"status.summary", "diary.preview"}

class OperationsService:
    def __init__(self, database: str | Path = ":memory:"):
        self.db = sqlite3.connect(database)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS work_items (id INTEGER PRIMARY KEY, title TEXT NOT NULL, request TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, work_item_id INTEGER NOT NULL REFERENCES work_items(id), actions_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT);
        CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE);
        CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
        """)

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def audit(self, kind: str, payload: dict[str, Any]) -> int:
        previous = self.db.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        previous_hash = previous[0] if previous else "GENESIS"
        created_at = self.now(); encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        event_hash = hashlib.sha256(f"{previous_hash}|{kind}|{created_at}|{encoded}".encode()).hexdigest()
        cursor = self.db.execute("INSERT INTO audit_events(kind,payload_json,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?)", (kind, encoded, created_at, previous_hash, event_hash))
        self.db.commit(); return cursor.lastrowid

    def create_work_item(self, title: str, request: str) -> dict[str, Any]:
        if not title.strip() or not request.strip(): raise ValueError("title and request are required")
        now = self.now(); cursor = self.db.execute("INSERT INTO work_items(title,request,state,created_at) VALUES(?,?,?,?)", (title.strip(), request.strip(), "open", now)); self.db.commit()
        item = {"id": cursor.lastrowid, "title": title.strip(), "request": request.strip(), "state": "open", "created_at": now}; self.audit("work_item.created", item); return item

    def propose_plan(self, work_item_id: int, actions: list[str]) -> dict[str, Any]:
        if not actions or any(action not in SAFE_ACTIONS for action in actions): raise ValueError("plan contains unsupported action")
        if not self.db.execute("SELECT 1 FROM work_items WHERE id=?", (work_item_id,)).fetchone(): raise ValueError("work item not found")
        now=self.now(); cursor=self.db.execute("INSERT INTO plans(work_item_id,actions_json,state,created_at) VALUES(?,?,?,?)", (work_item_id, json.dumps(actions), "awaiting_approval", now)); self.db.commit()
        plan={"id":cursor.lastrowid,"work_item_id":work_item_id,"actions":actions,"state":"awaiting_approval","created_at":now}; self.audit("plan.proposed", plan); return plan

    def approve_plan(self, plan_id: int) -> dict[str, Any]:
        row=self.db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row: raise ValueError("plan not found")
        if row["state"] != "awaiting_approval": raise ValueError("plan is not awaiting approval")
        approved_at=self.now(); self.db.execute("UPDATE plans SET state=?, approved_at=? WHERE id=?", ("approved", approved_at, plan_id)); self.db.commit()
        result={"id":plan_id,"state":"approved","approved_at":approved_at}; self.audit("plan.approved", result); return result

    def execute_plan(self, plan_id: int) -> dict[str, Any]:
        row=self.db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row: raise ValueError("plan not found")
        if row["state"] != "approved": raise ValueError("plan requires approval")
        actions=json.loads(row["actions_json"]); results=[]
        for action in actions:
            if action == "status.summary": results.append({"action": action, "result": self.status_summary()})
            elif action == "diary.preview": results.append({"action": action, "result": self.diary(limit=5)})
            else: raise ValueError("action is not safe")
        self.db.execute("UPDATE plans SET state=? WHERE id=?", ("completed", plan_id)); self.db.commit()
        result={"id":plan_id,"state":"completed","results":results}; self.audit("plan.executed", result); return result

    def status_summary(self) -> dict[str, int]:
        return {"work_items": self.db.execute("SELECT COUNT(*) FROM work_items").fetchone()[0], "plans": self.db.execute("SELECT COUNT(*) FROM plans").fetchone()[0], "audit_events": self.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]}

    def diary(self, limit: int = 25) -> list[dict[str, Any]]:
        rows=self.db.execute("SELECT id,kind,payload_json,created_at,event_hash FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id":r["id"],"kind":r["kind"],"payload":json.loads(r["payload_json"]),"created_at":r["created_at"],"event_hash":r["event_hash"]} for r in reversed(rows)]
