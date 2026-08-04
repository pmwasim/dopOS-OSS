#!/usr/bin/env python3
"""Controlled local SaaS engineering loop with durable evidence."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT = ("inspect", "plan", "implement", "build", "test", "verify", "package")

def run(command: str, repo: Path) -> dict:
    result = subprocess.run(command, cwd=repo, shell=True, text=True, capture_output=True)
    return {"command": command, "returncode": result.returncode, "stdout": result.stdout[-12000:], "stderr": result.stderr[-12000:]}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--title", default="Autonomous SaaS maintenance cycle")
    parser.add_argument("--phases", nargs="*", default=DEFAULT)
    parser.add_argument("--release", action="store_true", help="Run configured release commands only when explicitly enabled.")
    args = parser.parse_args(); repo = args.repo.resolve()
    config = json.loads((repo / ".companyos/autonomous-loop.json").read_text())
    unknown = set(args.phases) - set(config["phases"])
    if unknown: parser.error(f"unknown phases: {', '.join(sorted(unknown))}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = repo / "workspace/generated/autonomous-loop" / stamp; output.mkdir(parents=True)
    report = {"title": args.title, "started_at": stamp, "phases": [], "result": "passed", "blocked_capabilities": config["blocked_capabilities"], "release": "not-requested"}
    for phase in args.phases:
        entries = [run(command, repo) for command in config["phases"][phase]]
        report["phases"].append({"name": phase, "commands": entries})
        if any(entry["returncode"] for entry in entries):
            report["result"] = "failed"
            report["recovery"] = [run(command, repo) for command in config["phases"]["recover"]]
            break
    if report["result"] == "passed" and args.release:
        release = config.get("release", {})
        if not release.get("enabled"):
            report["result"] = "blocked"
            report["release"] = "blocked: release.enabled is false"
        else:
            entries = [run(command, repo) for command in release.get("commands", [])]
            report["phases"].append({"name": "release", "commands": entries})
            report["release"] = "passed" if all(e["returncode"] == 0 for e in entries) else "failed"
            if report["release"] == "failed": report["result"] = "failed"
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [f"# {args.title}", "", f"Result: **{report['result']}**", "", "## Phases"]
    lines += [f"- {p['name']}: " + ("passed" if all(c['returncode'] == 0 for c in p['commands']) else "failed") for p in report["phases"]]
    if report["result"] == "failed": lines += ["", "## Recovery", "Diagnostics captured; no reset, delete, deployment, or external action was performed."]
    (output / "journal.md").write_text("\n".join(lines) + "\n")
    print(f"Autonomous loop {report['result']}: {output}")
    return 0 if report["result"] == "passed" else 1

if __name__ == "__main__": raise SystemExit(main())
