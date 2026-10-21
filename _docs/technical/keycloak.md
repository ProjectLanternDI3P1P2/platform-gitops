# Keycloak

Keycloak and its dedicated PostgreSQL database belong to the `keycloak`
namespace. They do not use the shared application database in `database`.

- Public OIDC base address: `https://groupe7.diiage.org/auth`.
- Keycloak image: `quay.io/keycloak/keycloak:26.7.4`, running with `start`.
- Database image: `postgres:16-alpine`.
- Database Service: `postgresql-keycloak.keycloak.svc.cluster.local:5432`.
- Storage: `postgresql-keycloak-pvc`, 5 GiB, Longhorn.
- Service exposure: ClusterIP behind Traefik on host `groupe7.diiage.org` and
  path `/auth`.
- Credentials: existing `keycloak-secrets` Secret, provisioned outside Git.

The reset completed on 2026-10-19 created an empty identity database. Users,
realms and OIDC clients must be configured again. The administration credentials
are reused without being committed to this repository.

`platform/keycloak` records the recreated resources for review and subsequent
GitOps adoption. The Application remains manually synchronized and is included
by the parent `platform` Application. The obsolete Helm example was removed so
that this component has one deployment definition.

The Kubernetes backend remains HTTP behind Traefik. The externally visible
OIDC URL is HTTPS and must preserve the `/auth` prefix. Application login and
SSO require configured realms and clients; successful server readiness alone
does not validate those flows.

Verified after reset: Keycloak and PostgreSQL each had one available replica.
The desired master-realm issuer is
`https://groupe7.diiage.org/auth/realms/master`; validate its discovery document
and an interactive login before enabling dependent SSO. The abandoned dedicated
database resources in database were removed; the shared CloudNativePG cluster
retained three ready instances. The former identity namespace was deleted. No
application SSO test was performed.
