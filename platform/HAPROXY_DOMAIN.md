# Argo CD and Harbor on groupe7.diiage.org

This is a migration procedure, not evidence that pfSense has been changed.
DNS already resolves `groupe7.diiage.org` to `192.214.203.200`.

| Public URL | HAProxy backend | Kubernetes TLS endpoint |
| --- | --- | --- |
| `https://groupe7.diiage.org:8443` | `lantern-argocd` | `192.168.0.11:30443` |
| `https://groupe7.diiage.org:18443` | `lantern-harbor` | `192.168.0.11:30444` |

Keep the existing frontend on port 443, including the website and Keycloak
`/auth` routing. These two new frontends have separate ports and backends.
Do not combine the Argo CD and Harbor backend servers into one pool.

## pfSense HAProxy preparation

1. Back up the pfSense configuration. Check that its management interface is
   not listening on the two requested ports.
2. In Services > HAProxy > Backends create the two backends above, each with
   its explicit internal address and port. Enable backend SSL and certificate
   verification. Import the Harbor CA and the Argo CD self-signed server
   certificate into the corresponding backend trust configuration. These are
   public certificates; no private key needs to leave Kubernetes. Verify each
   backend in HAProxy stats before cutover. If the installed HAProxy version
   requires a matching DNS verification name, provision a suitable backend
   certificate before cutover; do not disable verification.
3. In Services > HAProxy > Frontends create separate HTTPS frontends on the
   public-facing address, ports 8443 and 18443. Use the existing trusted
   certificate covering `groupe7.diiage.org` for both SSL-offloading listeners.
   Use HTTP mode and the corresponding default backend from the table.
   Preserve the Host header including its port. Set `X-Forwarded-Proto` to
   `https`. Use suitable client/server timeouts for large image uploads.
4. Allow the two ports to pfSense itself from the approved client networks.
   Existing NAT port-forward rules on these same address/port pairs must be
   disabled at cutover so traffic reaches HAProxy instead of bypassing it.
   Keep the old rule definitions for rollback. Apply the HAProxy configuration.
5. Confirm access from the workstation and from the cluster/ARC network. If
   the public IP is not reachable internally, use split DNS pointing the same
   domain to a pfSense address on which both new frontends also listen. Do not
   point the domain directly to a worker, whose ports are 30443 and 30444.

The TLS certificate presented to public clients comes from HAProxy. Harbor's
existing auto certificate and Argo CD's server certificate remain backend
certificates. Changing the public URL does not replace those certificates.

## GitOps and application prerequisites

Before merging the domain change:

- Both HAProxy endpoints must pass HTTPS verification with the existing
  trusted domain certificate.
- In the Keycloak `argocd` client, add redirect URI
  `https://groupe7.diiage.org:8443/auth/callback` and web origin
  `https://groupe7.diiage.org:8443`. Keep previous entries until login succeeds.
- Prepare `harbor-pull` credentials for `groupe7.diiage.org:18443` outside Git
  in all application namespaces. The bootstrap script uses the new address.
- Verify containerd node trust and routing to the new address. For ARC, the
  Docker certificate mount now uses the domain and port. Existing private CA
  bundles can remain; the public endpoint uses the trusted frontend chain.
- Check that each image/tag referenced by the overlays exists in Harbor. The
  endpoint migration does not publish or copy images.

After merging GitOps, update application CD callers to the exact new shared
workflow commit. The workflow registry, caller image names, promotion
allowlist, imagePullSecrets and Kustomize references must use the same domain
and port. Do not run old IP-based callers after the promotion allowlist changes.

## Validation

```powershell
curl.exe --fail https://groupe7.diiage.org:8443/api/version
curl.exe --fail https://groupe7.diiage.org:18443/api/v2.0/ping
curl.exe --include https://groupe7.diiage.org:18443/v2/
```

The last request should return 401 with a token realm starting with
`https://groupe7.diiage.org:18443/service/token`. It is an unauthenticated
registry probe, not a failed login. Do not use `--insecure` for acceptance.
Test Argo CD OIDC login and an authenticated image push/pull separately. For
the HTTP-mode proxy, use `argocd login groupe7.diiage.org:8443 --grpc-web`.

## Rollback

Revert the domain change in Git and the caller workflow references, wait for
Argo CD to report the reverted revision, then restore the old NAT listeners.
Keep old pull-secret registry entries and Keycloak callback entries during
the transition. Do not change parent Application reconciliation policy or
remove volumes, Secrets, or registry artifacts.

References: [pfSense HAProxy](https://docs.netgate.com/pfsense/en/latest/packages/haproxy.html),
[Argo CD TLS](https://argo-cd.readthedocs.io/en/stable/operator-manual/tls/),
[Harbor HTTPS](https://goharbor.io/docs/2.14.0/install-config/configure-https/).
