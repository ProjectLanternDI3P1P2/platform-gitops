# Harbor registry on K3s

Harbor is installed from the official `harbor/harbor` Helm chart `1.19.2`
(Harbor `2.15.2`). It is exposed through Traefik at
`https://registry.lantern.diiage` and uses the Longhorn StorageClass.

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

The generated ingress certificate is self-signed. Before using Harbor from
Docker, CI runners or K3s nodes, distribute its CA to each trusted client. Do
not configure clients with global TLS verification disabled.

## Network and certificate access

Harbor access is expected to pass through the pfSense TCP `443` NAT rule. No
DNS record is required. Each approved workstation and self-hosted CI runner
must map the configured pfSense NAT address locally while retaining the Harbor
hostname:

```text
<PFSENSE_NAT_IP> registry.lantern.diiage
```

See `NAT_EXPOSURE.md` for the pfSense fields and the Windows/Linux hosts-file
locations. Do not use the pfSense or worker IP as the Docker registry name;
Harbor's certificate and token service require `registry.lantern.diiage`.

Export the public Harbor CA without exporting any private key:

```powershell
$encoded = kubectl -n harbor get secret harbor-ingress `
  -o jsonpath='{.data.ca\.crt}'
[IO.File]::WriteAllBytes(
  "$env:USERPROFILE\.kube\harbor-ca.crt",
  [Convert]::FromBase64String($encoded)
)
```

Trust that CA only on approved Docker/CI clients. K3s nodes also need the CA in
their containerd registry configuration before workloads can pull private
images from Harbor.

## Verification

```powershell
kubectl -n harbor get pods,pvc,ingress
kubectl -n harbor rollout status deployment/harbor-core --timeout=300s
kubectl -n harbor rollout status deployment/harbor-portal --timeout=300s
kubectl -n harbor rollout status deployment/harbor-registry --timeout=300s
```

Back up the registry, PostgreSQL and Valkey volumes before upgrades. Keep Helm
as the only reconciler until every secret required by the chart can be supplied
through the cluster secret-management system and an Argo CD adoption diff has
been reviewed.
