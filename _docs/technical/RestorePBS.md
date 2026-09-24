# Procédure : Restauration d'une VM depuis le stockage PBS

Ce document détaille la démarche pour restaurer une machine virtuelle ou un conteneur à partir de l'interface Proxmox VE liée au stockage PBS (`pbs-cluster`)[cite: 2].

---

### 1. Navigation vers l'espace de sauvegarde

1. Dans l'arborescence latérale gauche (**Server View** / Datacenter)[cite: 2] :
   - Dérouler le nœud hébergeant le stockage (ex : `pve-backup`)[cite: 2].
   - Cliquer sur le stockage **`pbs-cluster (pve-backup)`**[cite: 2].
2. Dans le menu horizontal supérieur, cliquer sur l'onglet **`Backups`** (situé entre *Summary* et *Permissions*)[cite: 2].

---

### 2. Identifier et sélectionner la sauvegarde

La liste affiche l'ensemble des snapshots disponibles sur le cluster[cite: 2]. Utiliser les colonnes pour repérer le bon point de restauration :
* **Name :** Format de l'archive (ex : `vm/105/2026-09-24T07:26:01Z`)[cite: 2].
* **Notes :** Nom d'affichage de la machine (ex : `kube-worker-03`, `pfsense`, `kube-master-01`)[cite: 2].
* **Date :** Horodatage de la réalisation du snapshot[cite: 2].
* **Size :** Taille logique du volume sauvegardé (ex : `20.00 GiB`)[cite: 2].
* **Verify State :** Contrôler la présence de la mention **`✔ OK`** (garantit l'intégrité des blocs dédupliqués)[cite: 2].

Sélectionner d'un clic la ligne du snapshot voulu[cite: 2].

---

### 3. Exécuter la restauration

1. Dans la barre d'outils au-dessus du tableau, cliquer sur le bouton **`Restore`**[cite: 2].
2. Configurer les options dans la fenêtre modale :
   * **Target node :** Sélectionner le nœud PVE de destination où démarrera l'instance (ex : `pve1`, `pve-diiage` ou `pve-backup`)[cite: 2].
   * **VM ID :** 
     * Conserver l'ID d'origine pour écraser et restaurer la machine existante.
     * Définir un nouvel ID libre pour déployer une copie conforme sans impacter la VM actuelle.
   * **Storage :** Sélectionner le stockage de disques cibles (ex : `local-lvm`).
   * **Start after restore :** À cocher si démarrage automatique souhaité à l'issue de l'opération.
3. Valider avec le bouton **Restore** et suivre la progression dans la fenêtre des logs de tâches.

---

### Options complémentaires de la barre d'actions

* **File Restore :** Permet d'explorer virtuellement les partitions du snapshot pour télécharger un fichier ou un dossier précis sans avoir à restaurer la VM complète[cite: 2].
* **Show Configuration :** Affiche la configuration matérielle (RAM, CPU, interfaces réseau SDN) enregistrée au moment du snapshot[cite: 2].
