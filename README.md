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

Its local API exposes `GET /health` (including audit-chain and execution-safety state), `GET /today` (needs-your-decision, active work, activity, and recovery summary), `GET /workspace` (a metadata-only local document inventory), and `GET /workspace?query=<filename-or-path>` (a bounded metadata-only filename/path search), `GET /diary` (raw technical evidence), `GET /journal` (readable operational entries), `GET /journal.md` (offline Markdown export), `POST /work-items`, `POST /plans`, `POST /plans/{id}/approve`, and `POST /plans/{id}/execute`. Requests are deterministically routed only to explicitly allowlisted local actions. Every action is frozen in a plan and requires approval before execution.

The core also verifies its chained audit events and supports an explicit local SQLite backup through `OperationsService.backup_to(...)`. An approved backup request creates a unique database copy in the configured local state directory and records its checksum and audit-chain result. An approved recovery-health request verifies each stored backup's SQLite integrity and audit chain without modifying it. Restore, retention, and off-machine storage are not implemented yet.

## Autonomous engineering loop

`scripts/autonomous_saas_loop.py` runs the repository's declared inspect, build, test, verification, and packaging gates, preserving timestamped JSON evidence and a Markdown journal. It selects a Markdown work item from `workspace/inbox/` when one is present. Use `--dry-run` to inspect the next cycle without executing it.

The loop is local-first and intentionally does not deploy, publish, access secrets, change production, or make destructive Git changes. GitHub Actions runs the same controls on pushes and pull requests and preserves the generated evidence as a short-lived build artifact.

## Local input boundary

The supplied service unit is loopback-only. Its JSON API accepts only bounded request bodies and bounded text work-item fields; malformed or oversized input is rejected before it reaches the local database or planner. Hosted multi-user authentication and authorization are separate future product work, not implied by this offline baseline.
