# Docker Desktop development cluster

This foundation is applied before the Helm releases and creates the namespaces.
The startup script updates Docker Desktop CoreDNS so workloads can reach
Keycloak through the same issuer URL used by the browser.

Enable Kubernetes in Docker Desktop, then run `_scripts/dev-up.ps1` on Windows
or `_scripts/dev-up.sh` on macOS and Linux. The scripts use Docker Desktop's
`kubectl` and execute Helm from a pinned container image. No additional local
cluster manager is required.

