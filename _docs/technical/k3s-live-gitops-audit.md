# K3s live-to-GitOps audit

Audit date: 2026-10-01

This document records the initial read-only comparison between the deployed
K3s cluster and the `main` branch of `platform-gitops`. It contains no Secret
data or kubeconfig material.

## Cluster snapshot

- K3s `v1.36.4+k3s1` with one control-plane node and three worker nodes.
- Traefik is managed by the built-in K3s Helm controller.
- Argo CD `v3.5.3` is installed from Helm chart `argo-cd` `10.9.2`.
- Longhorn `v1.12.1` is installed from Helm chart `longhorn` `1.12.1` and is
  the default StorageClass.
- Alloy `v1.20.0` is installed from Helm chart `alloy` `1.13.0` as a
  DaemonSet with one pod on every node.
- The Player application is managed by Argo CD from this repository. It was
  `Synced` and `Healthy` at Git revision
  `bc06906895eaac533cc80250a49cb04581a3451b`.

## Logging health

- Alloy was `Ready` on all four nodes at the end of the audit.
- Its readiness endpoint returned `Alloy is ready` through the Kubernetes API
  service proxy.
- The selected Alloy instance reported 9,952 entries and about 1.22 MB sent to
  Loki, with zero batch retries and zero dropped entries.
- No Alloy warning or error was present in the final 30-minute log window.
- Earlier reflector errors between approximately 11:05 and 11:08 UTC showed a
  temporary loss of the Kubernetes API route while nodes were restarting. The
  watchers recovered and resumed tailing files afterwards.

## Ownership classification

| Live component | Current owner | Git state | Required action |
| --- | --- | --- | --- |
| Player API and PostgreSQL | Argo CD | Declared and synchronized | Keep Argo CD as the only reconciler |
| Alloy | Helm CLI | Values were absent | Review the new manual-adoption Application before syncing |
| Argo CD | Helm CLI | K3s values were absent | Live non-secret values are now recorded |
| Longhorn | Helm CLI | Absent | Back up and compare a pinned render before GitOps adoption |
| Traefik | K3s Helm controller | Production values exist but do not own the live release | Keep the K3s Helm controller authoritative until a planned migration |
| Keycloak and PostgreSQL in `lantern-dev` | Manual resources | Different from the repository production chart | Back up PostgreSQL and compare manifests before adoption |
| Docusaurus in `default` | Manual resources | Absent; mutable `latest` image | Identify its source repository and pin an immutable image |
| Platform namespaces | Mixed/manual | Declared but not reconciled as one foundation | Review and manually sync `cluster-foundation` |

## Important drift

1. `observability/` was empty although Alloy was already collecting cluster
   logs and sending them to `http://192.168.0.15:3100`.
2. Several platform components are Helm or manually managed and therefore have
   no continuous reconciliation from Git.
3. The live Keycloak deployment is in `lantern-dev`, while the repository also
   contains a separate platform chart and production profile. The live database
   is a Deployment named `postgresql-keycloak` with an existing 5 GiB Longhorn
   PVC, while the chart would create a differently named StatefulSet and PVC.
   They must not be merged blindly because the live PostgreSQL PVC contains
   state.
4. Docusaurus uses `beveradb/docusaurus:example-nginx-latest`, which is not an
   immutable or reproducible deployment reference.
5. The production profiles still contain `REPLACE_*` markers and are not ready
   for unattended synchronization.

## Safe reconciliation order

1. Review and push the Alloy values and bootstrap manifests.
2. Apply only the K3s AppProjects and Applications; do not sync them yet.
3. Review the Argo CD diffs for `alloy` and `cluster-foundation`.
4. Manually sync Alloy with pruning disabled, then verify DaemonSet readiness,
   errors and delivery to Loki.
5. Manually sync the namespace foundation after confirming ownership of every
   namespace.
6. Export and back up the live Keycloak PostgreSQL database before adopting
   Keycloak.
7. Configure and test Longhorn backups before attempting GitOps ownership of
   the storage layer.
8. Move Docusaurus to its owning application repository and replace `latest`
   with an immutable tag or digest.
