# Implementation plan

## Phase 0 — public foundation

1. Select licence and contribution governance.
2. Publish architecture decisions, threat model, supported environments, and
   release policy.
3. Establish a clean reproducible local developer environment and CI.

## Phase 1 — trustworthy local core

1. Local runtime and durable database.
2. Work item, plan, approval, execution, audit, and diary contracts.
3. Tokenless local operator session, with no secret rendered to the browser.
4. Policy engine and kill switch; fixed privileged operations only.
5. Reference UI: Today, conversation, approval, Live Work, and Diary.

## Phase 2 — information workspace

1. Local document catalogue, folders, metadata, full-text indexing, versioning,
   retention, and export/import boundaries.
2. Open-source document/editor adapters: Nextcloud-compatible storage,
   OnlyOffice/Collabora, LibreOffice, PDF.js, and calculator.
3. File-level permissions and audited sharing contract for the later team mode.

## Phase 3 — business modules

1. ERP/CRM adapter contract and read-only health/status adapters.
2. Calendar, scheduling, and Jitsi meeting adapters.
3. Work, automation, reporting, and reliability adapters.
4. Each connector follows: configure → verify → scope → approve → execute →
   audit; never assume it is connected.

## Phase 4 — scale and release

1. Personal, team, organisation, and enterprise policy profiles.
2. Backup, recovery, upgrade, and portability evidence.
3. Accessibility, security, performance, and end-to-end validation.
4. Public OSS release; only then define separate CSS extension boundaries.
