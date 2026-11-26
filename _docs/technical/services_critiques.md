# Services critiques par serveur

Proposition du 26/11/2026, squad INFRA - Logging, **à valider avec l'équipe**. Elle s'appuie sur l'inventaire des services (`INVENTAIRE-services-par-vm.md`) et prépare les priorités des futurs triggers de supervision.

## 1. Critères de criticité

| Niveau | Définition | Priorité de supervision (proposition) |
|---|---|---|
| **Critique (P1)** | Son arrêt coupe un service dont d'autres machines dépendent, ou fait perdre des données (logs, alertes, supervision, secrets). | Haute : alerte immédiate |
| **Important (P2)** | Son arrêt dégrade l'exploitation (interface indisponible, perte de visibilité, protection réduite) sans perte de données ni coupure pour les autres machines. | Moyenne : alerte en heures ouvrées |
| **Secondaire (P3)** | Le reste du système (terminaux, sessions utilisateur, services de base de l'OS). | Pas d'item individuel |

## 2. Services critiques par serveur

| Serveur | Service critique (unité) | Impact si arrêt | Services importants (P2) |
|---|---|---|---|
| zabbix-bdd-01 | `postgresql@17-main.service` | Toute la supervision s'arrête : le serveur Zabbix ne peut plus écrire ni lire ses données. | — |
| zabbix-server-01 | `zabbix-server.service` | Plus de collecte, plus de triggers ni d'alertes sur tout le parc. | `snmpd.service` |
| zabbix-front-01 | — | La supervision continue de fonctionner sans le frontend. | `nginx.service` et `php8.4-fpm.service` : plus d'interface web, ni d'API Zabbix (8080) utilisée par Ansible |
| loki-01 | `loki.service` | Les logs des LXC ne sont plus reçus. Au-delà de quelques minutes de réessais, ils sont perdus. | — |
| loki-02 | `loki.service` | Idem pour les logs du cluster K3s (pods et nœuds). | — |
| loki-03 | `loki.service` | Idem pour les logs du SOC. | — |
| grafana-01 | — | Les logs restent stockés : seuls les dashboards et l'exploration sont indisponibles. | `grafana-server.service` |
| notify-01 | `ntfy.service` | Les notifications ne partent plus (à confirmer : canal d'alerte de Zabbix). | — |
| vault-01 | `docker.service` et `containerd.service` | Si Vault tourne en conteneur (à confirmer), les secrets ne sont plus servis. **Le vrai service critique est le conteneur, invisible dans l'inventaire systemd** (voir points à valider). | — |
| wazuh-01 | `wazuh-manager.service`, `wazuh-indexer.service` et `filebeat.service` | Les événements de sécurité ne sont plus analysés ni stockés (le manager analyse, filebeat transporte vers l'indexer, qui stocke). | `wazuh-dashboard.service` : plus d'interface |
| kube-master-03 | `k3s.service` (control-plane et etcd) et `keepalived.service` | Le cluster perd un membre etcd et un nœud du control-plane. keepalived porte l'adresse virtuelle (à confirmer : celle de l'API). | `iscsid.service` |
| kube-worker-01, 02, 04 | `k3s-agent.service` | Le nœud n'exécute plus de pods : les applications de jeu qu'il porte tombent. | `iscsid.service` (prérequis habituel des volumes Longhorn, ADR-004) |
| lxc-ansible-01 | — | Aucun service de production : seul l'outillage d'administration est affecté. | `ssh.service`, `alloy.service` |

## 3. Services transverses (P2 sur toutes les machines)

À traiter par un template Zabbix unique plutôt que machine par machine.

| Unité | Rôle | Impact si arrêt | Présent sur |
|---|---|---|---|
| `ssh.service` | Accès d'administration | Plus d'accès SSH (reste l'accès par console Proxmox) | les 15 |
| `zabbix-agent2.service` | Supervision de la machine | La machine n'est plus supervisée | 14 (pas lxc-ansible-01) |
| `alloy.service` | Collecte des logs | Les logs de la machine ne remontent plus | 11 |
| `wazuh-agent.service` | Détection côté SOC | La machine n'est plus surveillée par Wazuh | 11 |
| `fail2ban.service` | Protection contre les attaques par force brute sur SSH | Protection réduite | 13 |

## 4. Chaînes de dépendance

L'ordre dans lequel un arrêt se propage, utile pour hiérarchiser les alertes :

- **Zabbix** : `postgresql` (zabbix-bdd-01) → `zabbix-server` (zabbix-server-01) → `nginx` / `php-fpm` (zabbix-front-01). Les agents Zabbix des 14 machines envoient vers `zabbix-server` (port 10051).
- **Logs** : Alloy des hôtes et du DaemonSet K3s → Loki (01, 02 ou 03 selon la zone) → datasources de Grafana.
- **SOC** : `wazuh-agent` → `wazuh-manager` → `filebeat` → `wazuh-indexer` → `wazuh-dashboard`.
- **Alertes** : Zabbix → ntfy (à confirmer).
- **Cluster K3s** : `k3s` (control-plane et etcd) → `k3s-agent` (workers) → pods applicatifs.