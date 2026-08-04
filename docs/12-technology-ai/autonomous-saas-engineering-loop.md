---
title: Autonomous SaaS Engineering Loop
document_id: CO-12-AUTONOMOUS-SAAS-ENGINEERING-LOOP
document_type: process
status: draft
version: 0.2.0
owner_role: [OWNER_ROLE]
approver_role: [OWNER_DECISION_REQUIRED]
author: CompanyOS bootstrap
created: 2026-08-04
updated: 2026-08-04
effective_date: null
next_review_date: 2027-08-04
review_cycle: annual
authoritative: false
confidentiality: internal
jurisdiction: [JURISDICTION_DECISION_REQUIRED]
applies_to: [COMPANY_SCOPE_DECISION_REQUIRED]
supersedes: null
superseded_by: null
related_documents: []
tags: [companyos, saas, autonomous-engineering]
---

# Autonomous SaaS Engineering Loop

## Purpose

Provide a repeatable local loop for building, debugging, enhancing, repairing, and recovering a SaaS codebase while producing evidence for every cycle.

## Lifecycle

`inspect → select work item → plan → implement → build → test → verify → package → record → repeat`.

On any failed build, test, or verification step, the loop enters `recover`: it preserves the working tree, captures diagnostics, runs only configured recovery checks, records the blocker, and exits non-zero. It never deletes work, resets Git, publishes a release, changes production, sends external messages, or installs packages unless a separately approved tool explicitly performs that action.

## Operating model

The repository-controlled `.companyos/autonomous-loop.json` specifies local commands. `scripts/autonomous_saas_loop.py` selects the oldest Markdown work item in `workspace/inbox/` (or accepts `--work-item`), runs the selected phases, creates timestamped schema-versioned JSON evidence under `workspace/generated/autonomous-loop/`, and writes a concise Markdown journal. An operator or permitted agent can then use the evidence to continue work safely.

The runner supports `--dry-run` for workflow review without execution. Empty `plan`, `implement`, and `package` phases are deliberate: the project owner must supply project-specific commands or an approved agent adapter, rather than having generic automation guess code changes or production actions.

## Autonomous work-item rules

An agent may inspect, plan, edit within the declared repository boundary, build, test, verify, and repeat. It must not silently turn a failed check into a pass, delete work to restore green status, or treat a test failure as an instruction to release. A failing cycle records evidence, runs read-only recovery diagnostics, and becomes a repair work item.

## CI/CD and release boundary

Continuous integration runs the safe phases on every push and pull request. Continuous delivery is not enabled by default. Release commands require all of: an approved change, clean validation evidence, a reviewed release plan, a rollback plan, `release.enabled: true` in the repository-controlled config, and an explicit `--release` invocation. This prevents generic automation from publishing, deploying, or changing production merely because checks passed.

The loop produces delivery-readiness evidence, not an implied deployment. A later environment-specific delivery adapter may be added only after its target, credentials, rollback, health check, and owner are documented.

## Required controls

- Preserve uncommitted work; capture `git status` before and after every cycle.
- Use the smallest work item from `workspace/inbox/` or an explicit supplied title.
- Treat failing checks as evidence, not permission to bypass them.
- Keep all network, deployment, production, secret, payment, customer-data, and destructive steps out of the default loop.
- Require policy approval before adding mutation or release adapters.

## Recovery

Recovery runs configured read-only diagnostics, records failure output and an unresolved gap, and leaves the repository intact for repair. A successful cycle may be committed through normal Git governance; this runner never commits or pushes on its own.

## Evidence

Every run records the selected work item, commands, exit status, bounded output, execution time, blocked capabilities, release state, and recovery status. Evidence is local by default and must be reviewed before it is used as release evidence.
