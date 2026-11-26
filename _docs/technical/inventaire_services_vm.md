# Inventaire des services systemd par VM

Relevé du 26/11/2026, squad INFRA - Logging. Sert de base aux items Zabbix `systemctl is-active` (colonne « Unité ») et `proc.num` (colonne « Processus »).

## 1. Méthode et périmètre

Un script en lecture seule (annexe A) a été exécuté par Ansible sur toutes les machines de `hosts.ini`. Pour chaque service **en cours d'exécution** (`running`), il relève : l'unité systemd, son état au démarrage, le nom du processus principal (celui qu'attend `proc.num`) et les ports en écoute de ce processus.

15 machines inventoriées :

| Hôte (inventaire) | Nom système | IP | Type | Rôle (déduit du nom et des services) |
|---|---|---|---|---|
| zabbix-bdd-01 | lxc-zabbix-bdd-01 | 192.168.2.22 | LXC | Base PostgreSQL de Zabbix |
| zabbix-server-01 | lxc-zabbix-server-01 | 192.168.2.20 | LXC | Serveur Zabbix |
| zabbix-front-01 | lxc-zabbix-front-01 | 192.168.2.21 | LXC | Frontend web Zabbix |
| loki-01 | lxc-loki-01 | 192.168.2.10 | LXC | Loki des journaux LXC |
| loki-02 | lxc-loki-02 | 192.168.0.15 | LXC | Loki du cluster K3s |
| loki-03 | lxc-loki-03 | 192.168.3.13 | LXC | Loki du SOC |
| grafana-01 | lxc-grafana-01 | 192.168.2.12 | LXC | Grafana |
| notify-01 | lxc-notify-01 | 192.168.2.31 | LXC | ntfy (notifications) |
| vault-01 | lxc-vault | 10.4.111.123 | LXC | Vault, probablement en conteneur Docker (à confirmer) |
| wazuh-01 | lxc-wazuh-01 | 192.168.3.33 | LXC | Wazuh (manager, indexer, dashboard) |
| kube-master-03 | kube-master-03 | 192.168.0.30 | VM | Control-plane K3s avec etcd |
| kube-worker-01 | kube-worker-01 | 192.168.0.11 | VM | Worker K3s |
| kube-worker-02 | kube-worker-02 | 192.168.0.12 | VM | Worker K3s |
| kube-worker-04 | kube-worker-04 | 192.168.0.14 | VM | Worker K3s |
| lxc-ansible-01 | lxc-ansible-01 | non relevée | LXC | Poste Ansible |

Hors périmètre : kube-master-01 et kube-master-02 (lignes commentées dans `hosts.ini`, donc non interrogés) et les machines absentes de l'inventaire (pfSense, Proxmox, Windows, etc.). kube-worker-03 n'existe plus (absent du cluster K3s).

## 2. Socle commun

Services présents sur (presque) toutes les machines. À superviser une fois pour toutes via un template, pas machine par machine.

| Unité | Processus (`proc.num`) | Port | Présent sur |
|---|---|---|---|
| `ssh.service` | `sshd` | tcp/22 | les 15 |
| `cron.service` | `cron` | n/a | les 15 |
| `dbus.service` | `dbus-daemon` | n/a | les 15 |
| `systemd-journald.service` | `systemd-journal` | n/a | les 15 |
| `systemd-logind.service` | `systemd-logind` | n/a | les 15 |
| `zabbix-agent2.service` | `zabbix_agent2` | tcp/10050 (toutes interfaces) | 14 (sauf lxc-ansible-01) |
| `fail2ban.service` | `fail2ban-server` | n/a | 13 (sauf lxc-ansible-01 et notify-01) |
| `alloy.service` | `alloy` | tcp/127.0.0.1:12345 | 11 (voir écarts) |
| `wazuh-agent.service` | non suivi par systemd (voir note) | n/a | 11 (voir écarts) |
| `postfix.service` | `master` | tcp/127.0.0.1:25 (local) | les 11 LXC (pas les VM K3s) |
| `qemu-guest-agent.service` | `qemu-ga` | n/a | les 4 VM |
| `systemd-timesyncd.service` | `systemd-timesyn` (tronqué à 15 caractères) | n/a | les 4 VM |
| `systemd-networkd.service` | `systemd-network` | n/a | les LXC (état « disabled » mais en cours d'exécution) |

Autres unités vues, sans intérêt pour la supervision : terminaux (`console-getty`, `container-getty@1/2`, `getty@tty1`) et sessions utilisateur (`user@0`, `user@1000`, `user@1001`), ainsi que `systemd-udevd` sur les VM.

Note `wazuh-agent` : `systemd` ne suit pas de processus principal (MainPID à 0), donc le nom du processus est inconnu à ce stade. Il faudra relever les démons réels (annexe B) avant de créer un item `proc.num`.

## 3. Services applicatifs par machine

### Zabbix
| Machine | Unité | Processus | Ports |
|---|---|---|---|
| zabbix-bdd-01 | `postgresql@17-main.service` | `postgres` | 5432 (127.0.0.1, ::1 et 192.168.2.22) |
| zabbix-server-01 | `zabbix-server.service` | `zabbix_server` | 10051 (192.168.2.20) |
| zabbix-server-01 | `snmpd.service` | `snmpd` | udp/161 (local uniquement) |
| zabbix-front-01 | `nginx.service` | `nginx` | 80 et 8080 (toutes interfaces) |
| zabbix-front-01 | `php8.4-fpm.service` | `php-fpm8.4` | aucun port TCP (socket) |

### Journalisation et supervision
| Machine | Unité | Processus | Ports |
|---|---|---|---|
| loki-01, loki-02, loki-03 | `loki.service` | `loki` | 3100 (HTTPS depuis le 25/11, ADR-007) et 9096 (gRPC), toutes interfaces |
| grafana-01 | `grafana-server.service` | `grafana` | 3000 |
| notify-01 | `ntfy.service` | `ntfy` | 8080 et 8443 |

### Sécurité (SOC et secrets)
| Machine | Unité | Processus | Ports |
|---|---|---|---|
| wazuh-01 | `wazuh-manager.service` | non suivi (MainPID à 0) | non relevés |
| wazuh-01 | `wazuh-indexer.service` | `java` (nom générique) | 9200 et 9300 |
| wazuh-01 | `wazuh-dashboard.service` | `node` (nom générique) | 443 |
| wazuh-01 | `filebeat.service` | `filebeat` | aucun port en écoute |
| vault-01 | `docker.service` | `dockerd` | aucun port relevé |
| vault-01 | `containerd.service` | `containerd` | aucun port relevé |

### Nœuds K3s
| Machines | Unité | Processus | Ports |
|---|---|---|---|
| kube-worker-01, 02, 04 | `k3s-agent.service` | `k3s-agent` | 10250 (kubelet) et 32192 (toutes interfaces) ; 10248, 10249, 10256 et 6444 en local |
| kube-master-03 | `k3s.service` | `k3s-server` | 6443 (API), 10250 et 32192 (toutes interfaces) ; etcd 2379 et 2380 (192.168.0.30 et local) ; 2381, 2382, 6444, 10248, 10249, 10256 à 10259 en local |
| kube-master-03 | `keepalived.service` | `keepalived` | aucun (adresse virtuelle) |
| les 4 nœuds | `iscsid.service` | `iscsid` | aucun (prérequis habituel de Longhorn, ADR-004) |
| les 4 nœuds | `nfs-blkmap.service` | `blkmapd` | aucun |
| les 4 nœuds | `rpcbind.service` | `rpcbind` | tcp/udp 111 |

### lxc-ansible-01
Seulement le socle réduit : `alloy` (processus `alloy`), `postfix`, `ssh`, `wazuh-agent`. Les ports n'ont pas pu être relevés (colonne vide) : l'outil `ss` y est probablement absent.

## 4. Écarts et points d'attention

1. **lxc-ansible-01** n'a ni `zabbix-agent2` ni `fail2ban` : la machine n'est donc pas supervisée par Zabbix.
2. **loki-01, loki-03 et notify-01 n'ont pas d'agent Wazuh.** à relever
3. **notify-01 n'a pas non plus `fail2ban`**, alors que ntfy écoute sur 8080 et 8443 sur toutes les interfaces.
4. **Alloy est absent de loki-02, loki-03, grafana-01 et vault-01** (déjà listé dans les points ouverts d'ADR-006).
5. **vault-01** s'appelle `lxc-vault` côté système et est sur un autre réseau (10.4.111.123) : nom et adresse hors convention.
6. **Le port gRPC 9096 de Loki** écoute sur toutes les interfaces des trois instances (point ouvert d'ADR-007).
7. **Noms de processus génériques** (`java`, `node`, `master`, `login`, `agetty`, `systemd`) : un `proc.num[java]` compterait tous les processus Java de la machine. Ajouter un filtre par utilisateur ou par ligne de commande.
8. **Wazuh** : processus (agent, manager) et ports du manager à relever (annexe B).

## 5. Limites

- Seuls les services **en cours d'exécution** sont listés : un service installé mais arrêté ou en échec n'apparaît pas. Un contrôle des unités en échec (`systemctl --failed`) est à faire séparément.
- Les ports sont ceux du processus principal systemd ; les processus enfants ne sont pas pris en compte.
- Les rôles des machines sont déduits des noms et des services, pas d'un référentiel.

---

## Annexe A : reproduire le relevé

Depuis lxc-ansible-01, avec l'utilisateur `ansible` (pas root : c'est lui qui a les clés SSH et les hôtes connus). Le script est dans `/lantern/ansible/inventaire-services.sh` :

```bash
#!/bin/bash
# Inventaire des services systemd qui tournent : unité ; activé au boot ; processus principal ; ports en écoute
echo "### $(hostname)"
systemctl list-units --type=service --state=running --no-legend --plain | awk '{print $1}' | while read -r u; do
  en=$(systemctl is-enabled "$u" 2>/dev/null | head -1)
  pid=$(systemctl show -p MainPID --value "$u")
  comm=""; ports=""
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    comm=$(ps -o comm= -p "$pid" 2>/dev/null)
    ports=$(ss -H -tulnp 2>/dev/null | grep "pid=$pid," | awk '{a=$5; sub(/^(0\.0\.0\.0|\[::\]|\*)/,"*",a); print $1"/"a}' | sort -u | paste -sd, -)
  fi
  echo "$u;${en:-?};${comm:-?};${ports:--}"
done
```

```bash
cd /lantern/ansible
ansible 'all:!localhost' -i hosts.ini -b -m script -a "/lantern/ansible/inventaire-services.sh executable=/bin/bash" > /tmp/services-vms.txt
sudo bash /lantern/ansible/inventaire-services.sh >> /tmp/services-vms.txt   # la VM Ansible elle-même
```