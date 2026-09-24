# Procedure: Restoring a VM from PBS Storage

This document outlines the steps to restore a virtual machine or container using the Proxmox VE web interface connected to the PBS storage (`pbs-cluster`)[cite: 2].

---

### 1. Navigate to the Backup Storage

1. In the left sidebar (**Server View** / Datacenter)[cite: 2]:
   - Expand the node hosting the storage (e.g., `pve-backup`)[cite: 2].
   - Click on the storage entry **`pbs-cluster (pve-backup)`**[cite: 2].
2. In the top navigation bar, select the **`Backups`** tab (located between *Summary* and *Permissions*)[cite: 2].

---

### 2. Locate and Select the Backup Snapshot

The main table lists all snapshots available across the cluster[cite: 2]. Use the table columns to identify the desired restore point:
* **Name:** Snapshot path identifier (e.g., `vm/105/2026-09-24T07:26:01Z`)[cite: 2].
* **Notes:** Guest hostname / display name (e.g., `kube-worker-03`, `pfsense`, `kube-master-01`)[cite: 2].
* **Date:** Timestamp of snapshot creation[cite: 2].
* **Size:** Logical volume size (e.g., `20.00 GiB`)[cite: 2].
* **Verify State:** Verify that the status shows **`✔ OK`** (confirms chunk integrity and deduplication health)[cite: 2].

Click on the row corresponding to the snapshot you want to restore[cite: 2].

---

### 3. Run the Restore Process

1. In the action toolbar above the table, click the **`Restore`** button[cite: 2].
2. Configure the settings in the modal dialog:
   * **Target node:** Select the destination PVE node where the VM will run (e.g., `pve1`, `pve-diiage`, or `pve-backup`)[cite: 2].
   * **VM ID:** 
     * Keep the original ID to overwrite and replace the existing VM.
     * Set a new, unused ID to deploy an exact clone without affecting the current VM.
   * **Storage:** Select the target storage pool for the virtual disk (e.g., `local-lvm`).
   * **Start after restore:** Check this box if you want the instance to boot automatically once restoration completes.
3. Click **Restore** and monitor the task execution logs in the popup window.

---

### Additional Toolbar Actions

* **File Restore:** Allows browsing the snapshot's partitions directly in the browser to download individual files or folders without restoring the full disk[cite: 2].
* **Show Configuration:** Displays the hardware and network configuration recorded at the time of the snapshot[cite: 2].
