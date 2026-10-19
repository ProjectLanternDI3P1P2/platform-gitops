# Alloy log collector

The K3s cluster currently runs Alloy as a DaemonSet in the `monitoring`
namespace. The release was installed with Helm before it was represented in
Git. `values.yaml` is the single canonical values file used by its Argo CD
Application and validation workflow. It preserves the existing log pipeline.

The chart is pinned to `grafana/alloy` `1.13.0` by the Argo CD Application in
`platform/argocd/applications/alloy.yaml`.

## Adoption process

The Argo CD Application intentionally has no automated sync policy. This keeps
the existing Helm release authoritative until an operator has:

1. pushed the reviewed manifests to the protected `main` branch;
2. created the `lantern-platform-k3s` AppProject and the `alloy` Application;
3. reviewed the Argo CD diff against the running Helm release;
4. confirmed that the rendered DaemonSet, RBAC and ConfigMap preserve the live
   log pipeline;
5. performed one manual sync with pruning disabled;
6. verified one Alloy pod per node and successful delivery to Loki;
7. documented that future Alloy changes are made only through Git.

Do not delete the existing Helm release metadata during the initial adoption.
It is rollback evidence until the Argo CD-managed deployment has been verified.

## Security constraints

Alloy runs as UID 0 because it reads the node's `/var/log/pods` files through
the chart's `varlog` host-path mount. The container drops all Linux capabilities
and cannot escalate privileges; moving to a non-root user requires changing
the node log-file ownership or collection mechanism first.

The current Loki endpoint is an HTTP address on the private `192.168.0.0/24`
network. This is a trusted-network deployment boundary, not transport
encryption. Replace it with an HTTPS Loki endpoint and configure the required
CA or client credentials before routing logs across an untrusted network.
