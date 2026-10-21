# Argo CD exposure through pfSense

Argo CD is exposed directly through a Kubernetes `NodePort`. No Ingress or DNS
name is required for the network path. Argo CD terminates TLS on the server pod.

## Kubernetes endpoint

The Helm values configure:

- Ingress disabled
- `argocd-server` Service type `NodePort`
- HTTPS NodePort `30443`
- Argo CD server-side TLS enabled

The Service also has the chart's HTTP-labelled NodePort `30080`. Both Service
ports target the same Argo CD server port, which speaks TLS in this
configuration. Publish only `30443` through pfSense.

Current worker addresses documented by the platform are:

| Worker | NAT target |
| --- | --- |
| `kube-worker-01` | `192.168.0.11:30443` |
| `kube-worker-02` | `192.168.0.12:30443` |
| `kube-worker-04` | `192.168.0.14:30443` |

With `externalTrafficPolicy: Cluster`, any Ready worker can forward traffic to
an available Argo CD server pod. A rule targeting one worker is nevertheless a
single point of failure.

## pfSense port forward

In **Firewall > NAT > Port Forward**, create one rule:

| Field | Value |
| --- | --- |
| Interface | Trusted private or VPN ingress interface |
| Address family | IPv4 |
| Protocol | TCP |
| Source | Approved administrator network alias |
| Destination | `10.4.0.130` |
| Destination port | `8443` |
| Redirect target IP | `192.168.0.11` |
| Redirect target port | `30443` |
| Description | `Argo CD HTTPS NodePort` |
| Filter rule association | Add associated filter rule |

Save and apply the rule, then confirm that the generated firewall rule has the
same restricted source alias. Do not expose `30080`, Redis, repo-server, or the
Kubernetes API.

The resulting URL is:

```text
https://10.4.0.130:8443
```

## TLS and authentication

Without an `argocd-server-tls` Secret, Argo CD generates a self-signed
certificate. A browser warning is therefore expected. For a trusted
certificate without DNS, issue a certificate containing the pfSense address as
an IP SAN and store it in `argocd/argocd-server-tls`. Never commit its private
key.

Keycloak remains available at `https://groupe7.diiage.org/auth`. Argo CD uses
issuer `https://groupe7.diiage.org/auth/realms/master`; the Keycloak client must
allow callback `https://10.4.0.130:8443/auth/callback` and web origin
`https://10.4.0.130:8443`. Keep at least one tested authentication path before
disabling the local admin account.

Do not expose this administration surface to the whole Internet with source
`any`. Prefer a VPN or a tightly restricted source alias.

## Validation after synchronization

First confirm the live Service and endpoints:

```powershell
$env:KUBECONFIG = 'D:\DIIAGE\DI3\Lantern Project\.kube\lantern-prod.yaml'
kubectl get svc argocd-server -n argocd -o wide
kubectl get endpointslice -n argocd -l kubernetes.io/service-name=argocd-server
```

From an approved remote client, test TCP first. The `curl` command deliberately
ignores certificate validation only to test the initial self-signed endpoint:

```powershell
Test-NetConnection 10.4.0.130 -Port 8443
curl.exe -vk https://10.4.0.130:8443/api/version
```

Then verify login in a browser and check the pfSense firewall log for the
expected source address only.
