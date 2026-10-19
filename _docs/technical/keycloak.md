# Keycloak

Keycloak and its dedicated PostgreSQL database belong to the `keycloak`
namespace. They do not use the shared application database in `database`.

- Address: `http://auth.lantern.diiage` on the private network.
- Keycloak image: `quay.io/keycloak/keycloak:26.7.4`, running with `start`.
- Database image: `postgres:16-alpine`.
- Database Service: `postgresql-keycloak.keycloak.svc.cluster.local:5432`.
- Storage: `postgresql-keycloak-pvc`, 5 GiB, Longhorn.
- Service exposure: ClusterIP behind Traefik.
- Credentials: existing `keycloak-secrets` Secret, provisioned outside Git.

The reset completed on 2026-10-19 created an empty identity database. Users,
realms and OIDC clients must be configured again. The administration credentials
are reused without being committed to this repository.

`platform/keycloak` records the recreated resources for review and subsequent
GitOps adoption. The Application remains manually synchronized and is included
by the parent `platform` Application. The obsolete Helm example was removed so
that this component has one deployment definition.

HTTP is retained from the existing private deployment. TLS remains a separate
configuration task. Application login and SSO require recreating their realms
and clients; successful server readiness alone does not validate those flows.

Verified after reset: Keycloak and PostgreSQL each have one available replica;
the OIDC discovery endpoint returns http://auth.lantern.diiage/realms/master.
The abandoned dedicated database resources in database were removed; the
shared CloudNativePG cluster retains three ready instances. The former identity
namespace was deleted. No application SSO test was performed.
