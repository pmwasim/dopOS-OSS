#!/usr/bin/env python3
"""Run a controlled, evidence-producing local SaaS engineering cycle.

The runner is deliberately local-first: it can select queued work, run the
repository's declared quality gates, and preserve failure evidence.  It does
not guess deployment commands, mutate infrastructure, commit, push, or publish
unless a repository owner explicitly enables and configures that capability.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any


DEFAULT = ("inspect", "plan", "implement", "build", "test", "verify", "package")
MAX_OUTPUT = 12_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def bounded(value: str) -> str:
    return value[-MAX_OUTPUT:]


def command_label(command: list[str]) -> str:
    return " ".join(command)


def run(command: list[str], repo: Path) -> dict[str, Any]:
    started = monotonic()
    result = subprocess.run(command, cwd=repo, text=True, capture_output=True)
    return {
        "command": command_label(command),
        "returncode": result.returncode,
        "stdout": bounded(result.stdout),
        "stderr": bounded(result.stderr),
        "duration_seconds": round(monotonic() - started, 3),
    }


def load_config(repo: Path) -> dict[str, Any]:
    config_path = repo / ".companyos" / "autonomous-loop.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load {config_path}: {exc}") from exc
    if not isinstance(config.get("phases"), dict) or not isinstance(config.get("blocked_capabilities"), list):
        raise ValueError("Loop config requires phases and blocked_capabilities.")
    for name, commands in config["phases"].items():
        if not isinstance(commands, list):
            raise ValueError(f"Phase {name!r} must be a command list.")
        for command in commands:
            if not isinstance(command, list) or not command or not all(isinstance(argument, str) and argument for argument in command):
                raise ValueError(f"Phase {name!r} commands must be non-empty argument lists; shell strings are not supported.")
    release = config.get("release", {})
    if release and not isinstance(release, dict):
        raise ValueError("Release config must be an object.")
    release_commands = release.get("commands", [])
    if not isinstance(release_commands, list):
        raise ValueError("Release commands must be a command list.")
    for command in release_commands:
        if not isinstance(command, list) or not command or not all(isinstance(argument, str) and argument for argument in command):
            raise ValueError("Release commands must be non-empty argument lists; shell strings are not supported.")
    if "recover" not in config["phases"]:
        raise ValueError("Loop config requires a recover phase.")
    return config


def select_work_item(repo: Path, explicit: str | None) -> dict[str, str] | None:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = repo / path
        if not path.is_file():
            raise ValueError(f"Work item not found: {path}")
        return {"path": str(path.relative_to(repo)), "title": path.stem.replace("-", " ")}
    inbox = repo / "workspace" / "inbox"
    candidates = sorted(path for path in inbox.glob("*.md") if path.name != ".gitkeep")
    if not candidates:
        return None
    item = candidates[0]
    for line in item.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return {"path": str(item.relative_to(repo)), "title": line[2:].strip()}
    return {"path": str(item.relative_to(repo)), "title": item.stem.replace("-", " ")}


def phase_result(name: str, commands: list[list[str]], repo: Path) -> dict[str, Any]:
    entries = [run(command, repo) for command in commands]
    return {
        "name": name,
        "commands": entries,
        "result": "passed" if all(entry["returncode"] == 0 for entry in entries) else "failed",
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [f"# {report['title']}", "", f"Result: **{report['result']}**", "", f"Started: {report['started_at']}"]
    if report.get("work_item"):
        item = report["work_item"]
        lines += ["", "## Work item", f"- {item['title']} (`{item['path']}`)"]
    lines += ["", "## Phases"]
    lines += [f"- {phase['name']}: {phase['result']}" for phase in report["phases"]]
    if report["result"] == "failed":
        lines += ["", "## Recovery", "Diagnostics were captured. No reset, deletion, deployment, publication, or external action was performed."]
    if report["release"] != "not-requested":
        lines += ["", "## Release", report["release"]]
    lines += ["", "## Guardrails", "Blocked by default: " + ", ".join(report["blocked_capabilities"]) + "."]
    return "\n".join(lines) + "\n"


def repair_brief(report: dict[str, Any]) -> str:
    """Produce a handoff for a future repair cycle without changing source."""
    failed = next((phase for phase in report["phases"] if phase["result"] == "failed"), None)
    commands = failed["commands"] if failed else []
    summaries = [entry["command"] for entry in commands if entry.get("returncode")]
    lines = ["# Repair work item", "", "status: draft", "source: autonomous-loop evidence", "", "## Goal"]
    lines.append(f"Repair the failed {failed['name'] if failed else 'unknown'} phase without bypassing its gate.")
    lines += ["", "## Evidence", "- `report.json` in this same evidence directory."]
    if summaries:
        lines += ["- Failed command(s):"] + [f"  - `{command}`" for command in summaries]
    lines += ["", "## Constraints", "- Preserve the working tree and audit evidence.", "- Do not reset, delete, deploy, publish, or weaken tests to restore a pass.", "- Re-run the complete autonomous cycle after repair."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--title", default="Autonomous SaaS engineering cycle")
    parser.add_argument("--work-item", help="Markdown work item relative to the repository or absolute path.")
    parser.add_argument("--phases", nargs="*", default=DEFAULT)
    parser.add_argument("--release", action="store_true", help="Run configured release commands only when explicitly enabled.")
    parser.add_argument("--dry-run", action="store_true", help="Validate the selected workflow without running commands.")
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        config = load_config(repo)
        unknown = set(args.phases) - set(config["phases"])
        if unknown:
            raise ValueError(f"Unknown phases: {', '.join(sorted(unknown))}")
        work_item = select_work_item(repo, args.work_item)
    except ValueError as exc:
        parser.error(str(exc))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = repo / "workspace" / "generated" / "autonomous-loop" / stamp
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "schema_version": 2,
        "title": args.title,
        "started_at": utc_now(),
        "repository": str(repo),
        "work_item": work_item,
        "phases": [],
        "result": "passed",
        "blocked_capabilities": config["blocked_capabilities"],
        "release": "not-requested",
        "dry_run": args.dry_run,
    }
    for phase in args.phases:
        if args.dry_run:
            result = {"name": phase, "commands": [{"command": command_label(command), "dry_run": True} for command in config["phases"][phase]], "result": "planned"}
        else:
            result = phase_result(phase, config["phases"][phase], repo)
        report["phases"].append(result)
        if result["result"] == "failed":
            report["result"] = "failed"
            report["recovery"] = phase_result("recover", config["phases"]["recover"], repo)
            break
    if report["result"] == "passed" and args.release:
        release = config.get("release", {})
        if not release.get("enabled"):
            report["result"] = "blocked"
            report["release"] = "blocked: release.enabled is false"
        elif args.dry_run:
            report["release"] = "planned"
        else:
            release_result = phase_result("release", release.get("commands", []), repo)
            report["phases"].append(release_result)
            report["release"] = release_result["result"]
            if release_result["result"] == "failed":
                report["result"] = "failed"
    report["completed_at"] = utc_now()
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "journal.md").write_text(markdown_report(report), encoding="utf-8")
    if report["result"] == "failed":
        (output / "repair-work-item.md").write_text(repair_brief(report), encoding="utf-8")
    print(f"Autonomous loop {report['result']}: {output}")
    return 0 if report["result"] in {"passed", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
