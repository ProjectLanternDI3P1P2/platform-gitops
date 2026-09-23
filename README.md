# Lantern platform GitOps

This repository contains the Helm values and Argo CD applications used to run
the Lantern administration platform: Keycloak, Argo CD, CISO Assistant and the
temporary Mailpit mail capture service.

## Local development

The only desktop dependency is Docker Desktop. Enable Kubernetes in
**Docker Desktop > Settings > Kubernetes** before starting the environment.
Helm runs from a pinned Docker image and is not installed on the workstation.

On Windows:

```powershell
.\_scripts\dev-up.ps1
```

On macOS or Linux:

```bash
./_scripts/dev-up.sh
```

| Service | Local URL |
|---|---|
| Keycloak | http://keycloak.localhost |
| Argo CD | http://argocd.localhost |
| CISO Assistant | http://ciso.localhost |
| Mailpit | http://mail.localhost |

Local credentials are generated in `.dev-secrets.env`, which is ignored by
Git. Mailpit remains enabled in development and captures messages without
delivering them to real recipients.

## Production profile

Production examples are stored in `values-prod.yaml` files. They use HTTPS,
external PostgreSQL, multiple replicas where the upstream chart supports them,
pod anti-affinity, disruption budgets and existing Kubernetes Secrets. Replace
every `REPLACE_*` value before deployment.

Mailpit is temporarily retained because no production SMTP service is
available. Its ingress is disabled: it captures CISO Assistant messages inside
the cluster and does not deliver email to users. See
[`_docs/technical/production-deployment.md`](_docs/technical/production-deployment.md)
for prerequisites, secrets and rollout order.

The production Kubernetes cluster remains k3s on Proxmox. Docker Desktop is
only the local development environment.
