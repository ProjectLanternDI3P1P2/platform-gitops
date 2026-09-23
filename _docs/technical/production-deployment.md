# Production deployment

## Inputs to provide

Replace every `REPLACE_*` marker in the production values with approved values:

- public DNS names for Keycloak, Argo CD and CISO Assistant;
- cert-manager ClusterIssuer name;
- production StorageClass;
- PostgreSQL hostnames and the initial CISO administrator email;
- Git repository URL and protected production revision.

Run this check before rendering anything:

```powershell
.\_scripts\prod-preflight.ps1
```

## Secret contract

Create these secrets through OpenBao and External Secrets before Argo CD syncs
the applications:

| Namespace | Secret | Required keys |
|---|---|---|
| `platform` | `keycloak-prod-secrets` | `admin-password`, `database-password`, `argocd-oidc-client-secret`, `ciso-assistant-oidc-client-secret` |
| `ciso-assistant` | `ciso-assistant-prod-secrets` | `django-secret-key` |
| `ciso-assistant` | `ciso-assistant-postgresql` | `password` |
| `argocd` | `argocd-secret` | `oidc.keycloak.clientSecret` |

Do not create production secrets from `.env` files or commit Secret manifests.

## Rollout order

1. Build the k3s cluster across distinct Proxmox failure domains.
2. Install the CNI, CSI, cert-manager and Traefik `41.6.0` with
   `platform/traefik/values-prod.yaml`.
3. Apply `clusters/prod` and the secret synchronization resources.
4. Provision and verify both external PostgreSQL databases.
5. Install Argo CD with `platform/argocd/values-prod.yaml`.
6. Apply the production AppProject and Applications from
   `bootstrap/argocd/production`.
7. Verify Keycloak OIDC from a private browser session before disabling the
   Argo CD local administrator.
8. Configure CISO Assistant OIDC and perform backup and restore tests.

## Temporary Mailpit access

Mailpit has no production ingress. It only captures messages and never delivers
them. From an authenticated administration workstation:

```bash
kubectl -n platform port-forward service/mailpit 8025:8025
```

Open `http://localhost:8025` only for the duration of the operation and stop the
port-forward afterwards. Replace Mailpit when an organizational SMTP relay or a
transactional email provider becomes available.

