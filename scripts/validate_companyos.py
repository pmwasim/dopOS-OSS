#!/usr/bin/env python3
"""Dependency-free validation for the CompanyOS governed documentation tree."""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

REQUIRED = {"title", "document_id", "document_type", "status", "version", "owner_role", "approver_role", "author", "created", "updated", "effective_date", "next_review_date", "review_cycle", "authoritative", "confidentiality", "jurisdiction", "applies_to", "supersedes", "superseded_by", "related_documents", "tags"}
STATUSES = {"draft", "review", "approved", "superseded", "archived", "retired"}
TYPES = {"policy", "standard", "framework", "process", "procedure", "work_instruction", "checklist", "template", "register", "report", "charter", "guidance", "decision_record", "runbook"}

def parse(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"): return {}, text
    end = text.find("\n---\n", 4)
    if end < 0: return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1); meta[k.strip()] = v.strip()
    return meta, text[end+5:]

def validate(repo: Path):
    errors=[]; warnings=[]; ids={}; titles={}; governed=[]
    for path in sorted((repo / "docs").rglob("*.md")):
        rel=path.relative_to(repo)
        if path.name in {"README.md", "index.md"}: continue
        meta, body=parse(path); governed.append((path,meta,body))
        missing=REQUIRED-set(meta)
        if missing: errors.append(f"{rel}: missing metadata {', '.join(sorted(missing))}"); continue
        ident=meta["document_id"]
        if ident in ids: errors.append(f"duplicate document_id {ident}: {ids[ident]} and {rel}")
        ids[ident]=str(rel)
        if meta["status"] not in STATUSES: errors.append(f"{rel}: invalid status {meta['status']}")
        if meta["document_type"] not in TYPES: errors.append(f"{rel}: invalid document type {meta['document_type']}")
        if meta["title"] in titles: warnings.append(f"duplicate title {meta['title']}: {titles[meta['title']]} and {rel}")
        titles[meta["title"]]=str(rel)
        for key in ("created", "updated", "next_review_date"):
            try: date.fromisoformat(meta[key])
            except ValueError: errors.append(f"{rel}: invalid {key}")
        if meta["status"] == "approved" and re.search(r"\[[A-Z_]+(?:_REQUIRED)?\]", body): errors.append(f"{rel}: approved document contains unresolved placeholder")
        if meta["document_type"] == "register" and "## Fields" not in body: errors.append(f"{rel}: malformed register; missing Fields")
        for href in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", body):
            if href.startswith(("http:", "https:", "mailto:")): continue
            target=(path.parent / href).resolve()
            if not target.exists(): errors.append(f"{rel}: broken relative link {href}")
    index=(repo / "docs/index.md").read_text(encoding="utf-8")
    for d in sorted(p for p in (repo / "docs").iterdir() if p.is_dir() and p.name not in {"99-archive"}):
        if d.name not in index: errors.append(f"docs/index.md: missing domain index entry {d.name}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "documents_checked": len(governed)}

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--repo", type=Path, default=Path.cwd()); p.add_argument("--json", action="store_true"); a=p.parse_args(); r=validate(a.repo.resolve()); print(json.dumps(r, indent=2) if a.json else f"CompanyOS: {'PASS' if r['ok'] else 'FAIL'}; {r['documents_checked']} governed documents; {len(r['errors'])} errors; {len(r['warnings'])} warnings" + ("\n"+"\n".join(r['errors']) if r['errors'] else "")); raise SystemExit(0 if r['ok'] else 1)
