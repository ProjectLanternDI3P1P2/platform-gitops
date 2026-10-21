# Harbor registry developer guide

The Lantern platform provides an internal Harbor registry for application
images:

```text
https://groupe7.diiage.org:18443
```

Harbor is currently intended for trusted private networks, CI runners and
K3s nodes. It is not a public Internet registry.

## Prerequisites

Before logging in, a workstation must:

1. reach `groupe7.diiage.org:18443` through the approved pfSense rule;
2. trust the domain certificate chain served by HAProxy;
3. have Docker, Podman or another OCI-compatible client installed;
4. have a named Harbor account or a scoped robot-account credential.

Do not use the Harbor `admin` account for application builds or CI. Do not
disable TLS verification globally and do not commit registry passwords, robot
tokens or Docker authentication files.

No local hosts-file entry is required. The registry address includes the
nonstandard port and must be used exactly as documented.

## Image naming convention

Application images use the shared private `lantern` project and an immutable
tag:

```text
groupe7.diiage.org:18443/lantern/<service>:<git-sha>
```

Examples:

```text
groupe7.diiage.org:18443/lantern/player:47e129f
groupe7.diiage.org:18443/lantern/combat:a12bc34
groupe7.diiage.org:18443/lantern/frontend-game:2026.10.01-7f31d9a
```

Do not deploy `latest`. A release tag may be added for human readability, but
Kubernetes manifests should ultimately pin the image digest.

## Login

Use an individual account for interactive work:

```powershell
docker login groupe7.diiage.org:18443
```

For CI, pass the robot-account token through the CI secret store and use
password stdin:

```powershell
$env:HARBOR_TOKEN | docker login groupe7.diiage.org:18443 `
  --username $env:HARBOR_USERNAME `
  --password-stdin
```

Never print either environment variable.

## Build and push

From a service repository:

```powershell
$service = "player"
$tag = (git rev-parse --short=7 HEAD)
$image = "groupe7.diiage.org:18443/lantern/${service}:${tag}"

docker build --pull --tag $image .
docker push $image
```

Record the immutable digest returned by the registry:

```powershell
docker inspect --format='{{index .RepoDigests 0}}' $image
```

Update the GitOps repository through a pull request. CI builds and pushes the
image; Argo CD deploys the reviewed Git change. CI must not run `kubectl apply`
or `helm upgrade` against the production cluster.

## Pull from K3s

K3s nodes must trust the Harbor CA before kubelet/containerd can pull an image.
The target namespace also needs a registry credential Secret, referenced by the
workload through `imagePullSecrets`. Create that Secret through the approved
secret-management workflow; never commit a Kubernetes Secret manifest.

## Vulnerability scanning

Trivy scanning is enabled. A successful push does not mean an image is approved
for deployment. Review the Harbor scan results and follow the project's policy
for `HIGH` and `CRITICAL` findings before updating GitOps.

## Getting help

When reporting a registry problem, provide:

- the repository and immutable tag or digest;
- the time of the failed operation;
- the HTTP status or client error;
- whether the NAT connection and CA trust succeed.

Never include passwords, robot tokens, Docker `config.json` contents or the
Harbor bootstrap Secret.
