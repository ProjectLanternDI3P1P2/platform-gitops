# MongoDB et RabbitMQ

| Service | Namespace | Adresse interne | Stockage |
| --- | --- | --- | --- |
| MongoDB 7.0, replica set `rs0` à un membre | `mongodb` | `mongodb.mongodb.svc.cluster.local:27017` | 10 Gi, `longhorn-stateful` |
| RabbitMQ 4.1 | `rabbitmq` | `rabbitmq.rabbitmq.svc.cluster.local:5672` (AMQP) | 5 Gi, `longhorn-stateful` |

Les deux applications Argo CD (`mongodb`, `rabbitmq`) sont générées par l'ApplicationSet
`lantern-apps` à partir de `apps/<nom>/overlays/k3s`.

## Choix

- **Replica set MongoDB.** Leaderboard écrit avec `w: majority` + journal et se connecte avec
  `replicaSet=rs0` (ADR-0037 de `leaderboard-backend`) : un replica set est obligatoire, même
  avec une seule instance. Le membre est déclaré sous le nom stable du pod
  (`mongodb-0.mongodb-headless.mongodb.svc.cluster.local`), résolu depuis tous les namespaces.
  Le changer après la mise en service demanderait un `rs.reconfig`.
- **Accès réseau.** MongoDB n'accepte que le namespace `leaderboard` (NetworkPolicy
  `mongodb-ingress`). RabbitMQ reste commun à tous les services : AMQP et métriques sont
  ouverts au cluster, l'API de management seulement au namespace `rabbitmq`.
- **Classe de stockage `longhorn-stateful`.** `longhorn-db` garde une seule copie parce que la
  redondance vient des 3 instances PostgreSQL. MongoDB et RabbitMQ n'ont qu'une instance :
  la redondance doit venir de Longhorn (3 copies). `Retain` protège contre une suppression
  accidentelle du PVC.
- **Comptes MongoDB.** `leaderboard` n'a que `find` et `insert` sur `progression_lake`
  (magasin en ajout seul). La collection `raw_events`, son validateur et ses index sont créés
  par le Job `mongodb-bootstrap`, qui reprend `RawEventCollectionInitializer` : l'image de
  Leaderboard ne l'exécute jamais (seuls les tests l'appellent). Une évolution du schéma
  côté `leaderboard-backend` doit être reportée dans `bootstrap-job.yaml`.
  `leaderboard-migrator` reste disponible pour les migrations futures.
- **Topologie RabbitMQ.** Les applications déclarent elles-mêmes leurs exchanges et leurs
  files. Le Job `rabbitmq-provisioning` ajoute seulement les liaisons
  `<service>.events → progression.events`, reprises de `RabbitMq:Subscriptions` dans
  `leaderboard-backend`. Chaque producteur ne peut écrire que dans son propre exchange ;
  seul `leaderboard` peut lire. `leaderboard` a aussi `write` sur `amq.default` : sa file
  `leaderboard.raw-events` rejette vers `leaderboard.raw-events.dead` par l'exchange par défaut,
  et RabbitMQ refuse sinon de la déclarer.
- **Futurs consommateurs.** La configuration de `player-backend` prévoit déjà une file
  (`player.events.v1`, abonnement à `dungeon.events`, rejet vers `lantern.dead-letter`), mais
  aucun code ne la consomme encore. Le jour où un producteur consomme, ajouter ses droits de
  lecture dans `provisioning-job.yaml`.

## Secrets (jamais dans Git)

Créés par `_scripts/bootstrap-data-services-secrets.ps1`, qui ne remplace jamais un Secret existant.

| Namespace | Secret | Clés |
| --- | --- | --- |
| `mongodb` | `mongodb-root` | `username`, `password` |
| `mongodb` | `mongodb-keyfile` | `keyfile` |
| `mongodb` | `mongodb-users` | `leaderboard`, `leaderboard-migrator` |
| `rabbitmq` | `rabbitmq-admin` | `username`, `password` |
| `rabbitmq` | `rabbitmq-users` | `leaderboard`, `player`, `dungeon`, `combat`, `rewards` |
| `leaderboard` | `leaderboard-mongodb` | `connection-string`, `migration-connection-string` |
| `leaderboard`, `player`, `dungeon`, `combat`, `rewards` | `rabbitmq-credentials` | `username`, `password` |

Changer un mot de passe applicatif : modifier la clé dans `mongodb-users` ou `rabbitmq-users`
**et** le Secret côté application, puis resynchroniser l'application : les Jobs PostSync
appliquent les nouveaux mots de passe. Les comptes `root` et `admin` ne sont créés qu'au
premier démarrage : les changer ensuite se fait à la main dans le serveur.

## Mise en service (ordre)

1. Appliquer une fois la classe de stockage :
   `kubectl apply -f platform/storage/longhorn-stateful.yaml`
2. Créer les Secrets :

   ```powershell
   powershell -File .\_scripts\bootstrap-data-services-secrets.ps1 -KubeConfig '<kubeconfig>'
   ```

   Fonctionne avec Windows PowerShell 5.1 (`powershell`) comme avec PowerShell 7 (`pwsh`).

3. Fusionner la pull request. La CI valide le rendu Kustomize. Ne pas inverser avec
   l'étape 2 : l'overlay de Leaderboard lit `leaderboard-mongodb` et `rabbitmq-credentials`,
   et son pod ne démarre plus si ces Secrets manquent.
4. `lantern-argocd-bootstrap` applique automatiquement le projet `lantern-apps` (nouvelles
   destinations) ; l'ApplicationSet crée ensuite les applications `mongodb` et `rabbitmq`.
5. Synchroniser à la main `cluster-foundation` pour poser les labels Pod Security sur les
   deux nouveaux namespaces (synchronisation manuelle par conception).
6. Vérifier que les Jobs `mongodb-bootstrap` et `rabbitmq-provisioning` sont `Complete`.

## Raccordement des producteurs

Préparé sur la branche `feat/rabbitmq-producers` (une PR séparée, car chaque overlay a son
CODEOWNER), avec `RabbitMq__Enabled` à `"false"` : l'équipe propriétaire n'a plus qu'à passer
la valeur à `"true"`.

```yaml
- name: RabbitMq__Enabled
  value: "false"
- name: RabbitMq__HostName
  value: rabbitmq.rabbitmq.svc.cluster.local
- name: RabbitMq__UserName
  valueFrom: { secretKeyRef: { name: rabbitmq-credentials, key: username } }
- name: RabbitMq__Password
  valueFrom: { secretKeyRef: { name: rabbitmq-credentials, key: password } }
```

`RabbitMq__ExchangeName` doit rester `<service>.events`, la valeur par défaut des dépôts.

## Validation

```bash
# Services et volumes
kubectl -n mongodb get pods,svc,pvc
kubectl -n rabbitmq get pods,svc,pvc
kubectl -n mongodb logs job/mongodb-bootstrap
kubectl -n rabbitmq logs job/rabbitmq-provisioning

# Replica set
kubectl -n mongodb exec mongodb-0 -- mongosh --quiet --eval 'rs.status().members[0].stateStr'
# attendu : PRIMARY

# Connexion de Leaderboard à MongoDB (compte applicatif, depuis le namespace leaderboard)
kubectl -n leaderboard run mongo-check --rm -it --restart=Never --image=mongo:7.0 \
  --overrides='{"spec":{"containers":[{"name":"mongo-check","image":"mongo:7.0","stdin":true,"tty":true,
  "command":["sh","-c","mongosh \"$URI\" --quiet --eval \"db.raw_events.find().limit(1).toArray()\""],
  "env":[{"name":"URI","valueFrom":{"secretKeyRef":{"name":"leaderboard-mongodb","key":"connection-string"}}}]}]}}'

# Publication puis consommation d'un message (API de management, compte admin)
kubectl -n rabbitmq port-forward svc/rabbitmq 15672:15672
#   publier sur combat.events avec la clé combat.combat-started.v1
#   -> le message doit apparaître dans la file leaderboard.raw-events, puis être consommé
#      par Leaderboard (compteur "Ready" à 0) et stocké dans progression_lake.raw_events.

# Persistance : redémarrer les pods puis refaire les vérifications ci-dessus
kubectl -n mongodb delete pod mongodb-0
kubectl -n rabbitmq delete pod rabbitmq-0
```
