# Private Argo CD access

Target URL: `https://10.4.111.200:8443`. This address must belong to pfSense
on the operator-accessible private network before cutover. Argo CD terminates
TLS. No public HAProxy frontend is used for Argo CD.

## pfSense cutover

1. Disable public NAT `192.214.203.200:8443` and any public Argo CD HAProxy
   frontend. Remove the associated public pass rule if it remains.
2. Create a TCP port-forward on the interface receiving the approved private
   administrator network: destination `10.4.111.200`, port `8443`, redirect
   target `192.168.0.30`, redirect port `30443`.
3. Restrict source to the administrator network or VPN, including the associated
   firewall pass rule. Evaluate reflection only if required by the private path.
4. Keep Kubernetes HTTPS NodePort `30443`. Do not publish port `30080`.

The target preserves the previous working NAT destination. Changing the URL
alone does not close public exposure; disable the old public NAT/frontend too.

## TLS and Keycloak

Provision a server certificate containing IP SAN `10.4.111.200` in Secret
`argocd/argocd-server-tls`, outside Git, and trust its issuer on operator
workstations. The existing generated certificate does not cover this IP.
Editing Helm values does not provision that certificate or change pfSense.

Keep issuer `https://groupe7.diiage.org/auth/realms/master`. In the Keycloak
`argocd` client, allow callback `https://10.4.111.200:8443/auth/callback`
and web origin `https://10.4.111.200:8443`. Test private login before removing
old callback entries or recovery access.

## Validation

From an approved private network:

```powershell
curl.exe --fail --cacert .\argocd-private-ca.crt https://10.4.111.200:8443/api/version
```

Test OIDC login and confirm that public port 8443 no longer reaches Argo CD.
Harbor remains on `https://10.4.111.200:18443`; its CD is unchanged.
