# GitHub Actions runners on K3s

The Lantern cluster uses GitHub Actions Runner Controller (ARC) to provide
ephemeral organization runners that can reach the private Harbor registry.
The official ARC Helm charts are pinned to `0.14.2`.

## Architecture

- The controller runs in `arc-systems`.
- Listener and runner pods run in `arc-runners`.
- The scale set is named `lantern-k3s-builders` and scales from zero to two.
- Each job receives a fresh runner pod.
- Docker-in-Docker is privileged and is isolated in the runner namespace.
- Runner pods have no Kubernetes service-account token.
- Inbound traffic to runner pods is denied.
- Harbor's public CA is copied to a ConfigMap; no Harbor private key is copied.
- The Harbor hostname is mapped inside runner pods to Traefik's ClusterIP.

Only image publication jobs should use these runners. Tests, linting and other
jobs that do not require LAN access should remain on GitHub-hosted runners.

## GitHub App

Create an organization-owned GitHub App with:

- Repository permission `Metadata`: read-only;
- Organization permission `Self-hosted runners`: read and write.

If repository-scoped registration is selected later, the App also requires
repository `Administration`: read and write. Install the App on the
`ProjectLanternDI3P1P2` organization and record the App ID and installation ID.

Never paste the private key or a runner registration token into Git, chat,
workflow YAML or Helm values. Store the downloaded `.pem` file locally and use
the bootstrap script to create `arc-github-app` directly in Kubernetes.

## Workflow routing

Select the scale set only for a job that must reach Harbor:

```yaml
jobs:
  publish:
    runs-on: lantern-k3s-builders
```

Use the Docker driver for Buildx so image pushes use the Docker daemon that
trusts the mounted Harbor CA:

```yaml
- uses: docker/setup-buildx-action@<pinned-commit>
  with:
    driver: docker
```

The target image is:

```text
registry.lantern.diiage/lantern/<service>:<immutable-tag>
```

Harbor credentials belong in protected GitHub environment or repository
secrets and must come from a scoped Harbor robot account. Do not mount Harbor
administrator credentials into runner pods.

## Verification

```powershell
kubectl -n arc-systems get pods
kubectl -n arc-runners get autoscalingrunnerset,ephemeralrunnerset,pods
kubectl -n arc-systems logs deployment/arc-gha-rs-controller
```

Trigger a dedicated smoke workflow before moving the production image job.
The smoke test must verify GitHub checkout, Docker availability, Harbor TLS,
login with the robot account, and a push/pull of a disposable image.
