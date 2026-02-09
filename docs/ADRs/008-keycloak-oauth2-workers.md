# ADR-008: Keycloak with OAuth2 client_credentials for Workers

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, DevOps Lead, Security

## Context

The CIB Seven engine exposes a REST API accessed by workers, the CDC bridge, dashboards, and human operators. This API must be secured with authentication and authorization. Different hospital units (tenants) require role-based access control.

CIB Seven supports: Basic Auth (username/password), OAuth2/OIDC with external provider, container-managed security. Basic Auth is simple but insecure for service-to-service communication — no token expiry, no scoping.

## Decision

We will use **Keycloak 24** as the identity provider with OAuth2 and OpenID Connect for all platform authentication.

A dedicated realm `austa-bpm` will contain:

1. **Service clients** with `client_credentials` grant for workers and CDC bridge — each worker type has its own client ID (e.g., `worker-eligibility`, `worker-tiss`, `cdc-bridge`) with scoped permissions
2. **User accounts** for human operators (Cockpit, Tasklist, Admin) with password + MFA
3. **Tenant-to-group mappings** — each hospital unit is a Keycloak group; users/clients assigned to groups enforce data visibility:
   - `austa-hospital`
   - `amh-sp-morumbi`
   - `amh-rj-barra`
   - `amh-mg-bh`

**Basic Auth will be removed** from all CIB Seven engine endpoints. Engine Spring Security validates JWT tokens, extracts tenant from claims, enforces RBAC.

Realm configuration exported as JSON, stored in IaC repo, deployed via Helm chart.

## Consequences

**Positive:**

- Token-based auth with automatic expiry (15-min access tokens, 8-hour refresh) is significantly more secure than static Basic Auth credentials.
- Each worker has its own client identity — granular audit trails and permission scoping (WhatsApp worker cannot access process history; TISS worker cannot start clinical processes).
- Tenant isolation reinforced through Keycloak groups — second layer beyond engine-level filtering.

**Negative:**

- Keycloak adds an infrastructure component. *Mitigation:* deployed as Kubernetes Deployment with PostgreSQL backing, included in standard monitoring.
- Workers must handle token refresh. *Mitigation:* `AustaWorker` base framework handles refresh transparently; individual developers never interact with auth directly.
