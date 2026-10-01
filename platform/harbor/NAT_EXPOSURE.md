# Harbor exposure through pfSense

This runbook prepares Harbor exposure through pfSense without applying any
firewall change automatically. Apply it only to trusted development or VPN
networks unless a separate Internet-facing security review has been completed.

## Current Kubernetes endpoint

Harbor is routed by Traefik using TLS and the host
`registry.lantern.diiage`. Traefik currently listens on:

| Worker | HTTPS target |
| --- | --- |
| `kube-worker-01` | `192.168.0.11:443` |
| `kube-worker-02` | `192.168.0.12:443` |
| `kube-worker-04` | `192.168.0.14:443` |

The Harbor health endpoint is:

```text
https://registry.lantern.diiage/api/v2.0/ping
```

It must return HTTP `200` with `Pong`.

## pfSense NAT rule

In **Firewall > NAT > Port Forward**, select **Add** and use:

| Field | Value |
| --- | --- |
| Interface | The trusted development or VPN ingress interface |
| Address family | IPv4 |
| Protocol | TCP |
| Source | Approved developer/CI network alias |
| Destination | Interface address, or the dedicated Harbor virtual IP |
| Destination port range | HTTPS (`443`) to HTTPS (`443`) |
| Redirect target IP | `192.168.0.11` |
| Redirect target port | HTTPS (`443`) |
| Description | `Harbor HTTPS to Traefik` |
| Filter rule association | Add associated filter rule |

Save, apply the changes, then confirm in **Firewall > Rules** that the generated
pass rule has the same restricted source alias. Do not expose ports `80`,
`5432`, `6379`, `5000`, `8001` or any Longhorn service.

The target above is a single worker and therefore is not highly available. A
stable internal VIP or health-checked reverse proxy should replace it before an
HA claim is made. Do not create multiple independent NAT rules for the same
destination port without a load-balancing mechanism.

## Client hostname without DNS

No DNS record is required, but each approved client must still send the Harbor
hostname because the TLS certificate and Harbor token service are configured
for `registry.lantern.diiage`.

On Windows, run the editor as Administrator and add this line to
`C:\Windows\System32\drivers\etc\hosts`:

```text
<PFSENSE_NAT_IP> registry.lantern.diiage
```

On Linux, add the same entry to `/etc/hosts`:

```text
<PFSENSE_NAT_IP> registry.lantern.diiage
```

Replace `<PFSENSE_NAT_IP>` with the pfSense interface address or dedicated
virtual IP selected as the NAT destination. Do not map the hostname directly to
`192.168.0.11` on remote clients: doing so would bypass the required NAT path.

The same hosts-file mapping is required on self-hosted CI runners. Hosted CI
runners cannot reach this private NAT endpoint unless a private runner or VPN
route is provided.

Harbor's token service uses its configured external URL. Clients must always
use `registry.lantern.diiage`; using a raw IP address will fail certificate and
token-service validation.

## TLS

The current certificate is issued by Harbor's private generated CA. Export only
`ca.crt` from the `harbor-ingress` Secret and add it to the trust store of each
approved workstation, CI runner and K3s node.

If the endpoint will be reachable from the Internet, stop here. Replace the
private certificate with a publicly trusted certificate, enforce OIDC/MFA,
restrict the administration surface, configure rate limiting and validate
tested backups before opening the rule.

## Post-pfSense checks

From an approved client:

```powershell
Test-NetConnection registry.lantern.diiage -Port 443
curl.exe --fail https://registry.lantern.diiage/api/v2.0/ping
docker login registry.lantern.diiage
```

Then push and pull a disposable image in a non-production project. Confirm that
Harbor records the artifact and that Trivy produces a scan result.

In pfSense, confirm that **Status > System Logs > Firewall** shows only expected
source addresses reaching the Harbor rule. A timeout generally indicates the
NAT/filter path; a certificate error generally indicates missing CA trust or an
incorrect hostname.
