# Remise en place du bootstrap Argo CD

Date : 2026-10-22

Les applications `mongodb` et `rabbitmq` ne se déployaient pas. La cause était l'absence
du bootstrap Argo CD dans le cluster. Ce document décrit le diagnostic, les actions menées
et leurs raisons.

## Symptômes

- `rabbitmq`, puis `mongodb` :
  `application destination server 'https://kubernetes.default.svc' and namespace '<ns>' do
  not match any of the allowed destinations in project 'lantern-apps'`.
- Après déblocage de la destination : `namespaces "mongodb" not found`.
- Avec l'option *AUTO-CREATE NAMESPACE* : `resource :Namespace is not permitted in project
  lantern-apps`.

## Diagnostic

Git était correct, mais le cluster ne l'appliquait pas.

- Dans Git, les destinations `database` et `mongodb` du projet `lantern-apps`
  ([project.yaml](../../bootstrap/argocd/k3s/project.yaml)) et le namespace
  ([platform/namespaces/mongodb.yaml](../../platform/namespaces/mongodb.yaml)) existaient.
- Dans le cluster, le projet `lantern-apps` n'avait que 7 destinations (player, dungeon,
  combat, rewards, leaderboard, frontend-game, frontend-public). Il datait d'avant l'ajout de
  PostgreSQL et de MongoDB.
- Les applications `lantern-argocd-bootstrap` et `cluster-foundation` n'existaient pas.
  L'étape 6 de [application-delivery.md](application-delivery.md) (installer une fois
  `bootstrap/argocd/k3s`) n'avait jamais été faite. L'ApplicationSet et l'application
  `platform` avaient été installées autrement.

Conséquences :

| Élément géré par le bootstrap | Effet de son absence |
| --- | --- |
| Projets `lantern-apps` et `lantern-platform-k3s` | Jamais mis à jour depuis Git : les nouveaux namespaces étaient refusés |
| `cluster-foundation` | Aucune création de namespace : `mongodb` et `rabbitmq` n'existaient pas |
| ApplicationSet | Version du cluster potentiellement différente de Git |

Le refus de l'option *AUTO-CREATE NAMESPACE* est voulu. Le projet `lantern-apps` n'autorise
aucune ressource de niveau cluster. Les namespaces sont créés uniquement par
`cluster-foundation`, du projet `lantern-platform-k3s`.

## Actions menées

1. **RabbitMQ déplacé dans la plateforme** (commit `dd389ff`). Il s'agit d'un broker partagé
   par cinq microservices, pas d'une application. Il est maintenant dans `platform/rabbitmq`,
   déclaré dans `platform/argocd/applications/rabbitmq.yaml` et rattaché au projet
   `lantern-platform-k3s`. Comme le reste de la plateforme, il se synchronise à la main.
   Ce changement ne corrigeait pas l'erreur à lui seul, car le projet du cluster n'était pas
   non plus à jour.
2. **Destinations ajoutées à la main dans le projet `lantern-apps`** (interface Argo CD), pour
   débloquer `mongodb`. Mesure provisoire, conforme à Git, remplacée par l'étape 3.
3. **Création de l'application `lantern-argocd-bootstrap` depuis l'interface Argo CD**
   (*NEW APP → EDIT AS YAML*), avec le contenu exact de
   [bootstrap.yaml](../../bootstrap/argocd/k3s/bootstrap.yaml). Elle remplace le
   `kubectl apply -k bootstrap/argocd/k3s` de la documentation, faute d'accès `kubectl`.
   Le résultat est identique : l'application se synchronise automatiquement, applique les deux
   projets, l'ApplicationSet et `cluster-foundation` depuis Git, puis se gère elle-même.
   Les ajouts manuels de l'étape 2 sont remplacés par la version de Git.
4. **Synchronisation manuelle de `cluster-foundation`**, après vérification du diff. Elle crée
   les namespaces `mongodb` et `rabbitmq` et pose les labels Pod Security.
5. **Synchronisation de `mongodb`, puis de `rabbitmq`.** Les ressources sont créées.

## État après intervention

- Les projets, l'ApplicationSet et `cluster-foundation` suivent maintenant `main`
  automatiquement.
- Un nouveau service n'a plus besoin de modification manuelle de projet. Il suffit de
  l'ajouter dans Git (namespace dans `platform/namespaces`, destination dans le projet), puis
  de synchroniser `cluster-foundation`, qui reste manuelle par conception.

## Points restant à suivre

- **Santé de MongoDB et RabbitMQ.** Vérifier que les pods démarrent et que les Jobs
  `mongodb-bootstrap` et `rabbitmq-provisioning` sont `Complete`. Ils dépendent de deux
  prérequis manuels :
  - les Secrets de [mongodb-rabbitmq.md](mongodb-rabbitmq.md) ;
  - la StorageClass `longhorn-stateful`. Elle manquait (`ProvisioningFailed`) et est
    désormais gérée par `cluster-foundation`.
- **Labels Pod Security.** `cluster-foundation` impose `baseline` sur les namespaces `argocd`,
  `keycloak` et `platform`. Un pod non conforme y serait refusé à son prochain redémarrage.
- **Applications en état Degraded.** `dungeon`, `player`, `frontend-game`, `leaderboard` et
  `rewards`. Problème distinct, non traité ici.
- **Prérequis encore hors GitOps.** StorageClass `longhorn-db`, opérateur CloudNativePG et
  Secrets.
  Pistes : les gérer comme applications de la plateforme, et Sealed Secrets ou External
  Secrets pour les Secrets.
