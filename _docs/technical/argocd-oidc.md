# Argo CD target configuration

`platform/argocd/values.yaml` is the desired configuration, not a snapshot of
the running release. It retains the previously planned Keycloak OIDC, RBAC,
HTTPS ingress, Redis HA, autoscaling, resource limits and two ApplicationSet
replicas. Worker placement from the running installation is retained.

## Prerequisites before synchronization

1. Provide trusted HTTPS for `auth.lantern.diiage` and `argocd.lantern.diiage`.
   Replace `REPLACE_CLUSTER_ISSUER` with the actual certificate issuer. The
   current private HTTP endpoints do not satisfy this target configuration.
2. Recreate realm `lantern` in Keycloak after its reset. Register confidential
   client `argocd` with redirect URI
   `https://argocd.lantern.diiage/auth/callback` and the matching web origin.
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

Restoring this source configuration does not provision TLS, create the realm,
write the client secret, disable the live administrator, or validate SSO.
