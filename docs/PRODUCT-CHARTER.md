---
title: Product Charter
document_id: DOPOS-LEGACY-PRODUCT-CHARTER
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

# Product charter

## Purpose

dopOS-OSS is a local-first operational software foundation. It gives a person
or organisation one clear place to understand work, create and review plans,
run approved operations, manage information, and retain a truthful journal.

## Primary experience

One local assistant is the user-facing interface. It accepts natural language,
explains what it knows, proposes scoped operations, waits for approval where
required, and records outcomes. Specialist tools and agents work behind this
interface and never require the operator to manage secrets or terminals.

## Built-in capability families

| Family | Open-source-first baseline |
| --- | --- |
| Documents and files | Nextcloud-compatible storage, OnlyOffice/Collabora, LibreOffice, PDF.js, local calculator |
| ERP and CRM | ERPNext/Frappe and EspoCRM adapters |
| Calendar and meetings | CalDAV/Nextcloud Calendar and Jitsi Meet adapters |
| Work and automation | Plane/OpenProject/Vikunja and n8n/Node-RED adapters |
| Reporting and reliability | Metabase, Grafana, Prometheus, Uptime Kuma, Restic |

An adapter is not "connected" merely because the underlying tool is installed.
It must expose a verified health state, explicit scope, permissions, and audit
policy first.

## Product scales

The core interface remains familiar from personal use through team,
organisation, and enterprise use. Added scale introduces optional roles,
policies, isolation, and deployment topology—not a different product.

## First release boundaries

- Standalone and offline-first with local data and no mandatory sign-in.
- Optional integrations; no hidden cloud dependency or fake connection state.
- No unrestricted arbitrary shell or root access for model output.
- Privileged operations must remain fixed, policy-controlled, approval-gated,
  time-bounded, and audited.

## Later commercial edition

`pmwasim/dopOS-CSS` may contain closed-source proprietary features. It must
consume stable OSS contracts and must not turn public contributions into an
unreviewed proprietary dependency.
