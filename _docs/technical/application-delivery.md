# Application delivery through Harbor and Argo CD

Application repositories call the reusable `publish-and-promote.yaml` workflow.
A release tag `vX.Y.Z`, created by release-please when the release pull request
is merged, is the only trigger: it builds the `vX.Y.Z` image once on the private
ARC runner, scans it, signs it with Cosign, pushes it to Harbor and sends a
validated `promote-image` repository dispatch to this repository.
The `promote-image.yaml` workflow changes only the matching Kustomize image tag
and digest and opens a pull request named `deploy(<application>): vX.Y.Z`. It
merges that pull request itself once the "Validate GitOps" check passes (see
below), then Argo CD performs the deployment. The only human review is the
release pull request that created the tag.

What a published release guarantees (see [ADR 6](../adr/6.%20ImageAdmission.md)):
the image passed the Harbor scan gate (no CRITICAL finding), is signed by digest
with the CI key, carries a signed provenance attestation (source repository,
commit, workflow run), and is deployed by that digest, not only by its tag.

Application workflows never receive Kubernetes credentials and never run Helm
or kubectl against the production cluster.

## Required GitHub secrets

Expose these organization or repository secrets to each application repository:

- `HARBOR_USERNAME`: a Harbor robot account allowed to push under `lantern/`;
- `HARBOR_TOKEN`: that robot account's token;
- `GITOPS_DISPATCH_TOKEN2`: a fine-grained token of `Diiage-Service-Account`
  (not a personal account) limited to `ProjectLanternDI3P1P2/platform-gitops`
  with "Contents: read and write", the minimum to create a repository dispatch.
  Callers pass it as the `GITOPS_DISPATCH_TOKEN` secret of the reusable workflow.
  The former `GITOPS_DISPATCH_TOKEN` organization secret is kept unused as a fallback;
- `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD`: the CI signing key (private key file
  content and its password), used to sign the image and its provenance. The source
  of truth is the team vault, never a repository (rotation every 12 months, see the
  [runbook](image-admission-runbook.md)).

The `platform-gitops` repository needs a `BOT_TOKEN` repository secret: a
fine-grained token of `Diiage-Service-Account` limited to this repository, with
"Contents: read and write", "Pull requests: read and write" and "Checks: read". The promotion
workflow uses it, not `GITHUB_TOKEN`, so that "Validate GitOps" runs on the
promotion pull request and "Allow GitHub Actions to create and approve pull
requests" can stay disabled. The workflow never pushes to `main`: it pushes a
`deploy/<application>-<tag>` branch, opens a PR, closes any older promotion PR
of the same application and merges the PR itself once "Validate GitOps" passes.
The human review is the release pull request merged by the team: once release-please
creates the `vX.Y.Z` tag, the image is built, signed and deployed without another
manual step. `Diiage-Service-Account` is a bypass actor of the `main: merge only`
ruleset in "pull request" mode (it can merge its pull requests, never push to `main`).

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

## Roll back a deployment

A rollback is a revert to a previous tag **and digest** in the overlay of the
application, through a pull request (people need the two approvals required by
the `main: merge only` ruleset; the promotion bot is the only one that merges
alone). Argo CD then redeploys exactly the previous image.

1. Find the previous version: `git log -p -- apps/<application>/overlays/k3s/kustomization.yaml`
   or the merged `deploy(<application>): vX.Y.Z` pull requests.
2. Restore both `newTag` and `digest` of that version. Example for Dungeon,
   from v2.5.0 back to v2.4.0:

   ```yaml
   images:
     - name: 10.4.111.200:18443/lantern/backend
       newName: 10.4.111.200:18443/lantern/dungeon-backend
       newTag: v2.4.0
       digest: sha256:fbddded312b5cb47e8fb294e27123a60c6bca61b6c7f154626a846ccba13f150
   ```

   v2.5.0 is `sha256:433662fafd923ce63a1096135b04bae6d9ab5d9b6779a5a41ea6d71787a6e09b`.
3. Open the pull request, get the two approvals, merge. Check Argo CD shows the
   application `Healthy` and `Synced`.
4. The previous image must still be signed and under the CRITICAL threshold,
   otherwise Harbor refuses to pull it (HTTP 412) when the pod restarts. Check
   its Signed and Vulnerabilities columns in Harbor before rolling back.

Never roll back by changing the tag alone: a digest left from the newer version
would still take priority over the tag.

## A deployment is stuck in `ImagePullBackOff`

Harbor enforces the image admission policy on every pull (signature required,
no CRITICAL vulnerability). A pod that uses an unsigned or vulnerable image
cannot start or be rescheduled. See "Understand a rejected deployment" in the
[runbook](image-admission-runbook.md): the fix is to publish a `vX.Y.Z` release
through the shared workflow, not to push the image by hand.
