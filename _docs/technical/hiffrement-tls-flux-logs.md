# ADR-007 : Chiffrement TLS des flux de logs vers Loki

## Statut
Acceptée — 25/11/2026 (appliquée sur les 3 Loki et sur tous leurs clients connus)

## Contexte
Les trois Loki recevaient les logs en HTTP non chiffré sur le port 3100, à travers les réseaux internes (zones LOGS, K3s et SOC). Ces flux transportent des journaux système, dont `auth.log`, et les logs du SOC (Wazuh). Le README de `observability/alloy` indiquait explicitement que cette situation était une frontière de confiance réseau et non un chiffrement du transport.

| Instance | Hôte | IP:port | Clients (avant la bascule) |
|---|---|---|---|
| loki-01 | lxc-loki-01 | 192.168.2.10:3100 | Alloy de zabbix-bdd-01, zabbix-server-01, zabbix-front-01, notify-01, loki-01 et de la VM Ansible ; datasource Grafana |
| loki-02 | lxc-loki-02 | 192.168.0.15:3100 | Alloy de kube-worker-01, 02, 04 ; DaemonSet Alloy du cluster K3s ; datasource Grafana |
| loki-03 | lxc-loki-03 | 192.168.3.13:3100 | Alloy de wazuh-01 ; datasource Grafana |

Contraintes connues :
- Loki n'expose qu'**un seul listener HTTP** : on ne peut pas écouter en HTTP et en HTTPS en même temps. Chaque Loki bascule donc d'un coup, et tous ses clients doivent suivre.
- Alloy réessaie l'envoi pendant environ 8,5 minutes avec les paramètres par défaut (`max_backoff_retries` à 10, délai de 500 ms à 5 min). La coupure doit rester bien en dessous.
- Le dépôt `platform-gitops` est public et aucun mécanisme de secrets n'existe : aucun secret ne doit y figurer.
- L'application ArgoCD `alloy` n'a pas de sync automatique (voir ADR-006).
- pfSense ne contenait que des autorités ACME publiques, aucune autorité interne.

Autres flux examinés :
- **Syslog** : aucun récepteur sur 514 ou 6514 sur les machines de l'inventaire Ansible.
- **Agents Wazuh vers le manager** : chiffrement natif du protocole Wazuh, hors périmètre.

## Décision
1. **TLS natif de Loki** (`server.http_tls_config` avec `cert_file` et `key_file`) sur les trois instances. Le port 3100 n'écoute plus qu'en HTTPS.
2. **CA interne « Lantern Logs CA »**, créée dans pfSense (validité 10 ans). **Un certificat serveur par Loki** (validité 2 ans), avec comme SAN le nom DNS `lxc-loki-0X` et l'IP. Sur chaque Loki : `/etc/loki/tls/ca.crt` (0644), `/etc/loki/tls/loki.crt` (0644) et `/etc/loki/tls/loki.key` (root:root 0600). Le certificat public de la CA est conservé sur la VM Ansible dans `/lantern/tls/ca.crt`. Les clés privées de la VM Ansible sont supprimées une fois les certificats déployés.
3. **Clients Alloy installés sur les hôtes** : la CA est ajoutée au magasin de certificats du système (`/usr/local/share/ca-certificates/lantern-logs-ca.crt` puis `update-ca-certificates`). Alloy, écrit en Go, la prend en compte automatiquement : seule l'URL passe en `https://`.
4. **DaemonSet K3s** : la CA est fournie directement dans la configuration Alloy, par un bloc `tls_config { ca_pem = "…" }` dans `endpoint` de `loki.write` (`observability/alloy/values.yaml`, PR `feat/alloy-loki-tls`). C'est un certificat public, sans risque dans un dépôt public. Aucun ConfigMap supplémentaire.
5. **Grafana** : les trois datasources Loki passent en `https://<ip>:3100`, avec la CA collée dans « TLS Settings → Add self-signed certificate ».
6. **TLS côté serveur uniquement** (le client vérifie le serveur). Pas de mTLS dans cette itération.
7. **Bascule un Loki à la fois**, avec un canari d'abord (Loki-03, un seul client), puis Loki-01, puis Loki-02. Pour chaque Loki : préparer les clients (fichier modifié, Alloy non redémarré), redémarrer le Loki, puis redémarrer tous ses clients tout de suite après.
8. `loki_servers` dans `group_vars/all.yml` passe en `https://`.

## Alternatives envisagées
- **Reverse proxy TLS devant Loki (nginx, Traefik)** : un composant de plus par instance pour un résultat que le TLS natif de Loki fournit déjà.
- **mTLS dès maintenant** : demanderait de distribuer un certificat client à chaque émetteur, DaemonSet compris, donc de gérer des secrets alors que `platform-gitops` est public et qu'aucun mécanisme n'existe. Reporté.
- **Certificats publics (ACME)** : inadaptés à des hôtes joints par IP privée ou par nom interne. Une CA interne convient mieux.
- **Rester en HTTP sur réseau de confiance** : situation précédente, écartée.
- **Écoute HTTP et HTTPS en parallèle pour migrer progressivement** : impossible avec un seul listener, d'où la bascule instance par instance.

## Conséquences
- Les logs sont chiffrés en transit et le client vérifie l'identité du Loki.
- **Les certificats expirent** : certificats serveur en novembre 2028, CA en novembre 2036. Un certificat expiré coupe les envois de logs et fait tomber les datasources Grafana. Le renouvellement est manuel.
- **Tout nouvel hôte doit avoir la CA installée** avant le premier démarrage d'Alloy, sinon l'envoi échoue en `x509`. Tant que le rôle `alloy_logging` ne s'en charge pas, c'est une étape manuelle (annexe A.2).
- **Les clients ne sont pas authentifiés** : toute machine qui joint le port 3100 peut pousser des logs.
- Le port gRPC 9096 reste en clair et à l'écoute sur toutes les interfaces. Les clients ne l'utilisent pas.
- Tout ce qui appelle encore `http://…:3100` (vérifications Zabbix, scripts) échoue.
- Modifier la config Alloy du DaemonSet suit toujours le chemin PR puis sync ArgoCD manuelle (ADR-006).

## Points ouverts
- **Rôle `alloy_logging`** : installer la CA (copie du certificat, `update-ca-certificates`, redémarrage d'Alloy si la CA change). `group_vars/all.yml` est déjà en `https`.
- **Calendrier de renouvellement** : émettre de nouveaux certificats serveur avant novembre 2028.
- **mTLS ou authentification des clients** : nécessite une gestion de secrets.
- **gRPC 9096** : restreindre à 127.0.0.1 ou filtrer au pare-feu.
- **Outils qui appellent Loki en HTTP** : contrôler les vérifications Zabbix.
- **README `observability/alloy`** : le paragraphe « Security constraints » décrit encore l'endpoint en HTTP.
- **kube-worker-03** n'existe plus : le retirer de `hosts.ini` et vérifier qu'il ne reste pas dans K3s.
- **Machines non enrôlées** (voir ADR-006) : les enrôler directement en HTTPS.
- **Syslog** : pfSense et les hôtes hors inventaire n'ont pas été examinés.

---

## Annexe A : procédures

### A.1 Basculer un Loki en HTTPS
Prérequis : `/etc/loki/tls/{ca.crt,loki.crt,loki.key}` déployés sur le Loki, et les clients préparés (A.2, étapes 1 à 3). Sur le Loki, en root :

```bash
cp -a /etc/loki/config.yaml /etc/loki/config.yaml.bak-tls
sed -i '/^  grpc_listen_port: 9096$/a\  http_tls_config:\n    cert_file: /etc/loki/tls/loki.crt\n    key_file: /etc/loki/tls/loki.key' /etc/loki/config.yaml
diff /etc/loki/config.yaml.bak-tls /etc/loki/config.yaml     # 3 lignes ajoutées
/usr/local/bin/loki -config.file=/etc/loki/config.yaml -verify-config   # config is valid
systemctl restart loki; sleep 20
wget -qO- --ca-certificate=/etc/loki/tls/ca.crt https://<IP>:3100/ready   # ready
```

Redémarrer tout de suite les clients (A.2, étape 4).

### A.2 Basculer (ou enrôler) un client Alloy installé sur un hôte
Depuis la VM Ansible (`/lantern/ansible`), avec `H` la liste des hôtes séparés par des virgules :

```bash
# 1. CA dans le magasin système (sans impact)
ansible $H -i hosts.ini -b -m copy -a "src=/lantern/tls/ca.crt dest=/usr/local/share/ca-certificates/lantern-logs-ca.crt owner=root group=root mode=0644"
ansible $H -i hosts.ini -b -m shell -a "update-ca-certificates | grep added"

# 2-3. URL en https + validation (n'écrase pas Alloy en cours : pas de redémarrage)
ansible $H -i hosts.ini -b -m shell -a "cp -a /etc/alloy/config.alloy /etc/alloy/config.alloy.bak-tls && sed -i 's#http://<IP>:3100#https://<IP>:3100#' /etc/alloy/config.alloy && /usr/bin/alloy validate /etc/alloy/config.alloy && grep -n 'https' /etc/alloy/config.alloy"

# 4. Redémarrage, juste après le redémarrage du Loki
ansible $H -i hosts.ini -b -m shell -a "systemctl restart alloy; sleep 10; systemctl is-active alloy"
```

Ne pas rejouer l'étape 2-3 : elle écrase `config.alloy.bak-tls` par la version déjà en `https`.

### A.3 DaemonSet K3s
Générer le bloc `tls_config` depuis la VM Ansible :

```bash
awk 'BEGIN{printf "          tls_config {\n            ca_pem = \""} NF{printf "%s\\n",$0} END{printf "\"\n          }\n"}' /lantern/tls/ca.crt
```

Dans `observability/alloy/values.yaml`, passer l'URL en `https://192.168.0.15:3100/…` et coller le bloc dans `endpoint` de `loki.write`. PR sur `platform-gitops`, merge, puis dans ArgoCD : Refresh de l'application `alloy`, contrôle du diff (seul le ConfigMap change), Sync sans Prune. Le sidecar de rechargement du chart recharge la configuration sans redémarrer les pods. À faire juste après le redémarrage de Loki-02.

### A.4 Vérifier
Sur le Loki concerné, quelques minutes après la bascule :

```bash
wget -qO- --ca-certificate=/etc/loki/tls/ca.crt "https://<IP>:3100/loki/api/v1/label/host/values?since=5m"
wget -qO- --ca-certificate=/etc/loki/tls/ca.crt "https://<IP>:3100/loki/api/v1/label/namespace/values?since=5m"   # Loki-02 : les pods
```

Tous les hôtes clients doivent apparaître. Dans Grafana, « Save & test » sur la datasource.

### A.5 Retour arrière
- **Loki** : `cp -a /etc/loki/config.yaml.bak-tls /etc/loki/config.yaml && systemctl restart loki`.
- **Clients** : si `config.alloy.bak-tls` est intact, le restaurer. Sinon remettre l'URL en `http` avec `sed -i 's#https://<IP>:3100#http://<IP>:3100#' /etc/alloy/config.alloy` puis `systemctl restart alloy`.
- **DaemonSet** : revert de la PR sur `main`, puis nouveau Sync.
- **Datasources Grafana** : remettre l'URL en `http` et retirer la CA.
