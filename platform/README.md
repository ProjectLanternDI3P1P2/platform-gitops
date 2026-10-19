# Platform

`kustomization.yaml` is the entry point of the Argo CD `platform` Application.
It contains child Applications, rather than recursively deploying every YAML
file in this directory.

The `keycloak` child manages `platform/keycloak`: Keycloak, its PostgreSQL
database, Services, Ingress and PVC in the `keycloak` namespace. Credentials
remain in the existing Secret and are never tracked in Git.

The parent and child use manual synchronization and no automatic pruning.
Neither Application has a deletion finalizer. Deleting an Application must not
implicitly delete its database or volume.

The parent project and Application are declared in `bootstrap/argocd/k3s`.
Publish the reviewed Git revision before applying those declarations, then
refresh and inspect both Applications before their first synchronization.

Harbor, runners, Traefik and Argo CD values remain in their component folders.
They are not adopted automatically: existing Helm releases and the K3s Helm
controller retain their current ownership. Add a child Application only after
checking the running release and reviewing its rendered changes.
