# Platform

The Argo CD `platform` Application groups nine child Applications:

| Application | Source | Destination | Adoption |
| --- | --- | --- | --- |
| keycloak | platform/keycloak | keycloak | Recreated resources; manual sync |
| argocd | argo-cd 10.9.2 | argocd | Existing Helm release; manual sync |
| harbor | harbor 1.19.2 | harbor | Visible; synchronization blocked pending credential review |
| arc-controller | gha-runner-scale-set-controller 0.14.2 | arc-systems | Existing Helm release; manual sync |
| arc-runners | gha-runner-scale-set 0.14.2 | arc-runners | Existing Helm release; manual sync |
| alloy | alloy 1.13.0 | monitoring | Existing Helm release; manual sync |
| longhorn | longhorn 1.12.1 | longhorn-system | Existing Helm release; manual sync |
| traefik | platform/traefik/k3s | kube-system | HelmChartConfig only; K3s owns the workloads |
| rabbitmq | platform/rabbitmq | rabbitmq | Shared message broker; manual sync ([details](../_docs/technical/mongodb-rabbitmq.md)) |

Use the `lantern-platform-k3s` project filter in Argo CD. Open `platform` to
see child Applications, then open a child to inspect its resources and diff.
Helm-backed workloads are not adopted or restarted merely by registering their
Application. A manual first sync transfers reconciliation to Argo CD; stop using
Helm CLI upgrades for that release after adoption.

## Branch review and main

`bootstrap/argocd/review` registers the parent against the review branch and
`overlays/platform-review` pins all child Git sources to that same branch. It
allows review in Argo CD before merging the PR, without syncing workloads.
These overlays intentionally refer to `refactor/unify-k3s-platform`.

After merge, apply `bootstrap/argocd/platform`, then manually synchronize the
parent. This switches its children to main. Remove the review overlays before
deleting the review branch. The full K3s bootstrap also includes the same parent.

## Existing data and credentials

Each Helm chart has one canonical YAML values file:

- `argocd/values.yaml`
- `harbor/values.yaml`
- `actions-runner-controller/controller/values.yaml`
- `actions-runner-controller/runners/values.yaml`
- `longhorn/values.yaml`
- `../observability/alloy/values.yaml`

These files define the intended settings used by the Applications. They retain
planned configuration as well as necessary installation settings; they are not
limited to the running release. Chart versions, release names and namespaces
remain unchanged. The former snapshots and alternative profiles were removed.
No Secret values are included. Harbor's
two inline password values are omitted.
Its project sync window blocks manual and automated sync until credential
preservation and the full rendered diff have been reviewed. Do not remove that
window merely to make the status green.

Secret data is excluded from Helm Application comparisons and preserved during
sync via RespectIgnoreDifferences. This works for existing resources; it does
not bootstrap missing credentials. Harbor additionally ignores generated pod
checksum annotations to avoid presenting secret regeneration as a rollout.
These settings do not replace the first-sync review.

All Applications use manual synchronization, no automatic pruning and no
cascade-delete finalizer. Helm chart CRDs are not installed through these child
Applications; existing CRD ownership is retained. Longhorn volumes and storage
settings must be reviewed before its first sync. Traefik stays under the K3s
Helm controller, with Argo CD tracking its existing HelmChartConfig.

## Planned changes retained during consolidation

Argo CD retains its planned OIDC, RBAC, TLS, Redis HA and autoscaling settings.
See [OIDC prerequisites](../_docs/technical/argocd-oidc.md) before syncing. These
settings have not been activated by the file cleanup.

Traefik retains the planned disruption budget, strict pod anti-affinity, ingress
class and logging settings inside its single HelmChartConfig. Existing HPA,
worker placement, trusted proxy addresses and traffic policy are retained.
Strict anti-affinity requires a separate eligible worker for each replica;
scaling above the current worker count needs additional eligible workers.

Alloy retains the planned capability restrictions, disabled privilege escalation
and readable River pipeline. Harbor and runner settings were also compared
against the removed profiles; their planned keys were already retained.
