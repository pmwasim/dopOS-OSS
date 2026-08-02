# Ubuntu reset runbook for dopOS-OSS

## Objective

Create a clean, separate OSS development environment without deleting the
private `dopOS` deployment or its data.

## Safe steps

1. Verify the existing private checkout is `/home/wasim/dopos` and its origin
   remains `pmwasim/dopOS`.
2. Create `/home/wasim/dopos-oss` from `pmwasim/dopOS-OSS`; do not copy files
   from `/home/wasim/dopos`.
3. Use new names for all state: `dopos-oss.service`, `/etc/dopos-oss.env`,
   `/home/wasim/dopos-oss/data`, and a distinct loopback port.
4. Add a fresh Python/runtime environment and run only OSS tests in that
   checkout.
5. Before any old-service shutdown, capture a private backup and verify the
   new service independently.

## Not authorised by this runbook

- Deleting `/home/wasim/dopos`, `/etc/dopos.env`, legacy backups, or the
  existing `dopos.service`.
- Publishing any legacy source or data.
- Treating a fresh OSS checkout as a production replacement before it passes
  its own acceptance and recovery checks.
