# DIT – Plateforme de journalisation Grafana / Loki / Alloy

**Dossier d'Installation Technique**

Projet : \<Lantern Project> · 

## 1. Informations sur le document

### 1.1 Historique des versions

| Version | Date | Auteur | Description |
| --- | --- | --- | --- |
| 0.1 | 22/10/2026 | \<Charles> | Création du document |


## 2. Objet et périmètre

### 2.1 Objet

Ce document décrit l'installation et la configuration technique d'une plateforme centralisée de gestion des logs reposant sur :

- **Grafana** : visualisation, exploration et alerting.
- **Loki** : stockage et indexation (par labels) des logs.
- **Grafana Alloy** : agent de collecte déployé sur les serveurs sources, qui remplace Promtail (arrivé en fin de vie).

### 2.2 Périmètre

Inclus : installation des serveurs Loki, de Grafana, déploiement des agents Alloy, configuration réseau et sécurité, procédures de recette, d'exploitation de base, de sauvegarde et de retour arrière.

Exclus : conception des dashboards métier, définition fine des règles d'alerte applicatives, intégration au SIEM.

### 2.3 Hypothèses retenues

- Systèmes cibles : Linux (Debian 12 / Ubuntu 22.04+ / RHEL 9 et dérivés) pour les machines, K3S pour les conteneurs.
- Trois serveurs Loki, un dans chacun des sous-réseaux LOGS, SOC et K3S
- Un seul serveur Grafana, dans le sous-réseau LOGS, sans haute disponibilité applicative.
- Agents Alloy sur les machines des trois sous-réseaux, et dans le cluster K3S (DaemonSet) pour les conteneurs.

## 3. Documents de référence et glossaire

### 3.1 Références

- Documentation Grafana : https://grafana.com/docs/grafana/latest/
- Documentation Loki : https://grafana.com/docs/loki/latest/
- Documentation Grafana Alloy : https://grafana.com/docs/alloy/latest/

### 3.2 Glossaire

| Terme | Définition |
| --- | --- |
| DIT | Dossier d'Installation Technique |
| DAT | Dossier d'Architecture Technique |
| Alloy | Collecteur de télémétrie de Grafana Labs (logs, métriques, traces), configuré en syntaxe Alloy |
| Label | Couple clé/valeur indexé par Loki pour retrouver les flux de logs |
| Chunk | Bloc de logs compressé stocké dans le stockage objet |
| LogQL | Langage de requête de Loki |
| Memberlist | Protocole de gossip utilisé par Loki pour le ring |

## 4. Architecture cible

### 4.1 Vue d'ensemble


Chaque sous-réseau héberge un Loki et ses agents Alloy. Les trois Loki remontent les informations sur le serveur grafana situé dans le sous réseau LOGS. Les agents sont déployés sur les OS physiques ainsi qu'en tant que conteneur, afin de récupérer les logs systèmes et applicatifs

### 4.2 Composants

| Composant | Rôle | Emplacement | Nombre | Port(s) |
| --- | --- | --- | --- | --- |
| Loki | Ingestion, stockage, requêtes | Un par sous-réseau : LOGS, SOC, K3S | 3 | 3100/TCP (HTTP), 9096/TCP (gRPC), 7946/TCP+UDP (memberlist) |
| Grafana | Interface, dashboards, alerting | Sous-réseau LOGS | 1 | 3000/TCP (exposé en HTTPS 443) |
| Alloy (machines) | Collecte journald et fichiers | Serveurs des trois sous-réseaux et nœuds K3S | 1 par machine | 12345/TCP (UI et métriques, local uniquement) |
| Alloy (conteneurs) | Collecte des logs des pods | Cluster K3S, namespace `monitoring` | 1 pod par nœud (DaemonSet) | 12345/TCP (métriques) |
| Point d'entrée Loki | Envoi unique des logs vers les 3 Loki | Sous-réseau LOGS | 443/TCP |


### 4.3 Flux réseau

| Source | Destination | Port | Protocole | Usage |
| --- | --- | --- | --- | --- |
| Alloy (machines LOGS et SOC) | Point d'entrée Loki | 443 | HTTPS | Envoi des logs |
| Alloy (nœuds et pods K3S) | Point d'entrée Loki | 443 | HTTPS | Envoi des logs (sortie du sous-réseau K3S) |
| Point d'entrée Loki | Loki LOGS, SOC et K3S | 3100 | HTTP | Répartition de charge vers les 3 sous-réseaux |
| Loki n | Loki des autres sous-réseaux | 7946 | TCP/UDP | Memberlist |
| Loki n | Loki des autres sous-réseaux | 9096 | gRPC | Réplication et requêtes entre nœuds |
| Loki (3 nœuds) | Stockage S3 | 443 | HTTPS | Chunks et index |
| Grafana (LOGS) | Point d'entrée Loki | 443 | HTTPS | Requêtes LogQL |
| Utilisateurs | Grafana | 443 | HTTPS | Accès à l'interface |
| Grafana | LDAP/OIDC | 636 / 443 | LDAPS / HTTPS | Authentification |
| Supervision | Loki, Grafana, Alloy | 3100 / 3000 / 12345 | HTTP | Métriques Prometheus |

Les flux entre sous-réseaux sont à ouvrir sur les pare-feux : 3100, 7946 (TCP et UDP) et 9096 entre les trois Loki, 443 depuis chaque sous-réseau vers le point d'entrée Loki.

## 5. Prérequis


### 5.1 Système

- OS à jour, synchronisation horaire (chrony/NTP) **obligatoire** : un décalage d'horloge provoque des rejets de logs.
- Accès au dépôt de paquets Grafana.
- Limite de descripteurs de fichiers : `LimitNOFILE=65536` minimum pour Loki.



## 6. Installation de Loki

Procédure à exécuter sur chacun des 3 nœuds (`loki-01`, `loki-02`, `loki-03`).

| Nœud | Sous-réseau | Zone Loki | Adresse IP |
| --- | --- | --- | --- |
| loki-01 | LOGS | logs | \<IP> |
| loki-02 | SOC | soc | \<IP> |
| loki-03 | K3S | k3s | \<IP> |

Chaque nœud déclare sa zone avec `instance_availability_zone`. Loki place alors chacune des 3 copies d'un log dans une zone différente : la perte d'un nœud ou d'un sous-réseau entier laisse l'écriture possible (2 copies sur 3).

### 6.1 Ajout du dépôt et installation (Debian/Ubuntu)

```bash
sudo apt-get install -y gpg
sudo mkdir -p /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install -y loki=<version>
```

Sous RHEL/Rocky : dépôt `https://rpm.grafana.com`, puis `dnf install loki-<version>`.

### 6.2 Préparation des répertoires

```bash
sudo mkdir -p /var/lib/loki/{wal,tsdb-index,tsdb-cache,compactor}
sudo chown -R loki:loki /var/lib/loki
```

### 6.3 Fichier de configuration `/etc/loki/config.yml`
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


## 7. Installation de Grafana

### 7.1 Installation du paquet

```bash
sudo apt-get install -y grafana=<version>      # dépôt Grafana déjà configuré (cf. 6.1)
```

### 7.5 Démarrage et vérification

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now grafana-server
curl -s http://localhost:3000/api/health
```

Résultat attendu : `"database": "ok"`. Se connecter ensuite à `https://grafana.<domaine>`, changer le mot de passe administrateur et tester la source de données (*Connections > Data sources > Loki-01/2/3 > Save & test*).

## 8. Déploiement des agents Alloy

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
### 8.2 Droits d'accès aux logs

L'utilisateur `alloy` doit pouvoir lire les logs cibles :

```bash
sudo usermod -aG adm alloy                 
sudo usermod -aG systemd-journal alloy     
```


### 8.4 Configuration `/etc/alloy/config.alloy

```bash
logging {
  level  = "info"
  format = "logfmt"
}

// ---------- Destination : Loki ----------
loki.write "default" {
  endpoint {
    url = "http://192.168.0.15:3100/loki/api/v1/push"  ##ip du serveur loki dans le sous réseau K3S, à modifier en fonction du subnet
  }

  external_labels = {
    host = constants.hostname,
  }
}

// ---------- Source : journald ----------
loki.source.journal "systemd" {
  max_age    = "120h"
  labels     = { job = "systemd-journal" }
  matches    = "PRIORITY=0 PRIORITY =1 PRIORITY =2 PRIORITY=3 PRIORITY=4"
  forward_to = [loki.write.default.receiver]
}

// ---------- Source : fichiers de logs ----------
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

### 8.5 Démarrage et vérification

```bash
sudo alloy fmt /etc/alloy/config.alloy          # contrôle de syntaxe
sudo systemctl enable --now alloy
sudo systemctl status alloy
journalctl -u alloy -n 50 --no-pager
curl -s http://127.0.0.1:12345/-/ready
```

L'interface d'Alloy (`http://127.0.0.1:12345`) permet de visualiser le graphe des composants et leur état de santé (accès via tunnel SSH).


### 8.7 Alloy dans le cluster K3S (conteneurs)

Les logs des conteneurs sont collectés par un DaemonSet Alloy : un pod par nœud K3S, qui lit via l'API Kubernetes les logs des pods de son nœud. Les nœuds K3S gardent en plus l'agent « machine » du §8.4 pour journald (services `k3s` et `k3s-agent`) : les deux agents lisent des sources différentes, sans doublon.

Prérequis : Helm 3 et un accès `kubectl` administrateur au cluster.

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install alloy grafana/alloy -n monitoring --version <version> -f values-alloy.yaml
```

Fichier `values-alloy.yaml` :

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

Vérification :

```bash
kubectl -n monitoring get daemonset alloy        # un pod prêt par nœud
kubectl -n monitoring logs daemonset/alloy --tail=50
```

Dans Grafana (Explore), la requête `{cluster="<nom-du-cluster>", namespace="kube-system"}` doit retourner des logs récents.

Points d'attention :

- Le label `pod` crée un flux par pod : surveiller le nombre de flux actifs par rapport à `max_global_streams_per_user`.
- Si `loki.<domaine>` utilise un certificat de la PKI interne, monter la CA dans le pod et ajouter un bloc `tls_config` à l'endpoint.
- Les pods Alloy doivent pouvoir joindre le point d'entrée Loki depuis le sous-réseau K3S (443).


Les trois sous-réseaux restent cloisonnés : seuls les flux du §4.3 sont ouverts entre eux. Les ports 7946 et 9096 ne sont accessibles qu'entre les trois nœuds Loki, jamais depuis les machines sources.

## 9. Haute disponibilité et résilience

- **Loki** : réplication ×3 avec une copie par zone (LOGS, SOC, K3S). La perte d'un nœud ou d'un sous-réseau entier laisse l'ingestion et les requêtes disponibles (2 copies sur 3).
- **Grafana** : un seul serveur, sans haute disponibilité. En cas de panne, Loki continue d'ingérer les logs, qui restent consultables après remise en service. La restauration repose sur la sauvegarde de `grafana.db` et de la configuration.
- **Alloy** : en cas d'indisponibilité de Loki, l'agent retente l'envoi avec backoff et conserve les positions de lecture. Dans K3S, Kubernetes redémarre le pod d'un DaemonSet en cas d'échec. Dimensionner la rétention locale des logs (logrotate) sur les serveurs sources selon l'indisponibilité tolérée.


### 10. Opérations courantes

```bash
# Redémarrage
sudo systemctl restart loki|grafana-server|alloy

# Journaux des services
journalctl -u loki -f
journalctl -u grafana-server -f
journalctl -u alloy -f

# Rechargement de la configuration Alloy sans coupure
sudo systemctl reload alloy
```

