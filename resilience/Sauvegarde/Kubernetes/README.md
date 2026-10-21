# Sauvegarde des manifests Kubernetes - Lantern

## Objectif

Conserver et versionner les manifests Kubernetes nécessaires au redéploiement des applications et des composants du cluster Lantern en cas d'incident.

## Infrastructure

Le cluster K3s comporte 3 masters et 4 workers.

Les applications sont principalement déployées avec Argo CD depuis le dépôt `platform-gitops`.

## Emplacement des manifests

Les configurations Kubernetes sont présentes dans plusieurs répertoires du dépôt :

- `apps/` : manifests des applications.
- `platform/` : composants de la plateforme.
- `clusters/` : configurations du cluster.
- `bootstrap/` : configuration d'initialisation.

Certaines applications utilisent la branche `main`, tandis que certains composants utilisent `refactor/unify-k3s-platform`.

## Méthode de sauvegarde

Les manifests sont conservés et versionnés dans GitHub. Les modifications sont suivies grâce à l'historique Git.

La restauration consiste à récupérer les versions appropriées des manifests et à les redéployer avec les outils adaptés, notamment Argo CD et Kustomize.

## Limites

Cette méthode ne sauvegarde pas les données persistantes, les bases de données, les Secrets Kubernetes ni l'état interne complet du cluster.

Une copie indépendante du dépôt Git reste recommandée pour assurer une véritable sauvegarde en cas de perte ou d'indisponibilité de GitHub.
