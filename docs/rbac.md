# OpenXFlow production RBAC

OpenXFlow ships a built-in database-backed authorization service. It evaluates
role assignments, inherited roles, user/team/public shares, resource ownership
and channel-scoped permissions. No external authorization plugin is required.

## Enable enforcement

Production deployments should use multi-user authentication and enable both
enforcement and audit logging:

```env
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_AUTHZ_ENABLED=true
LANGFLOW_AUTHZ_AUDIT_ENABLED=true
LANGFLOW_AUTHZ_SUPERUSER_BYPASS=true
```

Enforcement can be introduced safely by enabling audit first, assigning roles,
reviewing denied decisions, and then enabling `LANGFLOW_AUTHZ_ENABLED`.

## Recommended roles

| Role | Scope | Typical permissions |
|---|---|---|
| `platform_admin` | global | all resources and audit |
| `organization_admin` | organization | resources, channels and audit read |
| `channel_admin` | channel | channel administration, flow execute and KB read |
| `resource_editor` | global/workspace/project | edit flows, KBs, files and variables |
| `viewer` | global/workspace/project/channel | read and execute granted resources |
| `auditor` | global/channel | read runtime, execution and audit records |
| `member` | any | owner resources and explicit shares only |

Custom roles use canonical permission slugs such as `flow:read`,
`knowledge_base:ingest`, `channel:write`, `channel:audit` and `audit:read`.
Role assignments support `global`, `organization`, `workspace`, `project` and
`channel` domains.

## Security invariants

- Resource owners retain access through the owner guard.
- Active superusers may bypass RBAC when explicitly enabled.
- Denied cross-user resource lookups resolve to 404 to prevent ID enumeration.
- Channel service identities are never administrators and cannot receive RBAC
  role assignments.
- Shared channel runs may use only the explicitly granted workflow, knowledge
  base and model-provider scope of the connection owner.
- Personal channel routes execute as the bound OpenXFlow user.
- Every guarded decision can be written to the authorization audit table.
