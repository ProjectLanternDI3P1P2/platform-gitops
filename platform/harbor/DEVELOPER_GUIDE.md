# Harbor registry developer guide

The Lantern platform provides an internal Harbor registry for application
images:

```text
https://10.4.111.200:18443
```

Harbor is currently intended for trusted private networks, CI runners and
K3s nodes. It is not a public Internet registry.

## Prerequisites

Before logging in, a workstation must:

1. reach `10.4.111.200:18443` through the approved pfSense rule;
2. trust the Harbor private CA and a certificate covering IP `10.4.111.200`;
3. have Docker, Podman or another OCI-compatible client installed;
4. have a named Harbor account or a scoped robot-account credential.

Do not use the Harbor `admin` account for application builds, CI or day-to-day checks. Do not
disable TLS verification globally and do not commit registry passwords, robot
tokens or Docker authentication files.

No local hosts-file entry is required. The registry address includes the
nonstandard port and must be used exactly as documented.

## Image naming convention

Application images use the shared private `lantern` project. The CD pipeline
publishes them; the name is the repository of the service:

```text
10.4.111.200:18443/lantern/<repository>:<tag>
```

Examples (real repositories of the project):

```text
10.4.111.200:18443/lantern/dungeon-backend:v2.5.0
10.4.111.200:18443/lantern/combat-backend:v1.2.0
10.4.111.200:18443/lantern/player-backend:v1.6.0
```

A release tag `vX.Y.Z` is what gets deployed. Builds from `main` are tagged
`main-<sha>` and `main-latest`: they are for testing only, never reference them
in a deployment. The pipeline resolves the digest of the image and the GitOps
overlay pins it next to the tag, so what runs is exactly what was scanned and
signed.

## Login

Use an individual account for interactive work:

```powershell
docker login 10.4.111.200:18443
```

For CI, pass the robot-account token through the CI secret store and use
password stdin:

```powershell
$env:HARBOR_TOKEN | docker login 10.4.111.200:18443 `
  --username $env:HARBOR_USERNAME `
  --password-stdin
```

Never print either environment variable.

## Build and push

Do not push images by hand for a deployment. Since 2026-11-27 Harbor refuses to
serve an image that is not signed (see "Scan, signature and blocking" below), so
a manual push cannot be deployed. The supported path is:

1. merge the release pull request of the service (release-please creates the
   `vX.Y.Z` tag);
2. the shared workflow builds, scans, signs and pushes the image, then asks
   `platform-gitops` to promote it;
3. a promotion pull request `deploy(<application>): vX.Y.Z` is merged
   automatically once "Validate GitOps" passes, and Argo CD deploys it.

Details: [application delivery](../../_docs/technical/application-delivery.md).
CI must not run `kubectl apply` or `helm upgrade` against the production cluster.

A manual `docker build` and `docker push` is still fine for a local test on a
temporary project, never on `lantern`.

## Pull from K3s

K3s nodes must trust the Harbor CA before kubelet/containerd can pull an image.
The target namespace also needs a registry credential Secret, referenced by the
workload through `imagePullSecrets`. Create that Secret through the approved
secret-management workflow; never commit a Kubernetes Secret manifest.

## Scan, signature and blocking

Harbor scans every push (Trivy) and generates an SBOM. Two controls are enforced
on the `lantern` project on every pull, including the one made by the cluster:

| Control | Rule | What you see when it blocks |
|---|---|---|
| Signature | The image must be signed with cosign by the CI | `HTTP 412 PROJECTPOLICYVIOLATION: The image is not signed by cosign.` |
| Vulnerabilities | No CRITICAL finding | `HTTP 412 PROJECTPOLICYVIOLATION` with the number of CRITICAL vulnerabilities |

Harbor checks the signature first, so an image that is both unsigned and
vulnerable only reports the signature.

If a pod is in `ImagePullBackOff` with an HTTP 412 event, open the artifact in
Harbor: the **Signed** and **Vulnerabilities** columns give the reason. To fix
it:

- unsigned image: publish a `vX.Y.Z` release through the shared workflow;
- CRITICAL vulnerability: update the dependency or the base image, then publish
  a new release (the pipeline also refuses to sign an image with CRITICAL
  findings);
- urgent case: ask for a documented exception (7 days maximum, approved by the
  Security team). See the
  [runbook](../../_docs/technical/image-admission-runbook.md), section 5.

Running pods keep running; the problem appears when a pod is restarted or
rescheduled, so check the images of your service before the next deployment.

## Getting help

When reporting a registry problem, provide:

- the repository and immutable tag or digest;
- the time of the failed operation;
- the HTTP status or client error;
- whether the NAT connection and CA trust succeed.

Never include passwords, robot tokens, Docker `config.json` contents or the
Harbor bootstrap Secret.
