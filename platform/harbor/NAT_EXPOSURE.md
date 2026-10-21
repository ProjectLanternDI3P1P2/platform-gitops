# Harbor exposure through pfSense

Harbor is exposed directly through a Kubernetes `NodePort`. No Ingress or DNS
name is required. Harbor's nginx component terminates TLS.

## Kubernetes endpoint

The Helm values configure:

- exposure type `nodePort`
- HTTPS NodePort `30444`
- HTTP NodePort `30082`, not published by pfSense
- TLS certificate generated for IP `10.4.0.130`
- external Harbor URL `https://10.4.0.130:8444`

The externally visible address and port are part of Harbor's token-service URL.
Clients must therefore use exactly `10.4.0.130:8444`.

Current worker addresses documented by the platform are:

| Worker | NAT target |
| --- | --- |
| `kube-worker-01` | `192.168.0.11:30444` |
| `kube-worker-02` | `192.168.0.12:30444` |
| `kube-worker-04` | `192.168.0.14:30444` |

The pfSense rule targets one worker and is therefore a single point of failure.
Kubernetes forwards the NodePort to the Harbor nginx pod even when that pod is
running on another worker.

## pfSense port forward

In **Firewall > NAT > Port Forward**, create one rule:

| Field | Value |
| --- | --- |
| Interface | Trusted private or VPN ingress interface |
| Address family | IPv4 |
| Protocol | TCP |
| Source | Approved developer, CI and K3s-node aliases |
| Destination | `10.4.0.130` |
| Destination port | `8444` |
| Redirect target IP | `192.168.0.11` |
| Redirect target port | `30444` |
| Description | `Harbor HTTPS NodePort` |
| Filter rule association | Add associated filter rule |

Save and apply the rule, then confirm that the generated pass rule has the same
restricted sources. Do not expose `30082`, `5000`, `5432`, `6379`, `8001` or
any Longhorn service.

NAT reflection or an equivalent internal route is required because K3s nodes
and in-cluster ARC runners also use `10.4.0.130:8444`. Validate that path before
removing the old Ingress from the live cluster.

## TLS

For NodePort mode the chart stores the generated certificate and CA in Secret
`harbor-nginx`. Chart version `1.19.2` recognizes an IPv4 common name and adds
it to the certificate IP SAN list.

Export only `ca.crt` and trust it on approved workstations, ARC runners and all
K3s/containerd nodes. Never export the private key or disable TLS verification.

## Validation after synchronization

First verify the live Service and certificate Secret:

```powershell
$env:KUBECONFIG = 'D:\DIIAGE\DI3\Lantern Project\.kube\lantern-prod.yaml'
kubectl get svc harbor -n harbor -o wide
kubectl get secret harbor-nginx -n harbor
```

From every required network zone, including a K3s node:

```powershell
Test-NetConnection 10.4.0.130 -Port 8444
curl.exe --fail --cacert .\harbor-ca.crt https://10.4.0.130:8444/api/v2.0/ping
docker login 10.4.0.130:8444
```

Push and pull a disposable image from a non-production project. Confirm that
Harbor records the artifact and that Trivy produces a scan result. Check the
pfSense firewall log for expected source addresses only.

Do not synchronize this change until the NodePort is confirmed free, NAT
reflection works, the new CA is distributed and registry pull Secrets have
been regenerated for `10.4.0.130:8444`.
