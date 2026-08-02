# Repository and migration boundaries

| Repository | Purpose | Current rule |
| --- | --- | --- |
| `pmwasim/dopOS` | Existing private implementation and historical Ubuntu deployment | Preserve as-is; do not migrate its source, data, secrets, or history into OSS. |
| `pmwasim/dopOS-OSS` | New public open-source foundation | Start clean with independently designed code, public documentation, tests, and licence. |
| `pmwasim/dopOS-CSS` | Future private commercial software | Start after OSS contracts are stable; keep proprietary modules separate. |

## Non-negotiable separation

- Never publish old deployment `.env` files, tokens, audit databases, backups,
  RDP configuration, customer data, or SSH material.
- Do not copy legacy source into OSS without a deliberate origin, licence,
  security, and secret-history review.
- Use a separate Ubuntu workspace, service name, data directory, and port for
  OSS development. The legacy private service remains untouched until a
  separately verified cutover plan exists.
