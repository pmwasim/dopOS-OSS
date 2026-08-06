# dopOS-OSS

An open-source, local-first foundation for dopOS.

`dopOS-OSS` starts clean. It will provide the reusable platform contracts,
local runtime, integration adapters, audit model, and reference user
experience that can run without cloud credentials or a required login screen.
It is designed to support individuals, teams, and organisations across sectors
through modular capabilities rather than separate products.

## What belongs here

- Local-first operational workspace and assistant contracts.
- Approval, audit, diary, recovery, and policy primitives.
- Open-source integration adapters and deployment recipes.
- Document workspace, business modules, schedule/meetings, and automation
  contracts built against open standards.
- Public documentation, tests, examples, and community contribution paths.

## What does not belong here

- Existing proprietary dopOS source, credentials, machine configuration, audit
  databases, private customer material, or private deployment history.
- Closed-source product features intended for `pmwasim/dopOS-CSS`.

## Current phase

Planning and public foundation. No legacy source has been copied into this
repository. Start with the [vision](docs/VISION.md), [mission](docs/MISSION.md),
[PRD](docs/PRD.md), [architecture](docs/ARCHITECTURE.md), and
[roadmap](docs/ROADMAP.md).

## Licensing

This repository is licensed under [Apache-2.0](LICENSE). The Apache licence
does not grant rights to dopOS names, marks, or any proprietary dopOS-CSS
material. See [the licence decision](docs/LICENSE-DECISION.md) and
[NOTICE](NOTICE) for the public-project baseline.
# dopOS-OSS

## Local core quick start

The first public implementation slice is a local, dependency-free operations core: work item → plan → explicit approval → safe execution → chained audit and Diary events.

```sh
PYTHONPATH=src python3 -m dopos_core.server --database dopos.db
```

Its local API exposes `GET /health` (including audit-chain, execution-safety, workspace configuration, local backup count, and unset backup-retention state), `GET /today` (needs-your-decision, active work, activity, recovery, workspace counts, execution-safety, and queue summary), `GET /autonomous-loop` (bounded, read-only loop-evidence summaries), `GET /autonomous-loop/queue` (ordered, metadata-only Markdown work-item candidates), `GET /workspace` (a metadata-only local document and folder inventory with a catalog revision, extension counts sorted by frequency, plus `total_bytes`, `unsupported_skipped`, `truncated`, and `listing_limit` as the effective page size), and `GET /workspace?query=<filename-or-path>` (a bounded metadata-only filename/path search), `GET /tools/status` (Docker, GitHub, CI, and local AI availability), `GET /backups` (local inventory with unset retention metadata), `GET /diary` (raw technical evidence), `GET /journal` (readable operational entries), `GET /journal.md` (offline Markdown export), `POST /work-items`, `POST /plans`, `POST /plans/{id}/approve`, and `POST /plans/{id}/execute`. An approved Workspace snapshot records only the document catalog revision and count in the immutable plan evidence; it does not read or copy document contents. An approved CI-status request reads at most five GitHub Actions run summaries; it does not dispatch, rerun, cancel, or change a workflow. An approved loop-status request returns bounded autonomous-loop evidence summaries only; it does not re-run the loop or expose command output. An approved queue-status request lists Markdown work-item titles and paths only; it does not read work-item bodies. An approved `backup.retention` request reports that prune/retention remain unset and never deletes backups. An approved `health.status` request returns the same read-only runtime health projection as `GET /health`. An approved `tools.status` request returns the aggregated local tool availability snapshot. An approved `control.status` request reports kill-switch state without changing it. Requests are deterministically routed only to explicitly allowlisted local actions. Every action is frozen in a plan and requires approval before execution.

The core also verifies its chained audit events and supports an explicit local SQLite backup through `OperationsService.backup_to(...)`. An approved backup request creates a unique database copy in the configured local state directory and records its checksum and audit-chain result. An approved recovery-health request verifies each stored backup's SQLite integrity and audit chain without modifying it. `GET /backups` returns the local inventory plus an explicit unset retention projection. `OperationsService.restore_from(...)` replaces the live database from a local backup, but only after proving the source is readable, passes its SQLite integrity check, and has an intact audit chain; the state being replaced is copied aside first, so a restore is itself recoverable. Restore is deliberately not an allowlisted action: it is the only destructive operation in the core and cannot be reached through a plan. Off-machine storage is not implemented yet; backup retention remains unset and never prunes. `GET /health` and Today recovery both report retention as unset and never prune backups. The local document workspace starts as an empty `workspace/documents` scaffold so inventory and search are configured without shipping document contents. Hidden scaffold paths (names starting with `.`) are omitted from inventory counts.

## Multi-step workflows

A plan is an ordered list of steps rather than a flat list of actions. A step may be a bare action name, or an object naming an `action`, an optional `id`, and `requires` — the ids of earlier steps that must have succeeded first:

```json
["github.status", {"action": "ci.status", "requires": ["github.status"]}]
```

A step whose requirement did not succeed is recorded as `skipped` with the reason, and nothing is run for it; independent later steps still run. Success is read from the frozen result — a step counts as failed when its own result reports `available: false` or `ok: false` — so the same evidence always produces the same continuation.

Requirements may only name earlier steps, so a workflow is acyclic by construction. Every action is still checked against the allowlist when the plan is proposed, a workflow can never widen what a plan may do, and the whole graph is frozen at approval. The deterministic router applies one fixed dependency of its own: a CI check requires the repository check, because both come from the same GitHub CLI. Plans written as a plain list of action names behave exactly as before.

`OperationsService` accepts its backup, workspace, loop-evidence, and inbox directories as optional keyword arguments. An explicit argument wins, then the matching `DOPOS_*_DIR` environment variable, then the repository default, so existing single-instance deployments are unaffected. Passing directories explicitly lets one process hold several independent services without them sharing state through a single process-wide variable.

## Autonomous engineering loop

`scripts/autonomous_saas_loop.py` runs the repository's declared inspect, build, test, verification, and packaging gates, preserving timestamped JSON evidence and a Markdown journal. It selects a Markdown work item from `workspace/inbox/` when one is present. Use `--dry-run` to inspect the next cycle without executing it.

The loop is local-first and intentionally does not deploy, publish, access secrets, change production, or make destructive Git changes. GitHub Actions runs the same controls on pushes and pull requests and preserves the generated evidence as a short-lived build artifact.

## Local input boundary

The supplied service unit is loopback-only. Its JSON API accepts only bounded request bodies and bounded text work-item fields; malformed or oversized input is rejected before it reaches the local database or planner. Hosted multi-user authentication and authorization are separate future product work, not implied by this offline baseline.
