# Monitoring Security — Access Control and Protected Communications

Scope: Zabbix, Grafana, Loki, Wazuh and the Alloy agents (Proxmox VMs in the LOGS and SOC subnets, Alloy DaemonSet in K3s)
User story: US-20 — secure access to and communications within the monitoring system
Version: 0.1 (draft for review)
Status: Inventory and target state defined; values marked **TBD** must be confirmed on the live systems

---

# 1. Inventory

Source: pfSense configuration backup (`resilience/Sauvegarde/Pfsense/Configuration/conf`, 2 October 2026) and the Alloy/Grafana installation document. Confirm against the live firewall before acting.

| Component | Host | Subnet | Port(s) | Managed from this repository |
| --- | --- | --- | --- | --- |
| Grafana | 192.168.2.12 | LOGS (192.168.2.0/24) | 3000 | No |
| Zabbix server + frontend | 192.168.2.21 | LOGS | 8080 (frontend), 10051 (server) | No |
| Wazuh (indexer, API, dashboard) | 192.168.3.33 | SOC (192.168.3.0/24) | 9200, 55000, 443 | No |
| Loki (K3s zone) | 192.168.0.15 | K3s (192.168.0.0/24) | 3100 | No |
| Alloy (pods) | DaemonSet, `monitoring` namespace | K3s | 12345 | Yes (`observability/alloy`) |
| Zabbix agents | **TBD** | **TBD** | 10050 | No |
| K3s servers | 192.168.0.10, .20, .30 | K3s | 6443 | Cluster |
| K3s workers | 192.168.0.11, .12, .14 | K3s | — | Cluster |
| Portainer CE | NodePort 30779 on every node | K3s | 30779 | No (manual install) |

# 2. Findings in the current firewall configuration

These rules contradict the [Filtering policy](Filtering%20policy.md) (Deny All, no any/any rule, administrative access through VPN only).

| # | Rule (interface, type) | Effect | Required change |
| --- | --- | --- | --- |
| F1 | WAN, pass, source any, destination any, no description | Any Internet source reaches any internal destination | Delete |
| F2 | LOGS (opt2), pass any/any, "DEBUG" | No isolation of the monitoring subnet | Delete; replace with the flows in §3 |
| F3 | SOC (opt3), pass any/any, "DEBUG" | No isolation of the SOC subnet | Delete; replace with the flows in §3 |
| F4 | NAT WAN `192.214.203.200:3000` → Grafana `:3000` | Grafana published on the Internet over HTTP | Delete; Grafana through VPN and HTTPS only |
| F5 | NAT WAN `:31080` → Zabbix frontend `:8080` | Zabbix frontend published on the Internet over HTTP | Delete; frontend through VPN and HTTPS only |
| F6 | NAT WAN `:3333` → Zabbix VM `:22` | SSH published on the Internet | Delete; SSH through VPN or bastion only |
| F7 | NAT WAN `:8082` and `10.4.0.126:8083` → Wazuh `:443` | Wazuh dashboard published on the Internet | Delete; Wazuh through VPN only |
| F8 | No OpenVPN or WireGuard server configured | No private access path for operators | Create the operator VPN (§4) |
| F9 | WAN, pass, source any, destination any, port 30779 | Portainer (NodePort 30779, ServiceAccount bound to `cluster-admin`) published on the Internet: full control of the cluster behind a single login | Delete; Portainer through VPN only, MFA on Portainer accounts |
| F10 | WAN, pass, source any, destination any, port 80 | Any internal host answering on port 80 is reachable from the Internet | Restrict the destination to the Traefik/HAProxy public entry point |

# 3. Target flow matrix

Every flow not listed here is denied. Each pfSense rule carries the reference of its row as its description.

| Ref | Source | Destination | Port | Protocol | Purpose |
| --- | --- | --- | --- | --- | --- |
| M1 | Operator VPN | Grafana 192.168.2.12 | 443 | HTTPS | Grafana interface |
| M2 | Operator VPN | Zabbix 192.168.2.21 | 443 | HTTPS | Zabbix frontend (only if retained, §6) |
| M3 | Operator VPN | Wazuh 192.168.3.33 | 443 | HTTPS | Wazuh dashboard |
| M4 | Operator VPN | Monitoring VMs | 22 | SSH | Administration |
| M4b | Operator VPN | K3s nodes | 30779 | HTTPS | Portainer |
| M5 | Zabbix agents | Zabbix server 192.168.2.21 | 10051 | TCP, TLS PSK | Active checks |
| M6 | Zabbix server 192.168.2.21 | Zabbix agents | 10050 | TCP, TLS PSK | Passive checks |
| M7 | Alloy (K3s nodes and pods) | Loki entry point | 443 | HTTPS | Log push (target) |
| M8 | Alloy (K3s pods) | Loki 192.168.0.15 | 3100 | HTTP | Log push (current, removed after task 91) |
| M9 | Grafana 192.168.2.12 | Loki entry point | 443 | HTTPS | LogQL queries |
| M10 | Grafana 192.168.2.12 | Wazuh 192.168.3.33 | 9200 | HTTPS | Wazuh indexer data source |
| M11 | Grafana 192.168.2.12 | Wazuh 192.168.3.33 | 55000 | HTTPS | Wazuh API data source |
| M12 | Grafana 192.168.2.12 | Zabbix 192.168.2.21 | 443 | HTTPS | Zabbix API data source (if used) |
| M13 | Grafana 192.168.2.12 | Keycloak | 443 | HTTPS | OIDC login |

# 4. Restricted access (task 92)

## 4.1 Kubernetes (implemented in this repository)

- `monitoring` namespace declared in `platform/namespaces/monitoring.yaml`.
- `observability/alloy/manifests/network-policy.yaml`: no ingress into `monitoring`; Alloy egress limited to CoreDNS, the Kubernetes API and Loki.
- `platform/rabbitmq/network-policy.yaml`: RabbitMQ metrics (15692) reachable from `monitoring` only; AMQP (5672) from cluster pods only.

## 4.2 Outside the cluster (manual)

1. Create the operator VPN on pfSense. Users are authenticated individually, never with a shared account.
2. Apply §2 (deletions) then §3 (allow rules), and export the new pfSense backup to `resilience/Sauvegarde/Pfsense`.
3. Serve Grafana, Zabbix and Wazuh over HTTPS only. Port 3000 and 8080 are no longer reachable from outside their VM.
4. Grafana login through Keycloak (OIDC), local `admin` kept only as break-glass with a password stored in the team vault.

Validation: from the Internet, every port in §2 is closed; from the VPN, M1 to M4 work; from the K3s subnet, Grafana and Zabbix frontends are not reachable.

# 5. Agent-server communication (task 91)

## 5.1 Zabbix agents — TLS with pre-shared key

On each monitored host:

```bash
openssl rand -hex 32 | sudo tee /etc/zabbix/zabbix_agent2.psk
sudo chown zabbix:zabbix /etc/zabbix/zabbix_agent2.psk
sudo chmod 400 /etc/zabbix/zabbix_agent2.psk
```

In `/etc/zabbix/zabbix_agent2.conf`:

```ini
TLSConnect=psk
TLSAccept=psk
TLSPSKIdentity=PSK-<hostname>
TLSPSKFile=/etc/zabbix/zabbix_agent2.psk
```

In the Zabbix frontend, host → *Encryption*: *Connections to host* = PSK, *Connections from host* = PSK only, same identity and key. One key per host; keys are never committed to Git.

Validation: the host stays available with a green *ZBX* icon and an encryption indicator; `zabbix_get -s <host> -k agent.ping` without `--tls-connect psk` is rejected.

## 5.2 Alloy → Loki

1. Publish Loki behind the HTTPS entry point (443) with a certificate from the internal CA.
2. Require authentication on that entry point (basic auth or client certificate).
3. In `observability/alloy/values.yaml`, set the endpoint to `https://`, add `tls_config` with the CA and `basic_auth` read from a Secret mounted through `alloy.mounts.extra`. The Secret is created outside Git.
4. Remove port 3100 from `alloy-egress` and flow M8.

# 6. Zabbix roles (task 93, if the frontend is retained)

Decision required: **TBD** — keep the Zabbix frontend, or use Grafana with the Zabbix data source only. If the frontend is removed, only the `grafana-api` account below is kept.

| Role | User type | Frontend access | API access | Host groups | Holders |
| --- | --- | --- | --- | --- | --- |
| Super admin | Super admin | Full | Full | All (read-write) | 2 named operators, **TBD** |
| Ops-Admin | Admin | Monitoring, Inventory, Data collection | Disabled | Assigned groups (read-write) | **TBD** |
| Ops-Viewer | User | Dashboards, Monitoring | Disabled | Assigned groups (read) | **TBD** |
| grafana-api | User | None (frontend access disabled) | Read methods only | All (read) | Service account used by Grafana |

Mandatory settings:

- Default `Admin` password changed; `guest` user disabled.
- Authentication through Keycloak (SAML), MFA (TOTP) for Super admin and Ops-Admin.
- Each person has a named account; no shared accounts.

Validation: an Ops-Viewer cannot open *Data collection* or edit a host; the `grafana-api` account cannot log in to the frontend.

# 7. Data source permissions and access (task 95)

Fill one row per data source configured in Grafana (*Connections → Data sources*).

| Data source | URL | Account used | Account rights | TLS verified | Credentials in secure fields | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Loki (LOGS) | **TBD** | None (Loki `auth_enabled: false`) | Full read and write | **TBD** | N/A | Fails until §5.2 |
| Loki (SOC) | **TBD** | **TBD** | **TBD** | **TBD** | **TBD** | **TBD** |
| Loki (K3s) | **TBD** | **TBD** | **TBD** | **TBD** | **TBD** | **TBD** |
| Wazuh indexer | https://192.168.3.33:9200 | **TBD** | Read only on `wazuh-alerts-*` | **TBD** | **TBD** | **TBD** |
| Wazuh API | https://192.168.3.33:55000 | **TBD** | Read only | **TBD** | **TBD** | **TBD** |
| Zabbix | **TBD** | `grafana-api` | §6 | **TBD** | **TBD** | **TBD** |

Expected for every row: dedicated read-only service account (never `admin`), *Skip TLS verify* disabled, secrets only in the secure fields.

Grafana OSS has no per-data-source permissions (Grafana Enterprise or Cloud feature). Access to data is controlled by:

- organisation roles: only Grafana admins edit data sources;
- folder permissions by team for dashboards;
- no *Explore* access for Viewers.

Test procedure with a Viewer account:

1. Open the dashboards of the assigned folder: allowed.
2. Open a dashboard in another team's folder: denied.
3. Open *Connections → Data sources* or call `GET /api/datasources`: denied.
4. Open *Explore*: not available.

Record the Grafana version and the result of each step with a screenshot.

# 8. Open questions

| Question | Owner |
| --- | --- |
| Is the Zabbix frontend retained? | **TBD** |
| Is the 2 October pfSense backup still current? | **TBD** |
| Which hosts run a Zabbix agent? | **TBD** |
| Grafana and Zabbix versions, OSS or Enterprise? | **TBD** |
| VPN technology (OpenVPN or WireGuard) and user directory | **TBD** |
