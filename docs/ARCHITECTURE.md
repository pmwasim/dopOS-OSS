---
title: Architecture
document_id: DOPOS-LEGACY-ARCHITECTURE
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

# Architecture

## Layers

1. **Web experience:** Home, Work, Workspace, Business, Schedule, Journal,
   and Settings share a persistent assistant and a consistent navigation model.
2. **Application core:** work items, plans, approvals, policies, identities,
   organisations, audit events, diary projection, and notifications.
3. **Adapter layer:** independently testable connectors for documents, ERP/CRM,
   calendar/meetings, automation, reporting, reliability, and host operations.
4. **Runtime layer:** local database, encrypted secret store, background jobs,
   backup/recovery, observability, and deployment manifests.

## SaaS readiness

The OSS core supports self-hosting first. Hosted web SaaS requires explicit
organisation tenancy, membership, active-organisation selection, roles,
per-tenant data isolation, rate limits, audit partitioning, backup policy, and
operational support. These are future release gates, not assumptions.

## Public/private product boundary

OSS owns reusable contracts and reference implementations. `dopOS-CSS` may
ship private UX, desktop packaging, enterprise deployment, and commercial
capabilities through these contracts. Neither edition may depend on private
credentials or unpublished data formats.
