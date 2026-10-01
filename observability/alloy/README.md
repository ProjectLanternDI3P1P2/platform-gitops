# Alloy log collector

The K3s cluster currently runs Alloy as a DaemonSet in the `monitoring`
namespace. The release was installed with Helm before it was represented in
Git. `values-k3s.yaml` mirrors the non-secret values observed from Helm release
revision 9 on 2026-10-01.

The chart is pinned to `grafana/alloy` `1.13.0` by the Argo CD Application in
`bootstrap/argocd/k3s/alloy.yaml`.

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
