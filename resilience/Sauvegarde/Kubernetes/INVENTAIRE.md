# Inventaire des sauvegardes Kubernetes — Lantern

## Objectif

Conserver les configurations Kubernetes versionnées dans GitOps afin de faciliter leur restauration en cas d'incident.

## Environnement

- Cluster K3s : 3 masters et 4 workers.
- Déploiements gérés principalement par Argo CD.
- Dépôt source : `ProjectLanternDI3PI2/platform-gitops`.

## Archives réalisées le 21 octobre 2026

| Archive | Référence Git | Vérification |
|---|---|---|
| `lantern-main.tar.gz` | `bceb8857ccaa6d7c8f14692a312baf4d5af282f6` | OK |
| `lantern-platform.tar.gz` | `60b11dd6a8953375b3f9ef3d7597c7c574728b24` | OK |
| `lantern-deployed.tar.gz` | `56cde75f` | OK |
| `lantern-database.tar.gz` | `ed70442d` | OK |

Les quatre archives ont été générées depuis Git, transférées sur un poste Windows et contrôlées après transfert.

Les empreintes SHA-256 sont conservées dans le fichier `SHA256SUMS.txt` avec les archives.

## Emplacement actuel

Les archives sont conservées temporairement sur le master Kubernetes et sur un poste de travail.

Un stockage indépendant, privé et sécurisé reste à mettre en place.

## Restauration

1. Récupérer l'archive correspondant à la version souhaitée.
2. Vérifier son empreinte SHA-256.
3. Extraire les fichiers de configuration.
4. Reconstituer les prérequis Kubernetes, Argo CD et les composants nécessaires.
5. Redéployer les manifests avec les outils adaptés.
6. Vérifier l'état des ressources et le fonctionnement des applications.

## Limites

Ces archives sont des instantanés du dépôt GitOps. Elles ne contiennent pas nécessairement tous les objets du cluster et ne remplacent pas les sauvegardes des Secrets, des données PostgreSQL, des volumes Longhorn ou d'etcd.

Les archives ne doivent pas être publiées dans un dépôt public sans audit de leur contenu.

## État

- [x] Identification des manifests et des branches Git.
- [x] Création des quatre archives.
- [x] Contrôle de lisibilité après transfert.
- [x] Calcul des empreintes SHA-256.
- [ ] Stockage sécurisé et indépendant.
- [ ] Vérification des ressources Kubernetes non présentes dans Git.
- [ ] Test de restauration.
