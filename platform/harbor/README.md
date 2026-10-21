# Harbor registry on K3s

Harbor is installed from the official `harbor/harbor` Helm chart `1.19.2`
(Harbor `2.15.2`). The target public endpoint is
`https://groupe7.diiage.org:18443` through pfSense HAProxy, which forwards over
TLS to the existing NodePort. It uses the Longhorn StorageClass. Complete
[the domain cutover](../HAPROXY_DOMAIN.md) before merging this configuration.

- Developer onboarding: `DEVELOPER_GUIDE.md`
- Firewall/NAT preparation: `NAT_EXPOSURE.md`
- Ready-to-send announcement: `ANNOUNCEMENT.md`

The initial deployment uses the internal PostgreSQL and Valkey components. All
stateful volumes have the Helm resource policy `keep`. Trivy scanning and Harbor
metrics are enabled.

## Secrets

`_scripts/install-harbor.ps1` creates the `harbor-bootstrap` Secret when it is
missing. The Secret contains the initial administrator password, the Harbor
encryption key, and internal database/registry passwords. Values are generated
with the operating-system cryptographic random-number generator and passed to
Helm over standard input. They are never written to Git or command arguments.

To retrieve the administrator password for an authorized operator:

```powershell
$encoded = kubectl -n harbor get secret harbor-bootstrap `
  -o jsonpath='{.data.HARBOR_ADMIN_PASSWORD}'
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded))
```

Do not paste the result into tickets, chat, logs or Git.

## Installation

Keep the SSH Kubernetes API tunnel open and run:

```powershell
$env:KUBECONFIG = 'D:\DIIAGE\DI3\Lantern Project\.kube\lantern-prod.yaml'
pwsh -File .\_scripts\install-harbor.ps1 `
  -HelmPath 'C:\path\to\helm.exe'
```

The generated backend certificate is private. HAProxy must trust its CA; public
Docker/CI clients validate the trusted domain certificate served by HAProxy.
Do not configure clients with global TLS verification disabled.

## Network and certificate access

Harbor access uses the HAProxy HTTPS listener on port `18443` and a TLS backend
on NodePort `30444`. DNS resolves `groupe7.diiage.org` to the public address.
See [HAProxy setup and validation](../HAPROXY_DOMAIN.md).

Export the public Harbor CA without exporting any private key:

```powershell
$encoded = kubectl -n harbor get secret harbor-nginx `
  -o jsonpath='{.data.ca\.crt}'
[IO.File]::WriteAllBytes(
  "$env:USERPROFILE\.kube\harbor-ca.crt",
  [Convert]::FromBase64String($encoded)
)
```

Use that public CA to configure the Harbor backend trust in HAProxy. Verify
that Docker/CI and containerd nodes trust the public frontend's certificate
chain before pulling images through the new address.

## Verification

```powershell
kubectl -n harbor get pods,pvc,svc
kubectl -n harbor rollout status deployment/harbor-core --timeout=300s
kubectl -n harbor rollout status deployment/harbor-portal --timeout=300s
kubectl -n harbor rollout status deployment/harbor-registry --timeout=300s
```

Back up the registry, PostgreSQL and Valkey volumes before upgrades. Keep Helm
as the only reconciler until every secret required by the chart can be supplied
through the cluster secret-management system and an Argo CD adoption diff has
been reviewed.
