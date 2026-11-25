# Technical Installation Document

Project: <Lantern Project> ·

# 1. Document information

# 1.1 Version history
Version	Date	Author	Description
0.1	22/10/2026	<Charles>	Document creation
# 2. Purpose and scope

# 2.1 Purpose

This document describes the installation and technical configuration of a centralized log management platform based on:

Grafana: visualization, exploration and alerting.
Loki: storage and indexing (by labels) of logs.
Grafana Alloy: collection agent deployed on the source servers, replacing Promtail (now end-of-life).

# 2.2 Scope

Included: installation of the Loki servers and Grafana, deployment of the Alloy agents, network and security configuration, acceptance testing, basic operations, backup and rollback procedures.

Excluded: design of business dashboards, detailed definition of application alert rules, SIEM integration.

# 2.3 Assumptions

Target systems: Linux (Debian 12 / Ubuntu 22.04+ / RHEL 9 and derivatives) for the machines, K3S for the containers.
Three Loki servers, one in each of the LOGS, SOC and K3S subnets.
A single Grafana server, in the LOGS subnet, without application-level high availability.
Alloy agents on the machines of the three subnets, and in the K3S cluster (DaemonSet) for the containers.

# 3. Reference documents and glossary

# 3.1 References

Grafana documentation: https://grafana.com/docs/grafana/latest/
Loki documentation: https://grafana.com/docs/loki/latest/
Grafana Alloy documentation: https://grafana.com/docs/alloy/latest/

# 3.2 Glossary

Term	Definition
DIT	Technical Installation Document (Dossier d'Installation Technique)
DAT	Technical Architecture Document (Dossier d'Architecture Technique)
Alloy	Grafana Labs telemetry collector (logs, metrics, traces), configured using Alloy syntax
Label	Key/value pair indexed by Loki to find log streams
Chunk	Compressed block of logs stored in object storage
LogQL	Loki's query language


# 4. Target architecture

# 4.1 Overview

Each subnet hosts a Loki instance and its Alloy agents. The three Loki instances report to the Grafana server located in the LOGS subnet. Agents are deployed on the physical OSes as well as containers, in order to collect both system and application logs.

# 4.2 Components

Component	Role	Location	Count	Port(s)
Loki	Ingestion, storage, queries	One per subnet: LOGS, SOC, K3S	3	3100/TCP (HTTP), 9096/TCP (gRPC), 7946/TCP+UDP (memberlist)
Grafana	Interface, dashboards, alerting	LOGS subnet	1	3000/TCP (exposed over HTTPS 443)
Alloy (machines)	Collection of journald and files	Servers of the three subnets and K3S nodes	1 per machine	12345/TCP (UI and metrics, local only)
Alloy (containers)	Collection of pod logs	K3S cluster, monitoring namespace	1 pod per node (DaemonSet)	12345/TCP (metrics)
Loki entry point	Single endpoint for sending logs to the 3 Loki instances	LOGS subnet	443/TCP	

# 4.3 Network flows

Source	Destination	Port	Protocol	Usage
Alloy (LOGS and SOC machines)	Loki entry point	443	HTTPS	Sending logs
Alloy (K3S nodes and pods)	Loki entry point	443	HTTPS	Sending logs (leaving the K3S subnet)
Loki entry point	Loki LOGS, SOC and K3S	3100	HTTP	Load balancing across the 3 subnets
Loki n	Loki in the other subnets	7946	TCP/UDP	Memberlist
Loki n	Loki in the other subnets	9096	gRPC	Replication and inter-node queries
Loki (3 nodes)	S3 storage	443	HTTPS	Chunks and index
Grafana (LOGS)	Loki entry point	443	HTTPS	LogQL queries
Users	Grafana	443	HTTPS	Interface access
Grafana	LDAP/OIDC	636 / 443	LDAPS / HTTPS	Authentication
Monitoring	Loki, Grafana, Alloy	3100 / 3000 / 12345	HTTP	Prometheus metrics

Flows between subnets must be opened on the firewalls: 3100, 7946 (TCP and UDP) and 9096 between the three Loki instances, and 443 from each subnet to the Loki entry point.

# 5. Prerequisites

# 5.1 System

OS up to date, time synchronization (chrony/NTP) mandatory: a clock drift causes log rejections.
Access to the Grafana package repository.
File descriptor limit: LimitNOFILE=65536 minimum for Loki.

# 6. Installing Loki

Procedure to run on each of the 3 nodes (loki-01, loki-02, loki-03).

Node    SubnetLoki      zone	
loki-01	    LOGS	    logs	
loki-02	    SOC	        soc	
loki-03	    K3S	        k3s	

Each node declares its zone with instance_availability_zone. Loki then places each of the 3 copies of a log in a different zone: the loss of a node or of an entire subnet still allows writes (2 copies out of 3).

# 6.1 Adding the repository and installing (Debian/Ubuntu)
```bash
sudo apt-get install -y gpg
sudo mkdir -p /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install -y loki=<version
```

On RHEL/Rocky: repository https://rpm.grafana.com, then dnf install loki-<version>.

# 6.2 Preparing the directories
```bash
sudo mkdir -p /var/lib/loki/{wal,tsdb-index,tsdb-cache,compactor}
sudo chown -R loki:loki /var/lib/loki
```

# 6.3 Configuration file /etc/loki/config.yml
```bash
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  instance_addr: 127.0.0.1
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

limits_config:
  retention_period: 72h
  retention_stream:
    - selector: '{category="security"}'
      priority: 1
      period: 4320h

    - selector: '{category="backup"}'
      priority: 2
      period: 720h

    - selector: '{level=~"error|fatal|critical|warn"}'
      priority: 3
      period: 168h

    - selector: '{category="cicd"}'
      priority: 4
      period: 72h

compactor:
  working_directory: /tmp/loki/boltdb-shipper-compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
  delete_request_store: filesystem
```

## 7. Installing Grafana

### 7.1 Package installation

```bash
sudo apt-get install -y grafana=<version>      # Grafana repository already configured (see 6.1)
```

### 7.5 Startup and verification

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now grafana-server
curl -s http://localhost:3000/api/health
```

Expected result: `"database": "ok"`. Then log in at `https://grafana.<domain>`, change the administrator password and test the data source (*Connections > Data sources > Loki-01/2/3 > Save & test*).

## 8. Deploying the Alloy agents

### 8.1 Installation (Linux)
```bash 
sudo apt install gpg
sudo mkdir -p /etc/apt/keyrings
sudo wget -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
sudo chmod 644 /etc/apt/keyrings/grafana.asc
echo "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install alloy
```
### 8.2 Log access permissions

The `alloy` user must be able to read the target logs:

```bash
sudo usermod -aG adm alloy                 
sudo usermod -aG systemd-journal alloy     
```


### 8.4 Configuration `/etc/alloy/config.alloy`

```bash
logging {
  level  = "info"
  format = "logfmt"
}

// ---------- Destination: Loki ----------
loki.write "default" {
  endpoint {
    url = "http://192.168.0.15:3100/loki/api/v1/push"  ##IP of the Loki server in the K3S subnet, to be changed depending on the subnet
  }

  external_labels = {
    host = constants.hostname,
  }
}

// ---------- Source: journald ----------
loki.source.journal "systemd" {
  max_age    = "120h"
  labels     = { job = "systemd-journal" }
  matches    = "PRIORITY=0 PRIORITY =1 PRIORITY =2 PRIORITY=3 PRIORITY=4"
  forward_to = [loki.write.default.receiver]
}

// ---------- Source: log files ----------
local.file_match "varlogs" {
  path_targets = [
    { __path__ = "/var/log/syslog",   job = "syslog" },
    { __path__ = "/var/log/auth.log", job = "auth" },
    { __path__ = "var/log/pods", job = "pods" },
  ]
}

loki.source.file "varlogs" {
  targets    = local.file_match.varlogs.targets
  forward_to = [loki.write.default.receiver]
}
```

### 8.5 Startup and verification

```bash
sudo alloy fmt /etc/alloy/config.alloy          # syntax check
sudo systemctl enable --now alloy
sudo systemctl status alloy
journalctl -u alloy -n 50 --no-pager
curl -s http://127.0.0.1:12345/-/ready
```

The Alloy interface (`http://127.0.0.1:12345`) lets you view the component graph and their health status (access via SSH tunnel).


### 8.7 Alloy in the K3S cluster (containers)

Container logs are collected by an Alloy DaemonSet: one pod per K3S node, which reads the logs of the pods on its node via the Kubernetes API. K3S nodes also keep the "machine" agent from §8.4 for journald (`k3s` and `k3s-agent` services): the two agents read different sources, so there are no duplicates.

Prerequisites: Helm 3 and administrator `kubectl` access to the cluster.

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install alloy grafana/alloy -n monitoring --version <version> -f values-alloy.yaml
```

`values-alloy.yaml` file:

```yaml
alloy:
  configMap:
    content: |-
      discovery.kubernetes "pods" {
        role = "pod"
      }

      discovery.relabel "pod_logs" {
        targets = discovery.kubernetes.pods.targets

        rule {
          target_label = "job"
          replacement  = "kubernetes-pods"
        }

        rule {
          source_labels = ["__meta_kubernetes_pod_uid", "__meta_kubernetes_pod_container_name"]
          separator     = "/"
          action        = "replace"
          replacement   = "/var/log/pods/*$1/*.log"
          target_label  = "__path__"
        }

        rule {
          source_labels = ["__meta_kubernetes_namespace"]
          action        = "replace"
          target_label  = "namespace"
        }

        rule {
          source_labels = ["__meta_kubernetes_pod_name"]
          action        = "replace"
          target_label  = "pod"
        }

        rule {
          source_labels = ["__meta_kubernetes_pod_container_name"]
          action        = "replace"
          target_label  = "container"
        }
      }

      local.file_match "pod_logs" {
        path_targets = discovery.relabel.pod_logs.output
      }

      loki.source.file "pod_logs" {
        targets    = local.file_match.pod_logs.targets
        forward_to = [loki.write.loki_endpoint.receiver]
      }

      loki.write "loki_endpoint" {
        endpoint {
          url = "http://192.168.0.15:3100/loki/api/v1/push"
        }
      }
    create: true
  mounts:
    varlog: true
  securityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
      - ALL
    runAsGroup: 0
    runAsUser: 0
```

Verification:

```bash
kubectl -n monitoring get daemonset alloy        # one ready pod per node
kubectl -n monitoring logs daemonset/alloy --tail=50
```

In Grafana (Explore), the query `{cluster="<cluster-name>", namespace="kube-system"}` must return recent logs.

Points of attention:

- The `pod` label creates one stream per pod: monitor the number of active streams against `max_global_streams_per_user`.
- If `loki.<domain>` uses a certificate from the internal PKI, mount the CA in the pod and add a `tls_config` block to the endpoint.
- The Alloy pods must be able to reach the Loki entry point from the K3S subnet (443).


The three subnets remain segregated: only the flows in §4.3 are open between them. Ports 7946 and 9096 are only accessible between the three Loki nodes, never from the source machines.

## 9. High availability and resilience

- **Loki**: ×3 replication with one copy per zone (LOGS, SOC, K3S). The loss of a node or of an entire subnet leaves ingestion and queries available (2 copies out of 3).
- **Grafana**: a single server, without high availability. In case of failure, Loki keeps ingesting logs, which remain available for consultation once the service is restored. Recovery relies on the backup of `grafana.db` and of the configuration.
- **Alloy**: if Loki is unavailable, the agent retries sending with backoff and keeps its reading positions. In K3S, Kubernetes restarts a DaemonSet pod on failure. Size the local log retention (logrotate) on the source servers according to the tolerated downtime.


### 10. Routine operations

```bash
# Restart
sudo systemctl restart loki|grafana-server|alloy

# Service logs
journalctl -u loki -f
journalctl -u grafana-server -f
journalctl -u alloy -f

# Reload the Alloy configuration without downtime
sudo systemctl reload alloy
```