# Tableau des versions déployées

Le workflow **Sync deployment project** met à jour les lignes des sept dépôts applicatifs toutes les six heures. Il peut aussi être lancé manuellement. Il lit les releases GitHub et les overlays Kustomize de `main`, puis consulte Argo CD si l’accès est configuré.

## Configuration initiale

1. Créer un Project privé, en vue Table, dans l’organisation `ProjectLanternDI3P1P2`. Ajouter cinq champs de type **Text** avec ces noms exacts. Le workflow crée les lignes `combat-backend`, `dungeon-backend`, `player-backend`, `reward-backend`, `leaderboard-backend`, `frontend-game` et `frontend-public` au premier lancement.
   - Latest release
   - GitOps image
   - Confirmed image
   - Argo CD status
   - Last checked
2. Le workflow cible le Project nº 1 par défaut. Pour choisir un autre Project, définir la variable Actions `DEPLOYMENT_PROJECT_NUMBER`. Le workflow utilise le secret Actions `BOT_TOKEN` de `platform-gitops`. Vérifier que son compte peut modifier le Project et lire les releases des sept dépôts. Pour un PAT à granularité fine, les permissions sont **Organization Projects: Read and write** et **Repository Contents: Read-only** sur les sept dépôts.
3. Pour confirmer le déploiement, définir la variable `DEPLOYMENT_ARGOCD_URL` avec l’URL HTTPS de l’Argo CD de production et le secret `DEPLOYMENT_ARGOCD_TOKEN` avec un jeton de lecture limité aux applications concernées. Les overlays suivis sont `apps/<service>/overlays/k3s`. Vérifier qu’ils correspondent à l’environnement voulu avant de configurer l’URL. Si Argo CD est privé, définir `DEPLOYMENT_BOARD_RUNNER` avec le label d’un runner autorisé qui peut le joindre.
4. Une fois les fichiers fusionnés sur la branche par défaut, lancer **Actions → Sync deployment project → Run workflow** et vérifier les sept lignes. Le premier lancement crée le champ **Deployment health**. Pour afficher ce champ si nécessaire, passer par **View → Fields**, puis enregistrer la vue.

## Lecture du tableau

- **Latest release** affiche le tag de la dernière release applicative stable GitHub au format `vX.Y.Z`. Les packages de contrats ont leurs propres versions.
- **GitOps image** affiche la référence déclarée dans Kustomize.
- **Confirmed image** affiche l’image du Deployment dont le rollout est terminé. Elle peut être différente de l’image déclarée pendant une promotion ou après un échec de migration.
- **Argo CD status** indique la synchronisation et la santé de l’application. Sans accès à Argo CD ou pendant un rollout en cours, l’image reste indiquée comme **Non vérifiée**.

## Couleurs de Deployment health

| Couleur | Statut | Signification |
| --- | --- | --- |
| Vert | Up to date | La dernière release correspond à GitOps et Argo CD confirme la même image, synchronisée et saine. |
| Jaune | Release pending | Le tag applicatif de GitOps est antérieur à la dernière release stable. |
| Bleu | Deployment pending | Un déploiement est en cours, Argo CD signale un écart de synchronisation ou la version en service diffère de GitOps. |
| Rouge | Degraded | Argo CD signale une application dégradée ou manquante. |
| Gris | Unverified | La version reste à confirmer, par exemple si Argo CD est inaccessible ou si le tag GitOps ne permet pas de comparer les versions. |


Depuis la racine du dépôt, `node .github/scripts/sync-deployment-project.mjs --check-manifests` vérifie la lecture des overlays sans contacter les API.
