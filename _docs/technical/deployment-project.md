# Tableau des versions déployées

Le tableau est rempli par deux sources, **sans aucun accès entrant à Argo CD** :

- **Argo CD lui-même** (notifications, `platform/argocd/values.yaml`) écrit après chaque synchronisation ce qui tourne vraiment : **Confirmed image** (images rapportées par Argo CD) et **Argo CD status** (synchronisation / santé · heure). Il appelle l’API GitHub en sortie, rien n’entre dans le cluster.
- Le workflow **Sync deployment project** écrit **Latest release**, **GitOps image**, **Last checked**, puis calcule **Deployment health** et **Status** à partir de ce qu’Argo CD a écrit. Il tourne juste après chaque promotion (fusion d’un `deploy(<app>): vX.Y.Z` sur `main`, puis relecture toutes les deux minutes, dix au plus, jusqu’à ce qu’Argo CD ait déployé), toutes les heures, et à la demande.

## Jeton d’Argo CD (une fois, hors Git)

Créer un jeton à droits limités du compte `Diiage-Service-Account` : propriétaire **ProjectLanternDI3P1P2**, *Organization permissions › Projects : Read and write*, rien d’autre. Puis l’ajouter au Secret des notifications (le chart le crée vide ; Argo CD ignore les différences de données des Secret, la clé est donc conservée) :

```bash
kubectl -n argocd patch secret argocd-notifications-secret --type merge \
  -p '{"stringData":{"github-project-token":"<jeton>"}}'
```

Le même jeton peut remplacer `DEPLOYMENT_PROJECT_TOKEN` (actuellement un jeton personnel).

Les identifiants du Project, des lignes et des champs sont écrits dans le modèle `template.board-live-state`. Si une ligne est recréée, mettre à jour son identifiant dans ce modèle.

## Configuration initiale

1. Créer un Project privé, en vue Table, dans l’organisation `ProjectLanternDI3P1P2`. Ajouter cinq champs de type **Text** avec ces noms exacts. Le workflow crée les lignes `combat-backend`, `dungeon-backend`, `player-backend`, `reward-backend`, `leaderboard-backend`, `frontend-game` et `frontend-public` au premier lancement.
   - Latest release
   - GitOps image
   - Confirmed image
   - Argo CD status
   - Last checked
2. Le workflow cible le Project nº 1 par défaut. Pour choisir un autre Project, définir la variable Actions `DEPLOYMENT_PROJECT_NUMBER`. Dans **Settings → Secrets and variables → Actions**, ajouter le secret **`DEPLOYMENT_PROJECT_TOKEN`**. Utiliser un PAT classique avec le scope **`project`** (lecture et écriture) et un compte qui peut modifier le Project. Le workflow utilise séparément **`BOT_TOKEN`** pour lire les releases des sept dépôts. Le PAT du Project peut se limiter au scope `project`.
3. (Facultatif, remplacé par les notifications d’Argo CD) Pour interroger Argo CD depuis le workflow, définir la variable `DEPLOYMENT_ARGOCD_URL` avec l’URL HTTPS de l’Argo CD de production et le secret `DEPLOYMENT_ARGOCD_TOKEN` avec un jeton de lecture limité aux applications concernées. Les overlays suivis sont `apps/<service>/overlays/k3s`. Vérifier qu’ils correspondent à l’environnement voulu avant de configurer l’URL. Si Argo CD est privé, définir `DEPLOYMENT_BOARD_RUNNER` avec le label d’un runner autorisé qui peut le joindre.
4. Une fois les fichiers fusionnés sur la branche par défaut, lancer **Actions → Sync deployment project → Run workflow** et vérifier les sept lignes. Le premier lancement crée le champ **Deployment health**. Pour afficher ce champ si nécessaire, passer par **View → Fields**, puis enregistrer la vue.

## Lecture du tableau

- **Latest release** affiche le tag de la dernière release applicative stable GitHub au format `vX.Y.Z`. Les packages de contrats ont leurs propres versions.
- **GitOps image** affiche la référence déclarée dans Kustomize.
- **Confirmed image** affiche l’image du Deployment dont le rollout est terminé. Elle peut être différente de l’image déclarée pendant une promotion ou après un échec de migration.
- **Argo CD status** indique la synchronisation et la santé de l’application. Sans accès à Argo CD ou pendant un rollout en cours, l’image reste indiquée comme **Non vérifiée**.

## Colonne Status (vue Board)

| Deployment health | Status |
| --- | --- |
| Up to date | Done |
| Release pending, Deployment pending | In Progress |
| Degraded, Unverified | Todo |

Pour une vue en colonnes : *New view › Board*, groupée par **Status**.

## Couleurs de Deployment health

| Couleur | Statut | Signification |
| --- | --- | --- |
| Vert | Up to date | La dernière release correspond à GitOps et Argo CD a confirmé que cette image tourne, synchronisée et saine. |
| Jaune | Release pending | Le tag applicatif de GitOps est antérieur à la dernière release stable, ou GitOps pointe encore une image hors release (`dev-…`, `git-…`, `main-latest`) alors qu’une release existe. |
| Bleu | Deployment pending | Un déploiement est en cours, Argo CD signale un écart de synchronisation ou la version en service diffère de GitOps. |
| Rouge | Degraded | Argo CD signale une application dégradée ou manquante. |
| Gris | Unverified | La version reste à confirmer, par exemple si Argo CD est inaccessible ou si le tag GitOps ne permet pas de comparer les versions. |


Depuis la racine du dépôt, `node .github/scripts/sync-deployment-project.mjs --check-manifests` vérifie la lecture des overlays sans contacter les API.
