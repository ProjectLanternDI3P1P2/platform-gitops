# Lantern platform GitOps

Single K3s configuration with namespaces organized by service.

- clusters/k3s: namespace foundation.
- bootstrap/argocd/k3s: cluster bootstrap and application discovery.
- platform/keycloak: Keycloak and its dedicated PostgreSQL database in the keycloak namespace.
- platform: Argo CD parent Application entry point, with one child per adopted component.
- apps/*/overlays/k3s: application configuration and published image identifiers.

Replace all REPLACE_* and repository markers before deployment. Provision Secrets outside Git. See [_docs/technical/keycloak.md](_docs/technical/keycloak.md) for the active Keycloak configuration.

The observed platform/argocd/values-k3s.yaml records the existing private cluster. The hardened platform/argocd/values.yaml requires completed DNS, TLS and OIDC settings before adoption.

Validate with the GitOps workflow and _scripts/preflight.ps1. Review the Argo CD diff and existing resource ownership before syncing.

The Player API now uses Production configuration. Verify database migrations separately: the removed demo patch previously enabled startup migrations and seeding.

Repository cleanup does not uninstall releases or delete live namespaces, PVCs, databases, Secrets or local credential files.
