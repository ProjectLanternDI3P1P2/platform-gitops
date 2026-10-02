# Application delivery through Harbor and Argo CD

Application repositories call the reusable `publish-and-promote.yaml` workflow.
A merge to `main` builds an immutable `main-<sha12>` image on the private ARC
runner, pushes it to Harbor, and sends a validated `promote-image` repository
dispatch to this repository. The `promote-image.yaml` workflow changes only the
matching Kustomize image tag on `main`. Argo CD then performs the deployment.

Application workflows never receive Kubernetes credentials and never run Helm
or kubectl against the production cluster.

## Required GitHub secrets

Expose these organization or repository secrets to each application repository:

- `HARBOR_USERNAME`: a Harbor robot account allowed to push under `lantern/`;
- `HARBOR_TOKEN`: that robot account's token;
- `GITOPS_DISPATCH_TOKEN`: a fine-grained token that can create repository
  dispatches in `ProjectLanternDI3P1P2/platform-gitops`.

The `platform-gitops` repository must allow Actions to write repository contents.
If `main` is protected, explicitly allow the GitHub Actions identity used by the
promotion workflow or replace the direct promotion commit with a reviewed PR.

## Cluster pull credentials

Create a separate Harbor robot account with pull-only access to `lantern/`. Keep
its credentials out of Git, then run from an operator workstation:

```powershell
$env:HARBOR_PULL_USERNAME = '<robot-account>'
$env:HARBOR_PULL_TOKEN = '<robot-token>'
pwsh -File .\_scripts\bootstrap-app-secrets.ps1 `
  -KubeConfig 'D:\DIIAGE\DI3\Lantern Project\.kube\lantern-prod.yaml'
Remove-Item Env:HARBOR_PULL_USERNAME, Env:HARBOR_PULL_TOKEN
```

The script creates only missing namespace secrets. It does not rotate an existing
database password or place credentials in command arguments, files, or Git.

## Deployment order

1. Merge the reusable and promotion workflows in `platform-gitops`.
2. Configure the three application-repository secrets.
3. Bootstrap the cluster pull and database secrets.
4. Merge each application CD branch into `main` to publish its first image.
5. Merge the GitOps application manifests.
6. Apply `bootstrap/argocd/k3s` once to install the self-managed bootstrap
   application, then verify Argo CD sync and health. Later bootstrap changes are
   reconciled from Git automatically.
