# Argo CD target configuration

`platform/argocd/values.yaml` is the desired configuration, not a snapshot of
the running release. It retains the planned Keycloak OIDC, RBAC, direct HTTPS
NodePort exposure, Redis HA, autoscaling, resource limits and two
ApplicationSet replicas. Worker placement from the running installation is
retained.

## Prerequisites before synchronization

1. Keep Keycloak reachable over trusted HTTPS at
   `https://groupe7.diiage.org/auth`. The Argo CD issuer is the realm-specific
   discovery root `https://groupe7.diiage.org/auth/realms/master`.
2. Register confidential client `argocd` in realm `master` with redirect URI
   `https://10.4.0.130:8443/auth/callback` and web origin
   `https://10.4.0.130:8443`.
3. Supply the matching client secret in `argocd/argocd-secret` under key
   `oidc.keycloak.clientSecret`, using the existing secret-management mechanism.
   The values file contains only its Argo CD reference. No secret belongs in Git.
4. Configure the requested `groups` scope and group claim with full paths.
   `/platform-ops` maps to administrator; `/developers` maps to the custom
   read-only application and log permissions. Ensure an operator belongs to
   the administrator group and test the returned claims.
5. Review worker capacity for Redis HA and server/repository autoscaling.
6. Test OIDC login and the resulting RBAC before applying
   `configs.cm.admin.enabled: false`. Keep the existing recovery access until
   that validation succeeds. Review the first sync without pruning.

Restoring this source configuration does not provision the Argo CD TLS
certificate, create the Keycloak client, write its secret, disable the live
administrator, or validate SSO.
