# ADR-006 : Convention de labels Loki (env, service, pod/container)

## Statut
Acceptée — 24/11/2026 (appliquée sur les pods K3s et sur les LXC déjà enrôlés). Mise à jour le 25/11/2026 : les endpoints Loki sont en HTTPS (voir ADR-007).

## Contexte
Trois instances Loki reçoivent les logs de l'infra, et de nombreux dashboards Grafana existent déjà dessus. Les labels n'étaient pas homogènes d'une source à l'autre : pas de `env` ni de `service` sur les pods, labels posés à la main sur certains LXC (par exemple un label `service` sur notify-01).

| Instance | Hôte | IP:port | Contenu |
|---|---|---|---|
| loki-01 | lxc-loki-01 | 192.168.2.10:3100 | Journaux des LXC (zone LOGS) |
| loki-02 | lxc-loki-02 | 192.168.0.15:3100 | K3s : pods + nœuds |
| loki-03 | lxc-loki-03 | 192.168.3.13:3100 | SOC (Wazuh uniquement pour l'instant) |

Contraintes connues :
- Les dashboards existants ne doivent pas être cassés.
- Loki 3.x dérive automatiquement un label `service_name` du premier label trouvé parmi `service_name, service, app, application, app_name, name, app_kubernetes_io_name, container, container_name, component, workload, job`. Ajouter un label `service` change donc la valeur de `service_name` si on ne la fixe pas.
- Les pods K3s sont collectés par un DaemonSet Alloy (namespace `monitoring`, chart grafana/alloy 1.13.0, exécuté en UID 0 pour lire `/var/log/pods`), déployé par ArgoCD depuis `platform-gitops`.
- Les LXC et nœuds sont collectés par un Alloy installé sur l'hôte (utilisateur `alloy`, sans droit de lecture sur `/var/log/pods`), configuré par Ansible (`/lantern/ansible`).
- Aucun namespace de dev n'existe pour l'instant : tout est en `prod`.

## Décision
1. **Pods K3s (Loki-02)** : labels `job=kubernetes-pods`, `namespace`, `pod`, `container` (déjà présents) auxquels on ajoute :
   - `env` : `prod` par défaut, `dev` si le namespace est `dev` ou `*-dev` ;
   - `service` : label `app.kubernetes.io/name`, sinon label `app`, sinon nom du conteneur (la dernière règle qui correspond l'emporte) ;
   - `service_name` **fixé explicitement sur le nom du conteneur**, pour que la dérivation automatique de Loki ne change pas.
   Modification dans `observability/alloy/values.yaml` (repo `platform-gitops`, bloc `discovery.relabel "pod_logs"`), PR mergée (commit 164c5ce).
2. **LXC et hôtes (Loki-01, Loki-02 pour les nœuds, Loki-03)** : labels `host`, `env`, `zone` (et `role` si renseigné) en labels externes ; `job` (`systemd-journal`, `syslog` ou `auth`), `unit` et `level` sur les journaux. Déployés par le rôle Ansible `alloy_logging` (`playbooks/site-logging.yml`), avec la Loki de destination déterminée par le groupe d'inventaire.
3. **Pas de label `service` sur les LXC** : `unit` + `role` identifient le service. Le rôle contient une option `alloy_enriched_labels` (désactivée par défaut) qui ajouterait ces règles si le besoin apparaît.
4. **Les hôtes ne collectent jamais `/var/log/pods`** (`alloy_collect_pods: false`) : le DaemonSet s'en charge, sinon les logs seraient en double.
5. **Pas de label à valeurs non bornées** (IP, identifiant de requête, message de log) : cela fait exploser la cardinalité.
6. **Toute modification de labels passe par le code** : PR sur `platform-gitops` pour les pods, rôle Ansible pour les hôtes. Pas de configuration posée à la main (sauf exceptions listées en points ouverts).

## Alternatives envisagées
- **Ajouter `service` sans fixer `service_name`** : rejeté, la valeur de `service_name` aurait changé pour les logs existants et cassé les dashboards qui filtrent dessus.
- **Ajouter `service` sur les LXC** : rejeté, `unit` et `role` suffisent et un label de plus n'apporte rien à ce stade.
- **Collecter les pods depuis l'Alloy des nœuds** : rejeté, doublon avec le DaemonSet et droits de lecture insuffisants pour l'utilisateur `alloy`.

## Conséquences
- Les logs des pods peuvent être filtrés par `env`, `service`, `namespace`, `pod` et `container`. Les valeurs de `service_name` restent identiques à celles d'avant.
- Chaque changement de labels sur les pods demande une PR puis une **synchronisation manuelle** de l'application ArgoCD `alloy` (pas de sync automatique sur cette application).
- Un nouveau LXC s'enrôle en le déclarant dans `hosts.ini` : aucun fichier de configuration Alloy à écrire à la main. Depuis le passage en HTTPS, il faut d'abord installer la CA interne sur l'hôte (annexe A.1, étape 2).
- Les endpoints Loki sont en HTTPS (CA interne) depuis le 25/11/2026, voir ADR-007.
- Un pod Alloy du DaemonSet (`alloy-fb7vr`, kube-master-01) est en CrashLoopBackOff : les pods de ce nœud ne sont pas collectés tant qu'il n'est pas réparé.

## Points ouverts
- Réparer `alloy-fb7vr` (kube-master-01).
- Enrôler les machines restantes : grafana-01, loki-02, loki-03, kube-master-03 ; vault-01 après un test réseau vers un Loki. Vérifier au préalable si le dépôt apt.grafana.com existe déjà (sinon `alloy_manage_apt_repo=false`).
- kube-worker-04 : configuration manuelle (bloc pods et labels de journal enrichis) à aligner sur le rôle.
- Contrôle visuel des dashboards K3S dans Grafana.
- Sync automatique ArgoCD pour `alloy` : décision d'équipe (revue côté ops).
- Installer la CA interne via le rôle `alloy_logging` (voir ADR-007).

---

## Annexe A : procédures

### A.1 Enrôler ou réaligner un LXC / un hôte

1. Déclarer l'hôte dans `/lantern/ansible/hosts.ini`, dans le groupe de sa Loki de destination (`lxc_logs`, `k3s_nodes`, `wazuh`), avec les variables utiles : `alloy_role=…`, `alloy_install=true` si Alloy n'est pas installé, `alloy_manage_apt_repo=false` si le dépôt apt.grafana.com existe déjà.
2. Installer la CA interne sur l'hôte (le rôle ne le fait pas encore, voir ADR-007) :

```bash
cd /lantern/ansible
ansible <hote> -i hosts.ini -b -m copy -a "src=/lantern/tls/ca.crt dest=/usr/local/share/ca-certificates/lantern-logs-ca.crt owner=root group=root mode=0644"
ansible <hote> -i hosts.ini -b -m shell -a "update-ca-certificates | grep added"
```

3. Simuler puis appliquer, une machine à la fois :

```bash
ansible-playbook -i hosts.ini playbooks/site-logging.yml --limit <hote> --check --diff
ansible-playbook -i hosts.ini playbooks/site-logging.yml --limit <hote>
```

`--check` échoue à l'étape `getent` sur un hôte où Alloy n'est pas encore installé : dans ce cas, appliquer directement.

4. Vérifier côté Loki :

```bash
wget -qO- --ca-certificate=/lantern/tls/ca.crt "https://192.168.2.10:3100/loki/api/v1/label/host/values?since=1h"
```

### A.2 Modifier les labels des pods K3s

1. Modifier `observability/alloy/values.yaml` dans `platform-gitops` (bloc `discovery.relabel "pod_logs"`). Utiliser `regex = "(.+)"` pour qu'une règle n'écrase pas une valeur existante par du vide.
2. Ouvrir une PR (CODEOWNERS : équipe observabilité ; la CI « Validate GitOps » fait un `helm template`), puis merger.
3. Synchroniser l'application `alloy` dans ArgoCD.
4. Vérifier :

```bash
wget -qO- --ca-certificate=/lantern/tls/ca.crt "https://192.168.0.15:3100/loki/api/v1/label/env/values?since=1h"
wget -qO- --ca-certificate=/lantern/tls/ca.crt "https://192.168.0.15:3100/loki/api/v1/label/service/values?since=1h"
```
