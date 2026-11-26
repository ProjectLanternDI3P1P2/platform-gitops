# Application delivery through Harbor and Argo CD

Application repositories call the reusable `publish-and-promote.yaml` workflow.
A release tag `vX.Y.Z`, created by release-please when the release pull request
is merged, is the only trigger: it builds the `vX.Y.Z` image once on the private
ARC runner, scans it, signs it with Cosign, pushes it to Harbor and sends a
validated `promote-image` repository dispatch to this repository.
The `promote-image.yaml` workflow changes only the matching Kustomize image tag
and opens a pull request named
`deploy(<application>): vX.Y.Z`. After the required reviews and the merge,
Argo CD performs the deployment.

Application workflows never receive Kubernetes credentials and never run Helm
or kubectl against the production cluster.

## Required GitHub secrets

Expose these organization or repository secrets to each application repository:

- `HARBOR_USERNAME`: a Harbor robot account allowed to push under `lantern/`;
- `HARBOR_TOKEN`: that robot account's token;
- `GITOPS_DISPATCH_TOKEN`: a fine-grained token that can create repository
  dispatches in `ProjectLanternDI3P1P2/platform-gitops`.

The `platform-gitops` repository must allow Actions to write repository contents
and to create pull requests (Settings, Actions, General, "Allow GitHub Actions to
create and approve pull requests"). The promotion workflow never pushes to
`main`: it pushes a `deploy/<application>-<tag>` branch and opens a reviewed PR.

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
