# Production readiness

The development profile validates integration only. Production uses the
separate `values-prod.yaml` files and the `clusters/prod` foundation.

## Required controls

- Publish Keycloak, Argo CD and CISO Assistant only through HTTPS with stable
  DNS names and certificates managed by cert-manager.
- Run Keycloak and CISO Assistant against separate external PostgreSQL
  databases with automated backups and tested restores.
- Store Kubernetes secrets in OpenBao or another secret manager and synchronize
  them with External Secrets. Never commit rendered Secrets.
- Require MFA or WebAuthn for platform operators, named accounts and temporary
  passwords for new users. Maintain two audited emergency accounts.
- Disable the Argo CD local administrator after OIDC recovery has been tested.
- Protect the Git default branch with reviews and successful validation checks.
- Export audit logs, monitor authentication failures and alert on changes to
  privileged groups.
- Back up etcd, persistent volumes, databases and firewall configuration, then
  perform a complete recovery exercise.

## Current limitations

- No production SMTP service is available. Mailpit is retained as an internal
  capture service, so invitations and password reset messages are not delivered
  to recipients. Administrators can inspect them through a temporary
  `kubectl port-forward` from the administration network.
- CISO Assistant chart `0.11.5` still uses SQLite for Huey. The production
  profile therefore keeps one backend replica while the frontend uses two.
- A highly available control plane requires an odd quorum. Two Proxmox hosts
  need a third control-plane failure domain or witness.

