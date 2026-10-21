# Private Harbor access

Target URL: `https://10.4.111.200:18443`. Harbor terminates TLS on the existing
HTTPS NodePort `30444`. Do not expose Harbor through public NAT or HAProxy.
Argo CD separately uses private URL `https://10.4.111.200:8443`.

## pfSense cutover

1. Ensure `10.4.111.200` belongs to pfSense on the approved private network.
2. Disable public NAT `192.214.203.200:18443` and any public Harbor HAProxy
   frontend. Remove remaining associated public firewall pass rules.
3. On the private-facing interface, forward TCP destination
   `10.4.111.200:18443` to `192.168.0.11:30444`. Restrict source networks to
   approved developer, CI and cluster networks and associate a matching pass rule.
4. Verify this route from workstations, ARC runners and K3s nodes. Private
   NAT reflection or an equivalent internal route may be needed.

Changing Harbor's externalURL does not close the old public exposure.
Do not publish HTTP port 30082, registry port 5000, or database/cache ports.

## TLS and credentials

Before merging the private endpoint configuration:

- Rotate the existing `harbor/harbor-nginx` TLS certificate to include IP SAN
  `10.4.111.200`. The current certificate does not cover this IP. Argo CD
  ignores Secret data changes, so changing auto.commonName alone will not
  rotate the live certificate. Keep private keys outside Git and logs.
- Distribute the new public CA to approved client trust stores, ARC ConfigMap
  `arc-runners/harbor-ca` and K3s/containerd registry trust. ARC's Docker mount
  uses `/etc/docker/certs.d/10.4.111.200:18443/ca.crt`.
- Regenerate application image pull credentials with registry key
  `10.4.111.200:18443`, outside Git. Keep the old entry during migration.
- Verify that each referenced image/tag exists. This change renames the
  registry endpoint and does not copy or publish any images.

The shared CD workflow, application callers, promotion allowlist and image
references all use `10.4.111.200:18443`. Merge the GitOps correction and the
caller updates in a coordinated window; avoid old-domain release promotions
once the allowlist changes. Do not disable TLS verification.

## Validation

```powershell
curl.exe --fail --cacert .\harbor-ca.crt https://10.4.111.200:18443/api/v2.0/ping
curl.exe --cacert .\harbor-ca.crt --include https://10.4.111.200:18443/v2/
```

Expect `Pong` for ping and an unauthenticated 401 for `/v2/` with token realm
`https://10.4.111.200:18443/service/token`. Then test an authenticated push and
pull. Confirm the old public endpoint no longer reaches Harbor.
Preserve volumes, Secrets and artifacts during migration.
