---
title: OSS Local Service Runbook
document_id: DOPOS-OSS-LOCAL-SERVICE-RUNBOOK
document_type: runbook
status: draft
version: 0.1.0
owner_role: [OWNER_ROLE]
approver_role: [OWNER_DECISION_REQUIRED]
author: dopOS engineering
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
related_documents: [DOPOS-OSS-LOCAL-SERVICE-RUNBOOK]
tags: [dopos, local-service, recovery]
---

# OSS Local Service Runbook

## Purpose

Operate the dependency-free local core on Ubuntu without exposing it to the network.

## Installation

Install `deploy/systemd/dopos-oss.service`, reload systemd, enable the service, and verify `http://127.0.0.1:18000/health` from the host. The unit runs as `wasim`, uses the systemd-managed dedicated state path `/var/lib/dopos-oss`, binds only to loopback, and restarts on failure.

## Recovery

If the service is unhealthy: capture `systemctl status` and `journalctl -u dopos-oss`, run the autonomous loop, verify the audit chain from a backup copy, and only then restart. Do not delete the state database to obtain a green service.

## Security boundary

This is a standalone local operator service. No remote listener, user login, tenant boundary, cloud deployment, or production-release claim is created by this runbook.
