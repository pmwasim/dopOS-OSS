---
title: Prd
document_id: DOPOS-LEGACY-PRD
document_type: guidance
status: draft
version: 0.1.0
owner_role: [OWNER_ROLE]
approver_role: [OWNER_DECISION_REQUIRED]
author: CompanyOS bootstrap
created: 2026-08-02
updated: 2026-08-02
effective_date: null
next_review_date: 2027-08-02
review_cycle: annual
authoritative: false
confidentiality: internal
jurisdiction: [JURISDICTION_DECISION_REQUIRED]
applies_to: [COMPANY_SCOPE_DECISION_REQUIRED]
supersedes: null
superseded_by: null
related_documents: []
tags: [companyos, legacy]
---

# Product requirements: dopOS-OSS

## Product

`dopOS-OSS` is a public, open-source, local-first web platform. It can be
self-hosted as a single-person workspace or deployed as a web SaaS foundation
for organisations. It does not require a cloud account for its core workflow.

## Users and scale

The same product supports freelancers, founders, small businesses, growing
teams, large organisations, enterprise deployments, and any sector. The core
experience stays stable while role, policy, isolation, and deployment features
are added as needed.

## Core user journey

`Ask → Understand → Decide → Do → Review → Remember`

1. The operator asks the local assistant for help through web chat or voice.
2. The system returns a grounded answer or a scoped proposed operation.
3. The operator approves, refines, or declines material changes.
4. Approved work runs through a policy-controlled adapter.
5. Results, artifacts, and explanations remain inspectable.
6. An audit-derived diary retains the operational memory.

## Required web modules

| Module | First-release requirement |
| --- | --- |
| Home / Today | Current date/time, needs-your-decision, in-motion work, upcoming work, activity, and persistent assistant. |
| Work | Frozen plans, approvals, Live Work, results, stop controls, and audit links. |
| Workspace | Folders, metadata, search, document versions, document/spreadsheet/presentation/PDF/calculator entry points. |
| Business | Adapter boundary for CRM, quotations/orders, inventory, finance, and ERP workflows. |
| Schedule & meetings | Calendar, tasks/reminders, and meeting lifecycle. |
| Journal | Readable daily journal derived from append-only audit data. |
| Settings | Local deployment, backup/recovery, policy, integration, and future hosted deployment configuration. |

## Open-source-first integration policy

- Documents: Nextcloud-compatible storage, OnlyOffice/Collabora, LibreOffice,
  PDF.js, and a local calculator.
- ERP/CRM: ERPNext/Frappe and EspoCRM.
- Calendar/meetings: CalDAV/Nextcloud Calendar and Jitsi Meet.
- Work/automation: Plane, OpenProject, Vikunja, n8n, and Node-RED.
- Reporting/reliability: Metabase, Grafana, Prometheus, Uptime Kuma, and
  Restic.

Every connector must show `not connected`, `configured`, `healthy`, or
`degraded` from observed state. Installed software is not enough to claim
access.

## Non-functional requirements

- Web-first, responsive desktop browser experience; mobile native clients are
  explicitly not in the current scope.
- Local data and private-network operation are supported.
- Strong tenant/role boundaries are required before any hosted multi-business
  deployment claims.
- Secrets never render in the browser; actions are scoped, time-bounded, and
  audited.
- Root/sudo capability is limited to policy-defined, approval-gated commands;
  model output never receives unrestricted root shell access.
